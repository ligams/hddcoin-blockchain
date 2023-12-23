from __future__ import annotations

from typing import Any

from hddcoin.types.blockchain_format.program import Program


def json_to_hddcoinlisp(json_data: Any) -> Any:
    list_for_hddcoinlisp = []
    if isinstance(json_data, list):
        for value in json_data:
            list_for_hddcoinlisp.append(json_to_hddcoinlisp(value))
    else:
        if isinstance(json_data, dict):
            for key, value in json_data:
                list_for_hddcoinlisp.append((key, json_to_hddcoinlisp(value)))
        else:
            list_for_hddcoinlisp = json_data
    return Program.to(list_for_hddcoinlisp)
