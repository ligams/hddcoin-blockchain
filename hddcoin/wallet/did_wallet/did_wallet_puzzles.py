from __future__ import annotations

from typing import Dict, Iterator, List, Optional, Tuple, Union

from chia_rs import G1Element

from hddcoin.types.blockchain_format.coin import Coin
from hddcoin.types.blockchain_format.program import Program
from hddcoin.types.blockchain_format.sized_bytes import bytes32
from hddcoin.types.coin_spend import CoinSpend, make_spend
from hddcoin.types.condition_opcodes import ConditionOpcode
from hddcoin.util.ints import uint64
from hddcoin.wallet.puzzles.load_clvm import load_clvm_maybe_recompile
from hddcoin.wallet.singleton import (
    SINGLETON_LAUNCHER_PUZZLE_HASH,
    SINGLETON_TOP_LAYER_MOD,
    SINGLETON_TOP_LAYER_MOD_HASH,
    is_singleton,
)
from hddcoin.wallet.util.curry_and_treehash import calculate_hash_of_quoted_mod_hash, curry_and_treehash

DID_INNERPUZ_MOD = load_clvm_maybe_recompile(
    "did_innerpuz.clsp", package_or_requirement="hddcoin.wallet.did_wallet.puzzles"
)
DID_INNERPUZ_MOD_HASH = DID_INNERPUZ_MOD.get_tree_hash()
INTERMEDIATE_LAUNCHER_MOD = load_clvm_maybe_recompile(
    "nft_intermediate_launcher.clsp", package_or_requirement="hddcoin.wallet.nft_wallet.puzzles"
)


def create_innerpuz(
    p2_puzzle_or_hash: Union[Program, bytes32],
    recovery_list: List[bytes32],
    num_of_backup_ids_needed: uint64,
    launcher_id: bytes32,
    metadata: Program = Program.to([]),
    recovery_list_hash: Optional[bytes32] = None,
) -> Program:
    """
    Create DID inner puzzle
    :param p2_puzzle_or_hash: Standard P2 puzzle or hash
    :param recovery_list: A list of DIDs used for the recovery
    :param num_of_backup_ids_needed: Need how many DIDs for the recovery
    :param launcher_id: ID of the launch coin
    :param metadata: DID customized metadata
    :param recovery_list_hash: Recovery list hash
    :return: DID inner puzzle
    Note: Receiving a standard P2 puzzle hash wouldn't calculate a valid puzzle, but
    that can be useful if calling `.get_tree_hash_precalc()` on it.
    """
    backup_ids_hash = Program(Program.to(recovery_list)).get_tree_hash()
    if recovery_list_hash is not None:
        backup_ids_hash = recovery_list_hash
    singleton_struct = Program.to((SINGLETON_TOP_LAYER_MOD_HASH, (launcher_id, SINGLETON_LAUNCHER_PUZZLE_HASH)))
    return DID_INNERPUZ_MOD.curry(
        p2_puzzle_or_hash, backup_ids_hash, num_of_backup_ids_needed, singleton_struct, metadata
    )


def get_inner_puzhash_by_p2(
    p2_puzhash: bytes32,
    recovery_list: List[bytes32],
    num_of_backup_ids_needed: uint64,
    launcher_id: bytes32,
    metadata: Program = Program.to([]),
) -> bytes32:
    """
    Calculate DID inner puzzle hash based on a P2 puzzle hash
    :param p2_puzhash: P2 puzzle hash
    :param recovery_list: A list of DIDs used for the recovery
    :param num_of_backup_ids_needed: Need how many DIDs for the recovery
    :param launcher_id: ID of the launch coin
    :param metadata: DID customized metadata
    :return: DID inner puzzle hash
    """

    backup_ids_hash = Program(Program.to(recovery_list)).get_tree_hash()
    singleton_struct = Program.to((SINGLETON_TOP_LAYER_MOD_HASH, (launcher_id, SINGLETON_LAUNCHER_PUZZLE_HASH)))

    quoted_mod_hash = calculate_hash_of_quoted_mod_hash(DID_INNERPUZ_MOD_HASH)

    return curry_and_treehash(
        quoted_mod_hash,
        p2_puzhash,
        Program.to(backup_ids_hash).get_tree_hash(),
        Program.to(num_of_backup_ids_needed).get_tree_hash(),
        Program.to(singleton_struct).get_tree_hash(),
        metadata.get_tree_hash(),
    )


