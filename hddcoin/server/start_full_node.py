from __future__ import annotations

import logging
import os
import pathlib
import sys
from multiprocessing import freeze_support
from typing import Any, Dict, List, Optional, Tuple

from hddcoin.consensus.constants import ConsensusConstants
from hddcoin.consensus.default_constants import DEFAULT_CONSTANTS
from hddcoin.full_node.full_node import FullNode
from hddcoin.full_node.full_node_api import FullNodeAPI
from hddcoin.rpc.full_node_rpc_api import FullNodeRpcApi
from hddcoin.server.outbound_message import NodeType
from hddcoin.server.start_service import RpcInfo, Service, async_run
from hddcoin.types.aliases import FullNodeService
from hddcoin.util.hddcoin_logging import initialize_service_logging
from hddcoin.util.config import load_config, load_config_cli
from hddcoin.util.default_root import DEFAULT_ROOT_PATH
from hddcoin.util.ints import uint16
from hddcoin.util.misc import SignalHandlers
from hddcoin.util.task_timing import maybe_manage_task_instrumentation

# See: https://bugs.python.org/issue29288
"".encode("idna")

SERVICE_NAME = "full_node"
log = logging.getLogger(__name__)


async def create_full_node_service(
    root_path: pathlib.Path,
    config: Dict[str, Any],
    consensus_constants: ConsensusConstants,
    connect_to_daemon: bool = True,
    override_capabilities: Optional[List[Tuple[uint16, str]]] = None,
) -> FullNodeService:
    service_config = config[SERVICE_NAME]

    full_node = await FullNode.create(
        service_config,
        root_path=root_path,
        consensus_constants=consensus_constants,
    )
    api = FullNodeAPI(full_node)

    upnp_list = []
    if service_config["enable_upnp"]:
        upnp_list = [service_config["port"]]
    network_id = service_config["selected_network"]
    rpc_info: Optional[RpcInfo[FullNodeRpcApi]] = None
    if service_config["start_rpc_server"]:
        rpc_info = (FullNodeRpcApi, service_config["rpc_port"])
    return Service(
        root_path=root_path,
        config=config,
        node=api.full_node,
        peer_api=api,
        node_type=NodeType.FULL_NODE,
        advertised_port=service_config["port"],
        service_name=SERVICE_NAME,
        upnp_ports=upnp_list,
        on_connect_callback=full_node.on_connect,
        network_id=network_id,
        rpc_info=rpc_info,
        connect_to_daemon=connect_to_daemon,
        override_capabilities=override_capabilities,
    )


async def async_main(service_config: Dict[str, Any]) -> int:
    # TODO: refactor to avoid the double load
    config = load_config(DEFAULT_ROOT_PATH, "config.yaml")
    config[SERVICE_NAME] = service_config
    network_id = service_config["selected_network"]
    overrides = service_config["network_overrides"]["constants"][network_id]
    updated_constants = DEFAULT_CONSTANTS.replace_str_to_bytes(**overrides)
    initialize_service_logging(service_name=SERVICE_NAME, config=config)
    service = await create_full_node_service(DEFAULT_ROOT_PATH, config, updated_constants)
    async with SignalHandlers.manage() as signal_handlers:
        await service.setup_process_global_state(signal_handlers=signal_handlers)
        await service.run()

    return 0


def main() -> int:
    freeze_support()

    with maybe_manage_task_instrumentation(enable=os.environ.get("CHIA_INSTRUMENT_NODE") is not None):
        service_config = load_config_cli(DEFAULT_ROOT_PATH, "config.yaml", SERVICE_NAME)
        target_peer_count = service_config.get("target_peer_count", 40) - service_config.get(
            "target_outbound_peer_count", 8
        )
        if target_peer_count < 0:
            target_peer_count = None
        if not service_config.get("use_hddcoin_loop_policy", True):
            target_peer_count = None
        return async_run(coro=async_main(service_config), connection_limit=target_peer_count)


if __name__ == "__main__":
    sys.exit(main())
