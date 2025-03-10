#!/usr/bin/env python

"""
run_block: Convert an encoded FullBlock from the HDDCoin blockchain into a list of transactions

As input, takes a file containing a [FullBlock](../hddcoin/types/full_block.py) in json format

```
curl --insecure --cert $config_root/config/ssl/full_node/private_full_node.crt \
     --key $config_root/config/ssl/full_node/private_full_node.key \
     -d '{ "header_hash": "'$hash'" }' -H "Content-Type: application/json" \
     -X POST https://localhost:$port/get_block

$ca_root is the directory containing your current HDDCoin config files
$hash is the header_hash of the [BlockRecord](../hddcoin/consensus/block_record.py)
$port is the Full Node RPC API port
```

The `transactions_generator` and `transactions_generator_ref_list` fields of a `FullBlock`
contain the information necessary to produce transaction record details.

`transactions_generator` is CLVM bytecode
`transactions_generator_ref_list` is a list of block heights as `uint32`

When this CLVM code is run in the correct environment, it produces information that can
then be verified by the consensus rules, or used to view some aspects of transaction history.

The information for each spend is an "NPC" (Name, Puzzle, Condition):
        "coin_name": a unique 32 byte identifier
        "conditions": a list of condition expressions, as in [condition_opcodes.py](../hddcoin/types/condition_opcodes.py)
        "puzzle_hash": the sha256 of the CLVM bytecode that controls spending this coin

Condition Opcodes, such as AGG_SIG_ME, or CREATE_COIN are created by running the "puzzle", i.e. the CLVM bytecode
associated with the coin being spent. Condition Opcodes are verified by every client on the network for every spend,
and in this way they control whether a spend is valid or not.

"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Tuple

import click

from hddcoin.consensus.constants import ConsensusConstants
from hddcoin.consensus.default_constants import DEFAULT_CONSTANTS
from hddcoin.types.blockchain_format.coin import Coin
from hddcoin.types.blockchain_format.serialized_program import SerializedProgram
from hddcoin.types.blockchain_format.sized_bytes import bytes32
from hddcoin.types.condition_opcodes import ConditionOpcode
from hddcoin.types.condition_with_args import ConditionWithArgs
from hddcoin.types.generator_types import BlockGenerator
from hddcoin.util.config import load_config
from hddcoin.util.default_root import DEFAULT_ROOT_PATH
from hddcoin.util.ints import uint32, uint64
from hddcoin.wallet.cat_wallet.cat_utils import match_cat_puzzle
from hddcoin.wallet.puzzles.load_clvm import load_serialized_clvm_maybe_recompile
from hddcoin.wallet.uncurried_puzzle import uncurry_puzzle

DESERIALIZE_MOD = load_serialized_clvm_maybe_recompile(
    "chialisp_deserialisation.clsp", package_or_requirement="hddcoin.wallet.puzzles"
)


@dataclass
class NPC:
    coin_name: bytes32
    puzzle_hash: bytes32
    conditions: List[Tuple[ConditionOpcode, List[ConditionWithArgs]]]


@dataclass
class CAT:
    asset_id: str
    memo: str
    npc: NPC

    def cat_to_dict(self):
        return {"asset_id": self.asset_id, "memo": self.memo, "npc": npc_to_dict(self.npc)}


def condition_with_args_to_dict(condition_with_args: ConditionWithArgs):
    return {
        "condition_opcode": condition_with_args.opcode.name,
        "arguments": [arg.hex() for arg in condition_with_args.vars],
    }


def condition_list_to_dict(condition_list: Tuple[ConditionOpcode, List[ConditionWithArgs]]):
    assert all([condition_list[0] == cwa.opcode for cwa in condition_list[1]])
    return [condition_with_args_to_dict(cwa) for cwa in condition_list[1]]


def npc_to_dict(npc: NPC):
    return {
        "coin_name": npc.coin_name.hex(),
        "conditions": [{"condition_type": c[0].name, "conditions": condition_list_to_dict(c)} for c in npc.conditions],
        "puzzle_hash": npc.puzzle_hash.hex(),
    }


def run_generator(block_generator: BlockGenerator, constants: ConsensusConstants, max_cost: int) -> List[CAT]:
    block_args = [bytes(a) for a in block_generator.generator_refs]
    cost, block_result = block_generator.program.run_with_cost(max_cost, [DESERIALIZE_MOD, block_args])

    coin_spends = block_result.first()

    cat_list: List[CAT] = []
    for spend in coin_spends.as_iter():
        parent, puzzle, amount, solution = spend.as_iter()
        args = match_cat_puzzle(uncurry_puzzle(puzzle))

        if args is None:
            continue

        _, asset_id, _ = args
        memo = ""

        puzzle_result = puzzle.run(solution)

        conds: Dict[ConditionOpcode, List[ConditionWithArgs]] = {}

        for condition in puzzle_result.as_python():
            op = ConditionOpcode(condition[0])

            if op not in conds:
                conds[op] = []

            if condition[0] != ConditionOpcode.CREATE_COIN or len(condition) < 4:
                conds[op].append(ConditionWithArgs(op, [i for i in condition[1:3]]))
                continue

            # If only 3 elements (opcode + 2 args), there is no memo, this is ph, amount
            if type(condition[3]) is not list:
                # If it's not a list, it's not the correct format
                conds[op].append(ConditionWithArgs(op, [i for i in condition[1:3]]))
                continue

            conds[op].append(ConditionWithArgs(op, [i for i in condition[1:3]] + [condition[3][0]]))

            # special retirement address
            if condition[3][0].hex() != "0000000000000000000000000000000000000000000000000000000000000000":
                continue

            if len(condition[3]) >= 2:
                try:
                    memo = condition[3][1].decode("utf-8", errors="strict")
                except UnicodeError:
                    pass  # ignore this error which should leave memo as empty string

            # technically there could be more such create_coin ops in the list but our wallet does not
            # so leaving it for the future
            break

        puzzle_hash = puzzle.get_tree_hash()
        coin = Coin(bytes32(parent.as_atom()), puzzle_hash, amount.as_int())
        cat_list.append(
            CAT(
                asset_id=bytes(asset_id).hex()[2:],
                memo=memo,
                npc=NPC(coin.name(), puzzle_hash, [(op, cond) for op, cond in conds.items()]),
            )
        )

    return cat_list


def ref_list_to_args(ref_list: List[uint32], root_path: Path) -> List[SerializedProgram]:
    args = []
    for height in ref_list:
        with open(root_path / f"{height}.json", "rb") as f:
            program_str = json.load(f)["block"]["transactions_generator"]
            args.append(SerializedProgram.fromhex(program_str))
    return args


def run_generator_with_args(
    generator_program_hex: str,
    generator_args: List[SerializedProgram],
    constants: ConsensusConstants,
    cost: uint64,
) -> List[CAT]:
    if not generator_program_hex:
        return []
    generator_program = SerializedProgram.fromhex(generator_program_hex)
    block_generator = BlockGenerator(generator_program, generator_args, [])
    return run_generator(block_generator, constants, min(constants.MAX_BLOCK_COST_CLVM, cost))


@click.command()
@click.argument("filename", type=click.Path(exists=True), default="testnet10.396963.json")
def cmd_run_json_block_file(filename):
    """`file` is a file containing a FullBlock in JSON format"""
    return run_json_block_file(Path(filename))


def run_json_block(full_block, parent: Path, constants: ConsensusConstants) -> List[CAT]:
    ref_list = full_block["block"]["transactions_generator_ref_list"]
    tx_info: dict = full_block["block"]["transactions_info"]
    generator_program_hex: str = full_block["block"]["transactions_generator"]
    cat_list: List[CAT] = []
    if tx_info and generator_program_hex:
        cost = tx_info["cost"]
        args = ref_list_to_args(ref_list, parent)
        cat_list = run_generator_with_args(generator_program_hex, args, constants, cost)

    return cat_list


def run_json_block_file(filename: Path):
    full_block = json.load(filename.open("rb"))
    # pull in current constants from config.yaml
    _, constants = get_config_and_constants()

    cat_list = run_json_block(full_block, filename.parent.absolute(), constants)

    cat_list_json = json.dumps([cat.cat_to_dict() for cat in cat_list])
    print(cat_list_json)


def get_config_and_constants():
    config = load_config(DEFAULT_ROOT_PATH, "config.yaml")
    network = config["selected_network"]
    overrides = config["network_overrides"]["constants"][network]
    updated_constants = DEFAULT_CONSTANTS.replace_str_to_bytes(**overrides)
    return config, updated_constants


if __name__ == "__main__":
    cmd_run_json_block_file()  # pylint: disable=no-value-for-parameter
