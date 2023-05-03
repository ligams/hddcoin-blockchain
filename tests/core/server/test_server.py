from __future__ import annotations

from typing import Tuple

import pytest

from hddcoin.full_node.full_node_api import FullNodeAPI
from hddcoin.server.server import HDDcoinServer
from hddcoin.simulator.block_tools import BlockTools
from hddcoin.types.peer_info import PeerInfo
from hddcoin.util.ints import uint16


@pytest.mark.asyncio
async def test_duplicate_client_connection(
    two_nodes: Tuple[FullNodeAPI, FullNodeAPI, HDDcoinServer, HDDcoinServer, BlockTools], self_hostname: str
) -> None:
    _, _, server_1, server_2, _ = two_nodes
    assert await server_2.start_client(PeerInfo(self_hostname, uint16(server_1._port)), None)
    assert not await server_2.start_client(PeerInfo(self_hostname, uint16(server_1._port)), None)
