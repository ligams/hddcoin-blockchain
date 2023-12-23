from __future__ import annotations

from logging import Logger
from typing import Tuple

import pytest

from hddcoin.full_node.full_node_api import FullNodeAPI
from hddcoin.server.node_discovery import FullNodeDiscovery
from hddcoin.server.peer_store_resolver import PeerStoreResolver
from hddcoin.server.server import HDDcoinServer
from hddcoin.simulator.block_tools import BlockTools
from hddcoin.util.default_root import SIMULATOR_ROOT_PATH


@pytest.mark.anyio
async def test_enable_private_networks(
    two_nodes: Tuple[FullNodeAPI, FullNodeAPI, HDDcoinServer, HDDcoinServer, BlockTools],
) -> None:
    hddcoin_server = two_nodes[2]

    # Missing `enable_private_networks` config entry in introducer_peer should default to False for back compat
    discovery0 = FullNodeDiscovery(
        hddcoin_server,
        0,
        PeerStoreResolver(
            SIMULATOR_ROOT_PATH,
            hddcoin_server.config,
            selected_network=hddcoin_server.config["selected_network"],
            peers_file_path_key="peers_file_path",
            legacy_peer_db_path_key="db/peer_table_node.sqlite",
            default_peers_file_path="db/peers.dat",
        ),
        {"host": "introducer.hddcoin.org", "port": 8444},
        [],
        0,
        hddcoin_server.config["selected_network"],
        None,
        Logger("node_discovery_tests"),
    )
    assert discovery0 is not None
    assert discovery0.enable_private_networks is False
    await discovery0.initialize_address_manager()
    assert discovery0.address_manager is not None
    assert discovery0.address_manager.allow_private_subnets is False

    # Test with enable_private_networks set to False in Config
    discovery1 = FullNodeDiscovery(
        hddcoin_server,
        0,
        PeerStoreResolver(
            SIMULATOR_ROOT_PATH,
            hddcoin_server.config,
            selected_network=hddcoin_server.config["selected_network"],
            peers_file_path_key="peers_file_path",
            legacy_peer_db_path_key="db/peer_table_node.sqlite",
            default_peers_file_path="db/peers.dat",
        ),
        {"host": "introducer.hddcoin.org", "port": 8444, "enable_private_networks": False},
        [],
        0,
        hddcoin_server.config["selected_network"],
        None,
        Logger("node_discovery_tests"),
    )
    assert discovery1 is not None
    assert discovery1.enable_private_networks is False
    await discovery1.initialize_address_manager()
    assert discovery1.address_manager is not None
    assert discovery1.address_manager.allow_private_subnets is False

    # Test with enable_private_networks set to True in Config
    discovery2 = FullNodeDiscovery(
        hddcoin_server,
        0,
        PeerStoreResolver(
            SIMULATOR_ROOT_PATH,
            hddcoin_server.config,
            selected_network=hddcoin_server.config["selected_network"],
            peers_file_path_key="peers_file_path",
            legacy_peer_db_path_key="db/peer_table_node.sqlite",
            default_peers_file_path="db/peers.dat",
        ),
        {"host": "introducer.hddcoin.org", "port": 8444, "enable_private_networks": True},
        [],
        0,
        hddcoin_server.config["selected_network"],
        None,
        Logger("node_discovery_tests"),
    )
    assert discovery2 is not None
    assert discovery2.enable_private_networks is True
    await discovery2.initialize_address_manager()
    assert discovery2.address_manager is not None
    assert discovery2.address_manager.allow_private_subnets is True
