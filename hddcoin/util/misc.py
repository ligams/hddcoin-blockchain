from __future__ import annotations

import asyncio
import contextlib
import dataclasses
import functools
import signal
import sys
from dataclasses import dataclass
from pathlib import Path
from types import FrameType
from typing import (
    Any,
    AsyncContextManager,
    AsyncIterator,
    Collection,
    ContextManager,
    Dict,
    Generic,
    Iterator,
    List,
    Optional,
    Sequence,
    TypeVar,
    Union,
    final,
)

from typing_extensions import Protocol

from hddcoin.util.errors import InvalidPathError
from hddcoin.util.ints import uint16, uint32, uint64
from hddcoin.util.streamable import Streamable, recurse_jsonify, streamable

T = TypeVar("T")


@streamable
@dataclasses.dataclass(frozen=True)
class VersionedBlob(Streamable):
    version: uint16
    blob: bytes


def format_bytes(bytes: int) -> str:
    if not isinstance(bytes, int) or bytes < 0:
        return "Invalid"

    LABELS = ("MiB", "GiB", "TiB", "PiB", "EiB", "ZiB", "YiB")
    BASE = 1024
    value = bytes / BASE
    for label in LABELS:
        value /= BASE
        if value < BASE:
            return f"{value:.3f} {label}"

    return f"{value:.3f} {LABELS[-1]}"


def format_minutes(minutes: int) -> str:
    if not isinstance(minutes, int):
        return "Invalid"

    if minutes == 0:
        return "Now"

    hour_minutes = 60
    day_minutes = 24 * hour_minutes
    week_minutes = 7 * day_minutes
    months_minutes = 43800
    year_minutes = 12 * months_minutes

    years = int(minutes / year_minutes)
    months = int(minutes / months_minutes)
    weeks = int(minutes / week_minutes)
    days = int(minutes / day_minutes)
    hours = int(minutes / hour_minutes)

    def format_unit_string(str_unit: str, count: int) -> str:
        return f"{count} {str_unit}{('s' if count > 1 else '')}"

    def format_unit(unit: str, count: int, unit_minutes: int, next_unit: str, next_unit_minutes: int) -> str:
        formatted = format_unit_string(unit, count)
        minutes_left = minutes % unit_minutes
        if minutes_left >= next_unit_minutes:
            formatted += " and " + format_unit_string(next_unit, int(minutes_left / next_unit_minutes))
        return formatted

    if years > 0:
        return format_unit("year", years, year_minutes, "month", months_minutes)
    if months > 0:
        return format_unit("month", months, months_minutes, "week", week_minutes)
    if weeks > 0:
        return format_unit("week", weeks, week_minutes, "day", day_minutes)
    if days > 0:
        return format_unit("day", days, day_minutes, "hour", hour_minutes)
    if hours > 0:
        return format_unit("hour", hours, hour_minutes, "minute", 1)
    if minutes > 0:
        return format_unit_string("minute", minutes)

    return "Unknown"


def prompt_yes_no(prompt: str) -> bool:
    while True:
        response = str(input(prompt + " (y/n): ")).lower().strip()
        ch = response[:1]
        if ch == "y":
            return True
        elif ch == "n":
            return False


def get_list_or_len(list_in: Sequence[object], length: bool) -> Union[int, Sequence[object]]:
    return len(list_in) if length else list_in


def dataclass_to_json_dict(instance: Any) -> Dict[str, Any]:
    ret: Dict[str, Any] = recurse_jsonify(instance)
    return ret


def validate_directory_writable(path: Path) -> None:
    write_test_path = path / ".write_test"
    try:
        with write_test_path.open("w"):
            pass
        write_test_path.unlink()
    except FileNotFoundError:
        raise InvalidPathError(path, "Directory doesn't exist")
    except OSError:
        raise InvalidPathError(path, "Directory not writable")


if sys.platform == "win32" or sys.platform == "cygwin":
    termination_signals = [signal.SIGBREAK, signal.SIGINT, signal.SIGTERM]
    sendable_termination_signals = [signal.SIGTERM]
else:
    termination_signals = [signal.SIGINT, signal.SIGTERM]
    sendable_termination_signals = termination_signals


@streamable
@dataclasses.dataclass(frozen=True)
class UInt32Range(Streamable):
    start: uint32 = uint32(0)
    stop: uint32 = uint32.MAXIMUM


@streamable
@dataclasses.dataclass(frozen=True)
class UInt64Range(Streamable):
    start: uint64 = uint64(0)
    stop: uint64 = uint64.MAXIMUM


@dataclass(frozen=True)
class Batch(Generic[T]):
    remaining: int
    entries: List[T]


def to_batches(to_split: Collection[T], batch_size: int) -> Iterator[Batch[T]]:
    if batch_size <= 0:
        raise ValueError("to_batches: batch_size must be greater than 0.")
    total_size = len(to_split)
    if total_size == 0:
        return iter(())

    if isinstance(to_split, list):
        for batch_start in range(0, total_size, batch_size):
            batch_end = min(batch_start + batch_size, total_size)
            yield Batch(total_size - batch_end, to_split[batch_start:batch_end])
    elif isinstance(to_split, set):
        processed = 0
        entries = []
        for entry in to_split:
            entries.append(entry)
            if len(entries) >= batch_size:
                processed += len(entries)
                yield Batch(total_size - processed, entries)
                entries = []
        if len(entries) > 0:
            processed += len(entries)
            yield Batch(total_size - processed, entries)
    else:
        raise ValueError(f"to_batches: Unsupported type {type(to_split)}")


