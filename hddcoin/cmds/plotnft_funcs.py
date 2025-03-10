from __future__ import annotations

import asyncio
import functools
import json
import time
from dataclasses import replace
from decimal import Decimal
from pprint import pprint
from typing import Any, Awaitable, Callable, Dict, List, Optional

import aiohttp

from hddcoin.cmds.cmds_util import (
    get_any_service_client,
    get_wallet_client,
    transaction_status_msg,
    transaction_submitted_msg,
)
from hddcoin.cmds.units import units
from hddcoin.cmds.wallet_funcs import print_balance, wallet_coin_unit
from hddcoin.pools.pool_config import PoolWalletConfig, load_pool_config, update_pool_config
from hddcoin.pools.pool_wallet_info import PoolSingletonState, PoolWalletInfo
from hddcoin.protocols.pool_protocol import POOL_PROTOCOL_VERSION
from hddcoin.rpc.farmer_rpc_client import FarmerRpcClient
from hddcoin.rpc.wallet_rpc_client import WalletRpcClient
from hddcoin.server.server import ssl_context_for_root
from hddcoin.ssl.create_ssl import get_mozilla_ca_crt
from hddcoin.types.blockchain_format.sized_bytes import bytes32
from hddcoin.util.bech32m import decode_puzzle_hash, encode_puzzle_hash
from hddcoin.util.byte_types import hexstr_to_bytes
from hddcoin.util.config import load_config
from hddcoin.util.default_root import DEFAULT_ROOT_PATH
from hddcoin.util.errors import CliRpcConnectionError
from hddcoin.util.ints import uint32, uint64
from hddcoin.wallet.transaction_record import TransactionRecord
from hddcoin.wallet.util.wallet_types import WalletType


async def create_pool_args(pool_url: str) -> Dict[str, Any]:
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{pool_url}/pool_info", ssl=ssl_context_for_root(get_mozilla_ca_crt())) as response:
                if response.ok:
                    json_dict: Dict[str, Any] = json.loads(await response.text())
                else:
                    raise ValueError(f"Response from {pool_url} not OK: {response.status}")
    except Exception as e:
        raise ValueError(f"Error connecting to pool {pool_url}: {e}")

    if json_dict["relative_lock_height"] > 1000:
        raise ValueError("Relative lock height too high for this pool, cannot join")
    if json_dict["protocol_version"] != POOL_PROTOCOL_VERSION:
        raise ValueError(f"Incorrect version: {json_dict['protocol_version']}, should be {POOL_PROTOCOL_VERSION}")

    header_msg = f"\n---- Pool parameters fetched from {pool_url} ----"
    print(header_msg)
    pprint(json_dict)
    print("-" * len(header_msg))
    return json_dict


async def create(
    wallet_rpc_port: Optional[int], fingerprint: int, pool_url: Optional[str], state: str, fee: Decimal, prompt: bool
) -> None:
    async with get_wallet_client(wallet_rpc_port, fingerprint) as (wallet_client, fingerprint, _):
        fee_mojos = uint64(int(fee * units["hddcoin"]))
        target_puzzle_hash: Optional[bytes32]
        # Could use initial_pool_state_from_dict to simplify
        if state == "SELF_POOLING":
            pool_url = None
            relative_lock_height = uint32(0)
            target_puzzle_hash = None  # wallet will fill this in
        elif state == "FARMING_TO_POOL":
            config = load_config(DEFAULT_ROOT_PATH, "config.yaml")
            enforce_https = config["full_node"]["selected_network"] == "mainnet"
            assert pool_url is not None
            if enforce_https and not pool_url.startswith("https://"):
                print(f"Pool URLs must be HTTPS on mainnet {pool_url}. Aborting.")
                return
            assert pool_url is not None
            json_dict = await create_pool_args(pool_url)
            relative_lock_height = json_dict["relative_lock_height"]
            target_puzzle_hash = bytes32.from_hexstr(json_dict["target_puzzle_hash"])
        else:
            raise ValueError("Plot NFT must be created in SELF_POOLING or FARMING_TO_POOL state.")

        pool_msg = f" and join pool: {pool_url}" if pool_url else ""
        print(f"Will create a plot NFT{pool_msg}.")
        if prompt:
            user_input: str = input("Confirm [n]/y: ")
        else:
            user_input = "yes"

        if user_input.lower() == "y" or user_input.lower() == "yes":
            try:
                tx_record: TransactionRecord = await wallet_client.create_new_pool_wallet(
                    target_puzzle_hash,
                    pool_url,
                    relative_lock_height,
                    "localhost:5000",
                    "new",
                    state,
                    fee_mojos,
                )
                start = time.time()
                while time.time() - start < 10:
                    await asyncio.sleep(0.1)
                    tx = await wallet_client.get_transaction(1, tx_record.name)
                    if len(tx.sent_to) > 0:
                        print(transaction_submitted_msg(tx))
                        print(transaction_status_msg(fingerprint, tx_record.name))
                        return None
            except Exception as e:
                print(
                    f"Error creating plot NFT: {e}\n    Please start both farmer and wallet with:  hddcoin start -r farmer"
                )
            return
        print("Aborting.")


