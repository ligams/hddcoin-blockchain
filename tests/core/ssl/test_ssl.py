from __future__ import annotations

import aiohttp
import pytest

from hddcoin.protocols.shared_protocol import capabilities, protocol_version
from hddcoin.server.outbound_message import NodeType
from hddcoin.server.server import HDDcoinServer, ssl_context_for_client
from hddcoin.server.ssl_context import hddcoin_ssl_ca_paths, private_ssl_ca_paths
from hddcoin.server.ws_connection import WSHDDcoinConnection
from hddcoin.ssl.create_ssl import generate_ca_signed_cert
from hddcoin.types.blockchain_format.sized_bytes import bytes32
from hddcoin.types.peer_info import PeerInfo


async def establish_connection(server: HDDcoinServer, self_hostname: str, ssl_context) -> None:
    timeout = aiohttp.ClientTimeout(total=10)
    dummy_port = 5  # this does not matter
    async with aiohttp.ClientSession(timeout=timeout) as session:
        url = f"wss://{self_hostname}:{server._port}/ws"
        ws = await session.ws_connect(url, autoclose=False, autoping=True, ssl=ssl_context)
        wsc = WSHDDcoinConnection.create(
            NodeType.FULL_NODE,
            ws,
            server.api,
            dummy_port,
            server.log,
            True,
            server.received_message_callback,
            None,
            bytes32(b"\x00" * 32),
            100,
            30,
            local_capabilities_for_handshake=capabilities,
        )
        await wsc.perform_handshake(server._network_id, protocol_version, dummy_port, NodeType.FULL_NODE)
        await wsc.close()


class TestSSL:
    @pytest.mark.anyio
    async def test_public_connections(self, simulator_and_wallet, self_hostname):
        full_nodes, wallets, _ = simulator_and_wallet
        full_node_api = full_nodes[0]
        server_1: HDDcoinServer = full_node_api.full_node.server
        wallet_node, server_2 = wallets[0]

        success = await server_2.start_client(PeerInfo(self_hostname, server_1.get_port()), None)
        assert success is True

    @pytest.mark.anyio
    async def test_farmer(self, farmer_one_harvester, self_hostname):
        _, farmer_service, bt = farmer_one_harvester
        farmer_api = farmer_service._api

        farmer_server = farmer_api.farmer.server
        ca_private_crt_path, ca_private_key_path = private_ssl_ca_paths(bt.root_path, bt.config)
        hddcoin_ca_crt_path, hddcoin_ca_key_path = hddcoin_ssl_ca_paths(bt.root_path, bt.config)
        # Create valid cert (valid meaning signed with private CA)
        priv_crt = farmer_server.root_path / "valid.crt"
        priv_key = farmer_server.root_path / "valid.key"
        generate_ca_signed_cert(
            ca_private_crt_path.read_bytes(),
            ca_private_key_path.read_bytes(),
            priv_crt,
            priv_key,
        )
        ssl_context = ssl_context_for_client(ca_private_crt_path, ca_private_key_path, priv_crt, priv_key)
        await establish_connection(farmer_server, self_hostname, ssl_context)

        # Create not authenticated cert
        pub_crt = farmer_server.root_path / "non_valid.crt"
        pub_key = farmer_server.root_path / "non_valid.key"
        generate_ca_signed_cert(hddcoin_ca_crt_path.read_bytes(), hddcoin_ca_key_path.read_bytes(), pub_crt, pub_key)
        ssl_context = ssl_context_for_client(hddcoin_ca_crt_path, hddcoin_ca_key_path, pub_crt, pub_key)
        with pytest.raises(aiohttp.ClientConnectorCertificateError):
            await establish_connection(farmer_server, self_hostname, ssl_context)
        ssl_context = ssl_context_for_client(ca_private_crt_path, ca_private_key_path, pub_crt, pub_key)
        with pytest.raises(aiohttp.ServerDisconnectedError):
            await establish_connection(farmer_server, self_hostname, ssl_context)

    @pytest.mark.anyio
    async def test_full_node(self, simulator_and_wallet, self_hostname):
        full_nodes, wallets, bt = simulator_and_wallet
        full_node_api = full_nodes[0]
        full_node_server = full_node_api.full_node.server
        hddcoin_ca_crt_path, hddcoin_ca_key_path = hddcoin_ssl_ca_paths(bt.root_path, bt.config)

        # Create not authenticated cert
        pub_crt = full_node_server.root_path / "p2p.crt"
        pub_key = full_node_server.root_path / "p2p.key"
        generate_ca_signed_cert(
            hddcoin_ca_crt_path.read_bytes(),
            hddcoin_ca_key_path.read_bytes(),
            pub_crt,
            pub_key,
        )
        ssl_context = ssl_context_for_client(hddcoin_ca_crt_path, hddcoin_ca_key_path, pub_crt, pub_key)
        await establish_connection(full_node_server, self_hostname, ssl_context)

    @pytest.mark.anyio
    async def test_introducer(self, introducer_service, self_hostname):
        introducer_server = introducer_service._node.server
        hddcoin_ca_crt_path, hddcoin_ca_key_path = hddcoin_ssl_ca_paths(introducer_service.root_path, introducer_service.config)

        # Create not authenticated cert
        pub_crt = introducer_server.root_path / "p2p.crt"
        pub_key = introducer_server.root_path / "p2p.key"
        generate_ca_signed_cert(
            hddcoin_ca_crt_path.read_bytes(),
            hddcoin_ca_key_path.read_bytes(),
            pub_crt,
            pub_key,
        )
        ssl_context = ssl_context_for_client(hddcoin_ca_crt_path, hddcoin_ca_key_path, pub_crt, pub_key)
        await establish_connection(introducer_server, self_hostname, ssl_context)
