from __future__ import annotations

import os
import pathlib
import sys
import time
from typing import Any, AsyncIterable, Awaitable, Callable, Dict, Iterator

import pytest

# https://github.com/pytest-dev/pytest/issues/7469
from _pytest.fixtures import SubRequest

from hddcoin.data_layer.data_layer_util import NodeType, Status
from hddcoin.data_layer.data_store import DataStore
from hddcoin.types.blockchain_format.sized_bytes import bytes32
from tests.core.data_layer.util import (
    ChiaRoot,
    Example,
    add_0123_example,
    add_01234567_example,
    create_valid_node_values,
)
from tests.util.misc import closing_hddcoin_root_popen

# TODO: These are more general than the data layer and should either move elsewhere or
#       be replaced with an existing common approach.  For now they can at least be
#       shared among the data layer test files.


@pytest.fixture(name="hddcoin_daemon", scope="function")
def hddcoin_daemon_fixture(hddcoin_root: ChiaRoot) -> Iterator[None]:
    with closing_hddcoin_root_popen(hddcoin_root=hddcoin_root, args=[sys.executable, "-m", "hddcoin.daemon.server"]):
        # TODO: this is not pretty as a hard coded time
        # let it settle
        time.sleep(5)
        yield


@pytest.fixture(name="hddcoin_data", scope="function")
def hddcoin_data_fixture(hddcoin_root: ChiaRoot, hddcoin_daemon: None, scripts_path: pathlib.Path) -> Iterator[None]:
    with closing_hddcoin_root_popen(hddcoin_root=hddcoin_root, args=[os.fspath(scripts_path.joinpath("hddcoin_data_layer"))]):
        # TODO: this is not pretty as a hard coded time
        # let it settle
        time.sleep(5)
        yield


@pytest.fixture(name="create_example", params=[add_0123_example, add_01234567_example])
def create_example_fixture(request: SubRequest) -> Callable[[DataStore, bytes32], Awaitable[Example]]:
    # https://github.com/pytest-dev/pytest/issues/8763
    return request.param  # type: ignore[no-any-return]


@pytest.fixture(name="tree_id", scope="function")
def tree_id_fixture() -> bytes32:
    base = b"a tree id"
    pad = b"." * (32 - len(base))
    return bytes32(pad + base)


@pytest.fixture(name="raw_data_store", scope="function")
async def raw_data_store_fixture(database_uri: str) -> AsyncIterable[DataStore]:
    async with DataStore.managed(database=database_uri, uri=True) as store:
        yield store


@pytest.fixture(name="data_store", scope="function")
async def data_store_fixture(raw_data_store: DataStore, tree_id: bytes32) -> AsyncIterable[DataStore]:
    await raw_data_store.create_tree(tree_id=tree_id, status=Status.COMMITTED)

    await raw_data_store.check()
    yield raw_data_store
    await raw_data_store.check()


@pytest.fixture(name="node_type", params=NodeType)
def node_type_fixture(request: SubRequest) -> NodeType:
    return request.param  # type: ignore[no-any-return]


@pytest.fixture(name="valid_node_values")
async def valid_node_values_fixture(
    data_store: DataStore,
    tree_id: bytes32,
    node_type: NodeType,
) -> Dict[str, Any]:
    await add_01234567_example(data_store=data_store, tree_id=tree_id)

    if node_type == NodeType.INTERNAL:
        node_a = await data_store.get_node_by_key(key=b"\x02", tree_id=tree_id)
        node_b = await data_store.get_node_by_key(key=b"\x04", tree_id=tree_id)
        return create_valid_node_values(node_type=node_type, left_hash=node_a.hash, right_hash=node_b.hash)
    elif node_type == NodeType.TERMINAL:
        return create_valid_node_values(node_type=node_type)
    else:
        raise Exception(f"invalid node type: {node_type!r}")


@pytest.fixture(name="bad_node_type", params=range(2 * len(NodeType)))
def bad_node_type_fixture(request: SubRequest, valid_node_values: Dict[str, Any]) -> int:
    if request.param == valid_node_values["node_type"]:
        pytest.skip("Actually, this is a valid node type")

    return request.param  # type: ignore[no-any-return]
