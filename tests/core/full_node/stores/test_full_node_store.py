from __future__ import annotations

import dataclasses
import logging
import random
from typing import AsyncIterator, List, Optional

import pytest

from hddcoin.consensus.blockchain import AddBlockResult, Blockchain
from hddcoin.consensus.constants import ConsensusConstants
from hddcoin.consensus.difficulty_adjustment import get_next_sub_slot_iters_and_difficulty
from hddcoin.consensus.find_fork_point import find_fork_point_in_chain
from hddcoin.consensus.multiprocess_validation import PreValidationResult
from hddcoin.consensus.pot_iterations import is_overflow_block
from hddcoin.full_node.full_node_store import FullNodeStore
from hddcoin.full_node.signage_point import SignagePoint
from hddcoin.protocols import timelord_protocol
from hddcoin.protocols.timelord_protocol import NewInfusionPointVDF
from hddcoin.simulator.block_tools import BlockTools, create_block_tools_async, get_signage_point
from hddcoin.simulator.keyring import TempKeyring
from hddcoin.types.blockchain_format.sized_bytes import bytes32
from hddcoin.types.full_block import FullBlock
from hddcoin.types.unfinished_block import UnfinishedBlock
from hddcoin.util.block_cache import BlockCache
from hddcoin.util.hash import std_hash
from hddcoin.util.ints import uint8, uint32, uint64, uint128
from tests.blockchain.blockchain_test_utils import _validate_and_add_block, _validate_and_add_block_no_error
from tests.util.blockchain import create_blockchain

log = logging.getLogger(__name__)


@pytest.fixture(scope="function")
async def custom_block_tools(blockchain_constants: ConsensusConstants) -> AsyncIterator[BlockTools]:
    with TempKeyring() as keychain:
        patched_constants = dataclasses.replace(
            blockchain_constants,
            DISCRIMINANT_SIZE_BITS=32,
            SUB_SLOT_ITERS_STARTING=uint64(2**12),
        )
        yield await create_block_tools_async(constants=patched_constants, keychain=keychain)


@pytest.fixture(scope="function")
async def empty_blockchain(db_version: int, blockchain_constants: ConsensusConstants) -> AsyncIterator[Blockchain]:
    patched_constants = dataclasses.replace(
        blockchain_constants,
        DISCRIMINANT_SIZE_BITS=32,
        SUB_SLOT_ITERS_STARTING=uint64(2**12),
    )
    async with create_blockchain(patched_constants, db_version) as (bc1, db_wrapper):
        yield bc1


@pytest.fixture(scope="function")
async def empty_blockchain_with_original_constants(
    db_version: int, blockchain_constants: ConsensusConstants
) -> AsyncIterator[Blockchain]:
    async with create_blockchain(blockchain_constants, db_version) as (bc1, db_wrapper):
        yield bc1


