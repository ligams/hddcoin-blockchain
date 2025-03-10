from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple, Union

from hddcoin.data_layer.data_layer_wallet import Mirror, SingletonRecord
from hddcoin.pools.pool_wallet_info import PoolWalletInfo
from hddcoin.rpc.rpc_client import RpcClient
from hddcoin.types.announcement import Announcement
from hddcoin.types.blockchain_format.coin import Coin
from hddcoin.types.blockchain_format.program import Program
from hddcoin.types.blockchain_format.sized_bytes import bytes32
from hddcoin.types.coin_record import CoinRecord
from hddcoin.util.bech32m import encode_puzzle_hash
from hddcoin.util.ints import uint16, uint32, uint64
from hddcoin.wallet.conditions import Condition, ConditionValidTimes, conditions_to_json_dicts
from hddcoin.wallet.notification_store import Notification
from hddcoin.wallet.trade_record import TradeRecord
from hddcoin.wallet.trading.offer import Offer
from hddcoin.wallet.transaction_record import TransactionRecord
from hddcoin.wallet.transaction_sorting import SortKey
from hddcoin.wallet.util.query_filter import TransactionTypeFilter
from hddcoin.wallet.util.tx_config import CoinSelectionConfig, TXConfig
from hddcoin.wallet.util.wallet_types import WalletType
from hddcoin.wallet.vc_wallet.vc_store import VCRecord
from hddcoin.wallet.wallet_coin_store import GetCoinRecords


def parse_result_transactions(result: Dict[str, Any]) -> Dict[str, Any]:
    result["transaction"] = TransactionRecord.from_json_dict(result["transaction"])
    if result["fee_transaction"]:
        result["fee_transaction"] = TransactionRecord.from_json_dict(result["fee_transaction"])
    return result