async def pprint_pool_wallet_state(
    wallet_client: WalletRpcClient,
    wallet_id: int,
    pool_wallet_info: PoolWalletInfo,
    address_prefix: str,
    pool_state_dict: Optional[Dict[str, Any]],
) -> None:
    print(f"Wallet ID: {wallet_id}")
    if pool_wallet_info.current.state == PoolSingletonState.LEAVING_POOL.value and pool_wallet_info.target is None:
        expected_leave_height = pool_wallet_info.singleton_block_height + pool_wallet_info.current.relative_lock_height
        print(f"Current state: INVALID_STATE. Please leave/join again after block height {expected_leave_height}")
    else:
        print(f"Current state: {PoolSingletonState(pool_wallet_info.current.state).name}")
    print(f"Current state from block height: {pool_wallet_info.singleton_block_height}")
    print(f"Launcher ID: {pool_wallet_info.launcher_id}")
    print(
        "Target address (not for plotting): "
        f"{encode_puzzle_hash(pool_wallet_info.current.target_puzzle_hash, address_prefix)}"
    )
    print(f"Number of plots: {0 if pool_state_dict is None else pool_state_dict['plot_count']}")
    print(f"Owner public key: {pool_wallet_info.current.owner_pubkey}")

    print(
        f"Pool contract address (use ONLY for plotting - do not send money to this address): "
        f"{encode_puzzle_hash(pool_wallet_info.p2_singleton_puzzle_hash, address_prefix)}"
    )
    if pool_wallet_info.target is not None:
        print(f"Target state: {PoolSingletonState(pool_wallet_info.target.state).name}")
        print(f"Target pool URL: {pool_wallet_info.target.pool_url}")
    if pool_wallet_info.current.state == PoolSingletonState.SELF_POOLING.value:
        balances: Dict[str, Any] = await wallet_client.get_wallet_balance(wallet_id)
        balance = balances["confirmed_wallet_balance"]
        typ = WalletType(int(WalletType.POOLING_WALLET))
        address_prefix, scale = wallet_coin_unit(typ, address_prefix)
        print(f"Claimable balance: {print_balance(balance, scale, address_prefix)}")
    if pool_wallet_info.current.state == PoolSingletonState.FARMING_TO_POOL.value:
        print(f"Current pool URL: {pool_wallet_info.current.pool_url}")
        if pool_state_dict is not None:
            print(f"Current difficulty: {pool_state_dict['current_difficulty']}")
            print(f"Points balance: {pool_state_dict['current_points']}")
            points_found_24h = [points for timestamp, points in pool_state_dict["points_found_24h"]]
            points_acknowledged_24h = [points for timestamp, points in pool_state_dict["points_acknowledged_24h"]]
            summed_points_found_24h = sum(points_found_24h)
            summed_points_acknowledged_24h = sum(points_acknowledged_24h)
            if summed_points_found_24h == 0:
                success_pct = 0.0
            else:
                success_pct = summed_points_acknowledged_24h / summed_points_found_24h
            print(f"Points found (24h): {summed_points_found_24h}")
            print(f"Percent Successful Points (24h): {success_pct:.2%}")
            payout_instructions: str = pool_state_dict["pool_config"]["payout_instructions"]
            try:
                payout_address = encode_puzzle_hash(bytes32.fromhex(payout_instructions), address_prefix)
                print(f"Payout instructions (pool will pay to this address): {payout_address}")
            except Exception:
                print(f"Payout instructions (pool will pay you with this): {payout_instructions}")
        print(f"Relative lock height: {pool_wallet_info.current.relative_lock_height} blocks")
    if pool_wallet_info.current.state == PoolSingletonState.LEAVING_POOL.value:
        expected_leave_height = pool_wallet_info.singleton_block_height + pool_wallet_info.current.relative_lock_height
        if pool_wallet_info.target is not None:
            print(f"Expected to leave after block height: {expected_leave_height}")