def is_did_innerpuz(inner_f: Program) -> bool:
    """
    Check if a puzzle is a DID inner mode
    :param inner_f: puzzle
    :return: Boolean
    """
    return inner_f == DID_INNERPUZ_MOD


def uncurry_innerpuz(puzzle: Program) -> Optional[Tuple[Program, Program, Program, Program, Program]]:
    """
    Uncurry a DID inner puzzle
    :param puzzle: DID puzzle
    :return: Curried parameters
    """
    r = puzzle.uncurry()
    if r is None:
        return r
    inner_f, args = r
    if not is_did_innerpuz(inner_f):
        return None

    p2_puzzle, id_list, num_of_backup_ids_needed, singleton_struct, metadata = list(args.as_iter())
    return p2_puzzle, id_list, num_of_backup_ids_needed, singleton_struct, metadata


def create_recovery_message_puzzle(recovering_coin_id: bytes32, newpuz: bytes32, pubkey: G1Element) -> Program:
    """
    Create attestment message puzzle
    :param recovering_coin_id: ID of the DID coin needs to recover
    :param newpuz: New wallet puzzle hash
    :param pubkey: New wallet pubkey
    :return: Message puzzle
    """
    return Program.to(
        (
            1,
            [
                [ConditionOpcode.CREATE_COIN_ANNOUNCEMENT, recovering_coin_id],
                [ConditionOpcode.AGG_SIG_UNSAFE, bytes(pubkey), newpuz],
            ],
        )
    )


def create_spend_for_message(
    parent_of_message: bytes32, recovering_coin: bytes32, newpuz: bytes32, pubkey: G1Element
) -> CoinSpend:
    """
    Create a CoinSpend for a atestment
    :param parent_of_message: Parent coin ID
    :param recovering_coin: ID of the DID coin needs to recover
    :param newpuz: New wallet puzzle hash
    :param pubkey: New wallet pubkey
    :return: CoinSpend
    """
    puzzle = create_recovery_message_puzzle(recovering_coin, newpuz, pubkey)
    coin = Coin(parent_of_message, puzzle.get_tree_hash(), uint64(0))
    solution = Program.to([])
    return make_spend(coin, puzzle, solution)


def match_did_puzzle(mod: Program, curried_args: Program) -> Optional[Iterator[Program]]:
    """
        Given a puzzle test if it's a DID, if it is, return the curried arguments
    :param puzzle: Puzzle
    :return: Curried parameters
    """
    try:
        if mod == SINGLETON_TOP_LAYER_MOD:
            mod, curried_args = curried_args.rest().first().uncurry()
            if mod == DID_INNERPUZ_MOD:
                return curried_args.as_iter()
    except Exception:
        import traceback

        print(f"exception: {traceback.format_exc()}")
    return None


def check_is_did_puzzle(puzzle: Program) -> bool:
    """
    Check if a puzzle is a DID puzzle
    :param puzzle: Puzzle
    :return: Boolean
    """
    r = puzzle.uncurry()
    if r is None:
        return False
    inner_f, args = r
    return is_singleton(inner_f)


def metadata_to_program(metadata: Dict) -> Program:
    """
    Convert the metadata dict to a Chialisp program
    :param metadata: User defined metadata
    :return: Chialisp program
    """
    kv_list = []
    for key, value in metadata.items():
        kv_list.append((key, value))
    return Program.to(kv_list)


def did_program_to_metadata(program: Program) -> Dict:
    """
    Convert a program to a metadata dict
    :param program: Chialisp program contains the metadata
    :return: Metadata dict
    """
    metadata = {}
    for key, val in program.as_python():
        metadata[str(key, "utf-8")] = str(val, "utf-8")
    return metadata
