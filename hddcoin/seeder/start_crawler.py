from __future__ import annotations

import logging
import pathlib
import sys
from multiprocessing import freeze_support
from typing import Any, Dict, Optional

from hddcoin.consensus.constants import ConsensusConstants
from hddcoin.consensus.default_constants import DEFAULT_CONSTANTS
from hddcoin.rpc.crawler_rpc_api import CrawlerRpcApi
from hddcoin.seeder.crawler import Crawler
from hddcoin.seeder.crawler_api import CrawlerAPI
from hddcoin.server.outbound_message import NodeType
from hddcoin.server.start_service import RpcInfo, Service, async_run
from hddcoin.types.aliases import CrawlerService
from hddcoin.util.hddcoin_logging import initialize_service_logging
from hddcoin.util.config import load_config, load_config_cli
from hddcoin.util.default_root import DEFAULT_ROOT_PATH
from hddcoin.util.misc import SignalHandlers

# See: https://bugs.python.org/issue29288
"".encode("idna")

SERVICE_NAME = "seeder"
log = logging.getLogger(__name__)


def create_full_node_crawler_service(
    root_path: pathlib.Path,
    config: Dict[str, Any],
    consensus_constants: ConsensusConstants,
    connect_to_daemon: bool = True,
) -> CrawlerService:
    service_config = config[SERVICE_NAME]
    crawler_config = service_config["crawler"]

    crawler = Crawler(
        service_config,
        root_path=root_path,
        constants=consensus_constants,
    )
    api = CrawlerAPI(crawler)

    network_id = service_config["selected_network"]

    rpc_info: Optional[RpcInfo[CrawlerRpcApi]] = None
    if crawler_config.get("start_rpc_server", True):
        rpc_info = (CrawlerRpcApi, crawler_config.get("rpc_port", 8561))

    return Service(
        root_path=root_path,
        config=config,
        node=api.crawler,
        peer_api=api,
        node_type=NodeType.FULL_NODE,
        advertised_port=service_config["port"],
        service_name="full_node",
        upnp_ports=[],
        on_connect_callback=crawler.on_connect,
        network_id=network_id,
        rpc_info=rpc_info,
        connect_to_daemon=connect_to_daemon,
    )


async def async_main() -> int:
    # TODO: refactor to avoid the double load
    config = load_config(DEFAULT_ROOT_PATH, "config.yaml")
    service_config = load_config_cli(DEFAULT_ROOT_PATH, "config.yaml", SERVICE_NAME)
    config[SERVICE_NAME] = service_config
    overrides = service_config["network_overrides"]["constants"][service_config["selected_network"]]
    updated_constants = DEFAULT_CONSTANTS.replace_str_to_bytes(**overrides)
    initialize_service_logging(service_name=SERVICE_NAME, config=config)
    service = create_full_node_crawler_service(DEFAULT_ROOT_PATH, config, updated_constants)
    async with SignalHandlers.manage() as signal_handlers:
        await service.setup_process_global_state(signal_handlers=signal_handlers)
        await service.run()

    return 0


def main() -> int:
    freeze_support()
    return async_run(async_main())


if __name__ == "__main__":
    sys.exit(main())
