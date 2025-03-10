from __future__ import annotations

import logging
import time
from typing import Optional

from hddcoin.protocols import timelord_protocol
from hddcoin.rpc.rpc_server import StateChangedProtocol
from hddcoin.timelord.iters_from_block import iters_from_block
from hddcoin.timelord.timelord import Timelord
from hddcoin.timelord.types import Chain, IterationType
from hddcoin.util.api_decorators import api_request
from hddcoin.util.ints import uint64

log = logging.getLogger(__name__)


class TimelordAPI:
    log: logging.Logger
    timelord: Timelord

    def __init__(self, timelord) -> None:
        self.log = logging.getLogger(__name__)
        self.timelord = timelord

    def ready(self) -> bool:
        return True

    def _set_state_changed_callback(self, callback: StateChangedProtocol) -> None:
        self.timelord.state_changed_callback = callback

    @api_request()
    async def new_peak_timelord(self, new_peak: timelord_protocol.NewPeakTimelord) -> None:
        if self.timelord.last_state is None:
            return None
        async with self.timelord.lock:
            if self.timelord.bluebox_mode:
                return None
            self.timelord.max_allowed_inactivity_time = 60

            # if there is a heavier unfinished block from a diff chain, skip
            for unf_block in self.timelord.unfinished_blocks:
                if unf_block.reward_chain_block.total_iters > new_peak.reward_chain_block.total_iters:
                    found = False
                    for rc, total_iters in new_peak.previous_reward_challenges:
                        if rc == unf_block.rc_prev:
                            found = True
                            break

                    if not found:
                        log.info("there is a heavier unfinished block that does not belong to this chain- skip peak")
                        return None

            if new_peak.reward_chain_block.weight > self.timelord.last_state.get_weight():
                log.info("Not skipping peak, don't have. Maybe we are not the fastest timelord")
                log.info(
                    f"New peak: height: {new_peak.reward_chain_block.height} weight: "
                    f"{new_peak.reward_chain_block.weight} "
                )
                self.timelord.new_peak = new_peak
                self.timelord.state_changed("new_peak", {"height": new_peak.reward_chain_block.height})
            elif (
                self.timelord.last_state.peak is not None
                and self.timelord.last_state.peak.reward_chain_block == new_peak.reward_chain_block
            ):
                log.info("Skipping peak, already have.")
                self.timelord.state_changed("skipping_peak", {"height": new_peak.reward_chain_block.height})
            else:
                log.warning("block that we don't have, changing to it.")
                self.timelord.new_peak = new_peak
                self.timelord.state_changed("new_peak", {"height": new_peak.reward_chain_block.height})

    @api_request()
    async def new_unfinished_block_timelord(self, new_unfinished_block: timelord_protocol.NewUnfinishedBlockTimelord):
        if self.timelord.last_state is None:
            return None
        async with self.timelord.lock:
            if self.timelord.bluebox_mode:
                return None
            try:
                sp_iters, ip_iters = iters_from_block(
                    self.timelord.constants,
                    new_unfinished_block.reward_chain_block,
                    self.timelord.last_state.get_sub_slot_iters(),
                    self.timelord.last_state.get_difficulty(),
                    self.timelord.get_height(),
                )
            except Exception:
                return None
            last_ip_iters = self.timelord.last_state.get_last_ip()
            if sp_iters > ip_iters:
                self.timelord.overflow_blocks.append(new_unfinished_block)
                log.debug(f"Overflow unfinished block, total {self.timelord.total_unfinished}")
            elif ip_iters > last_ip_iters:
                new_block_iters: Optional[uint64] = self.timelord._can_infuse_unfinished_block(new_unfinished_block)
                if new_block_iters:
                    self.timelord.unfinished_blocks.append(new_unfinished_block)
                    for chain in [Chain.REWARD_CHAIN, Chain.CHALLENGE_CHAIN]:
                        self.timelord.iters_to_submit[chain].append(new_block_iters)
                    if self.timelord.last_state.get_deficit() < self.timelord.constants.MIN_BLOCKS_PER_CHALLENGE_BLOCK:
                        self.timelord.iters_to_submit[Chain.INFUSED_CHALLENGE_CHAIN].append(new_block_iters)
                    self.timelord.iteration_to_proof_type[new_block_iters] = IterationType.INFUSION_POINT
                    self.timelord.total_unfinished += 1
                    log.debug(f"Non-overflow unfinished block, total {self.timelord.total_unfinished}")

    @api_request()
    async def request_compact_proof_of_time(self, vdf_info: timelord_protocol.RequestCompactProofOfTime):
        async with self.timelord.lock:
            if not self.timelord.bluebox_mode:
                return None
            now = time.time()
            # work older than 5s can safely be assumed to be from the previous batch, and needs to be cleared
            while self.timelord.pending_bluebox_info and (now - self.timelord.pending_bluebox_info[0][0] > 5):
                del self.timelord.pending_bluebox_info[0]
            self.timelord.pending_bluebox_info.append((now, vdf_info))
