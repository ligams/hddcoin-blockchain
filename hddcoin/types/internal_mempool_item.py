from __future__ import annotations

from dataclasses import dataclass
from typing import Dict

from hddcoin.consensus.cost_calculator import NPCResult
from hddcoin.types.blockchain_format.sized_bytes import bytes32
from hddcoin.types.mempool_item import BundleCoinSpend
from hddcoin.types.spend_bundle import SpendBundle
from hddcoin.util.ints import uint32


@dataclass(frozen=True)
class InternalMempoolItem:
    spend_bundle: SpendBundle
    npc_result: NPCResult
    height_added_to_mempool: uint32
    # Map of coin ID to coin spend data between the bundle and its NPCResult
    bundle_coin_spends: Dict[bytes32, BundleCoinSpend]
