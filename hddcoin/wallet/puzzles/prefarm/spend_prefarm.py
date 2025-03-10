from __future__ import annotations

import asyncio

from chia_rs import G2Element
from clvm_tools import binutils

from hddcoin.consensus.block_rewards import calculate_base_farmer_reward, calculate_pool_reward
from hddcoin.rpc.full_node_rpc_client import FullNodeRpcClient
from hddcoin.types.blockchain_format.program import Program
from hddcoin.types.blockchain_format.serialized_program import SerializedProgram
from hddcoin.types.coin_spend import CoinSpend
from hddcoin.types.condition_opcodes import ConditionOpcode
from hddcoin.types.spend_bundle import SpendBundle
from hddcoin.util.bech32m import decode_puzzle_hash
from hddcoin.util.condition_tools import parse_sexp_to_conditions
from hddcoin.util.config import load_config
from hddcoin.util.default_root import DEFAULT_ROOT_PATH
from hddcoin.util.ints import uint16, uint32


def print_conditions(spend_bundle: SpendBundle) -> None:
    print("\nConditions:")
    for coin_spend in spend_bundle.coin_spends:
        result = Program.from_bytes(bytes(coin_spend.puzzle_reveal)).run(Program.from_bytes(bytes(coin_spend.solution)))
        for cvp in parse_sexp_to_conditions(result):
            print(f"{ConditionOpcode(cvp.opcode).name}: {[var.hex() for var in cvp.vars]}")
    print("")


async def main() -> None:
    rpc_port: uint16 = uint16(8555)
    self_hostname = "localhost"
    path = DEFAULT_ROOT_PATH
    config = load_config(path, "config.yaml")
    client = await FullNodeRpcClient.create(self_hostname, rpc_port, path, config)
    try:
        block_record = await client.get_block_record_by_height(1)
        assert block_record is not None
        assert block_record.reward_claims_incorporated is not None
        farmer_prefarm = block_record.reward_claims_incorporated[1]
        pool_prefarm = block_record.reward_claims_incorporated[0]

        pool_amounts = int(calculate_pool_reward(uint32(0)) / 2)
        farmer_amounts = int(calculate_base_farmer_reward(uint32(0)) / 2)
        print(farmer_prefarm.amount, farmer_amounts)
        assert farmer_amounts == farmer_prefarm.amount // 2
        assert pool_amounts == pool_prefarm.amount // 2
        address1 = "xch1rdatypul5c642jkeh4yp933zu3hw8vv8tfup8ta6zfampnyhjnusxdgns6"  # Key 1
        address2 = "xch1duvy5ur5eyj7lp5geetfg84cj2d7xgpxt7pya3lr2y6ke3696w9qvda66e"  # Key 2

        ph1 = decode_puzzle_hash(address1)
        ph2 = decode_puzzle_hash(address2)

        p_farmer_2 = SerializedProgram.to(
            binutils.assemble(
                f"(q . ((51 0x{ph1.hex()} {farmer_amounts}) " f"(51 0x{ph2.hex()} {farmer_amounts})))"
            )  # type: ignore[no-untyped-call]
        )
        p_pool_2 = SerializedProgram.to(
            binutils.assemble(
                f"(q . ((51 0x{ph1.hex()} {pool_amounts}) " f"(51 0x{ph2.hex()} {pool_amounts})))"
            )  # type: ignore[no-untyped-call]
        )

        print(f"Ph1: {ph1.hex()}")
        print(f"Ph2: {ph2.hex()}")
        assert ph1.hex() == "1b7ab2079fa635554ad9bd4812c622e46ee3b1875a7813afba127bb0cc9794f9"
        assert ph2.hex() == "6f184a7074c925ef8688ce56941eb8929be320265f824ec7e351356cc745d38a"

        p_solution = SerializedProgram.to(binutils.assemble("()"))  # type: ignore[no-untyped-call]

        sb_farmer = SpendBundle([CoinSpend(farmer_prefarm, p_farmer_2, p_solution)], G2Element())
        sb_pool = SpendBundle([CoinSpend(pool_prefarm, p_pool_2, p_solution)], G2Element())

        print("\n\n\nConditions")
        print_conditions(sb_pool)
        print("\n\n\n")
        print("Farmer to spend")
        print(sb_pool)
        print(sb_farmer)
        print("\n\n\n")
        # res = await client.push_tx(sb_farmer)
        # res = await client.push_tx(sb_pool)

        # print(res)
        up = await client.get_coin_records_by_puzzle_hash(farmer_prefarm.puzzle_hash, True)
        uf = await client.get_coin_records_by_puzzle_hash(pool_prefarm.puzzle_hash, True)
        print(up)
        print(uf)
    finally:
        client.close()


asyncio.run(main())