class Handler(Protocol):
    def __call__(
        self,
        signal_: signal.Signals,
        stack_frame: Optional[FrameType],
        loop: asyncio.AbstractEventLoop,
    ) -> None:
        ...


class AsyncHandler(Protocol):
    async def __call__(
        self,
        signal_: signal.Signals,
        stack_frame: Optional[FrameType],
        loop: asyncio.AbstractEventLoop,
    ) -> None:
        ...


@final
@dataclasses.dataclass
class SignalHandlers:
    tasks: List[asyncio.Task[None]] = dataclasses.field(default_factory=list)

    @classmethod
    @contextlib.asynccontextmanager
    async def manage(cls) -> AsyncIterator[SignalHandlers]:
        self = cls()
        try:
            yield self
        finally:
            # TODO: log errors?
            # TODO: return to previous signal handlers?
            await asyncio.gather(*self.tasks)

    def remove_done_handlers(self) -> None:
        self.tasks = [task for task in self.tasks if not task.done()]

    def loop_safe_sync_signal_handler_for_async(
        self,
        signal_: signal.Signals,
        stack_frame: Optional[FrameType],
        loop: asyncio.AbstractEventLoop,
        handler: AsyncHandler,
    ) -> None:
        self.remove_done_handlers()

        task = asyncio.create_task(
            handler(signal_=signal_, stack_frame=stack_frame, loop=loop),
        )
        self.tasks.append(task)

    def threadsafe_sync_signal_handler_for_async(
        self,
        signal_: signal.Signals,
        stack_frame: Optional[FrameType],
        loop: asyncio.AbstractEventLoop,
        handler: AsyncHandler,
    ) -> None:
        loop.call_soon_threadsafe(
            functools.partial(
                self.loop_safe_sync_signal_handler_for_async,
                signal_=signal_,
                stack_frame=stack_frame,
                loop=loop,
                handler=handler,
            ),
        )

    def setup_sync_signal_handler(self, handler: Handler) -> None:
        loop = asyncio.get_event_loop()

        if sys.platform == "win32" or sys.platform == "cygwin":
            for signal_ in [signal.SIGBREAK, signal.SIGINT, signal.SIGTERM]:
                signal.signal(signal_, functools.partial(handler, loop=loop))
        else:
            for signal_ in [signal.SIGINT, signal.SIGTERM]:
                loop.add_signal_handler(
                    signal_,
                    functools.partial(handler, signal_=signal_, stack_frame=None, loop=loop),
                )

    def setup_async_signal_handler(self, handler: AsyncHandler) -> None:
        # https://docs.python.org/3/library/asyncio-eventloop.html#asyncio.loop.add_signal_handler
        # > a callback registered with this function is allowed to interact with the event
        # > loop
        #
        # This is a bit vague so let's just use a thread safe call for Windows
        # compatibility.

        self.setup_sync_signal_handler(
            handler=functools.partial(self.threadsafe_sync_signal_handler_for_async, handler=handler)
        )


@dataclass
class SplitManager(Generic[T]):
    # NOTE: only for transitional testing use, please avoid usage
    manager: ContextManager[object]
    object: T
    _entered: bool = False
    _exited: bool = False

    def enter(self) -> None:
        messages: List[str] = []
        if self._entered:
            messages.append("already entered")
        if self._exited:
            messages.append("already exited")
        if len(messages) > 0:
            raise Exception(", ".join(messages))

        self._entered = True
        self.manager.__enter__()

    def exit(self, if_needed: bool = False) -> None:
        if if_needed and (not self._entered or self._exited):
            return

        messages: List[str] = []
        if not self._entered:
            messages.append("not yet entered")
        if self._exited:
            messages.append("already exited")
        if len(messages) > 0:
            raise Exception(", ".join(messages))

        self._exited = True
        self.manager.__exit__(None, None, None)


@dataclass
class SplitAsyncManager(Generic[T]):
    # NOTE: only for transitional testing use, please avoid usage
    manager: AsyncContextManager[object]
    object: T
    _entered: bool = False
    _exited: bool = False

    async def enter(self) -> None:
        messages: List[str] = []
        if self._entered:
            messages.append("already entered")
        if self._exited:
            messages.append("already exited")
        if len(messages) > 0:
            raise Exception(", ".join(messages))

        self._entered = True
        await self.manager.__aenter__()

    async def exit(self, if_needed: bool = False) -> None:
        if if_needed and (not self._entered or self._exited):
            return

        messages: List[str] = []
        if not self._entered:
            messages.append("not yet entered")
        if self._exited:
            messages.append("already exited")
        if len(messages) > 0:
            raise Exception(", ".join(messages))

        self._exited = True
        await self.manager.__aexit__(None, None, None)


@contextlib.contextmanager
def split_manager(manager: ContextManager[object], object: T) -> Iterator[SplitManager[T]]:
    # NOTE: only for transitional testing use, please avoid usage
    split = SplitManager(manager=manager, object=object)
    try:
        yield split
    finally:
        split.exit(if_needed=True)


@contextlib.asynccontextmanager
async def split_async_manager(manager: AsyncContextManager[object], object: T) -> AsyncIterator[SplitAsyncManager[T]]:
    # NOTE: only for transitional testing use, please avoid usage
    split = SplitAsyncManager(manager=manager, object=object)
    try:
        yield split
    finally:
        await split.exit(if_needed=True)