@pytest.mark.limit_consensus_modes(reason="save time")
@pytest.mark.anyio
@pytest.mark.parametrize("normalized_to_identity", [False, True])
async def test_basic_store(
    empty_blockchain: Blockchain,
    custom_block_tools: BlockTools,
    normalized_to_identity: bool,
    seeded_random: random.Random,
) -> None:
    blockchain = empty_blockchain
    blocks = custom_block_tools.get_consecutive_blocks(
        10,
        seed=b"1234",
        normalized_to_identity_cc_eos=normalized_to_identity,
        normalized_to_identity_icc_eos=normalized_to_identity,
        normalized_to_identity_cc_ip=normalized_to_identity,
        normalized_to_identity_cc_sp=normalized_to_identity,
    )

    store = FullNodeStore(empty_blockchain.constants)

    unfinished_blocks = []
    for block in blocks:
        unfinished_blocks.append(
            UnfinishedBlock(
                block.finished_sub_slots,
                block.reward_chain_block.get_unfinished(),
                block.challenge_chain_sp_proof,
                block.reward_chain_sp_proof,
                block.foliage,
                block.foliage_transaction_block,
                block.transactions_info,
                block.transactions_generator,
                [],
            )
        )

    # Add/get candidate block
    assert store.get_candidate_block(unfinished_blocks[0].get_hash()) is None
    for height, unf_block in enumerate(unfinished_blocks):
        store.add_candidate_block(unf_block.get_hash(), uint32(height), unf_block)

    candidate = store.get_candidate_block(unfinished_blocks[4].get_hash())
    assert candidate is not None
    assert candidate[1] == unfinished_blocks[4]
    store.clear_candidate_blocks_below(uint32(8))
    assert store.get_candidate_block(unfinished_blocks[5].get_hash()) is None
    assert store.get_candidate_block(unfinished_blocks[8].get_hash()) is not None

    # Test seen unfinished blocks
    h_hash_1 = bytes32.random(seeded_random)
    assert not store.seen_unfinished_block(h_hash_1)
    assert store.seen_unfinished_block(h_hash_1)
    store.clear_seen_unfinished_blocks()
    assert not store.seen_unfinished_block(h_hash_1)

    # Add/get unfinished block
    for height, unf_block in enumerate(unfinished_blocks):
        assert store.get_unfinished_block(unf_block.partial_hash) is None
        store.add_unfinished_block(uint32(height), unf_block, PreValidationResult(None, uint64(123532), None, False))
        assert store.get_unfinished_block(unf_block.partial_hash) == unf_block
        store.remove_unfinished_block(unf_block.partial_hash)
        assert store.get_unfinished_block(unf_block.partial_hash) is None

    blocks = custom_block_tools.get_consecutive_blocks(
        1,
        skip_slots=5,
        normalized_to_identity_cc_ip=normalized_to_identity,
        normalized_to_identity_cc_sp=normalized_to_identity,
        normalized_to_identity_cc_eos=normalized_to_identity,
        normalized_to_identity_icc_eos=normalized_to_identity,
    )
    sub_slots = blocks[0].finished_sub_slots
    assert len(sub_slots) == 5

    assert (
        store.get_finished_sub_slots(
            BlockCache({}),
            None,
            sub_slots[0].challenge_chain.challenge_chain_end_of_slot_vdf.challenge,
        )
        == []
    )
    # Test adding non-connecting sub-slots genesis
    assert store.get_sub_slot(empty_blockchain.constants.GENESIS_CHALLENGE) is None
    assert store.get_sub_slot(sub_slots[0].challenge_chain.get_hash()) is None
    assert store.get_sub_slot(sub_slots[1].challenge_chain.get_hash()) is None
    next_sub_slot_iters = custom_block_tools.constants.SUB_SLOT_ITERS_STARTING
    next_difficulty = custom_block_tools.constants.DIFFICULTY_STARTING
    assert (
        store.new_finished_sub_slot(sub_slots[1], blockchain, None, next_sub_slot_iters, next_difficulty, None) is None
    )
    assert (
        store.new_finished_sub_slot(sub_slots[2], blockchain, None, next_sub_slot_iters, next_difficulty, None) is None
    )

    # Test adding sub-slots after genesis
    assert (
        store.new_finished_sub_slot(sub_slots[0], blockchain, None, next_sub_slot_iters, next_difficulty, None)
        is not None
    )
    sub_slot = store.get_sub_slot(sub_slots[0].challenge_chain.get_hash())
    assert sub_slot is not None
    assert sub_slot[0] == sub_slots[0]
    assert store.get_sub_slot(sub_slots[1].challenge_chain.get_hash()) is None
    assert (
        store.new_finished_sub_slot(sub_slots[1], blockchain, None, next_sub_slot_iters, next_difficulty, None)
        is not None
    )
    for i in range(len(sub_slots)):
        assert (
            store.new_finished_sub_slot(sub_slots[i], blockchain, None, next_sub_slot_iters, next_difficulty, None)
            is not None
        )
        slot_i = store.get_sub_slot(sub_slots[i].challenge_chain.get_hash())
        assert slot_i is not None
        assert slot_i[0] == sub_slots[i]

    assert store.get_finished_sub_slots(BlockCache({}), None, sub_slots[-1].challenge_chain.get_hash()) == sub_slots
    assert store.get_finished_sub_slots(BlockCache({}), None, std_hash(b"not a valid hash")) is None

    assert (
        store.get_finished_sub_slots(BlockCache({}), None, sub_slots[-2].challenge_chain.get_hash()) == sub_slots[:-1]
    )

    # Test adding genesis peak
    await _validate_and_add_block(blockchain, blocks[0])
    peak = blockchain.get_peak()
    assert peak is not None
    peak_full_block = await blockchain.get_full_peak()
    assert peak_full_block is not None
    next_sub_slot_iters, next_difficulty = get_next_sub_slot_iters_and_difficulty(
        blockchain.constants, False, peak, blockchain
    )

    if peak.overflow:
        store.new_peak(
            peak,
            peak_full_block,
            sub_slots[-2],
            sub_slots[-1],
            None,
            blockchain,
            next_sub_slot_iters,
            next_difficulty,
        )
    else:
        store.new_peak(
            peak, peak_full_block, None, sub_slots[-1], None, blockchain, next_sub_slot_iters, next_difficulty
        )

    assert store.get_sub_slot(sub_slots[0].challenge_chain.get_hash()) is None
    assert store.get_sub_slot(sub_slots[1].challenge_chain.get_hash()) is None
    assert store.get_sub_slot(sub_slots[2].challenge_chain.get_hash()) is None
    if peak.overflow:
        slot_3 = store.get_sub_slot(sub_slots[3].challenge_chain.get_hash())
        assert slot_3 is not None
        assert slot_3[0] == sub_slots[3]
    else:
        assert store.get_sub_slot(sub_slots[3].challenge_chain.get_hash()) is None

    slot_4 = store.get_sub_slot(sub_slots[4].challenge_chain.get_hash())
    assert slot_4 is not None
    assert slot_4[0] == sub_slots[4]

    assert (
        store.get_finished_sub_slots(
            blockchain,
            peak,
            sub_slots[-1].challenge_chain.get_hash(),
        )
        == []
    )

    # Test adding non genesis peak directly
    blocks = custom_block_tools.get_consecutive_blocks(
        2,
        skip_slots=2,
        normalized_to_identity_cc_eos=normalized_to_identity,
        normalized_to_identity_icc_eos=normalized_to_identity,
        normalized_to_identity_cc_ip=normalized_to_identity,
        normalized_to_identity_cc_sp=normalized_to_identity,
    )
    blocks = custom_block_tools.get_consecutive_blocks(
        3,
        block_list_input=blocks,
        normalized_to_identity_cc_eos=normalized_to_identity,
        normalized_to_identity_icc_eos=normalized_to_identity,
        normalized_to_identity_cc_ip=normalized_to_identity,
        normalized_to_identity_cc_sp=normalized_to_identity,
    )

    for block in blocks:
        await _validate_and_add_block_no_error(blockchain, block)
        sb = blockchain.block_record(block.header_hash)
        next_sub_slot_iters, next_difficulty = get_next_sub_slot_iters_and_difficulty(
            blockchain.constants, False, sb, blockchain
        )
        result = await blockchain.get_sp_and_ip_sub_slots(block.header_hash)
        assert result is not None
        sp_sub_slot, ip_sub_slot = result
        res = store.new_peak(
            sb, block, sp_sub_slot, ip_sub_slot, None, blockchain, next_sub_slot_iters, next_difficulty
        )
        assert res.added_eos is None

    # Add reorg blocks
    blocks_reorg = custom_block_tools.get_consecutive_blocks(
        20,
        normalized_to_identity_cc_eos=normalized_to_identity,
        normalized_to_identity_icc_eos=normalized_to_identity,
        normalized_to_identity_cc_ip=normalized_to_identity,
        normalized_to_identity_cc_sp=normalized_to_identity,
    )
    for block in blocks_reorg:
        peak = blockchain.get_peak()
        assert peak is not None

        await _validate_and_add_block_no_error(blockchain, block)

        peak_here = blockchain.get_peak()
        assert peak_here is not None
        if peak_here.header_hash == block.header_hash:
            sb = blockchain.block_record(block.header_hash)
            fork = await find_fork_point_in_chain(blockchain, peak, blockchain.block_record(sb.header_hash))
            if fork > 0:
                fork_block = blockchain.height_to_block_record(uint32(fork))
            else:
                fork_block = None
            result = await blockchain.get_sp_and_ip_sub_slots(block.header_hash)
            assert result is not None
            sp_sub_slot, ip_sub_slot = result
            next_sub_slot_iters, next_difficulty = get_next_sub_slot_iters_and_difficulty(
                blockchain.constants, False, sb, blockchain
            )
            res = store.new_peak(
                sb, block, sp_sub_slot, ip_sub_slot, fork_block, blockchain, next_sub_slot_iters, next_difficulty
            )
            assert res.added_eos is None

    # Add slots to the end
    blocks_2 = custom_block_tools.get_consecutive_blocks(
        1,
        block_list_input=blocks_reorg,
        skip_slots=2,
        normalized_to_identity_cc_eos=normalized_to_identity,
        normalized_to_identity_icc_eos=normalized_to_identity,
        normalized_to_identity_cc_ip=normalized_to_identity,
        normalized_to_identity_cc_sp=normalized_to_identity,
    )
    peak = blockchain.get_peak()
    for slot in blocks_2[-1].finished_sub_slots:
        next_sub_slot_iters, next_difficulty = get_next_sub_slot_iters_and_difficulty(
            blockchain.constants, True, peak, blockchain
        )

        store.new_finished_sub_slot(
            slot,
            blockchain,
            blockchain.get_peak(),
            next_sub_slot_iters,
            next_difficulty,
            await blockchain.get_full_peak(),
        )

    assert store.get_sub_slot(sub_slots[3].challenge_chain.get_hash()) is None
    assert store.get_sub_slot(sub_slots[4].challenge_chain.get_hash()) is None

    # Test adding signage point
    peak = blockchain.get_peak()
    assert peak is not None
    ss_start_iters = peak.ip_sub_slot_total_iters(custom_block_tools.constants)
    for i in range(
        1, custom_block_tools.constants.NUM_SPS_SUB_SLOT - custom_block_tools.constants.NUM_SP_INTERVALS_EXTRA
    ):
        sp = get_signage_point(
            custom_block_tools.constants,
            blockchain,
            peak,
            ss_start_iters,
            uint8(i),
            [],
            peak.sub_slot_iters,
        )
        assert store.new_signage_point(uint8(i), blockchain, peak, peak.sub_slot_iters, sp)

    blocks = blocks_reorg
    while True:
        blocks = custom_block_tools.get_consecutive_blocks(
            1,
            block_list_input=blocks,
            normalized_to_identity_cc_eos=normalized_to_identity,
            normalized_to_identity_icc_eos=normalized_to_identity,
            normalized_to_identity_cc_ip=normalized_to_identity,
            normalized_to_identity_cc_sp=normalized_to_identity,
        )
        await _validate_and_add_block(blockchain, blocks[-1])
        peak_here = blockchain.get_peak()
        assert peak_here is not None
        if peak_here.header_hash == blocks[-1].header_hash:
            sb = blockchain.block_record(blocks[-1].header_hash)
            fork = await find_fork_point_in_chain(blockchain, peak, blockchain.block_record(sb.header_hash))
            if fork > 0:
                fork_block = blockchain.height_to_block_record(uint32(fork))
            else:
                fork_block = None
            result = await blockchain.get_sp_and_ip_sub_slots(blocks[-1].header_hash)
            assert result is not None
            sp_sub_slot, ip_sub_slot = result

            next_sub_slot_iters, next_difficulty = get_next_sub_slot_iters_and_difficulty(
                blockchain.constants, False, sb, blockchain
            )
            res = store.new_peak(
                sb,
                blocks[-1],
                sp_sub_slot,
                ip_sub_slot,
                fork_block,
                blockchain,
                next_sub_slot_iters,
                next_difficulty,
            )
            assert res.added_eos is None
            if sb.overflow and sp_sub_slot is not None:
                assert sp_sub_slot != ip_sub_slot
                break

    peak = blockchain.get_peak()
    assert peak is not None
    assert peak.overflow
    # Overflow peak should result in 2 finished sub slots
    assert len(store.finished_sub_slots) == 2

    # Add slots to the end, except for the last one, which we will use to test invalid SP
    blocks_2 = custom_block_tools.get_consecutive_blocks(
        1,
        block_list_input=blocks,
        skip_slots=3,
        normalized_to_identity_cc_eos=normalized_to_identity,
        normalized_to_identity_icc_eos=normalized_to_identity,
        normalized_to_identity_cc_ip=normalized_to_identity,
        normalized_to_identity_cc_sp=normalized_to_identity,
    )
    for slot in blocks_2[-1].finished_sub_slots[:-1]:
        next_sub_slot_iters, next_difficulty = get_next_sub_slot_iters_and_difficulty(
            blockchain.constants, True, peak, blockchain
        )

        store.new_finished_sub_slot(
            slot,
            blockchain,
            blockchain.get_peak(),
            next_sub_slot_iters,
            next_difficulty,
            await blockchain.get_full_peak(),
        )
    finished_sub_slots = blocks_2[-1].finished_sub_slots
    assert len(store.finished_sub_slots) == 4

    # Test adding signage points for overflow blocks (sp_sub_slot)
    ss_start_iters = peak.sp_sub_slot_total_iters(custom_block_tools.constants)
    # for i in range(peak.signage_point_index, custom_block_tools.constants.NUM_SPS_SUB_SLOT):
    #     if i < peak.signage_point_index:
    #         continue
    #     latest = peak
    #     while latest.total_iters > peak.sp_total_iters(custom_block_tools.constants):
    #         latest = blockchain.blocks[latest.prev_hash]
    #     sp = get_signage_point(
    #         custom_block_tools.constants,
    #         blockchain.blocks,
    #         latest,
    #         ss_start_iters,
    #         uint8(i),
    #         [],
    #         peak.sub_slot_iters,
    #     )
    #     assert store.new_signage_point(i, blockchain.blocks, peak, peak.sub_slot_iters, sp)

    # Test adding signage points for overflow blocks (ip_sub_slot)
    for i in range(
        1, custom_block_tools.constants.NUM_SPS_SUB_SLOT - custom_block_tools.constants.NUM_SP_INTERVALS_EXTRA
    ):
        sp = get_signage_point(
            custom_block_tools.constants,
            blockchain,
            peak,
            peak.ip_sub_slot_total_iters(custom_block_tools.constants),
            uint8(i),
            [],
            peak.sub_slot_iters,
        )
        assert store.new_signage_point(uint8(i), blockchain, peak, peak.sub_slot_iters, sp)

    # Test adding future signage point, a few slots forward (good)
    saved_sp_hash = None
    for slot_offset in range(1, len(finished_sub_slots)):
        for i in range(
            1,
            custom_block_tools.constants.NUM_SPS_SUB_SLOT - custom_block_tools.constants.NUM_SP_INTERVALS_EXTRA,
        ):
            sp = get_signage_point(
                custom_block_tools.constants,
                blockchain,
                peak,
                uint128(peak.ip_sub_slot_total_iters(custom_block_tools.constants) + slot_offset * peak.sub_slot_iters),
                uint8(i),
                finished_sub_slots[:slot_offset],
                peak.sub_slot_iters,
            )
            assert sp.cc_vdf is not None
            saved_sp_hash = sp.cc_vdf.output.get_hash()
            assert store.new_signage_point(uint8(i), blockchain, peak, peak.sub_slot_iters, sp)

    # Test adding future signage point (bad)
    for i in range(
        1, custom_block_tools.constants.NUM_SPS_SUB_SLOT - custom_block_tools.constants.NUM_SP_INTERVALS_EXTRA
    ):
        sp = get_signage_point(
            custom_block_tools.constants,
            blockchain,
            peak,
            uint128(
                peak.ip_sub_slot_total_iters(custom_block_tools.constants)
                + len(finished_sub_slots) * peak.sub_slot_iters
            ),
            uint8(i),
            finished_sub_slots[: len(finished_sub_slots)],
            peak.sub_slot_iters,
        )
        assert not store.new_signage_point(uint8(i), blockchain, peak, peak.sub_slot_iters, sp)

    # Test adding past signage point
    sp = SignagePoint(
        blocks[1].reward_chain_block.challenge_chain_sp_vdf,
        blocks[1].challenge_chain_sp_proof,
        blocks[1].reward_chain_block.reward_chain_sp_vdf,
        blocks[1].reward_chain_sp_proof,
    )
    assert not store.new_signage_point(
        blocks[1].reward_chain_block.signage_point_index,
        blockchain,
        peak,
        uint64(blockchain.block_record(blocks[1].header_hash).sp_sub_slot_total_iters(custom_block_tools.constants)),
        sp,
    )

    # Get signage point by index
    assert (
        store.get_signage_point_by_index(
            finished_sub_slots[0].challenge_chain.get_hash(),
            uint8(4),
            finished_sub_slots[0].reward_chain.get_hash(),
        )
        is not None
    )

    assert (
        store.get_signage_point_by_index(finished_sub_slots[0].challenge_chain.get_hash(), uint8(4), std_hash(b"1"))
        is None
    )

    # Get signage point by hash
    assert saved_sp_hash is not None
    assert store.get_signage_point(saved_sp_hash) is not None
    assert store.get_signage_point(std_hash(b"2")) is None

    # Test adding signage points before genesis
    store.initialize_genesis_sub_slot()
    assert len(store.finished_sub_slots) == 1
    for i in range(
        1, custom_block_tools.constants.NUM_SPS_SUB_SLOT - custom_block_tools.constants.NUM_SP_INTERVALS_EXTRA
    ):
        sp = get_signage_point(
            custom_block_tools.constants,
            BlockCache({}, {}),
            None,
            uint128(0),
            uint8(i),
            [],
            peak.sub_slot_iters,
        )
        assert store.new_signage_point(uint8(i), blockchain, None, peak.sub_slot_iters, sp)

    blocks_3 = custom_block_tools.get_consecutive_blocks(
        1,
        skip_slots=2,
        normalized_to_identity_cc_eos=normalized_to_identity,
        normalized_to_identity_icc_eos=normalized_to_identity,
        normalized_to_identity_cc_ip=normalized_to_identity,
        normalized_to_identity_cc_sp=normalized_to_identity,
    )
    peak = blockchain.get_peak()
    assert peak is not None
    for slot in blocks_3[-1].finished_sub_slots:
        next_sub_slot_iters, next_difficulty = get_next_sub_slot_iters_and_difficulty(
            blockchain.constants, True, peak, blockchain
        )

        store.new_finished_sub_slot(slot, blockchain, None, next_sub_slot_iters, next_difficulty, None)
    assert len(store.finished_sub_slots) == 3
    finished_sub_slots = blocks_3[-1].finished_sub_slots

    for slot_offset in range(1, len(finished_sub_slots) + 1):
        for i in range(
            1,
            custom_block_tools.constants.NUM_SPS_SUB_SLOT - custom_block_tools.constants.NUM_SP_INTERVALS_EXTRA,
        ):
            sp = get_signage_point(
                custom_block_tools.constants,
                BlockCache({}, {}),
                None,
                uint128(slot_offset * peak.sub_slot_iters),
                uint8(i),
                finished_sub_slots[:slot_offset],
                peak.sub_slot_iters,
            )
            assert store.new_signage_point(uint8(i), blockchain, None, peak.sub_slot_iters, sp)

    # Test adding signage points after genesis
    blocks_4 = custom_block_tools.get_consecutive_blocks(
        1,
        normalized_to_identity_cc_eos=normalized_to_identity,
        normalized_to_identity_icc_eos=normalized_to_identity,
        normalized_to_identity_cc_ip=normalized_to_identity,
        normalized_to_identity_cc_sp=normalized_to_identity,
    )
    blocks_5 = custom_block_tools.get_consecutive_blocks(
        1,
        block_list_input=blocks_4,
        skip_slots=1,
        normalized_to_identity_cc_eos=normalized_to_identity,
        normalized_to_identity_icc_eos=normalized_to_identity,
        normalized_to_identity_cc_ip=normalized_to_identity,
        normalized_to_identity_cc_sp=normalized_to_identity,
    )

    # If this is not the case, fix test to find a block that is
    assert (
        blocks_4[-1].reward_chain_block.signage_point_index
        < custom_block_tools.constants.NUM_SPS_SUB_SLOT - custom_block_tools.constants.NUM_SP_INTERVALS_EXTRA
    )
    await _validate_and_add_block(blockchain, blocks_4[-1], expected_result=AddBlockResult.ADDED_AS_ORPHAN)

    sb = blockchain.block_record(blocks_4[-1].header_hash)
    next_sub_slot_iters, next_difficulty = get_next_sub_slot_iters_and_difficulty(
        blockchain.constants, False, sb, blockchain
    )

    store.new_peak(sb, blocks_4[-1], None, None, None, blockchain, next_sub_slot_iters, next_difficulty)
    for i in range(
        sb.signage_point_index + custom_block_tools.constants.NUM_SP_INTERVALS_EXTRA,
        custom_block_tools.constants.NUM_SPS_SUB_SLOT,
    ):
        if is_overflow_block(custom_block_tools.constants, uint8(i)):
            finished_sub_slots = blocks_5[-1].finished_sub_slots
        else:
            finished_sub_slots = []

        sp = get_signage_point(
            custom_block_tools.constants,
            blockchain,
            sb,
            uint128(0),
            uint8(i),
            finished_sub_slots,
            peak.sub_slot_iters,
        )
        assert store.new_signage_point(uint8(i), empty_blockchain, sb, peak.sub_slot_iters, sp)

    # Test future EOS cache
    store.initialize_genesis_sub_slot()
    blocks = custom_block_tools.get_consecutive_blocks(
        1,
        normalized_to_identity_cc_eos=normalized_to_identity,
        normalized_to_identity_icc_eos=normalized_to_identity,
        normalized_to_identity_cc_ip=normalized_to_identity,
        normalized_to_identity_cc_sp=normalized_to_identity,
    )
    await _validate_and_add_block_no_error(blockchain, blocks[-1])
    while True:
        blocks = custom_block_tools.get_consecutive_blocks(
            1,
            block_list_input=blocks,
            normalized_to_identity_cc_eos=normalized_to_identity,
            normalized_to_identity_icc_eos=normalized_to_identity,
            normalized_to_identity_cc_ip=normalized_to_identity,
            normalized_to_identity_cc_sp=normalized_to_identity,
        )
        await _validate_and_add_block_no_error(blockchain, blocks[-1])
        sb = blockchain.block_record(blocks[-1].header_hash)
        if sb.first_in_sub_slot:
            break
    assert len(blocks) >= 2
    dependant_sub_slots = blocks[-1].finished_sub_slots
    peak = blockchain.get_peak()
    assert peak is not None
    peak_full_block = await blockchain.get_full_peak()
    for block in blocks[:-2]:
        sb = blockchain.block_record(block.header_hash)
        result = await blockchain.get_sp_and_ip_sub_slots(block.header_hash)
        assert result is not None
        sp_sub_slot, ip_sub_slot = result
        peak = sb
        peak_full_block = block
        next_sub_slot_iters, next_difficulty = get_next_sub_slot_iters_and_difficulty(
            blockchain.constants, False, peak, blockchain
        )

        res = store.new_peak(
            sb, block, sp_sub_slot, ip_sub_slot, None, blockchain, next_sub_slot_iters, next_difficulty
        )
        assert res.added_eos is None

    next_sub_slot_iters, next_difficulty = get_next_sub_slot_iters_and_difficulty(
        blockchain.constants, True, peak, blockchain
    )

    assert (
        store.new_finished_sub_slot(
            dependant_sub_slots[0], blockchain, peak, next_sub_slot_iters, next_difficulty, peak_full_block
        )
        is None
    )
    block = blocks[-2]
    sb = blockchain.block_record(block.header_hash)
    result = await blockchain.get_sp_and_ip_sub_slots(block.header_hash)
    assert result is not None
    sp_sub_slot, ip_sub_slot = result
    next_sub_slot_iters, next_difficulty = get_next_sub_slot_iters_and_difficulty(
        blockchain.constants, False, sb, blockchain
    )

    res = store.new_peak(sb, block, sp_sub_slot, ip_sub_slot, None, blockchain, next_sub_slot_iters, next_difficulty)
    assert res.added_eos == dependant_sub_slots[0]
    assert res.new_signage_points == []
    assert res.new_infusion_points == []

    # Test future IP cache
    store.initialize_genesis_sub_slot()
    blocks = custom_block_tools.get_consecutive_blocks(
        60,
        normalized_to_identity_cc_ip=normalized_to_identity,
        normalized_to_identity_cc_sp=normalized_to_identity,
        normalized_to_identity_cc_eos=normalized_to_identity,
        normalized_to_identity_icc_eos=normalized_to_identity,
    )

    for block in blocks[:5]:
        await _validate_and_add_block_no_error(blockchain, block)
        sb = blockchain.block_record(block.header_hash)
        result = await blockchain.get_sp_and_ip_sub_slots(block.header_hash)
        assert result is not None
        sp_sub_slot, ip_sub_slot = result
        next_sub_slot_iters, next_difficulty = get_next_sub_slot_iters_and_difficulty(
            blockchain.constants, False, sb, blockchain
        )

        res = store.new_peak(
            sb, block, sp_sub_slot, ip_sub_slot, None, blockchain, next_sub_slot_iters, next_difficulty
        )
        assert res.added_eos is None

    case_0, case_1 = False, False
    for i in range(5, len(blocks) - 1):
        prev_block = blocks[i]
        block = blocks[i + 1]
        new_ip = NewInfusionPointVDF(
            block.reward_chain_block.get_unfinished().get_hash(),
            block.reward_chain_block.challenge_chain_ip_vdf,
            block.challenge_chain_ip_proof,
            block.reward_chain_block.reward_chain_ip_vdf,
            block.reward_chain_ip_proof,
            block.reward_chain_block.infused_challenge_chain_ip_vdf,
            block.infused_challenge_chain_ip_proof,
        )
        store.add_to_future_ip(new_ip)

        await _validate_and_add_block_no_error(blockchain, prev_block)
        result = await blockchain.get_sp_and_ip_sub_slots(prev_block.header_hash)
        assert result is not None
        sp_sub_slot, ip_sub_slot = result
        sb = blockchain.block_record(prev_block.header_hash)
        next_sub_slot_iters, next_difficulty = get_next_sub_slot_iters_and_difficulty(
            blockchain.constants, False, sb, blockchain
        )

        res = store.new_peak(
            sb, prev_block, sp_sub_slot, ip_sub_slot, None, blockchain, next_sub_slot_iters, next_difficulty
        )
        if len(block.finished_sub_slots) == 0:
            case_0 = True
            assert res.new_infusion_points == [new_ip]
        else:
            case_1 = True
            assert res.new_infusion_points == []
            found_ips: List[timelord_protocol.NewInfusionPointVDF] = []
            peak = blockchain.get_peak()

            for ss in block.finished_sub_slots:
                next_sub_slot_iters, next_difficulty = get_next_sub_slot_iters_and_difficulty(
                    blockchain.constants, True, peak, blockchain
                )

                ipvdf = store.new_finished_sub_slot(
                    ss, blockchain, sb, next_sub_slot_iters, next_difficulty, prev_block
                )
                assert ipvdf is not None
                found_ips += ipvdf
            assert found_ips == [new_ip]

    # If flaky, increase the number of blocks created
    assert case_0 and case_1

    # Try to get two blocks in the same slot, such that we have
    # SP, B2 SP .... SP B1
    #     i2 .........  i1
    # Then do a reorg up to B2, removing all signage points after B2, but not before
    log.warning(f"Adding blocks up to {blocks[-1]}")
    for block in blocks:
        await _validate_and_add_block_no_error(blockchain, block)

    log.warning("Starting loop")
    while True:
        log.warning("Looping")
        blocks = custom_block_tools.get_consecutive_blocks(1, block_list_input=blocks, skip_slots=1)
        await _validate_and_add_block_no_error(blockchain, blocks[-1])
        peak = blockchain.get_peak()
        assert peak is not None
        result = await blockchain.get_sp_and_ip_sub_slots(peak.header_hash)
        assert result is not None
        sp_sub_slot, ip_sub_slot = result
        next_sub_slot_iters, next_difficulty = get_next_sub_slot_iters_and_difficulty(
            blockchain.constants, False, peak, blockchain
        )

        store.new_peak(
            peak, blocks[-1], sp_sub_slot, ip_sub_slot, None, blockchain, next_sub_slot_iters, next_difficulty
        )

        blocks = custom_block_tools.get_consecutive_blocks(2, block_list_input=blocks, guarantee_transaction_block=True)

        i3 = blocks[-3].reward_chain_block.signage_point_index
        i2 = blocks[-2].reward_chain_block.signage_point_index
        i1 = blocks[-1].reward_chain_block.signage_point_index
        if (
            len(blocks[-2].finished_sub_slots) == len(blocks[-1].finished_sub_slots) == 0
            and not is_overflow_block(custom_block_tools.constants, signage_point_index=i2)
            and not is_overflow_block(custom_block_tools.constants, signage_point_index=i1)
            and i2 > i3 + 3
            and i1 > (i2 + 3)
        ):
            # We hit all the conditions that we want
            all_sps: List[Optional[SignagePoint]] = [None] * custom_block_tools.constants.NUM_SPS_SUB_SLOT

            def assert_sp_none(sp_index: int, is_none: bool) -> None:
                sp_to_check: Optional[SignagePoint] = all_sps[sp_index]
                assert sp_to_check is not None
                assert sp_to_check.cc_vdf is not None
                fetched = store.get_signage_point(sp_to_check.cc_vdf.output.get_hash())
                assert (fetched is None) == is_none
                if fetched is not None:
                    assert fetched == sp_to_check

            for i in range(i3 + 1, custom_block_tools.constants.NUM_SPS_SUB_SLOT - 3):
                finished_sub_slots = []
                sp = get_signage_point(
                    custom_block_tools.constants,
                    blockchain,
                    peak,
                    uint128(peak.ip_sub_slot_total_iters(custom_block_tools.constants)),
                    uint8(i),
                    finished_sub_slots,
                    peak.sub_slot_iters,
                )
                all_sps[i] = sp
                assert store.new_signage_point(uint8(i), blockchain, peak, peak.sub_slot_iters, sp)

            # Adding a new peak clears all SPs after that peak
            await _validate_and_add_block_no_error(blockchain, blocks[-2])
            peak = blockchain.get_peak()
            assert peak is not None
            result = await blockchain.get_sp_and_ip_sub_slots(peak.header_hash)
            assert result is not None
            sp_sub_slot, ip_sub_slot = result
            next_sub_slot_iters, next_difficulty = get_next_sub_slot_iters_and_difficulty(
                blockchain.constants, False, peak, blockchain
            )

            store.new_peak(
                peak, blocks[-2], sp_sub_slot, ip_sub_slot, None, blockchain, next_sub_slot_iters, next_difficulty
            )

            assert_sp_none(i2, False)
            assert_sp_none(i2 + 1, False)
            assert_sp_none(i1, True)
            assert_sp_none(i1 + 1, True)
            # We load into `all_sps` only up to `NUM_SPS_SUB_SLOT - 3`, so make sure we're not out of range
            if i1 + 4 < custom_block_tools.constants.NUM_SPS_SUB_SLOT - 3:
                assert_sp_none(i1 + 4, True)

            for i in range(i2, custom_block_tools.constants.NUM_SPS_SUB_SLOT):
                if is_overflow_block(custom_block_tools.constants, uint8(i)):
                    blocks_alt = custom_block_tools.get_consecutive_blocks(
                        1, block_list_input=blocks[:-1], skip_slots=1
                    )
                    finished_sub_slots = blocks_alt[-1].finished_sub_slots
                else:
                    finished_sub_slots = []
                sp = get_signage_point(
                    custom_block_tools.constants,
                    blockchain,
                    peak,
                    uint128(peak.ip_sub_slot_total_iters(custom_block_tools.constants)),
                    uint8(i),
                    finished_sub_slots,
                    peak.sub_slot_iters,
                )
                all_sps[i] = sp
                assert store.new_signage_point(uint8(i), blockchain, peak, peak.sub_slot_iters, sp)

            assert_sp_none(i2, False)
            assert_sp_none(i2 + 1, False)
            assert_sp_none(i1, False)
            assert_sp_none(i1 + 1, False)
            assert_sp_none(i1 + 4, False)

            await _validate_and_add_block_no_error(blockchain, blocks[-1])
            peak = blockchain.get_peak()
            assert peak is not None
            result = await blockchain.get_sp_and_ip_sub_slots(peak.header_hash)
            assert result is not None
            sp_sub_slot, ip_sub_slot = result
            next_sub_slot_iters, next_difficulty = get_next_sub_slot_iters_and_difficulty(
                blockchain.constants, False, peak, blockchain
            )

            # Do a reorg, which should remove everything after B2
            store.new_peak(
                peak,
                blocks[-1],
                sp_sub_slot,
                ip_sub_slot,
                (await blockchain.get_block_records_at([blocks[-2].height]))[0],
                blockchain,
                next_sub_slot_iters,
                next_difficulty,
            )

            assert_sp_none(i2, False)
            assert_sp_none(i2 + 1, False)
            assert_sp_none(i1, True)
            assert_sp_none(i1 + 1, True)
            assert_sp_none(i1 + 4, True)
            break
        else:
            for block in blocks[-2:]:
                await _validate_and_add_block_no_error(blockchain, block)


