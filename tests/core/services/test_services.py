from __future__ import annotations

import asyncio
import signal
import sys
import time
from pathlib import Path
from typing import Any, Dict

import aiohttp.client_exceptions
import pytest
from typing_extensions import Protocol

from hddcoin.daemon.client import DaemonProxy, connect_to_daemon_and_validate
from hddcoin.rpc.data_layer_rpc_client import DataLayerRpcClient
from hddcoin.rpc.farmer_rpc_client import FarmerRpcClient
from hddcoin.rpc.full_node_rpc_client import FullNodeRpcClient
from hddcoin.rpc.harvester_rpc_client import HarvesterRpcClient
from hddcoin.rpc.rpc_client import RpcClient
from hddcoin.rpc.wallet_rpc_client import WalletRpcClient
from hddcoin.simulator.socket import find_available_listen_port
from hddcoin.util.config import lock_and_load_config, save_config
from hddcoin.util.ints import uint16
from hddcoin.util.misc import sendable_termination_signals
from hddcoin.util.timing import adjusted_timeout
from tests.core.data_layer.util import ChiaRoot
from tests.util.misc import closing_hddcoin_root_popen


class CreateServiceProtocol(Protocol):
    async def __call__(
        self,
        self_hostname: str,
        port: uint16,
        root_path: Path,
        net_config: Dict[str, Any],
    ) -> RpcClient:
        ...


async def wait_for_daemon_connection(root_path: Path, config: Dict[str, Any], timeout: float = 15) -> DaemonProxy:
    timeout = adjusted_timeout(timeout=timeout)

    start = time.monotonic()
    while time.monotonic() - start < timeout:
        client = await connect_to_daemon_and_validate(root_path=root_path, config=config, quiet=True)
        if client is not None:
            break
        await asyncio.sleep(0.1)
    else:
        raise Exception(f"unable to connect within {timeout} seconds")
    return client


@pytest.mark.parametrize(argnames="signal_number", argvalues=sendable_termination_signals)
@pytest.mark.anyio
async def test_daemon_terminates(signal_number: signal.Signals, hddcoin_root: ChiaRoot) -> None:
    port = find_available_listen_port()
    with lock_and_load_config(root_path=hddcoin_root.path, filename="config.yaml") as config:
        config["daemon_port"] = port
        save_config(root_path=hddcoin_root.path, filename="config.yaml", config_data=config)

    with closing_hddcoin_root_popen(hddcoin_root=hddcoin_root, args=[sys.executable, "-m", "hddcoin.daemon.server"]) as process:
        client = await wait_for_daemon_connection(root_path=hddcoin_root.path, config=config)

        try:
            return_code = process.poll()
            assert return_code is None

            process.send_signal(signal_number)
            process.communicate(timeout=adjusted_timeout(timeout=5))
        finally:
            await client.close()


@pytest.mark.parametrize(argnames="signal_number", argvalues=sendable_termination_signals)
@pytest.mark.parametrize(
    argnames=["create_service", "module_path", "service_config_name"],
    argvalues=[
        [DataLayerRpcClient.create, "hddcoin.server.start_data_layer", "data_layer"],
        [FarmerRpcClient.create, "hddcoin.server.start_farmer", "farmer"],
        [FullNodeRpcClient.create, "hddcoin.server.start_full_node", "full_node"],
        [HarvesterRpcClient.create, "hddcoin.server.start_harvester", "harvester"],
        [WalletRpcClient.create, "hddcoin.server.start_wallet", "wallet"],
        # TODO: review and somehow test the other services too
        # [, "hddcoin.server.start_introducer", "introducer"],
        # [, "hddcoin.seeder.start_crawler", ""],
        # [, "hddcoin.server.start_timelord", "timelord"],
        # [, "hddcoin.timelord.timelord_launcher", ],
        # [, "hddcoin.simulator.start_simulator", ],
        # [, "hddcoin.data_layer.data_layer_server", "data_layer"],
    ],
)
@pytest.mark.anyio
async def test_services_terminate(
    signal_number: signal.Signals,
    hddcoin_root: ChiaRoot,
    create_service: CreateServiceProtocol,
    module_path: str,
    service_config_name: str,
) -> None:
    with lock_and_load_config(root_path=hddcoin_root.path, filename="config.yaml") as config:
        config["daemon_port"] = find_available_listen_port(name="daemon")
        service_config = config[service_config_name]
        if "port" in service_config:
            port = find_available_listen_port(name="service")
            service_config["port"] = port
        rpc_port = find_available_listen_port(name="rpc")
        service_config["rpc_port"] = rpc_port
        save_config(root_path=hddcoin_root.path, filename="config.yaml", config_data=config)

    # TODO: make the wallet start up regardless so this isn't needed
    with closing_hddcoin_root_popen(
        hddcoin_root=hddcoin_root,
        args=[sys.executable, "-m", "hddcoin.daemon.server"],
    ):
        # Make sure the daemon is running and responsive before starting other services.
        # This probably shouldn't be required.  For now, it helps at least with the
        # farmer.
        daemon_client = await wait_for_daemon_connection(root_path=hddcoin_root.path, config=config)
        await daemon_client.close()

        with closing_hddcoin_root_popen(
            hddcoin_root=hddcoin_root,
            args=[sys.executable, "-m", module_path],
        ) as process:
            client = await create_service(
                self_hostname=config["self_hostname"],
                port=uint16(rpc_port),
                root_path=hddcoin_root.path,
                net_config=config,
            )
            try:
                start = time.monotonic()
                while time.monotonic() - start < 50:
                    return_code = process.poll()
                    assert return_code is None

                    try:
                        result = await client.healthz()
                    except (
                        aiohttp.client_exceptions.ClientConnectorError,
                        aiohttp.client_exceptions.ClientResponseError,
                    ):
                        pass
                    else:
                        if result.get("success", False):
                            break

                    await asyncio.sleep(0.1)
                else:
                    raise Exception("unable to connect")

                return_code = process.poll()
                assert return_code is None

                process.send_signal(signal_number)
                process.communicate(timeout=adjusted_timeout(timeout=30))
            finally:
                client.close()
                await client.await_closed()