async def pprint_all_pool_wallet_state(
    wallet_client: WalletRpcClient,
    get_wallets_response: List[Dict[str, Any]],
    address_prefix: str,
    pool_state_dict: Dict[bytes32, Dict[str, Any]],
) -> None:
    print(f"Wallet height: {await wallet_client.get_height_info()}")
    print(f"Sync status: {'Synced' if (await wallet_client.get_synced()) else 'Not synced'}")
    for wallet_info in get_wallets_response:
        pool_wallet_id = wallet_info["id"]
        typ = WalletType(int(wallet_info["type"]))
        if typ == WalletType.POOLING_WALLET:
            pool_wallet_info, _ = await wallet_client.pw_status(pool_wallet_id)
            await pprint_pool_wallet_state(
                wallet_client,
                pool_wallet_id,
                pool_wallet_info,
                address_prefix,
                pool_state_dict.get(pool_wallet_info.launcher_id),
            )
            print("")


async def show(wallet_rpc_port: Optional[int], fp: Optional[int], wallet_id_passed_in: Optional[int]) -> None:
    async with get_wallet_client(wallet_rpc_port, fp) as (wallet_client, fingerprint, _):
        try:
            async with get_any_service_client(FarmerRpcClient) as (farmer_client, config):
                address_prefix = config["network_overrides"]["config"][config["selected_network"]]["address_prefix"]
                summaries_response = await wallet_client.get_wallets()
                pool_state_list = (await farmer_client.get_pool_state())["pool_state"]
                pool_state_dict: Dict[bytes32, Dict[str, Any]] = {
                    bytes32.from_hexstr(pool_state_item["pool_config"]["launcher_id"]): pool_state_item
                    for pool_state_item in pool_state_list
                }
                if wallet_id_passed_in is not None:
                    for summary in summaries_response:
                        typ = WalletType(int(summary["type"]))
                        if summary["id"] == wallet_id_passed_in and typ != WalletType.POOLING_WALLET:
                            print(
                                f"Wallet with id: {wallet_id_passed_in} is not a pooling wallet."
                                " Please provide a different id."
                            )
                            return
                    pool_wallet_info, _ = await wallet_client.pw_status(wallet_id_passed_in)
                    await pprint_pool_wallet_state(
                        wallet_client,
                        wallet_id_passed_in,
                        pool_wallet_info,
                        address_prefix,
                        pool_state_dict.get(pool_wallet_info.launcher_id),
                    )
                else:
                    await pprint_all_pool_wallet_state(
                        wallet_client, summaries_response, address_prefix, pool_state_dict
                    )
        except CliRpcConnectionError:  # we want to output this if we can't connect to the farmer
            await pprint_all_pool_wallet_state(wallet_client, summaries_response, address_prefix, pool_state_dict)


async def get_login_link(launcher_id_str: str) -> None:
    launcher_id: bytes32 = bytes32.from_hexstr(launcher_id_str)
    async with get_any_service_client(FarmerRpcClient) as (farmer_client, _):
        login_link: Optional[str] = await farmer_client.get_pool_login_link(launcher_id)
        if login_link is None:
            print("Was not able to get login link.")
        else:
            print(login_link)


async def submit_tx_with_confirmation(
    message: str,
    prompt: bool,
    func: Callable[[], Awaitable[Dict[str, Any]]],
    wallet_client: WalletRpcClient,
    fingerprint: int,
    wallet_id: int,
) -> None:
    print(message)
    if prompt:
        user_input: str = input("Confirm [n]/y: ")
    else:
        user_input = "yes"

    if user_input.lower() == "y" or user_input.lower() == "yes":
        try:
            result = await func()
            tx_record: TransactionRecord = result["transaction"]
            start = time.time()
            while time.time() - start < 10:
                await asyncio.sleep(0.1)
                tx = await wallet_client.get_transaction(1, tx_record.name)
                if len(tx.sent_to) > 0:
                    print(transaction_submitted_msg(tx))
                    print(transaction_status_msg(fingerprint, tx_record.name))
                    return None
        except Exception as e:
            print(f"Error performing operation on Plot NFT -f {fingerprint} wallet id: {wallet_id}: {e}")
        return
    print("Aborting.")


