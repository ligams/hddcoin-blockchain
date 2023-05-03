from __future__ import annotations

from typing import Generator, KeysView

SERVICES_FOR_GROUP = {
    "all": (
        "hddcoin_harvester hddcoin_timelord_launcher hddcoin_timelord hddcoin_farmer "
        "hddcoin_full_node hddcoin_wallet hddcoin_data_layer hddcoin_data_layer_http"
    ).split(),
    # TODO: should this be `data_layer`?
    "data": "hddcoin_wallet hddcoin_data_layer".split(),
    "data_layer_http": "hddcoin_data_layer_http".split(),
    "node": "hddcoin_full_node".split(),
    "harvester": "hddcoin_harvester".split(),
    "farmer": "hddcoin_harvester hddcoin_farmer hddcoin_full_node hddcoin_wallet".split(),
    "farmer-no-wallet": "hddcoin_harvester hddcoin_farmer hddcoin_full_node".split(),
    "farmer-only": "hddcoin_farmer".split(),
    "timelord": "hddcoin_timelord_launcher hddcoin_timelord hddcoin_full_node".split(),
    "timelord-only": "hddcoin_timelord".split(),
    "timelord-launcher-only": "hddcoin_timelord_launcher".split(),
    "wallet": "hddcoin_wallet".split(),
    "introducer": "hddcoin_introducer".split(),
    "simulator": "hddcoin_full_node_simulator".split(),
    "crawler": "hddcoin_crawler".split(),
    "seeder": "hddcoin_crawler hddcoin_seeder".split(),
    "seeder-only": "hddcoin_seeder".split(),
}


def all_groups() -> KeysView[str]:
    return SERVICES_FOR_GROUP.keys()


def services_for_groups(groups) -> Generator[str, None, None]:
    for group in groups:
        for service in SERVICES_FOR_GROUP[group]:
            yield service


def validate_service(service: str) -> bool:
    return any(service in _ for _ in SERVICES_FOR_GROUP.values())