@pytest.mark.limit_consensus_modes(reason="save time")
@pytest.mark.anyio
async def test_long_chain_slots(
    empty_blockchain_with_original_constants: Blockchain,
    default_1000_blocks: List[FullBlock],
) -> None:
    blockchain = empty_blockchain_with_original_constants
    store = FullNodeStore(blockchain.constants)
    peak = None
    peak_full_block = None
    for block in default_1000_blocks:
        next_sub_slot_iters, next_difficulty = get_next_sub_slot_iters_and_difficulty(
            blockchain.constants, True, peak, blockchain
        )

        for sub_slot in block.finished_sub_slots:
            assert (
                store.new_finished_sub_slot(
                    sub_slot, blockchain, peak, next_sub_slot_iters, next_difficulty, peak_full_block
                )
                is not None
            )
        await _validate_and_add_block(blockchain, block)
        peak = blockchain.get_peak()
        assert peak is not None
        peak_full_block = await blockchain.get_full_peak()
        assert peak_full_block is not None
        result = await blockchain.get_sp_and_ip_sub_slots(peak.header_hash)
        assert result is not None
        sp_sub_slot, ip_sub_slot = result
        store.new_peak(
            peak, peak_full_block, sp_sub_slot, ip_sub_slot, None, blockchain, next_sub_slot_iters, next_difficulty
        )