async def join_pool(
    *,
    wallet_rpc_port: Optional[int],
    fingerprint: int,
    pool_url: str,
    fee: Decimal,
    wallet_id: int,
    prompt: bool,
) -> None:
    async with get_wallet_client(wallet_rpc_port, fingerprint) as (wallet_client, fingerprint, config):
        enforce_https = config["full_node"]["selected_network"] == "mainnet"
        fee_mojos = uint64(int(fee * units["hddcoin"]))

        if enforce_https and not pool_url.startswith("https://"):
            print(f"Pool URLs must be HTTPS on mainnet {pool_url}. Aborting.")
            return
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{pool_url}/pool_info", ssl=ssl_context_for_root(get_mozilla_ca_crt())
                ) as response:
                    if response.ok:
                        json_dict = json.loads(await response.text())
                    else:
                        print(f"Response not OK: {response.status}")
                        return
        except Exception as e:
            print(f"Error connecting to pool {pool_url}: {e}")
            return

        if json_dict["relative_lock_height"] > 1000:
            print("Relative lock height too high for this pool, cannot join")
            return
        if json_dict["protocol_version"] != POOL_PROTOCOL_VERSION:
            print(f"Incorrect version: {json_dict['protocol_version']}, should be {POOL_PROTOCOL_VERSION}")
            return

        pprint(json_dict)
        msg = f"\nWill join pool: {pool_url} with Plot NFT {fingerprint}."
        func = functools.partial(
            wallet_client.pw_join_pool,
            wallet_id,
            hexstr_to_bytes(json_dict["target_puzzle_hash"]),
            pool_url,
            json_dict["relative_lock_height"],
            fee_mojos,
        )

        await submit_tx_with_confirmation(msg, prompt, func, wallet_client, fingerprint, wallet_id)


async def self_pool(
    *, wallet_rpc_port: Optional[int], fingerprint: int, fee: Decimal, wallet_id: int, prompt: bool
) -> None:
    async with get_wallet_client(wallet_rpc_port, fingerprint) as (wallet_client, fingerprint, _):
        fee_mojos = uint64(int(fee * units["hddcoin"]))
        msg = f"Will start self-farming with Plot NFT on wallet id {wallet_id} fingerprint {fingerprint}."
        func = functools.partial(wallet_client.pw_self_pool, wallet_id, fee_mojos)
        await submit_tx_with_confirmation(msg, prompt, func, wallet_client, fingerprint, wallet_id)


async def inspect_cmd(wallet_rpc_port: Optional[int], fingerprint: int, wallet_id: int) -> None:
    async with get_wallet_client(wallet_rpc_port, fingerprint) as (wallet_client, fingerprint, _):
        pool_wallet_info, unconfirmed_transactions = await wallet_client.pw_status(wallet_id)
        print(
            {
                "pool_wallet_info": pool_wallet_info,
                "unconfirmed_transactions": [
                    {"sent_to": tx.sent_to, "transaction_id": tx.name.hex()} for tx in unconfirmed_transactions
                ],
            }
        )


async def claim_cmd(*, wallet_rpc_port: Optional[int], fingerprint: int, fee: Decimal, wallet_id: int) -> None:
    async with get_wallet_client(wallet_rpc_port, fingerprint) as (wallet_client, fingerprint, _):
        fee_mojos = uint64(int(fee * units["hddcoin"]))
        msg = f"\nWill claim rewards for wallet ID: {wallet_id}."
        func = functools.partial(
            wallet_client.pw_absorb_rewards,
            wallet_id,
            fee_mojos,
        )
        await submit_tx_with_confirmation(msg, False, func, wallet_client, fingerprint, wallet_id)


async def change_payout_instructions(launcher_id: str, address: str) -> None:
    new_pool_configs: List[PoolWalletConfig] = []
    id_found = False
    try:
        puzzle_hash = decode_puzzle_hash(address)
    except ValueError:
        print(f"Invalid Address: {address}")
        return

    old_configs: List[PoolWalletConfig] = load_pool_config(DEFAULT_ROOT_PATH)
    for pool_config in old_configs:
        if pool_config.launcher_id == hexstr_to_bytes(launcher_id):
            id_found = True
            pool_config = replace(pool_config, payout_instructions=puzzle_hash.hex())
        new_pool_configs.append(pool_config)
    if id_found:
        print(f"Launcher Id: {launcher_id} Found, Updating Config.")
        await update_pool_config(DEFAULT_ROOT_PATH, new_pool_configs)
        print(f"Payout Instructions for launcher id: {launcher_id} successfully updated to: {address}.")
        print(f"You will need to change the payout instructions on every device you use to: {address}.")
    else:
        print(f"Launcher Id: {launcher_id} Not found.")
