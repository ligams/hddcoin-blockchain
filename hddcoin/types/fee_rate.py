from __future__ import annotations

import math
from dataclasses import dataclass

import typing_extensions

from hddcoin.types.clvm_cost import CLVMCost
from hddcoin.types.bytes import Bytes
from hddcoin.util.ints import uint64
from hddcoin.util.streamable import Streamable, streamable


@typing_extensions.final
@streamable
@dataclass(frozen=True)
class FeeRate(Streamable):
    """
    Represents Fee Rate in bytes divided by CLVM Cost.
    Performs HDD/byte conversion.
    Similar to 'Fee per cost'.
    """

    mojos_per_clvm_cost: uint64

    @classmethod
    def create(cls, bytes: Bytes, clvm_cost: CLVMCost) -> FeeRate:
        return cls(uint64(math.ceil(bytes / clvm_cost)))


@dataclass(frozen=True)
class FeeRateV2:
    """
    Represents Fee Rate in bytes divided by CLVM Cost.
    Similar to 'Fee per cost'.
    """

    mojos_per_clvm_cost: float
