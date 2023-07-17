from __future__ import annotations

from typing import Generator, KeysView

SERVICES_FOR_GROUP = {
    "all": [
        "hddcoin_harvester",
        "hddcoin_timelord_launcher",
        "hddcoin_timelord",
        "hddcoin_farmer",
        "hddcoin_full_node",
        "hddcoin_wallet",
        "hddcoin_data_layer",
        "hddcoin_data_layer_http",
    ],
    # TODO: should this be `data_layer`?
    "data": ["hddcoin_wallet", "hddcoin_data_layer"],
    "data_layer_http": ["hddcoin_data_layer_http"],
    "node": ["hddcoin_full_node"],
    "harvester": ["hddcoin_harvester"],
    "farmer": ["hddcoin_harvester", "hddcoin_farmer", "hddcoin_full_node", "hddcoin_wallet"],
    "farmer-no-wallet": ["hddcoin_harvester", "hddcoin_farmer", "hddcoin_full_node"],
    "farmer-only": ["hddcoin_farmer"],
    "timelord": ["hddcoin_timelord_launcher", "hddcoin_timelord", "hddcoin_full_node"],
    "timelord-only": ["hddcoin_timelord"],
    "timelord-launcher-only": ["hddcoin_timelord_launcher"],
    "wallet": ["hddcoin_wallet"],
    "introducer": ["hddcoin_introducer"],
    "simulator": ["hddcoin_full_node_simulator"],
    "crawler": ["hddcoin_crawler"],
    "seeder": ["hddcoin_crawler", "hddcoin_seeder"],
    "seeder-only": ["hddcoin_seeder"],
}


def all_groups() -> KeysView[str]:
    return SERVICES_FOR_GROUP.keys()


def services_for_groups(groups) -> Generator[str, None, None]:
    for group in groups:
        for service in SERVICES_FOR_GROUP[group]:
            yield service


def validate_service(service: str) -> bool:
    return any(service in _ for _ in SERVICES_FOR_GROUP.values())
