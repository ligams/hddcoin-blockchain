from __future__ import annotations

import pathlib
import sys
from typing import Any, Dict, Optional

from hddcoin.introducer.introducer import Introducer
from hddcoin.introducer.introducer_api import IntroducerAPI
from hddcoin.server.outbound_message import NodeType
from hddcoin.server.start_service import Service, async_run
from hddcoin.types.aliases import IntroducerService
from hddcoin.util.hddcoin_logging import initialize_service_logging
from hddcoin.util.config import load_config, load_config_cli
from hddcoin.util.default_root import DEFAULT_ROOT_PATH
from hddcoin.util.misc import SignalHandlers

# See: https://bugs.python.org/issue29288
"".encode("idna")

SERVICE_NAME = "introducer"


def create_introducer_service(
    root_path: pathlib.Path,
    config: Dict[str, Any],
    advertised_port: Optional[int] = None,
    connect_to_daemon: bool = True,
) -> IntroducerService:
    service_config = config[SERVICE_NAME]

    if advertised_port is None:
        advertised_port = service_config["port"]

    introducer = Introducer(service_config["max_peers_to_send"], service_config["recent_peer_threshold"])
    node__api = IntroducerAPI(introducer)
    network_id = service_config["selected_network"]
    return Service(
        root_path=root_path,
        config=config,
        node=introducer,
        peer_api=node__api,
        node_type=NodeType.INTRODUCER,
        service_name=SERVICE_NAME,
        network_id=network_id,
        advertised_port=advertised_port,
        connect_to_daemon=connect_to_daemon,
    )


async def async_main() -> int:
    # TODO: refactor to avoid the double load
    config = load_config(DEFAULT_ROOT_PATH, "config.yaml")
    service_config = load_config_cli(DEFAULT_ROOT_PATH, "config.yaml", SERVICE_NAME)
    config[SERVICE_NAME] = service_config
    service = create_introducer_service(DEFAULT_ROOT_PATH, config)
    initialize_service_logging(service_name=SERVICE_NAME, config=config)
    async with SignalHandlers.manage() as signal_handlers:
        await service.setup_process_global_state(signal_handlers=signal_handlers)
        await service.run()

    return 0


def main() -> int:
    return async_run(async_main())


if __name__ == "__main__":
    sys.exit(main())
