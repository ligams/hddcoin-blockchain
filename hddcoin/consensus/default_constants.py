from __future__ import annotations

from typing import Any, Dict

from hddcoin.types.blockchain_format.sized_bytes import bytes32
from hddcoin.util.ints import uint8, uint32, uint64, uint128

from .constants import ConsensusConstants

DEFAULT_CONSTANTS = ConsensusConstants(
    SLOT_BLOCKS_TARGET=uint32(32),
    MIN_BLOCKS_PER_CHALLENGE_BLOCK=uint8(16),  # Must be less than half of SLOT_BLOCKS_TARGET
    MAX_SUB_SLOT_BLOCKS=uint32(128),  # Must be less than half of SUB_EPOCH_BLOCKS
    NUM_SPS_SUB_SLOT=uint32(64),  # Must be a power of 2
    SUB_SLOT_ITERS_STARTING=uint64(2**27),
    # DIFFICULTY_STARTING is the starting difficulty for the first epoch, which is then further
    # multiplied by another factor of DIFFICULTY_CONSTANT_FACTOR, to be used in the VDF iter calculation formula.
    DIFFICULTY_CONSTANT_FACTOR=uint128(2**67),
    DIFFICULTY_STARTING=uint64(7),
    DIFFICULTY_CHANGE_MAX_FACTOR=uint32(3),  # The next difficulty is truncated to range [prev / FACTOR, prev * FACTOR]
    # These 3 constants must be changed at the same time
    SUB_EPOCH_BLOCKS=uint32(384),  # The number of blocks per sub-epoch, mainnet 384
    EPOCH_BLOCKS=uint32(4608),  # The number of blocks per epoch, mainnet 4608. Must be multiple of SUB_EPOCH_SB
    SIGNIFICANT_BITS=8,  # The number of bits to look at in difficulty and min iters. The rest are zeroed
    DISCRIMINANT_SIZE_BITS=1024,  # Max is 1024 (based on ClassGroupElement int size)
    NUMBER_ZERO_BITS_PLOT_FILTER=9,  # H(plot signature of the challenge) must start with these many zeroes
    MIN_PLOT_SIZE=32,  # 32 for mainnet
    MAX_PLOT_SIZE=50,
    SUB_SLOT_TIME_TARGET=600,  # The target number of seconds per slot, mainnet 600
    NUM_SP_INTERVALS_EXTRA=3,  # The number of sp intervals to add to the signage point
    MAX_FUTURE_TIME2=2 * 60,  # The next block can have a timestamp of at most these many seconds in the future
    NUMBER_OF_TIMESTAMPS=11,  # Than the average of the last NUMBER_OF_TIMESTAMPS blocks
    # Used as the initial cc rc challenges, as well as first block back pointers, and first SES back pointer
    # We override this value based on the chain being run (testnet0, testnet1, mainnet, etc)
    # Default used for tests is std_hash(b'')
    "GENESIS_CHALLENGE": bytes.fromhex("f663a54192e4fc8832d62c5f914d1c3a15dd2a519c3ca23609a508f4641da23e"),
    # Forks of hddcoin should change this value to provide replay attack protection. This is set to mainnet genesis chall
    "AGG_SIG_ME_ADDITIONAL_DATA": bytes.fromhex("49f4afb189342858dba5c1bb6b50b0deaa706088474f0c5431d65b857d54ddb5"),
    "GENESIS_PRE_FARM_POOL_PUZZLE_HASH": bytes.fromhex(
        "5ed49df42106663947059a3323da310f24c804c6cf7420f3c1ac0cffb3f9d2b3"
    ),
    "GENESIS_PRE_FARM_FARMER_PUZZLE_HASH": bytes.fromhex(
        "5ed49df42106663947059a3323da310f24c804c6cf7420f3c1ac0cffb3f9d2b3"
    ),
    MAX_VDF_WITNESS_SIZE=64,
    # Size of mempool = 10x the size of block
    MEMPOOL_BLOCK_BUFFER=10,
    # Max coin amount, fits into 64 bits
    MAX_COIN_AMOUNT=uint64((1 << 64) - 1),
    # Max block cost in clvm cost units
    MAX_BLOCK_COST_CLVM=11000000000,
    # The cost per byte of generator program
    "COST_PER_BYTE": 12000,
    "WEIGHT_PROOF_THRESHOLD": 2,
    "BLOCKS_CACHE_SIZE": 4608 + (128 * 4),
    "WEIGHT_PROOF_RECENT_BLOCKS": 1000,
    "MAX_BLOCK_COUNT_PER_REQUESTS": 32,  # Allow up to 32 blocks per request
    "MAX_GENERATOR_SIZE": 1000000,
    "MAX_GENERATOR_REF_LIST_SIZE": 512,  # Number of references allowed in the block generator ref list
    "POOL_SUB_SLOT_ITERS": 37600000000,  # iters limit * NUM_SPS
    "SOFT_FORK2_HEIGHT": 3700000,
    # September 2023
    "SOFT_FORK3_HEIGHT": 3750000,
    # June 2024
    "HARD_FORK_HEIGHT": 4996000,
    # June 2027
    PLOT_FILTER_128_HEIGHT=uint32(10542000),
    # June 2030
    PLOT_FILTER_64_HEIGHT=uint32(15592000),
    # June 2033
    PLOT_FILTER_32_HEIGHT=uint32(20643000),
)


DEFAULT_CONSTANTS = ConsensusConstants(**default_kwargs)  # type: ignore
