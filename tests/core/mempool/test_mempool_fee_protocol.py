from __future__ import annotations

import datetime
from typing import List, Tuple, Union

import pytest

from hddcoin.full_node.full_node_api import FullNodeAPI
from hddcoin.protocols import wallet_protocol
from hddcoin.protocols.protocol_message_types import ProtocolMessageTypes
from hddcoin.protocols.wallet_protocol import RespondFeeEstimates
from hddcoin.server.server import HDDcoinServer
from hddcoin.simulator.block_tools import BlockTools
from hddcoin.simulator.full_node_simulator import FullNodeSimulator
from hddcoin.util.ints import uint64
from hddcoin.wallet.wallet import Wallet
from tests.core.node_height import node_height_at_least
from tests.util.time_out_assert import time_out_assert


@pytest.mark.anyio
async def test_protocol_messages(
    simulator_and_wallet: Tuple[
        List[Union[FullNodeAPI, FullNodeSimulator]], List[Tuple[Wallet, HDDcoinServer]], BlockTools
    ]
) -> None:
    full_nodes, wallets, bt = simulator_and_wallet
    a_wallet = bt.get_pool_wallet_tool()
    reward_ph = a_wallet.get_new_puzzlehash()
    blocks = bt.get_consecutive_blocks(
        35,
        guarantee_transaction_block=True,
        farmer_reward_puzzle_hash=reward_ph,
        pool_reward_puzzle_hash=reward_ph,
    )

    full_node_sim: Union[FullNodeAPI, FullNodeSimulator] = full_nodes[0]

    for block in blocks:
        await full_node_sim.full_node.add_block(block)

    await time_out_assert(60, node_height_at_least, True, full_node_sim, blocks[-1].height)

    offset_secs = [60, 120, 300]
    now_unix_secs = int(datetime.datetime.utcnow().timestamp())
    request_times = [uint64(now_unix_secs + s) for s in offset_secs]
    request: wallet_protocol.RequestFeeEstimates = wallet_protocol.RequestFeeEstimates(request_times)
    estimates = await full_node_sim.request_fee_estimates(request)
    assert estimates is not None
    assert estimates.type == ProtocolMessageTypes.respond_fee_estimates.value
    response: RespondFeeEstimates = wallet_protocol.RespondFeeEstimates.from_bytes(estimates.data)

    # Sanity check the response
    assert len(response.estimates.estimates) == len(request_times)
    assert response.estimates.error is None