class WalletRpcClient(RpcClient):
    """
    Client to Chia RPC, connects to a local wallet. Uses HTTP/JSON, and converts back from
    JSON into native python objects before returning. All api calls use POST requests.
    Note that this is not the same as the peer protocol, or wallet protocol (which run Chia's
    protocol on top of TCP), it's a separate protocol on top of HTTP that provides easy access
    to the full node.
    """

    # Key Management APIs
    async def log_in(self, fingerprint: int) -> Dict:
        try:
            return await self.fetch(
                "log_in",
                {"fingerprint": fingerprint, "type": "start"},
            )

        except ValueError as e:
            return e.args[0]

    async def set_wallet_resync_on_startup(self, enable: bool = True) -> Dict[str, Any]:
        return await self.fetch(
            path="set_wallet_resync_on_startup",
            request_json={"enable": enable},
        )

    async def get_logged_in_fingerprint(self) -> int:
        return (await self.fetch("get_logged_in_fingerprint", {}))["fingerprint"]

    async def get_public_keys(self) -> List[int]:
        return (await self.fetch("get_public_keys", {}))["public_key_fingerprints"]

    async def get_private_key(self, fingerprint: int) -> Dict:
        return (await self.fetch("get_private_key", {"fingerprint": fingerprint}))["private_key"]

    async def generate_mnemonic(self) -> List[str]:
        return (await self.fetch("generate_mnemonic", {}))["mnemonic"]

    async def add_key(self, mnemonic: List[str], request_type: str = "new_wallet") -> Dict[str, Any]:
        return await self.fetch("add_key", {"mnemonic": mnemonic, "type": request_type})

    async def delete_key(self, fingerprint: int) -> Dict[str, Any]:
        return await self.fetch("delete_key", {"fingerprint": fingerprint})

    async def check_delete_key(self, fingerprint: int, max_ph_to_search: int = 100) -> Dict[str, Any]:
        return await self.fetch("check_delete_key", {"fingerprint": fingerprint, "max_ph_to_search": max_ph_to_search})

    async def delete_all_keys(self) -> Dict[str, Any]:
        return await self.fetch("delete_all_keys", {})

    # Wallet Node APIs
    async def get_sync_status(self) -> bool:
        return (await self.fetch("get_sync_status", {}))["syncing"]

    async def get_synced(self) -> bool:
        return (await self.fetch("get_sync_status", {}))["synced"]

    async def get_height_info(self) -> uint32:
        return (await self.fetch("get_height_info", {}))["height"]

    async def push_tx(self, spend_bundle):
        return await self.fetch("push_tx", {"spend_bundle": bytes(spend_bundle).hex()})

    async def push_transactions(self, txs: List[TransactionRecord]):
        transactions = [bytes(tx).hex() for tx in txs]

        return await self.fetch("push_transactions", {"transactions": transactions})

    async def farm_block(self, address: str) -> Dict[str, Any]:
        return await self.fetch("farm_block", {"address": address})

    async def get_timestamp_for_height(self, height: uint32) -> uint64:
        return uint64((await self.fetch("get_timestamp_for_height", {"height": height}))["timestamp"])

    # Wallet Management APIs
    async def get_wallets(self, wallet_type: Optional[WalletType] = None) -> List[Dict[str, Any]]:
        request: Dict[str, Any] = {}
        if wallet_type is not None:
            request["type"] = wallet_type
        return (await self.fetch("get_wallets", request))["wallets"]

    # Wallet APIs
    async def get_wallet_balance(self, wallet_id: int) -> Dict:
        return (await self.fetch("get_wallet_balance", {"wallet_id": wallet_id}))["wallet_balance"]

    async def get_wallet_balances(self, wallet_ids: Optional[List[int]] = None) -> Dict:
        return (await self.fetch("get_wallet_balances", {"wallet_ids": wallet_ids}))["wallet_balances"]

    async def get_transaction(self, wallet_id: int, transaction_id: bytes32) -> TransactionRecord:
        res = await self.fetch(
            "get_transaction",
            {"walled_id": wallet_id, "transaction_id": transaction_id.hex()},
        )
        return TransactionRecord.from_json_dict_convenience(res["transaction"])

    async def get_transactions(
        self,
        wallet_id: int,
        start: int = None,
        end: int = None,
        sort_key: SortKey = None,
        reverse: bool = False,
        to_address: Optional[str] = None,
        type_filter: Optional[TransactionTypeFilter] = None,
        confirmed: Optional[bool] = None,
    ) -> List[TransactionRecord]:
        request: Dict[str, Any] = {"wallet_id": wallet_id}

        if start is not None:
            request["start"] = start
        if end is not None:
            request["end"] = end
        if sort_key is not None:
            request["sort_key"] = sort_key.name
        request["reverse"] = reverse

        if to_address is not None:
            request["to_address"] = to_address

        if type_filter is not None:
            request["type_filter"] = type_filter.to_json_dict()

        if confirmed is not None:
            request["confirmed"] = confirmed

        res = await self.fetch(
            "get_transactions",
            request,
        )
        return [TransactionRecord.from_json_dict_convenience(tx) for tx in res["transactions"]]

    async def get_transaction_count(
        self,
        wallet_id: int,
        confirmed: Optional[bool] = None,
        type_filter: Optional[TransactionTypeFilter] = None,
    ) -> List[TransactionRecord]:
        request: Dict[str, Any] = {"wallet_id": wallet_id}
        if type_filter is not None:
            request["type_filter"] = type_filter.to_json_dict()

        if confirmed is not None:
            request["confirmed"] = confirmed
        res = await self.fetch("get_transaction_count", request)
        return res["count"]

    async def get_next_address(self, wallet_id: int, new_address: bool) -> str:
        return (await self.fetch("get_next_address", {"wallet_id": wallet_id, "new_address": new_address}))["address"]

    async def send_transaction(
        self,
        wallet_id: int,
        amount: uint64,
        address: str,
        tx_config: TXConfig,
        fee: uint64 = uint64(0),
        memos: Optional[List[str]] = None,
        puzzle_decorator_override: Optional[List[Dict[str, Union[str, int, bool]]]] = None,
        extra_conditions: Tuple[Condition, ...] = tuple(),
        timelock_info: ConditionValidTimes = ConditionValidTimes(),
    ) -> TransactionRecord:
        request = {
            "wallet_id": wallet_id,
            "amount": amount,
            "address": address,
            "fee": fee,
            "puzzle_decorator": puzzle_decorator_override,
            "extra_conditions": conditions_to_json_dicts(extra_conditions),
            **tx_config.to_json_dict(),
            **timelock_info.to_json_dict(),
        }
        if memos is not None:
            request["memos"] = memos
        response = await self.fetch("send_transaction", request)
        return TransactionRecord.from_json_dict_convenience(response["transaction"])

    async def send_transaction_multi(
        self,
        wallet_id: int,
        additions: List[Dict],
        tx_config: TXConfig,
        coins: List[Coin] = None,
        fee: uint64 = uint64(0),
    ) -> TransactionRecord:
        # Converts bytes to hex for puzzle hashes
        additions_hex = []
        for ad in additions:
            additions_hex.append({"amount": ad["amount"], "puzzle_hash": ad["puzzle_hash"].hex()})
            if "memos" in ad:
                additions_hex[-1]["memos"] = ad["memos"]
        request = {"wallet_id": wallet_id, "additions": additions_hex, "fee": fee, **tx_config.to_json_dict()}
        if coins is not None and len(coins) > 0:
            coins_json = [c.to_json_dict() for c in coins]
            request["coins"] = coins_json
        response = await self.fetch("send_transaction_multi", request)
        return TransactionRecord.from_json_dict_convenience(response["transaction"])

    async def spend_clawback_coins(
        self,
        coin_ids: List[bytes32],
        fee: int = 0,
        force: bool = False,
        extra_conditions: Tuple[Condition, ...] = tuple(),
        timelock_info: ConditionValidTimes = ConditionValidTimes(),
    ) -> Dict:
        response = await self.fetch(
            "spend_clawback_coins",
            {
                "coin_ids": [cid.hex() for cid in coin_ids],
                "fee": fee,
                "force": force,
                "extra_conditions": conditions_to_json_dicts(extra_conditions),
                **timelock_info.to_json_dict(),
            },
        )
        return response

    async def delete_unconfirmed_transactions(self, wallet_id: int) -> None:
        await self.fetch(
            "delete_unconfirmed_transactions",
            {"wallet_id": wallet_id},
        )
        return None

    async def get_current_derivation_index(self) -> str:
        return (await self.fetch("get_current_derivation_index", {}))["index"]

    async def extend_derivation_index(self, index: int) -> str:
        return (await self.fetch("extend_derivation_index", {"index": index}))["index"]

    async def get_farmed_amount(self) -> Dict:
        return await self.fetch("get_farmed_amount", {})

    async def create_signed_transactions(
        self,
        additions: List[Dict],
        tx_config: TXConfig,
        coins: List[Coin] = None,
        fee: uint64 = uint64(0),
        coin_announcements: Optional[List[Announcement]] = None,
        puzzle_announcements: Optional[List[Announcement]] = None,
        wallet_id: Optional[int] = None,
        extra_conditions: Tuple[Condition, ...] = tuple(),
        timelock_info: ConditionValidTimes = ConditionValidTimes(),
    ) -> List[TransactionRecord]:
        # Converts bytes to hex for puzzle hashes
        additions_hex = []
        for ad in additions:
            additions_hex.append({"amount": ad["amount"], "puzzle_hash": ad["puzzle_hash"].hex()})
            if "memos" in ad:
                additions_hex[-1]["memos"] = ad["memos"]

        request: Dict[str, Any] = {
            "additions": additions_hex,
            "fee": fee,
            "extra_conditions": conditions_to_json_dicts(extra_conditions),
            **tx_config.to_json_dict(),
            **timelock_info.to_json_dict(),
        }

        if coin_announcements is not None and len(coin_announcements) > 0:
            request["coin_announcements"] = [
                {
                    "coin_id": ann.origin_info.hex(),
                    "message": ann.message.hex(),
                    "morph_bytes": ann.morph_bytes.hex() if ann.morph_bytes is not None else b"".hex(),
                }
                for ann in coin_announcements
            ]

        if puzzle_announcements is not None and len(puzzle_announcements) > 0:
            request["puzzle_announcements"] = [
                {
                    "puzzle_hash": ann.origin_info.hex(),
                    "message": ann.message.hex(),
                    "morph_bytes": ann.morph_bytes.hex() if ann.morph_bytes is not None else b"".hex(),
                }
                for ann in puzzle_announcements
            ]

        if coins is not None and len(coins) > 0:
            coins_json = [c.to_json_dict() for c in coins]
            request["coins"] = coins_json

        if wallet_id:
            request["wallet_id"] = wallet_id

        response: Dict = await self.fetch("create_signed_transaction", request)
        return [TransactionRecord.from_json_dict_convenience(tx) for tx in response["signed_txs"]]

    async def create_signed_transaction(
        self,
        additions: List[Dict],
        tx_config: TXConfig,
        coins: List[Coin] = None,
        fee: uint64 = uint64(0),
        coin_announcements: Optional[List[Announcement]] = None,
        puzzle_announcements: Optional[List[Announcement]] = None,
        wallet_id: Optional[int] = None,
    ) -> TransactionRecord:
        txs: List[TransactionRecord] = await self.create_signed_transactions(
            additions=additions,
            tx_config=tx_config,
            coins=coins,
            fee=fee,
            coin_announcements=coin_announcements,
            puzzle_announcements=puzzle_announcements,
            wallet_id=wallet_id,
        )
        if len(txs) == 0:
            raise ValueError("`create_signed_transaction` returned empty list!")

        return txs[0]

    async def select_coins(
        self,
        amount: int,
        wallet_id: int,
        coin_selection_config: CoinSelectionConfig,
    ) -> List[Coin]:
        request = {
            "amount": amount,
            "wallet_id": wallet_id,
            **coin_selection_config.to_json_dict(),
        }
        response: Dict[str, List[Dict]] = await self.fetch("select_coins", request)
        return [Coin.from_json_dict(coin) for coin in response["coins"]]

    async def get_coin_records(self, request: GetCoinRecords) -> Dict[str, Any]:
        return await self.fetch("get_coin_records", request.to_json_dict())

    async def get_spendable_coins(
        self,
        wallet_id: int,
        coin_selection_config: CoinSelectionConfig,
    ) -> Tuple[List[CoinRecord], List[CoinRecord], List[Coin]]:
        """
        We return a tuple containing: (confirmed records, unconfirmed removals, unconfirmed additions)
        """
        request = {
            "wallet_id": wallet_id,
            **coin_selection_config.to_json_dict(),
        }
        response: Dict[str, List[Dict]] = await self.fetch("get_spendable_coins", request)
        confirmed_wrs = [CoinRecord.from_json_dict(coin) for coin in response["confirmed_records"]]
        unconfirmed_removals = [CoinRecord.from_json_dict(coin) for coin in response["unconfirmed_removals"]]
        unconfirmed_additions = [Coin.from_json_dict(coin) for coin in response["unconfirmed_additions"]]
        return confirmed_wrs, unconfirmed_removals, unconfirmed_additions

    async def get_coin_records_by_names(
        self,
        names: List[bytes32],
        include_spent_coins: bool = True,
        start_height: Optional[int] = None,
        end_height: Optional[int] = None,
    ) -> List:
        names_hex = [name.hex() for name in names]
        request = {"names": names_hex, "include_spent_coins": include_spent_coins}
        if start_height is not None:
            request["start_height"] = start_height
        if end_height is not None:
            request["end_height"] = end_height

        response = await self.fetch("get_coin_records_by_names", request)
        return [CoinRecord.from_json_dict(cr) for cr in response["coin_records"]]

    # DID wallet
    async def create_new_did_wallet(
        self,
        amount: int,
        fee: int = 0,
        name: Optional[str] = "DID Wallet",
        backup_ids: List[str] = [],
        required_num: int = 0,
    ) -> Dict:
        request: Dict[str, Any] = {
            "wallet_type": "did_wallet",
            "did_type": "new",
            "backup_dids": backup_ids,
            "num_of_backup_ids_needed": required_num,
            "amount": amount,
            "fee": fee,
            "wallet_name": name,
        }
        response = await self.fetch("create_new_wallet", request)
        return response

    async def get_did_id(self, wallet_id: int) -> Dict:
        request: Dict[str, Any] = {
            "wallet_id": wallet_id,
        }
        response = await self.fetch("did_get_did", request)
        return response

    async def get_did_info(self, coin_id: str, latest: bool) -> Dict:
        request: Dict[str, Any] = {
            "coin_id": coin_id,
            "latest": latest,
        }
        response = await self.fetch("did_get_info", request)
        return response

    async def create_did_backup_file(self, wallet_id: int, filename: str) -> Dict:
        request: Dict[str, Any] = {
            "wallet_id": wallet_id,
            "filename": filename,
        }
        response = await self.fetch("did_create_backup_file", request)
        return response

    async def update_did_recovery_list(
        self,
        wallet_id: int,
        recovery_list: List[str],
        num_verification: int,
        tx_config: TXConfig,
        extra_conditions: Tuple[Condition, ...] = tuple(),
        timelock_info: ConditionValidTimes = ConditionValidTimes(),
    ) -> Dict:
        request: Dict[str, Any] = {
            "wallet_id": wallet_id,
            "new_list": recovery_list,
            "num_verifications_required": num_verification,
            "extra_conditions": conditions_to_json_dicts(extra_conditions),
            **tx_config.to_json_dict(),
            **timelock_info.to_json_dict(),
        }
        response = await self.fetch("did_update_recovery_ids", request)
        return response

    async def get_did_recovery_list(self, wallet_id: int) -> Dict:
        request: Dict[str, Any] = {
            "wallet_id": wallet_id,
        }
        response = await self.fetch("did_get_recovery_list", request)
        return response

    async def did_message_spend(
        self,
        wallet_id: int,
        puzzle_announcements: List[str],
        coin_announcements: List[str],
        tx_config: TXConfig,
        extra_conditions: Tuple[Condition, ...] = tuple(),
        timelock_info: ConditionValidTimes = ConditionValidTimes(),
    ) -> Dict:
        request: Dict[str, Any] = {
            "wallet_id": wallet_id,
            "coin_announcements": coin_announcements,
            "puzzle_announcements": puzzle_announcements,
            "extra_conditions": conditions_to_json_dicts(extra_conditions),
            **tx_config.to_json_dict(),
            **timelock_info.to_json_dict(),
        }
        response = await self.fetch("did_message_spend", request)
        return response

    async def update_did_metadata(
        self,
        wallet_id: int,
        metadata: Dict,
        tx_config: TXConfig,
        extra_conditions: Tuple[Condition, ...] = tuple(),
        timelock_info: ConditionValidTimes = ConditionValidTimes(),
    ) -> Dict:
        request: Dict[str, Any] = {
            "wallet_id": wallet_id,
            "metadata": metadata,
            "extra_conditions": conditions_to_json_dicts(extra_conditions),
            **tx_config.to_json_dict(),
            **timelock_info.to_json_dict(),
        }
        response = await self.fetch("did_update_metadata", request)
        return response

    async def get_did_metadata(self, wallet_id: int) -> Dict:
        request: Dict[str, Any] = {
            "wallet_id": wallet_id,
        }
        response = await self.fetch("did_get_metadata", request)
        return response

    async def find_lost_did(
        self, coin_id: str, recovery_list_hash: Optional[str], metadata: Optional[Dict], num_verification: Optional[int]
    ) -> Dict:
        request: Dict[str, Any] = {
            "coin_id": coin_id,
        }
        if recovery_list_hash is not None:
            request["recovery_list_hash"] = recovery_list_hash
        if metadata is not None:
            request["metadata"] = (metadata,)
        if num_verification is not None:
            request["num_verification"] = num_verification
        response = await self.fetch("did_find_lost_did", request)
        return response

    async def create_new_did_wallet_from_recovery(self, filename: str) -> Dict:
        request: Dict[str, Any] = {
            "wallet_type": "did_wallet",
            "did_type": "recovery",
            "filename": filename,
        }
        response = await self.fetch("create_new_wallet", request)
        return response

    async def did_create_attest(
        self,
        wallet_id: int,
        coin_name: str,
        pubkey: str,
        puzhash: str,
        file_name: str,
        extra_conditions: Tuple[Condition, ...] = tuple(),
        timelock_info: ConditionValidTimes = ConditionValidTimes(),
    ) -> Dict:
        request: Dict[str, Any] = {
            "wallet_id": wallet_id,
            "coin_name": coin_name,
            "pubkey": pubkey,
            "puzhash": puzhash,
            "filename": file_name,
            "extra_conditions": conditions_to_json_dicts(extra_conditions),
            **timelock_info.to_json_dict(),
        }
        response = await self.fetch("did_create_attest", request)
        return response

    async def did_recovery_spend(self, wallet_id: int, attest_filenames: str) -> Dict:
        request: Dict[str, Any] = {
            "wallet_id": wallet_id,
            "attest_filenames": attest_filenames,
        }
        response = await self.fetch("did_recovery_spend", request)
        return response

    async def did_transfer_did(
        self,
        wallet_id: int,
        address: str,
        fee: int,
        with_recovery: bool,
        tx_config: TXConfig,
        extra_conditions: Tuple[Condition, ...] = tuple(),
        timelock_info: ConditionValidTimes = ConditionValidTimes(),
    ) -> Dict:
        request: Dict[str, Any] = {
            "wallet_id": wallet_id,
            "inner_address": address,
            "fee": fee,
            "with_recovery_info": with_recovery,
            "extra_conditions": conditions_to_json_dicts(extra_conditions),
            **tx_config.to_json_dict(),
            **timelock_info.to_json_dict(),
        }
        response = await self.fetch("did_transfer_did", request)
        return response

    async def did_set_wallet_name(self, wallet_id: int, name: str) -> Dict:
        request = {"wallet_id": wallet_id, "name": name}
        response = await self.fetch("did_set_wallet_name", request)
        return response

    async def did_get_wallet_name(self, wallet_id: int) -> Dict:
        request = {"wallet_id": wallet_id}
        response = await self.fetch("did_get_wallet_name", request)
        return response

    # TODO: test all invocations of create_new_pool_wallet with new fee arg.
    async def create_new_pool_wallet(
        self,
        target_puzzlehash: Optional[bytes32],
        pool_url: Optional[str],
        relative_lock_height: uint32,
        backup_host: str,
        mode: str,
        state: str,
        fee: uint64,
        p2_singleton_delay_time: Optional[uint64] = None,
        p2_singleton_delayed_ph: Optional[bytes32] = None,
        extra_conditions: Tuple[Condition, ...] = tuple(),
        timelock_info: ConditionValidTimes = ConditionValidTimes(),
    ) -> TransactionRecord:
        request: Dict[str, Any] = {
            "wallet_type": "pool_wallet",
            "mode": mode,
            "initial_target_state": {
                "target_puzzle_hash": target_puzzlehash.hex() if target_puzzlehash else None,
                "relative_lock_height": relative_lock_height,
                "pool_url": pool_url,
                "state": state,
            },
            "fee": fee,
            "extra_conditions": conditions_to_json_dicts(extra_conditions),
            **timelock_info.to_json_dict(),
        }
        if p2_singleton_delay_time is not None:
            request["p2_singleton_delay_time"] = p2_singleton_delay_time
        if p2_singleton_delayed_ph is not None:
            request["p2_singleton_delayed_ph"] = p2_singleton_delayed_ph.hex()
        res = await self.fetch("create_new_wallet", request)
        return TransactionRecord.from_json_dict(res["transaction"])

    async def pw_self_pool(self, wallet_id: int, fee: uint64) -> Dict:
        reply = await self.fetch("pw_self_pool", {"wallet_id": wallet_id, "fee": fee})
        reply = parse_result_transactions(reply)
        return reply

    async def pw_join_pool(
        self, wallet_id: int, target_puzzlehash: bytes32, pool_url: str, relative_lock_height: uint32, fee: uint64
    ) -> Dict:
        request = {
            "wallet_id": int(wallet_id),
            "target_puzzlehash": target_puzzlehash.hex(),
            "relative_lock_height": relative_lock_height,
            "pool_url": pool_url,
            "fee": fee,
        }

        reply = await self.fetch("pw_join_pool", request)
        reply = parse_result_transactions(reply)
        return reply

    async def pw_absorb_rewards(
        self, wallet_id: int, fee: uint64 = uint64(0), max_spends_in_tx: Optional[int] = None
    ) -> Dict:
        reply = await self.fetch(
            "pw_absorb_rewards", {"wallet_id": wallet_id, "fee": fee, "max_spends_in_tx": max_spends_in_tx}
        )
        reply["state"] = PoolWalletInfo.from_json_dict(reply["state"])
        reply = parse_result_transactions(reply)
        return reply

    async def pw_status(self, wallet_id: int) -> Tuple[PoolWalletInfo, List[TransactionRecord]]:
        json_dict = await self.fetch("pw_status", {"wallet_id": wallet_id})
        return (
            PoolWalletInfo.from_json_dict(json_dict["state"]),
            [TransactionRecord.from_json_dict(tr) for tr in json_dict["unconfirmed_transactions"]],
        )

    # CATS
    async def create_new_cat_and_wallet(self, amount: uint64, fee: uint64 = uint64(0), test: bool = False) -> Dict:
        request: Dict[str, Any] = {
            "wallet_type": "cat_wallet",
            "mode": "new",
            "amount": amount,
            "fee": fee,
            "test": test,
        }
        return await self.fetch("create_new_wallet", request)

    async def create_wallet_for_existing_cat(self, asset_id: bytes) -> Dict:
        request: Dict[str, Any] = {
            "wallet_type": "cat_wallet",
            "asset_id": asset_id.hex(),
            "mode": "existing",
        }
        return await self.fetch("create_new_wallet", request)

    async def get_cat_asset_id(self, wallet_id: int) -> bytes32:
        request: Dict[str, Any] = {
            "wallet_id": wallet_id,
        }
        return bytes32.from_hexstr((await self.fetch("cat_get_asset_id", request))["asset_id"])

    async def get_stray_cats(self) -> Dict:
        response = await self.fetch("get_stray_cats", {})
        return response["stray_cats"]

    async def cat_asset_id_to_name(self, asset_id: bytes32) -> Optional[Tuple[Optional[uint32], str]]:
        request: Dict[str, Any] = {
            "asset_id": asset_id.hex(),
        }
        try:
            res = await self.fetch("cat_asset_id_to_name", request)
        except ValueError:
            return None

        wallet_id: Optional[uint32] = None if res["wallet_id"] is None else uint32(int(res["wallet_id"]))
        return wallet_id, res["name"]

    async def get_cat_name(self, wallet_id: int) -> str:
        request: Dict[str, Any] = {
            "wallet_id": wallet_id,
        }
        return (await self.fetch("cat_get_name", request))["name"]

    async def set_cat_name(self, wallet_id: int, name: str) -> None:
        request: Dict[str, Any] = {
            "wallet_id": wallet_id,
            "name": name,
        }
        await self.fetch("cat_set_name", request)

    async def cat_spend(
        self,
        wallet_id: int,
        tx_config: TXConfig,
        amount: Optional[uint64] = None,
        inner_address: Optional[str] = None,
        fee: uint64 = uint64(0),
        memos: Optional[List[str]] = None,
        additions: Optional[List[Dict[str, Any]]] = None,
        removals: Optional[List[Coin]] = None,
        cat_discrepancy: Optional[Tuple[int, Program, Program]] = None,  # (extra_delta, tail_reveal, tail_solution)
        extra_conditions: Tuple[Condition, ...] = tuple(),
        timelock_info: ConditionValidTimes = ConditionValidTimes(),
    ) -> TransactionRecord:
        send_dict: Dict[str, Any] = {
            "wallet_id": wallet_id,
            "fee": fee,
            "memos": memos if memos else [],
            "extra_conditions": conditions_to_json_dicts(extra_conditions),
            **tx_config.to_json_dict(),
            **timelock_info.to_json_dict(),
        }
        if amount is not None and inner_address is not None:
            send_dict["amount"] = amount
            send_dict["inner_address"] = inner_address
        elif additions is not None:
            additions_hex = []
            for ad in additions:
                additions_hex.append({"amount": ad["amount"], "puzzle_hash": ad["puzzle_hash"].hex()})
                if "memos" in ad:
                    additions_hex[-1]["memos"] = ad["memos"]
            send_dict["additions"] = additions_hex
        else:
            raise ValueError("Must specify either amount and inner_address or additions")
        if removals is not None and len(removals) > 0:
            send_dict["coins"] = [c.to_json_dict() for c in removals]
        if cat_discrepancy is not None:
            send_dict["extra_delta"] = cat_discrepancy[0]
            send_dict["tail_reveal"] = bytes(cat_discrepancy[1]).hex()
            send_dict["tail_solution"] = bytes(cat_discrepancy[2]).hex()
        res = await self.fetch("cat_spend", send_dict)
        return TransactionRecord.from_json_dict_convenience(res["transaction"])

    # Offers
    async def create_offer_for_ids(
        self,
        offer_dict: Dict[Union[uint32, str], int],
        tx_config: TXConfig,
        driver_dict: Dict[str, Any] = None,
        solver: Dict[str, Any] = None,
        fee=uint64(0),
        validate_only: bool = False,
        extra_conditions: Tuple[Condition, ...] = tuple(),
        timelock_info: ConditionValidTimes = ConditionValidTimes(),
    ) -> Tuple[Optional[Offer], TradeRecord]:
        send_dict: Dict[str, int] = {str(key): value for key, value in offer_dict.items()}

        req = {
            "offer": send_dict,
            "validate_only": validate_only,
            "fee": fee,
            "extra_conditions": conditions_to_json_dicts(extra_conditions),
            **tx_config.to_json_dict(),
            **timelock_info.to_json_dict(),
        }
        if driver_dict is not None:
            req["driver_dict"] = driver_dict
        if solver is not None:
            req["solver"] = solver
        res = await self.fetch("create_offer_for_ids", req)
        offer: Optional[Offer] = None if validate_only else Offer.from_bech32(res["offer"])
        offer_str: str = "" if offer is None else bytes(offer).hex()
        return offer, TradeRecord.from_json_dict_convenience(res["trade_record"], offer_str)

    async def get_offer_summary(
        self, offer: Offer, advanced: bool = False
    ) -> Tuple[bytes32, Dict[str, Dict[str, int]]]:
        res = await self.fetch("get_offer_summary", {"offer": offer.to_bech32(), "advanced": advanced})
        return bytes32.from_hexstr(res["id"]), res["summary"]

    async def check_offer_validity(self, offer: Offer) -> Tuple[bytes32, bool]:
        res = await self.fetch("check_offer_validity", {"offer": offer.to_bech32()})
        return bytes32.from_hexstr(res["id"]), res["valid"]

    async def take_offer(
        self,
        offer: Offer,
        tx_config: TXConfig,
        solver: Dict[str, Any] = None,
        fee=uint64(0),
        extra_conditions: Tuple[Condition, ...] = tuple(),
        timelock_info: ConditionValidTimes = ConditionValidTimes(),
    ) -> TradeRecord:
        req = {
            "offer": offer.to_bech32(),
            "fee": fee,
            "extra_conditions": conditions_to_json_dicts(extra_conditions),
            **tx_config.to_json_dict(),
            **timelock_info.to_json_dict(),
        }
        if solver is not None:
            req["solver"] = solver
        res = await self.fetch("take_offer", req)
        return TradeRecord.from_json_dict_convenience(res["trade_record"])

    async def get_offer(self, trade_id: bytes32, file_contents: bool = False) -> TradeRecord:
        res = await self.fetch("get_offer", {"trade_id": trade_id.hex(), "file_contents": file_contents})
        offer_str = bytes(Offer.from_bech32(res["offer"])).hex() if file_contents else ""
        return TradeRecord.from_json_dict_convenience(res["trade_record"], offer_str)

    async def get_all_offers(
        self,
        start: int = 0,
        end: int = 50,
        sort_key: str = None,
        reverse: bool = False,
        file_contents: bool = False,
        exclude_my_offers: bool = False,
        exclude_taken_offers: bool = False,
        include_completed: bool = False,
    ) -> List[TradeRecord]:
        res = await self.fetch(
            "get_all_offers",
            {
                "start": start,
                "end": end,
                "sort_key": sort_key,
                "reverse": reverse,
                "file_contents": file_contents,
                "exclude_my_offers": exclude_my_offers,
                "exclude_taken_offers": exclude_taken_offers,
                "include_completed": include_completed,
            },
        )

        records = []
        if file_contents:
            optional_offers = [bytes(Offer.from_bech32(o)).hex() for o in res["offers"]]
        else:
            optional_offers = [""] * len(res["trade_records"])
        for record, offer in zip(res["trade_records"], optional_offers):
            records.append(TradeRecord.from_json_dict_convenience(record, offer))

        return records

    async def cancel_offer(
        self,
        trade_id: bytes32,
        tx_config: TXConfig,
        fee=uint64(0),
        secure: bool = True,
        extra_conditions: Tuple[Condition, ...] = tuple(),
        timelock_info: ConditionValidTimes = ConditionValidTimes(),
    ):
        await self.fetch(
            "cancel_offer",
            {
                "trade_id": trade_id.hex(),
                "secure": secure,
                "fee": fee,
                "extra_conditions": conditions_to_json_dicts(extra_conditions),
                **tx_config.to_json_dict(),
                **timelock_info.to_json_dict(),
            },
        )

    async def cancel_offers(
        self,
        tx_config: TXConfig,
        fee=uint64(0),
        secure: bool = True,
        batch_size: int = 5,
        cancel_all: bool = False,
        asset_id: Optional[bytes32] = None,
        extra_conditions: Tuple[Condition, ...] = tuple(),
        timelock_info: ConditionValidTimes = ConditionValidTimes(),
    ) -> None:
        await self.fetch(
            "cancel_offers",
            {
                "secure": secure,
                "batch_fee": fee,
                "secure": secure,
                "batch_size": batch_size,
                "cancel_all": cancel_all,
                "asset_id": None if asset_id is None else asset_id.hex(),
                "extra_conditions": conditions_to_json_dicts(extra_conditions),
                **tx_config.to_json_dict(),
                **timelock_info.to_json_dict(),
            },
        )

    # NFT wallet
    async def create_new_nft_wallet(self, did_id, name=None) -> dict[str, Any]:
        request: Dict[str, Any] = {
            "wallet_type": "nft_wallet",
            "did_id": did_id,
            "name": name,
        }
        response = await self.fetch("create_new_wallet", request)
        return response

    async def mint_nft(
        self,
        wallet_id,
        royalty_address,
        target_address,
        hash,
        uris,
        tx_config: TXConfig,
        meta_hash="",
        meta_uris=[],
        license_hash="",
        license_uris=[],
        edition_total=1,
        edition_number=1,
        fee=0,
        royalty_percentage=0,
        did_id=None,
        extra_conditions: Tuple[Condition, ...] = tuple(),
        timelock_info: ConditionValidTimes = ConditionValidTimes(),
    ):
        request: Dict[str, Any] = {
            "wallet_id": wallet_id,
            "royalty_address": royalty_address,
            "target_address": target_address,
            "hash": hash,
            "uris": uris,
            "meta_hash": meta_hash,
            "meta_uris": meta_uris,
            "license_hash": license_hash,
            "license_uris": license_uris,
            "edition_number": edition_number,
            "edition_total": edition_total,
            "royalty_percentage": royalty_percentage,
            "did_id": did_id,
            "fee": fee,
            "extra_conditions": conditions_to_json_dicts(extra_conditions),
            **tx_config.to_json_dict(),
            **timelock_info.to_json_dict(),
        }
        response = await self.fetch("nft_mint_nft", request)
        return response

    async def add_uri_to_nft(
        self,
        wallet_id,
        nft_coin_id,
        key,
        uri,
        fee,
        tx_config: TXConfig,
        extra_conditions: Tuple[Condition, ...] = tuple(),
        timelock_info: ConditionValidTimes = ConditionValidTimes(),
    ):
        request: Dict[str, Any] = {
            "wallet_id": wallet_id,
            "nft_coin_id": nft_coin_id,
            "uri": uri,
            "key": key,
            "fee": fee,
            "extra_conditions": conditions_to_json_dicts(extra_conditions),
            **tx_config.to_json_dict(),
            **timelock_info.to_json_dict(),
        }
        response = await self.fetch("nft_add_uri", request)
        return response

    async def nft_calculate_royalties(
        self,
        royalty_assets_dict: Dict[Any, Tuple[Any, uint16]],
        fungible_asset_dict: Dict[Any, uint64],
    ) -> Dict[Any, List[Dict[str, Any]]]:
        request: Dict[str, Any] = {
            "royalty_assets": [
                {"asset": id, "royalty_address": royalty_info[0], "royalty_percentage": royalty_info[1]}
                for id, royalty_info in royalty_assets_dict.items()
            ],
            "fungible_assets": [{"asset": name, "amount": amount} for name, amount in fungible_asset_dict.items()],
        }
        response = await self.fetch("nft_calculate_royalties", request)
        del response["success"]
        return response

    async def get_nft_info(self, coin_id: str, latest: bool = True):
        request: Dict[str, Any] = {"coin_id": coin_id, "latest": latest}
        response = await self.fetch("nft_get_info", request)
        return response

    async def transfer_nft(
        self,
        wallet_id,
        nft_coin_id,
        target_address,
        fee,
        tx_config: TXConfig,
        extra_conditions: Tuple[Condition, ...] = tuple(),
        timelock_info: ConditionValidTimes = ConditionValidTimes(),
    ):
        request: Dict[str, Any] = {
            "wallet_id": wallet_id,
            "nft_coin_id": nft_coin_id,
            "target_address": target_address,
            "fee": fee,
            "extra_conditions": conditions_to_json_dicts(extra_conditions),
            **tx_config.to_json_dict(),
            **timelock_info.to_json_dict(),
        }
        response = await self.fetch("nft_transfer_nft", request)
        return response

    async def count_nfts(self, wallet_id: Optional[int]):
        request: Dict[str, Any] = {"wallet_id": wallet_id}
        response = await self.fetch("nft_count_nfts", request)
        return response

    async def list_nfts(self, wallet_id, num: int = 50, start_index: int = 0):
        request: Dict[str, Any] = {"wallet_id": wallet_id, "num": num, "start_index": start_index}
        response = await self.fetch("nft_get_nfts", request)
        return response

    async def set_nft_did(
        self,
        wallet_id,
        did_id,
        nft_coin_id,
        fee,
        tx_config: TXConfig,
        extra_conditions: Tuple[Condition, ...] = tuple(),
        timelock_info: ConditionValidTimes = ConditionValidTimes(),
    ):
        request: Dict[str, Any] = {
            "wallet_id": wallet_id,
            "did_id": did_id,
            "nft_coin_id": nft_coin_id,
            "fee": fee,
            "extra_conditions": conditions_to_json_dicts(extra_conditions),
            **tx_config.to_json_dict(),
            **timelock_info.to_json_dict(),
        }
        response = await self.fetch("nft_set_nft_did", request)
        return response

    async def get_nft_wallet_did(self, wallet_id) -> dict[str, Optional[str]]:
        request: Dict[str, Any] = {"wallet_id": wallet_id}
        response = await self.fetch("nft_get_wallet_did", request)
        return response

    async def nft_mint_bulk(
        self,
        wallet_id: int,
        metadata_list: List[Dict[str, Any]],
        royalty_percentage: Optional[int],
        royalty_address: Optional[str],
        tx_config: TXConfig,
        target_list: Optional[List[str]] = None,
        mint_number_start: Optional[int] = 1,
        mint_total: Optional[int] = None,
        hdd_coins: Optional[List[Dict]] = None,
        hdd_change_target: Optional[str] = None,
        new_innerpuzhash: Optional[str] = None,
        did_coin: Optional[Dict] = None,
        did_lineage_parent: Optional[str] = None,
        mint_from_did: Optional[bool] = False,
        fee: Optional[int] = 0,
        extra_conditions: Tuple[Condition, ...] = tuple(),
        timelock_info: ConditionValidTimes = ConditionValidTimes(),
    ) -> Dict:
        request = {
            "wallet_id": wallet_id,
            "metadata_list": metadata_list,
            "target_list": target_list,
            "royalty_percentage": royalty_percentage,
            "royalty_address": royalty_address,
            "mint_number_start": mint_number_start,
            "mint_total": mint_total,
            "hdd_coins": hdd_coins,
            "hdd_change_target": hdd_change_target,
            "new_innerpuzhash": new_innerpuzhash,
            "did_coin": did_coin,
            "did_lineage_parent": did_lineage_parent,
            "mint_from_did": mint_from_did,
            "fee": fee,
            "extra_conditions": conditions_to_json_dicts(extra_conditions),
            **tx_config.to_json_dict(),
            **timelock_info.to_json_dict(),
        }
        response = await self.fetch("nft_mint_bulk", request)
        return response

    # DataLayer
    async def create_new_dl(
        self,
        root: bytes32,
        fee: uint64,
        extra_conditions: Tuple[Condition, ...] = tuple(),
        timelock_info: ConditionValidTimes = ConditionValidTimes(),
    ) -> Tuple[List[TransactionRecord], bytes32]:
        request = {
            "root": root.hex(),
            "fee": fee,
            "extra_conditions": conditions_to_json_dicts(extra_conditions),
            **timelock_info.to_json_dict(),
        }
        response = await self.fetch("create_new_dl", request)
        txs: List[TransactionRecord] = [
            TransactionRecord.from_json_dict_convenience(tx) for tx in response["transactions"]
        ]
        launcher_id: bytes32 = bytes32.from_hexstr(response["launcher_id"])
        return txs, launcher_id

    async def dl_track_new(self, launcher_id: bytes32) -> None:
        request = {"launcher_id": launcher_id.hex()}
        await self.fetch("dl_track_new", request)
        return None

    async def dl_stop_tracking(self, launcher_id: bytes32) -> None:
        request = {"launcher_id": launcher_id.hex()}
        await self.fetch("dl_stop_tracking", request)
        return None

    async def dl_latest_singleton(
        self, launcher_id: bytes32, only_confirmed: bool = False
    ) -> Optional[SingletonRecord]:
        request = {"launcher_id": launcher_id.hex(), "only_confirmed": only_confirmed}
        response = await self.fetch("dl_latest_singleton", request)
        return None if response["singleton"] is None else SingletonRecord.from_json_dict(response["singleton"])

    async def dl_singletons_by_root(self, launcher_id: bytes32, root: bytes32) -> List[SingletonRecord]:
        request = {"launcher_id": launcher_id.hex(), "root": root.hex()}
        response = await self.fetch("dl_singletons_by_root", request)
        return [SingletonRecord.from_json_dict(single) for single in response["singletons"]]

    async def dl_update_root(
        self,
        launcher_id: bytes32,
        new_root: bytes32,
        fee: uint64,
        extra_conditions: Tuple[Condition, ...] = tuple(),
        timelock_info: ConditionValidTimes = ConditionValidTimes(),
    ) -> TransactionRecord:
        request = {
            "launcher_id": launcher_id.hex(),
            "new_root": new_root.hex(),
            "fee": fee,
            "extra_conditions": conditions_to_json_dicts(extra_conditions),
            **timelock_info.to_json_dict(),
        }
        response = await self.fetch("dl_update_root", request)
        return TransactionRecord.from_json_dict_convenience(response["tx_record"])

    async def dl_update_multiple(
        self,
        update_dictionary: Dict[bytes32, bytes32],
        extra_conditions: Tuple[Condition, ...] = tuple(),
        timelock_info: ConditionValidTimes = ConditionValidTimes(),
    ) -> List[TransactionRecord]:
        updates_as_strings: Dict[str, str] = {}
        for lid, root in update_dictionary.items():
            updates_as_strings[str(lid)] = str(root)
        request = {
            "updates": updates_as_strings,
            "extra_conditions": conditions_to_json_dicts(extra_conditions),
            **timelock_info.to_json_dict(),
        }
        response = await self.fetch("dl_update_multiple", request)
        return [TransactionRecord.from_json_dict_convenience(tx) for tx in response["tx_records"]]

    async def dl_history(
        self,
        launcher_id: bytes32,
        min_generation: Optional[uint32] = None,
        max_generation: Optional[uint32] = None,
        num_results: Optional[uint32] = None,
    ) -> List[SingletonRecord]:
        request = {"launcher_id": launcher_id.hex()}

        if min_generation is not None:
            request["min_generation"] = str(min_generation)
        if max_generation is not None:
            request["max_generation"] = str(max_generation)
        if num_results is not None:
            request["num_results"] = str(num_results)

        response = await self.fetch("dl_history", request)
        return [SingletonRecord.from_json_dict(single) for single in response["history"]]

    async def dl_owned_singletons(self) -> List[SingletonRecord]:
        response = await self.fetch(path="dl_owned_singletons", request_json={})
        return [SingletonRecord.from_json_dict(singleton) for singleton in response["singletons"]]

    async def dl_get_mirrors(self, launcher_id: bytes32) -> List[Mirror]:
        response = await self.fetch(path="dl_get_mirrors", request_json={"launcher_id": launcher_id.hex()})
        return [Mirror.from_json_dict(mirror) for mirror in response["mirrors"]]

    async def dl_new_mirror(
        self,
        launcher_id: bytes32,
        amount: uint64,
        urls: List[bytes],
        fee: uint64 = uint64(0),
        extra_conditions: Tuple[Condition, ...] = tuple(),
        timelock_info: ConditionValidTimes = ConditionValidTimes(),
    ) -> List[TransactionRecord]:
        response = await self.fetch(
            path="dl_new_mirror",
            request_json={
                "launcher_id": launcher_id.hex(),
                "amount": amount,
                "urls": [url.decode("utf8") for url in urls],
                "fee": fee,
                "extra_conditions": conditions_to_json_dicts(extra_conditions),
                **timelock_info.to_json_dict(),
            },
        )
        return [TransactionRecord.from_json_dict_convenience(tx) for tx in response["transactions"]]

    async def dl_delete_mirror(
        self,
        coin_id: bytes32,
        fee: uint64 = uint64(0),
        extra_conditions: Tuple[Condition, ...] = tuple(),
        timelock_info: ConditionValidTimes = ConditionValidTimes(),
    ) -> List[TransactionRecord]:
        response = await self.fetch(
            path="dl_delete_mirror",
            request_json={
                "coin_id": coin_id.hex(),
                "fee": fee,
                "extra_conditions": conditions_to_json_dicts(extra_conditions),
                **timelock_info.to_json_dict(),
            },
        )
        return [TransactionRecord.from_json_dict_convenience(tx) for tx in response["transactions"]]

    async def get_notifications(
        self, ids: Optional[List[bytes32]] = None, pagination: Optional[Tuple[Optional[int], Optional[int]]] = None
    ) -> List[Notification]:
        request: Dict[str, Any] = {}
        if ids is not None:
            request["ids"] = [id.hex() for id in ids]
        if pagination is not None:
            if pagination[0] is not None:
                request["start"] = pagination[0]
            if pagination[1] is not None:
                request["end"] = pagination[1]
        response = await self.fetch("get_notifications", request)
        return [
            Notification(
                bytes32.from_hexstr(notification["id"]),
                bytes.fromhex(notification["message"]),
                uint64(notification["amount"]),
                uint32(notification["height"]),
            )
            for notification in response["notifications"]
        ]

    async def delete_notifications(self, ids: Optional[List[bytes32]] = None) -> bool:
        request: Dict[str, Any] = {}
        if ids is not None:
            request["ids"] = [id.hex() for id in ids]
        response = await self.fetch("delete_notifications", request)
        return response["success"]

    async def send_notification(
        self,
        target: bytes32,
        msg: bytes,
        amount: uint64,
        fee: uint64 = uint64(0),
        extra_conditions: Tuple[Condition, ...] = tuple(),
        timelock_info: ConditionValidTimes = ConditionValidTimes(),
    ) -> TransactionRecord:
        response = await self.fetch(
            "send_notification",
            {
                "target": target.hex(),
                "message": msg.hex(),
                "amount": amount,
                "fee": fee,
                "extra_conditions": conditions_to_json_dicts(extra_conditions),
                **timelock_info.to_json_dict(),
            },
        )
        return TransactionRecord.from_json_dict_convenience(response["tx"])

    async def sign_message_by_address(self, address: str, message: str) -> Tuple[str, str, str]:
        response = await self.fetch("sign_message_by_address", {"address": address, "message": message})
        return response["pubkey"], response["signature"], response["signing_mode"]

    async def sign_message_by_id(self, id: str, message: str) -> Tuple[str, str, str]:
        response = await self.fetch("sign_message_by_id", {"id": id, "message": message})
        return response["pubkey"], response["signature"], response["signing_mode"]

    # DAOs
    async def create_new_dao_wallet(
        self,
        mode: str,
        tx_config: TXConfig,
        dao_rules: Optional[Dict[str, uint64]] = None,
        amount_of_cats: Optional[uint64] = None,
        treasury_id: Optional[bytes32] = None,
        filter_amount: uint64 = uint64(1),
        name: Optional[str] = None,
        fee: uint64 = uint64(0),
        fee_for_cat: uint64 = uint64(0),
        extra_conditions: Tuple[Condition, ...] = tuple(),
    ) -> Dict:
        request: Dict[str, Any] = {
            "wallet_type": "dao_wallet",
            "mode": mode,
            "treasury_id": treasury_id,
            "dao_rules": dao_rules,
            "amount_of_cats": amount_of_cats,
            "filter_amount": filter_amount,
            "name": name,
            "fee": fee,
            "fee_for_cat": fee_for_cat,
            "extra_conditions": list(extra_conditions),
            **tx_config.to_json_dict(),
        }
        response = await self.fetch("create_new_wallet", request)
        return response

    async def dao_get_treasury_id(
        self,
        wallet_id: int,
    ) -> Dict:
        request: Dict[str, Any] = {"wallet_id": wallet_id}
        response = await self.fetch("dao_get_treasury_id", request)
        return response

    async def dao_get_rules(
        self,
        wallet_id: int,
    ) -> Dict:
        request: Dict[str, Any] = {"wallet_id": wallet_id}
        response = await self.fetch("dao_get_rules", request)
        return response

    async def dao_create_proposal(
        self,
        wallet_id: int,
        proposal_type: str,
        tx_config: TXConfig,
        additions: Optional[List[Dict]] = None,
        amount: Optional[uint64] = None,
        inner_address: Optional[str] = None,
        asset_id: Optional[str] = None,
        cat_target_address: Optional[str] = None,
        vote_amount: Optional[int] = None,
        new_dao_rules: Optional[Dict[str, Optional[uint64]]] = None,
        fee: uint64 = uint64(0),
        extra_conditions: Tuple[Condition, ...] = tuple(),
    ) -> Dict:
        request: Dict[str, Any] = {
            "wallet_id": wallet_id,
            "proposal_type": proposal_type,
            "additions": additions,
            "amount": amount,
            "inner_address": inner_address,
            "asset_id": asset_id,
            "cat_target_address": cat_target_address,
            "vote_amount": vote_amount,
            "new_dao_rules": new_dao_rules,
            "fee": fee,
            "extra_conditions": list(extra_conditions),
            **tx_config.to_json_dict(),
        }

        response = await self.fetch("dao_create_proposal", request)
        return response

    async def dao_get_proposal_state(self, wallet_id: int, proposal_id: str):
        request: Dict[str, Any] = {"wallet_id": wallet_id, "proposal_id": proposal_id}
        response = await self.fetch("dao_get_proposal_state", request)
        return response

    async def dao_parse_proposal(self, wallet_id: int, proposal_id: str):
        request: Dict[str, Any] = {"wallet_id": wallet_id, "proposal_id": proposal_id}
        response = await self.fetch("dao_parse_proposal", request)
        return response

    async def dao_vote_on_proposal(
        self,
        wallet_id: int,
        proposal_id: str,
        vote_amount: uint64,
        tx_config: TXConfig,
        is_yes_vote: bool = True,
        fee: uint64 = uint64(0),
        extra_conditions: Tuple[Condition, ...] = tuple(),
    ):
        request: Dict[str, Any] = {
            "wallet_id": wallet_id,
            "proposal_id": proposal_id,
            "vote_amount": vote_amount,
            "is_yes_vote": is_yes_vote,
            "fee": fee,
            "extra_conditions": list(extra_conditions),
            **tx_config.to_json_dict(),
        }
        response = await self.fetch("dao_vote_on_proposal", request)
        return response

    async def dao_get_proposals(self, wallet_id: int, include_closed: bool = True):
        request: Dict[str, Any] = {"wallet_id": wallet_id, "include_closed": include_closed}
        response = await self.fetch("dao_get_proposals", request)
        return response

    async def dao_close_proposal(
        self,
        wallet_id: int,
        proposal_id: str,
        tx_config: TXConfig,
        self_destruct: bool = None,
        fee: uint64 = uint64(0),
        extra_conditions: Tuple[Condition, ...] = tuple(),
    ):
        request: Dict[str, Any] = {
            "wallet_id": wallet_id,
            "proposal_id": proposal_id,
            "self_destruct": self_destruct,
            "fee": fee,
            "extra_conditions": list(extra_conditions),
            **tx_config.to_json_dict(),
        }
        response = await self.fetch("dao_close_proposal", request)
        return response

    async def dao_free_coins_from_finished_proposals(
        self,
        wallet_id: int,
        tx_config: TXConfig,
        fee: uint64 = uint64(0),
        extra_conditions: Tuple[Condition, ...] = tuple(),
    ):
        request: Dict[str, Any] = {
            "wallet_id": wallet_id,
            "fee": fee,
            "extra_conditions": list(extra_conditions),
            **tx_config.to_json_dict(),
        }
        response = await self.fetch("dao_free_coins_from_finished_proposals", request)
        return response

    async def dao_get_treasury_balance(self, wallet_id: int):
        request: Dict[str, Any] = {"wallet_id": wallet_id}
        response = await self.fetch("dao_get_treasury_balance", request)
        return response

    async def dao_add_funds_to_treasury(
        self,
        wallet_id: int,
        funding_wallet_id: int,
        amount: uint64,
        tx_config: TXConfig,
        fee: uint64 = uint64(0),
        extra_conditions: Tuple[Condition, ...] = tuple(),
    ):
        request: Dict[str, Any] = {
            "wallet_id": wallet_id,
            "funding_wallet_id": funding_wallet_id,
            "amount": amount,
            "fee": fee,
            "extra_conditions": list(extra_conditions),
            **tx_config.to_json_dict(),
        }
        response = await self.fetch("dao_add_funds_to_treasury", request)
        return response

    async def dao_send_to_lockup(
        self,
        wallet_id: int,
        amount: uint64,
        tx_config: TXConfig,
        fee: uint64 = uint64(0),
        extra_conditions: Tuple[Condition, ...] = tuple(),
    ):
        request: Dict[str, Any] = {
            "wallet_id": wallet_id,
            "amount": amount,
            "fee": fee,
            "extra_conditions": list(extra_conditions),
            **tx_config.to_json_dict(),
        }
        response = await self.fetch("dao_send_to_lockup", request)
        return response

    async def dao_exit_lockup(
        self,
        wallet_id: int,
        tx_config: TXConfig,
        coins: Optional[List[Dict]] = None,
        fee: uint64 = uint64(0),
        extra_conditions: Tuple[Condition, ...] = tuple(),
    ):
        request: Dict[str, Any] = {
            "wallet_id": wallet_id,
            "coins": coins,
            "fee": fee,
            "extra_conditions": list(extra_conditions),
            **tx_config.to_json_dict(),
        }
        response = await self.fetch("dao_exit_lockup", request)
        return response

    async def dao_adjust_filter_level(self, wallet_id: int, filter_level: int):
        request: Dict[str, Any] = {"wallet_id": wallet_id, "filter_level": filter_level}
        response = await self.fetch("dao_adjust_filter_level", request)
        return response

    async def vc_mint(
        self,
        did_id: bytes32,
        tx_config: TXConfig,
        target_address: Optional[bytes32] = None,
        fee: uint64 = uint64(0),
        extra_conditions: Tuple[Condition, ...] = tuple(),
        timelock_info: ConditionValidTimes = ConditionValidTimes(),
    ) -> Tuple[VCRecord, List[TransactionRecord]]:
        response = await self.fetch(
            "vc_mint",
            {
                "did_id": encode_puzzle_hash(did_id, "rpc"),
                "target_address": encode_puzzle_hash(target_address, "rpc") if target_address is not None else None,
                "fee": fee,
                "extra_conditions": conditions_to_json_dicts(extra_conditions),
                **tx_config.to_json_dict(),
                **timelock_info.to_json_dict(),
            },
        )
        return VCRecord.from_json_dict(response["vc_record"]), [
            TransactionRecord.from_json_dict_convenience(tx) for tx in response["transactions"]
        ]

    async def vc_get(self, vc_id: bytes32) -> Optional[VCRecord]:
        response = await self.fetch("vc_get", {"vc_id": vc_id.hex()})
        return None if response["vc_record"] is None else VCRecord.from_json_dict(response["vc_record"])

    async def vc_get_list(self, start: int = 0, count: int = 50) -> Tuple[List[VCRecord], Dict[str, Any]]:
        response = await self.fetch("vc_get_list", {"start": start, "count": count})
        return [VCRecord.from_json_dict(rec) for rec in response["vc_records"]], response["proofs"]

    async def vc_spend(
        self,
        vc_id: bytes32,
        tx_config: TXConfig,
        new_puzhash: Optional[bytes32] = None,
        new_proof_hash: Optional[bytes32] = None,
        provider_inner_puzhash: Optional[bytes32] = None,
        fee: uint64 = uint64(0),
        extra_conditions: Tuple[Condition, ...] = tuple(),
        timelock_info: ConditionValidTimes = ConditionValidTimes(),
    ) -> List[TransactionRecord]:
        response = await self.fetch(
            "vc_spend",
            {
                "vc_id": vc_id.hex(),
                "new_puzhash": new_puzhash.hex() if new_puzhash is not None else new_puzhash,
                "new_proof_hash": new_proof_hash.hex() if new_proof_hash is not None else new_proof_hash,
                "provider_inner_puzhash": provider_inner_puzhash.hex()
                if provider_inner_puzhash is not None
                else provider_inner_puzhash,
                "fee": fee,
                "extra_conditions": conditions_to_json_dicts(extra_conditions),
                **tx_config.to_json_dict(),
                **timelock_info.to_json_dict(),
            },
        )
        return [TransactionRecord.from_json_dict_convenience(tx) for tx in response["transactions"]]

    async def vc_add_proofs(self, proofs: Dict[str, Any]) -> None:
        await self.fetch("vc_add_proofs", {"proofs": proofs})

    async def vc_get_proofs_for_root(self, root: bytes32) -> Dict[str, Any]:
        response = await self.fetch("vc_get_proofs_for_root", {"root": root.hex()})
        return response["proofs"]

    async def vc_revoke(
        self,
        vc_parent_id: bytes32,
        tx_config: TXConfig,
        fee: uint64 = uint64(0),
        extra_conditions: Tuple[Condition, ...] = tuple(),
        timelock_info: ConditionValidTimes = ConditionValidTimes(),
    ) -> List[TransactionRecord]:
        response = await self.fetch(
            "vc_revoke",
            {
                "vc_parent_id": vc_parent_id.hex(),
                "fee": fee,
                "extra_conditions": conditions_to_json_dicts(extra_conditions),
                **tx_config.to_json_dict(),
                **timelock_info.to_json_dict(),
            },
        )
        return [TransactionRecord.from_json_dict_convenience(tx) for tx in response["transactions"]]

    async def crcat_approve_pending(
        self,
        wallet_id: uint32,
        min_amount_to_claim: uint64,
        tx_config: TXConfig,
        fee: uint64 = uint64(0),
    ) -> List[TransactionRecord]:
        response = await self.fetch(
            "crcat_approve_pending",
            {
                "wallet_id": wallet_id,
                "min_amount_to_claim": min_amount_to_claim,
                "fee": fee,
                **tx_config.to_json_dict(),
            },
        )
        return [TransactionRecord.from_json_dict_convenience(tx) for tx in response["transactions"]]
