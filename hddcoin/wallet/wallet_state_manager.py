from __future__ import annotations

import asyncio
import logging
import multiprocessing.context
import time
import traceback
from contextlib import asynccontextmanager
from pathlib import Path
from typing import (
    TYPE_CHECKING,
    Any,
    AsyncIterator,
    Callable,
    Dict,
    Iterator,
    List,
    Optional,
    Set,
    Tuple,
    Type,
    TypeVar,
    Union,
)

import aiosqlite
from chia_rs import G1Element, G2Element, PrivateKey

from hddcoin.consensus.block_rewards import calculate_base_farmer_reward, calculate_pool_reward
from hddcoin.consensus.coinbase import farmer_parent_id, pool_parent_id
from hddcoin.consensus.constants import ConsensusConstants
from hddcoin.data_layer.data_layer_wallet import DataLayerWallet
from hddcoin.data_layer.dl_wallet_store import DataLayerStore
from hddcoin.pools.pool_puzzles import (
    SINGLETON_LAUNCHER_HASH,
    get_most_recent_singleton_coin_from_coin_spend,
    solution_to_pool_state,
)
from hddcoin.pools.pool_wallet import PoolWallet
from hddcoin.protocols.wallet_protocol import CoinState
from hddcoin.rpc.rpc_server import StateChangedProtocol
from hddcoin.server.outbound_message import NodeType
from hddcoin.server.server import HDDcoinServer
from hddcoin.server.ws_connection import WSHDDcoinConnection
from hddcoin.types.announcement import Announcement
from hddcoin.types.blockchain_format.coin import Coin
from hddcoin.types.blockchain_format.program import Program
from hddcoin.types.blockchain_format.sized_bytes import bytes32
from hddcoin.types.coin_record import CoinRecord
from hddcoin.types.coin_spend import CoinSpend, compute_additions
from hddcoin.types.mempool_inclusion_status import MempoolInclusionStatus
from hddcoin.types.spend_bundle import SpendBundle
from hddcoin.util.bech32m import encode_puzzle_hash
from hddcoin.util.db_synchronous import db_synchronous_on
from hddcoin.util.db_wrapper import DBWrapper2
from hddcoin.util.errors import Err
from hddcoin.util.hash import std_hash
from hddcoin.util.ints import uint16, uint32, uint64, uint128
from hddcoin.util.lru_cache import LRUCache
from hddcoin.util.misc import UInt32Range, UInt64Range, VersionedBlob
from hddcoin.util.path import path_from_root
from hddcoin.util.streamable import Streamable
from hddcoin.wallet.cat_wallet.cat_constants import DEFAULT_CATS
from hddcoin.wallet.cat_wallet.cat_info import CATCoinData, CATInfo, CRCATInfo
from hddcoin.wallet.cat_wallet.cat_utils import CAT_MOD, CAT_MOD_HASH, construct_cat_puzzle, match_cat_puzzle
from hddcoin.wallet.cat_wallet.cat_wallet import CATWallet
from hddcoin.wallet.cat_wallet.dao_cat_wallet import DAOCATWallet
from hddcoin.wallet.conditions import Condition, ConditionValidTimes, parse_timelock_info
from hddcoin.wallet.dao_wallet.dao_utils import (
    get_p2_singleton_puzhash,
    match_dao_cat_puzzle,
    match_finished_puzzle,
    match_funding_puzzle,
    match_proposal_puzzle,
    match_treasury_puzzle,
)
from hddcoin.wallet.dao_wallet.dao_wallet import DAOWallet
from hddcoin.wallet.db_wallet.db_wallet_puzzles import MIRROR_PUZZLE_HASH
from hddcoin.wallet.derivation_record import DerivationRecord
from hddcoin.wallet.derive_keys import (
    _derive_path,
    _derive_path_unhardened,
    master_sk_to_wallet_sk,
    master_sk_to_wallet_sk_intermediate,
    master_sk_to_wallet_sk_unhardened,
    master_sk_to_wallet_sk_unhardened_intermediate,
)
from hddcoin.wallet.did_wallet.did_info import DIDCoinData
from hddcoin.wallet.did_wallet.did_wallet import DIDWallet
from hddcoin.wallet.did_wallet.did_wallet_puzzles import DID_INNERPUZ_MOD, match_did_puzzle
from hddcoin.wallet.key_val_store import KeyValStore
from hddcoin.wallet.nft_wallet.nft_puzzles import get_metadata_and_phs, get_new_owner_did
from hddcoin.wallet.nft_wallet.nft_wallet import NFTWallet
from hddcoin.wallet.nft_wallet.uncurry_nft import NFTCoinData, UncurriedNFT
from hddcoin.wallet.notification_manager import NotificationManager
from hddcoin.wallet.outer_puzzles import AssetType
from hddcoin.wallet.payment import Payment
from hddcoin.wallet.puzzle_drivers import PuzzleInfo
from hddcoin.wallet.puzzles.clawback.drivers import generate_clawback_spend_bundle, match_clawback_puzzle
from hddcoin.wallet.puzzles.clawback.metadata import ClawbackMetadata, ClawbackVersion
from hddcoin.wallet.puzzles.p2_delegated_puzzle_or_hidden_puzzle import (
    DEFAULT_HIDDEN_PUZZLE_HASH,
    calculate_synthetic_secret_key,
    puzzle_hash_for_synthetic_public_key,
)
from hddcoin.wallet.sign_coin_spends import sign_coin_spends
from hddcoin.wallet.singleton import create_singleton_puzzle, get_inner_puzzle_from_singleton, get_singleton_id_from_puzzle
from hddcoin.wallet.trade_manager import TradeManager
from hddcoin.wallet.trading.trade_status import TradeStatus
from hddcoin.wallet.transaction_record import TransactionRecord
from hddcoin.wallet.uncurried_puzzle import uncurry_puzzle
from hddcoin.wallet.util.address_type import AddressType
from hddcoin.wallet.util.compute_hints import compute_spend_hints_and_additions
from hddcoin.wallet.util.compute_memos import compute_memos
from hddcoin.wallet.util.puzzle_decorator import PuzzleDecoratorManager
from hddcoin.wallet.util.query_filter import HashFilter
from hddcoin.wallet.util.transaction_type import CLAWBACK_INCOMING_TRANSACTION_TYPES, TransactionType
from hddcoin.wallet.util.tx_config import TXConfig, TXConfigLoader
from hddcoin.wallet.util.wallet_sync_utils import (
    PeerRequestException,
    fetch_coin_spend_for_coin_state,
    last_change_height_cs,
)
from hddcoin.wallet.util.wallet_types import CoinType, WalletIdentifier, WalletType
from hddcoin.wallet.vc_wallet.cr_cat_drivers import CRCAT, ProofsChecker, construct_pending_approval_state
from hddcoin.wallet.vc_wallet.cr_cat_wallet import CRCATWallet
from hddcoin.wallet.vc_wallet.vc_drivers import VerifiedCredential
from hddcoin.wallet.vc_wallet.vc_store import VCStore
from hddcoin.wallet.vc_wallet.vc_wallet import VCWallet
from hddcoin.wallet.wallet import Wallet
from hddcoin.wallet.wallet_blockchain import WalletBlockchain
from hddcoin.wallet.wallet_coin_record import MetadataTypes, WalletCoinRecord
from hddcoin.wallet.wallet_coin_store import WalletCoinStore
from hddcoin.wallet.wallet_info import WalletInfo
from hddcoin.wallet.wallet_interested_store import WalletInterestedStore
from hddcoin.wallet.wallet_nft_store import WalletNftStore
from hddcoin.wallet.wallet_pool_store import WalletPoolStore
from hddcoin.wallet.wallet_protocol import WalletProtocol
from hddcoin.wallet.wallet_puzzle_store import WalletPuzzleStore
from hddcoin.wallet.wallet_retry_store import WalletRetryStore
from hddcoin.wallet.wallet_transaction_store import WalletTransactionStore
from hddcoin.wallet.wallet_user_store import WalletUserStore

TWalletType = TypeVar("TWalletType", bound=WalletProtocol[Any])

if TYPE_CHECKING:
    from hddcoin.wallet.wallet_node import WalletNode


PendingTxCallback = Callable[[], None]


class WalletStateManager:
    interested_ph_cache: Dict[bytes32, List[int]] = {}
    interested_coin_cache: Dict[bytes32, List[int]] = {}
    constants: ConsensusConstants
    config: Dict[str, Any]
    tx_store: WalletTransactionStore
    puzzle_store: WalletPuzzleStore
    user_store: WalletUserStore
    nft_store: WalletNftStore
    vc_store: VCStore
    basic_store: KeyValStore

    # Makes sure only one asyncio thread is changing the blockchain state at one time
    lock: asyncio.Lock

    log: logging.Logger

    # TODO Don't allow user to send tx until wallet is synced
    _sync_target: Optional[uint32]

    state_changed_callback: Optional[StateChangedProtocol] = None
    pending_tx_callback: Optional[PendingTxCallback]
    db_path: Path
    db_wrapper: DBWrapper2

    main_wallet: Wallet
    wallets: Dict[uint32, WalletProtocol[Any]]
    private_key: PrivateKey

    trade_manager: TradeManager
    notification_manager: NotificationManager
    blockchain: WalletBlockchain
    coin_store: WalletCoinStore
    interested_store: WalletInterestedStore
    retry_store: WalletRetryStore
    multiprocessing_context: multiprocessing.context.BaseContext
    server: HDDcoinServer
    root_path: Path
    wallet_node: WalletNode
    pool_store: WalletPoolStore
    dl_store: DataLayerStore
    default_cats: Dict[str, Any]
    asset_to_wallet_map: Dict[AssetType, Any]
    initial_num_public_keys: int
    decorator_manager: PuzzleDecoratorManager

    @staticmethod
    async def create(
        private_key: PrivateKey,
        config: Dict[str, Any],
        db_path: Path,
        constants: ConsensusConstants,
        server: HDDcoinServer,
        root_path: Path,
        wallet_node: WalletNode,
    ) -> WalletStateManager:
        self = WalletStateManager()

        self.config = config
        self.constants = constants
        self.server = server
        self.root_path = root_path
        self.log = logging.getLogger(__name__)
        self.lock = asyncio.Lock()
        self.log.debug(f"Starting in db path: {db_path}")
        fingerprint = private_key.get_g1().get_fingerprint()
        sql_log_path: Optional[Path] = None
        if self.config.get("log_sqlite_cmds", False):
            sql_log_path = path_from_root(self.root_path, "log/wallet_sql.log")
            self.log.info(f"logging SQL commands to {sql_log_path}")

        self.db_wrapper = await DBWrapper2.create(
            database=db_path,
            reader_count=self.config.get("db_readers", 4),
            log_path=sql_log_path,
            synchronous=db_synchronous_on(self.config.get("db_sync", "auto")),
        )

        self.initial_num_public_keys = config["initial_num_public_keys"]
        min_num_public_keys = 425
        if not config.get("testing", False) and self.initial_num_public_keys < min_num_public_keys:
            self.initial_num_public_keys = min_num_public_keys

        self.coin_store = await WalletCoinStore.create(self.db_wrapper)
        self.tx_store = await WalletTransactionStore.create(self.db_wrapper)
        self.puzzle_store = await WalletPuzzleStore.create(self.db_wrapper)
        self.user_store = await WalletUserStore.create(self.db_wrapper)
        self.nft_store = await WalletNftStore.create(self.db_wrapper)
        self.vc_store = await VCStore.create(self.db_wrapper)
        self.basic_store = await KeyValStore.create(self.db_wrapper)
        self.trade_manager = await TradeManager.create(self, self.db_wrapper)
        self.notification_manager = await NotificationManager.create(self, self.db_wrapper)
        self.pool_store = await WalletPoolStore.create(self.db_wrapper)
        self.dl_store = await DataLayerStore.create(self.db_wrapper)
        self.interested_store = await WalletInterestedStore.create(self.db_wrapper)
        self.retry_store = await WalletRetryStore.create(self.db_wrapper)
        self.default_cats = DEFAULT_CATS

        self.wallet_node = wallet_node
        self._sync_target = None
        self.blockchain = await WalletBlockchain.create(self.basic_store, self.constants)
        self.state_changed_callback = None
        self.pending_tx_callback = None
        self.db_path = db_path
        puzzle_decorators = self.config.get("puzzle_decorators", {}).get(fingerprint, [])
        self.decorator_manager = PuzzleDecoratorManager.create(puzzle_decorators)

        main_wallet_info = await self.user_store.get_wallet_by_id(1)
        assert main_wallet_info is not None

        self.private_key = private_key
        self.main_wallet = await Wallet.create(self, main_wallet_info)

        self.wallets = {main_wallet_info.id: self.main_wallet}

        self.asset_to_wallet_map = {
            AssetType.CAT: CATWallet,
        }

        wallet: Optional[WalletProtocol[Any]] = None
        for wallet_info in await self.get_all_wallet_info_entries():
            wallet_type = WalletType(wallet_info.type)
            if wallet_type == WalletType.STANDARD_WALLET:
                if wallet_info.id == 1:
                    continue
                wallet = await Wallet.create(self, wallet_info)
            elif wallet_type == WalletType.CAT:
                wallet = await CATWallet.create(
                    self,
                    self.main_wallet,
                    wallet_info,
                )
            elif wallet_type == WalletType.DECENTRALIZED_ID:
                wallet = await DIDWallet.create(
                    self,
                    self.main_wallet,
                    wallet_info,
                )
            elif wallet_type == WalletType.NFT:
                wallet = await NFTWallet.create(
                    self,
                    self.main_wallet,
                    wallet_info,
                )
            elif wallet_type == WalletType.POOLING_WALLET:
                wallet = await PoolWallet.create_from_db(
                    self,
                    self.main_wallet,
                    wallet_info,
                )
            elif wallet_type == WalletType.DATA_LAYER:  # pragma: no cover
                wallet = await DataLayerWallet.create(
                    self,
                    wallet_info,
                )
            elif wallet_type == WalletType.DAO:  # pragma: no cover
                wallet = await DAOWallet.create(
                    self,
                    self.main_wallet,
                    wallet_info,
                )
            elif wallet_type == WalletType.DAO_CAT:  # pragma: no cover
                wallet = await DAOCATWallet.create(
                    self,
                    self.main_wallet,
                    wallet_info,
                )
            elif wallet_type == WalletType.VC:  # pragma: no cover
                wallet = await VCWallet.create(
                    self,
                    self.main_wallet,
                    wallet_info,
                )
            elif wallet_type == WalletType.CRCAT:  # pragma: no cover
                wallet = await CRCATWallet.create(
                    self,
                    self.main_wallet,
                    wallet_info,
                )
            if wallet is not None:
                self.wallets[wallet_info.id] = wallet

        return self

    def get_public_key_unhardened(self, index: uint32) -> G1Element:
        return master_sk_to_wallet_sk_unhardened(self.private_key, index).get_g1()

    async def get_private_key(self, puzzle_hash: bytes32) -> PrivateKey:
        record = await self.puzzle_store.record_for_puzzle_hash(puzzle_hash)
        if record is None:
            raise ValueError(f"No key for puzzle hash: {puzzle_hash.hex()}")
        if record.hardened:
            return master_sk_to_wallet_sk(self.private_key, record.index)
        return master_sk_to_wallet_sk_unhardened(self.private_key, record.index)

    async def get_synthetic_private_key_for_puzzle_hash(self, puzzle_hash: bytes32) -> Optional[PrivateKey]:
        record = await self.puzzle_store.record_for_puzzle_hash(puzzle_hash)
        if record is None:
            return None
        if record.hardened:
            base_key = master_sk_to_wallet_sk(self.private_key, record.index)
        else:
            base_key = master_sk_to_wallet_sk_unhardened(self.private_key, record.index)

        return calculate_synthetic_secret_key(base_key, DEFAULT_HIDDEN_PUZZLE_HASH)

    async def get_private_key_for_pubkey(self, pubkey: G1Element) -> Optional[PrivateKey]:
        record = await self.puzzle_store.record_for_pubkey(pubkey)
        if record is None:
            return None
        if record.hardened:
            return master_sk_to_wallet_sk(self.private_key, record.index)
        return master_sk_to_wallet_sk_unhardened(self.private_key, record.index)

    def get_wallet(self, id: uint32, required_type: Type[TWalletType]) -> TWalletType:
        wallet = self.wallets[id]
        if not isinstance(wallet, required_type):
            raise Exception(
                f"wallet id {id} is of type {type(wallet).__name__} but type {required_type.__name__} is required",
            )

        return wallet

    async def create_more_puzzle_hashes(
        self,
        from_zero: bool = False,
        mark_existing_as_used: bool = True,
        up_to_index: Optional[uint32] = None,
        num_additional_phs: Optional[int] = None,
    ) -> None:
        """
        For all wallets in the user store, generates the first few puzzle hashes so
        that we can restore the wallet from only the private keys.
        """
        targets = list(self.wallets.keys())
        self.log.debug("Target wallets to generate puzzle hashes for: %s", repr(targets))
        unused: Optional[uint32] = (
            uint32(up_to_index + 1) if up_to_index is not None else await self.puzzle_store.get_unused_derivation_path()
        )
        if unused is None:
            # This handles the case where the database has entries but they have all been used
            unused = await self.puzzle_store.get_last_derivation_path()
            self.log.debug("Tried finding unused: %s", unused)
            if unused is None:
                # This handles the case where the database is empty
                unused = uint32(0)

        self.log.debug(f"Requested to generate puzzle hashes to at least index {unused}")
        start_t = time.time()
        to_generate = num_additional_phs if num_additional_phs is not None else self.initial_num_public_keys
        new_paths: bool = False

        for wallet_id in targets:
            target_wallet = self.wallets[wallet_id]
            if not target_wallet.require_derivation_paths():
                self.log.debug("Skipping wallet %s as no derivation paths required", wallet_id)
                continue
            last: Optional[uint32] = await self.puzzle_store.get_last_derivation_path_for_wallet(wallet_id)
            self.log.debug(
                "Fetched last record for wallet %r:  %s (from_zero=%r, unused=%r)", wallet_id, last, from_zero, unused
            )
            start_index = 0
            derivation_paths: List[DerivationRecord] = []

            if last is not None:
                start_index = last + 1

            # If the key was replaced (from_zero=True), we should generate the puzzle hashes for the new key
            if from_zero:
                start_index = 0
            last_index = unused + to_generate
            if start_index >= last_index:
                self.log.debug(f"Nothing to create for for wallet_id: {wallet_id}, index: {start_index}")
            else:
                creating_msg = (
                    f"Creating puzzle hashes from {start_index} to {last_index - 1} for wallet_id: {wallet_id}"
                )
                self.log.info(f"Start: {creating_msg}")
                intermediate_sk = master_sk_to_wallet_sk_intermediate(self.private_key)
                intermediate_sk_un = master_sk_to_wallet_sk_unhardened_intermediate(self.private_key)
                for index in range(start_index, last_index):
                    if target_wallet.type() == WalletType.POOLING_WALLET:
                        continue

                    # Hardened
                    pubkey: G1Element = _derive_path(intermediate_sk, [index]).get_g1()
                    puzzlehash: Optional[bytes32] = target_wallet.puzzle_hash_for_pk(pubkey)
                    if puzzlehash is None:
                        self.log.error(f"Unable to create puzzles with wallet {target_wallet}")
                        break
                    self.log.debug(f"Puzzle at index {index} wallet ID {wallet_id} puzzle hash {puzzlehash.hex()}")
                    new_paths = True
                    derivation_paths.append(
                        DerivationRecord(
                            uint32(index),
                            puzzlehash,
                            pubkey,
                            target_wallet.type(),
                            uint32(target_wallet.id()),
                            True,
                        )
                    )
                    # Unhardened
                    pubkey_unhardened: G1Element = _derive_path_unhardened(intermediate_sk_un, [index]).get_g1()
                    puzzlehash_unhardened: Optional[bytes32] = target_wallet.puzzle_hash_for_pk(pubkey_unhardened)
                    if puzzlehash_unhardened is None:
                        self.log.error(f"Unable to create puzzles with wallet {target_wallet}")
                        break
                    self.log.debug(
                        f"Puzzle at index {index} wallet ID {wallet_id} puzzle hash {puzzlehash_unhardened.hex()}"
                    )
                    # We await sleep here to allow an asyncio context switch (since the other parts of this loop do
                    # not have await and therefore block). This can prevent networking layer from responding to ping.
                    await asyncio.sleep(0)
                    derivation_paths.append(
                        DerivationRecord(
                            uint32(index),
                            puzzlehash_unhardened,
                            pubkey_unhardened,
                            target_wallet.type(),
                            uint32(target_wallet.id()),
                            False,
                        )
                    )
                self.log.info(f"Done: {creating_msg} Time: {time.time() - start_t} seconds")
            await self.puzzle_store.add_derivation_paths(derivation_paths)
            if len(derivation_paths) > 0:
                if wallet_id == self.main_wallet.id():
                    await self.wallet_node.new_peak_queue.subscribe_to_puzzle_hashes(
                        [record.puzzle_hash for record in derivation_paths]
                    )
                self.state_changed("new_derivation_index", data_object={"index": derivation_paths[-1].index})
        # By default, we'll mark previously generated unused puzzle hashes as used if we have new paths
        if mark_existing_as_used and unused > 0 and new_paths:
            self.log.info(f"Updating last used derivation index: {unused - 1}")
            await self.puzzle_store.set_used_up_to(uint32(unused - 1))

    async def update_wallet_puzzle_hashes(self, wallet_id: uint32) -> None:
        derivation_paths: List[DerivationRecord] = []
        target_wallet = self.wallets[wallet_id]
        last: Optional[uint32] = await self.puzzle_store.get_last_derivation_path_for_wallet(wallet_id)
        unused: Optional[uint32] = await self.puzzle_store.get_unused_derivation_path()
        if unused is None:
            # This handles the case where the database has entries but they have all been used
            unused = await self.puzzle_store.get_last_derivation_path()
            if unused is None:
                # This handles the case where the database is empty
                unused = uint32(0)
        if last is not None:
            for index in range(unused, last):
                # Since DID are not released yet we can assume they are only using unhardened keys derivation
                pubkey: G1Element = self.get_public_key_unhardened(uint32(index))
                puzzlehash = target_wallet.puzzle_hash_for_pk(pubkey)
                self.log.info(f"Generating public key at index {index} puzzle hash {puzzlehash.hex()}")
                derivation_paths.append(
                    DerivationRecord(
                        uint32(index),
                        puzzlehash,
                        pubkey,
                        WalletType(target_wallet.wallet_info.type),
                        uint32(target_wallet.wallet_info.id),
                        False,
                    )
                )
            await self.puzzle_store.add_derivation_paths(derivation_paths)

    async def get_unused_derivation_record(self, wallet_id: uint32, *, hardened: bool = False) -> DerivationRecord:
        """
        Creates a puzzle hash for the given wallet, and then makes more puzzle hashes
        for every wallet to ensure we always have more in the database. Never reusue the
        same public key more than once (for privacy).
        """
        async with self.puzzle_store.lock:
            # If we have no unused public keys, we will create new ones
            unused: Optional[uint32] = await self.puzzle_store.get_unused_derivation_path()
            if unused is None:
                self.log.debug("No unused paths, generate more ")
                await self.create_more_puzzle_hashes()
                # Now we must have unused public keys
                unused = await self.puzzle_store.get_unused_derivation_path()
                assert unused is not None

            self.log.debug("Fetching derivation record for: %s %s %s", unused, wallet_id, hardened)
            record: Optional[DerivationRecord] = await self.puzzle_store.get_derivation_record(
                unused, wallet_id, hardened
            )
            if record is None:
                raise ValueError(f"Missing derivation '{unused}' for wallet id '{wallet_id}' (hardened={hardened})")

            # Set this key to used so we never use it again
            await self.puzzle_store.set_used_up_to(record.index)

            # Create more puzzle hashes / keys
            await self.create_more_puzzle_hashes()
            return record

    async def get_current_derivation_record_for_wallet(self, wallet_id: uint32) -> Optional[DerivationRecord]:
        async with self.puzzle_store.lock:
            # If we have no unused public keys, we will create new ones
            current: Optional[DerivationRecord] = await self.puzzle_store.get_current_derivation_record_for_wallet(
                wallet_id
            )
            return current

    def set_callback(self, callback: StateChangedProtocol) -> None:
        """
        Callback to be called when the state of the wallet changes.
        """
        self.state_changed_callback = callback

    def set_pending_callback(self, callback: PendingTxCallback) -> None:
        """
        Callback to be called when new pending transaction enters the store
        """
        self.pending_tx_callback = callback

    def state_changed(
        self, state: str, wallet_id: Optional[int] = None, data_object: Optional[Dict[str, Any]] = None
    ) -> None:
        """
        Calls the callback if it's present.
        """
        if self.state_changed_callback is None:
            return None
        change_data: Dict[str, Any] = {"state": state}
        if wallet_id is not None:
            change_data["wallet_id"] = wallet_id
        if data_object is not None:
            change_data["additional_data"] = data_object
        self.state_changed_callback(state, change_data)

    def tx_pending_changed(self) -> None:
        """
        Notifies the wallet node that there's new tx pending
        """
        if self.pending_tx_callback is None:
            return None

        self.pending_tx_callback()

    async def synced(self) -> bool:
        if len(self.server.get_connections(NodeType.FULL_NODE)) == 0:
            return False

        latest = await self.blockchain.get_peak_block()
        if latest is None:
            return False

        if "simulator" in self.config.get("selected_network", ""):
            return True  # sim is always synced if we have a genesis block.

        if latest.height - await self.blockchain.get_finished_sync_up_to() > 1:
            return False

        latest_timestamp = self.blockchain.get_latest_timestamp()
        has_pending_queue_items = self.wallet_node.new_peak_queue.has_pending_data_process_items()

        if latest_timestamp > int(time.time()) - 5 * 60 and not has_pending_queue_items:
            return True
        return False

    @property
    def sync_mode(self) -> bool:
        return self._sync_target is not None

    @property
    def sync_target(self) -> Optional[uint32]:
        return self._sync_target

    @asynccontextmanager
    async def set_sync_mode(self, target_height: uint32) -> AsyncIterator[uint32]:
        if self.log.level == logging.DEBUG:
            self.log.debug(f"set_sync_mode enter {await self.blockchain.get_finished_sync_up_to()}-{target_height}")
        async with self.lock:
            self._sync_target = target_height
            start_time = time.time()
            start_height = await self.blockchain.get_finished_sync_up_to()
            self.log.info(f"set_sync_mode syncing - range: {start_height}-{target_height}")
            self.state_changed("sync_changed")
            try:
                yield start_height
            except Exception:
                self.log.exception(
                    f"set_sync_mode failed - range: {start_height}-{target_height}, seconds: {time.time() - start_time}"
                )
            finally:
                self.state_changed("sync_changed")
                if self.log.level == logging.DEBUG:
                    self.log.debug(
                        f"set_sync_mode exit - range: {start_height}-{target_height}, "
                        f"get_finished_sync_up_to: {await self.blockchain.get_finished_sync_up_to()}, "
                        f"seconds: {time.time() - start_time}"
                    )
                self._sync_target = None

    async def get_confirmed_spendable_balance_for_wallet(
        self, wallet_id: int, unspent_records: Optional[Set[WalletCoinRecord]] = None
    ) -> uint128:
        """
        Returns the balance amount of all coins that are spendable.
        """

        spendable: Set[WalletCoinRecord] = await self.get_spendable_coins_for_wallet(wallet_id, unspent_records)

        spendable_amount: uint128 = uint128(0)
        for record in spendable:
            spendable_amount = uint128(spendable_amount + record.coin.amount)

        return spendable_amount

    async def does_coin_belong_to_wallet(
        self, coin: Coin, wallet_id: int, hint_dict: Dict[bytes32, bytes32] = {}
    ) -> bool:
        """
        Returns true if we have the key for this coin.
        """
        wallet_identifier = await self.get_wallet_identifier_for_coin(coin, hint_dict)
        return wallet_identifier is not None and wallet_identifier.id == wallet_id

    async def get_confirmed_balance_for_wallet(
        self,
        wallet_id: int,
        unspent_coin_records: Optional[Set[WalletCoinRecord]] = None,
    ) -> uint128:
        """
        Returns the confirmed balance, including coinbase rewards that are not spendable.
        """
        # lock only if unspent_coin_records is None
        if unspent_coin_records is None:
            if self.wallets[uint32(wallet_id)].type() == WalletType.CRCAT:
                coin_type = CoinType.CRCAT
            else:
                coin_type = CoinType.NORMAL
            unspent_coin_records = await self.coin_store.get_unspent_coins_for_wallet(wallet_id, coin_type)
        return uint128(sum(cr.coin.amount for cr in unspent_coin_records))

    async def get_unconfirmed_balance(
        self, wallet_id: int, unspent_coin_records: Optional[Set[WalletCoinRecord]] = None
    ) -> uint128:
        """
        Returns the balance, including coinbase rewards that are not spendable, and unconfirmed
        transactions.
        """
        # This API should change so that get_balance_from_coin_records is called for Set[WalletCoinRecord]
        # and this method is called only for the unspent_coin_records==None case.
        if unspent_coin_records is None:
            wallet_type: WalletType = self.wallets[uint32(wallet_id)].type()
            if wallet_type == WalletType.CRCAT:
                unspent_coin_records = await self.coin_store.get_unspent_coins_for_wallet(wallet_id, CoinType.CRCAT)
                pending_crcat = await self.coin_store.get_unspent_coins_for_wallet(wallet_id, CoinType.CRCAT_PENDING)
                unspent_coin_records = unspent_coin_records.union(pending_crcat)
            else:
                unspent_coin_records = await self.coin_store.get_unspent_coins_for_wallet(wallet_id)

        unconfirmed_tx: List[TransactionRecord] = await self.tx_store.get_unconfirmed_for_wallet(wallet_id)
        all_unspent_coins: Set[Coin] = {cr.coin for cr in unspent_coin_records}

        for record in unconfirmed_tx:
            for addition in record.additions:
                # This change or a self transaction
                if await self.does_coin_belong_to_wallet(addition, wallet_id, record.hint_dict()):
                    all_unspent_coins.add(addition)

            for removal in record.removals:
                if (
                    await self.does_coin_belong_to_wallet(removal, wallet_id, record.hint_dict())
                    and removal in all_unspent_coins
                ):
                    all_unspent_coins.remove(removal)

        return uint128(sum(coin.amount for coin in all_unspent_coins))

    async def unconfirmed_removals_for_wallet(self, wallet_id: int) -> Dict[bytes32, Coin]:
        """
        Returns new removals transactions that have not been confirmed yet.
        """
        removals: Dict[bytes32, Coin] = {}
        unconfirmed_tx = await self.tx_store.get_unconfirmed_for_wallet(wallet_id)
        for record in unconfirmed_tx:
            for coin in record.removals:
                removals[coin.name()] = coin
        trade_removals: Dict[bytes32, WalletCoinRecord] = await self.trade_manager.get_locked_coins()
        return {**removals, **{coin_id: cr.coin for coin_id, cr in trade_removals.items() if cr.wallet_id == wallet_id}}

    async def determine_coin_type(
        self, peer: WSHDDcoinConnection, coin_state: CoinState, fork_height: Optional[uint32]
    ) -> Tuple[Optional[WalletIdentifier], Optional[Streamable]]:
        if coin_state.created_height is not None and (
            self.is_pool_reward(uint32(coin_state.created_height), coin_state.coin)
            or self.is_farmer_reward(uint32(coin_state.created_height), coin_state.coin)
        ):
            return None, None

        response: List[CoinState] = await self.wallet_node.get_coin_state(
            [coin_state.coin.parent_coin_info], peer=peer, fork_height=fork_height
        )
        if len(response) == 0:
            self.log.warning(f"Could not find a parent coin with ID: {coin_state.coin.parent_coin_info}")
            return None, None
        parent_coin_state = response[0]
        assert parent_coin_state.spent_height == coin_state.created_height

        coin_spend = await fetch_coin_spend_for_coin_state(parent_coin_state, peer)

        puzzle = Program.from_bytes(bytes(coin_spend.puzzle_reveal))
        solution = Program.from_bytes(bytes(coin_spend.solution))

        uncurried = uncurry_puzzle(puzzle)

        dao_ids = []
        wallets = self.wallets.values()
        for wallet in wallets:
            if wallet.type() == WalletType.DAO.value:
                assert isinstance(wallet, DAOWallet)
                dao_ids.append(wallet.dao_info.treasury_id)
        funding_puzzle_check = match_funding_puzzle(uncurried, solution, coin_state.coin, dao_ids)
        if funding_puzzle_check:
            return await self.get_dao_wallet_from_coinspend_hint(coin_spend, coin_state), None

        # Check if the coin is a DAO Treasury
        dao_curried_args = match_treasury_puzzle(uncurried.mod, uncurried.args)
        if dao_curried_args is not None:
            return await self.handle_dao_treasury(dao_curried_args, parent_coin_state, coin_state, coin_spend), None
        # Check if the coin is a Proposal and that it isn't the timer coin (amount == 0)
        dao_curried_args = match_proposal_puzzle(uncurried.mod, uncurried.args)
        if (dao_curried_args is not None) and (coin_state.coin.amount != 0):
            return await self.handle_dao_proposal(dao_curried_args, parent_coin_state, coin_state, coin_spend), None

        # Check if the coin is a finished proposal
        dao_curried_args = match_finished_puzzle(uncurried.mod, uncurried.args)
        if dao_curried_args is not None:
            return (
                await self.handle_dao_finished_proposals(dao_curried_args, parent_coin_state, coin_state, coin_spend),
                None,
            )

        # Check if the coin is a DAO CAT
        dao_cat_args = match_dao_cat_puzzle(uncurried)
        if dao_cat_args:
            return await self.handle_dao_cat(dao_cat_args, parent_coin_state, coin_state, coin_spend, fork_height), None

        # Check if the coin is a CAT
        cat_curried_args = match_cat_puzzle(uncurried)
        if cat_curried_args is not None:
            cat_mod_hash, tail_program_hash, cat_inner_puzzle = cat_curried_args
            cat_data: CATCoinData = CATCoinData(
                bytes32(cat_mod_hash.atom),
                bytes32(tail_program_hash.atom),
                cat_inner_puzzle,
                parent_coin_state.coin.parent_coin_info,
                uint64(parent_coin_state.coin.amount),
            )
            return (
                await self.handle_cat(
                    cat_data,
                    parent_coin_state,
                    coin_state,
                    coin_spend,
                    peer,
                    fork_height,
                ),
                cat_data,
            )

        # Check if the coin is a NFT
        #                                                        hint
        # First spend where 1 byte coin -> Singleton launcher -> NFT -> NFT
        uncurried_nft = UncurriedNFT.uncurry(uncurried.mod, uncurried.args)
        if uncurried_nft is not None and coin_state.coin.amount % 2 == 1:
            nft_data = NFTCoinData(uncurried_nft, parent_coin_state, coin_spend)
            return await self.handle_nft(nft_data), nft_data

        # Check if the coin is a DID
        did_curried_args = match_did_puzzle(uncurried.mod, uncurried.args)
        if did_curried_args is not None and coin_state.coin.amount % 2 == 1:
            p2_puzzle, recovery_list_hash, num_verification, singleton_struct, metadata = did_curried_args
            did_data: DIDCoinData = DIDCoinData(
                p2_puzzle,
                bytes32(recovery_list_hash.atom),
                uint16(num_verification.as_int()),
                singleton_struct,
                metadata,
                get_inner_puzzle_from_singleton(coin_spend.puzzle_reveal.to_program()),
                parent_coin_state,
            )
            return await self.handle_did(did_data, parent_coin_state, coin_state, coin_spend, peer), did_data

        # Check if the coin is clawback
        solution = coin_spend.solution.to_program()
        clawback_coin_data = match_clawback_puzzle(uncurried, puzzle, solution)
        if clawback_coin_data is not None:
            return await self.handle_clawback(clawback_coin_data, coin_state, coin_spend, peer), clawback_coin_data

        # Check if the coin is a VC
        is_vc, err_msg = VerifiedCredential.is_vc(uncurried)
        if is_vc:
            vc: VerifiedCredential = VerifiedCredential.get_next_from_coin_spend(coin_spend)
            return await self.handle_vc(vc), vc

        await self.notification_manager.potentially_add_new_notification(coin_state, coin_spend)

        return None, None

    async def auto_claim_coins(self) -> None:
        # Get unspent clawback coin
        current_timestamp = self.blockchain.get_latest_timestamp()
        clawback_coins: Dict[Coin, ClawbackMetadata] = {}
        tx_fee = uint64(self.config.get("auto_claim", {}).get("tx_fee", 0))
        assert self.wallet_node.logged_in_fingerprint is not None
        tx_config_loader: TXConfigLoader = TXConfigLoader.from_json_dict(self.config.get("auto_claim", {}))
        if tx_config_loader.min_coin_amount is None:
            tx_config_loader = tx_config_loader.override(
                min_coin_amount=self.config.get("auto_claim", {}).get("min_amount"),
            )
        tx_config: TXConfig = tx_config_loader.autofill(
            constants=self.constants,
            config=self.config,
            logged_in_fingerprint=self.wallet_node.logged_in_fingerprint,
        )
        unspent_coins = await self.coin_store.get_coin_records(
            coin_type=CoinType.CLAWBACK,
            wallet_type=WalletType.STANDARD_WALLET,
            spent_range=UInt32Range(stop=uint32(0)),
            amount_range=UInt64Range(
                start=tx_config.coin_selection_config.min_coin_amount,
                stop=tx_config.coin_selection_config.max_coin_amount,
            ),
        )
        for coin in unspent_coins.records:
            try:
                metadata: MetadataTypes = coin.parsed_metadata()
                assert isinstance(metadata, ClawbackMetadata)
                if await metadata.is_recipient(self.puzzle_store):
                    coin_timestamp = await self.wallet_node.get_timestamp_for_height(coin.confirmed_block_height)
                    if current_timestamp - coin_timestamp >= metadata.time_lock:
                        clawback_coins[coin.coin] = metadata
                        if len(clawback_coins) >= self.config.get("auto_claim", {}).get("batch_size", 50):
                            await self.spend_clawback_coins(clawback_coins, tx_fee, tx_config)
                            clawback_coins = {}
            except Exception as e:
                self.log.error(f"Failed to claim clawback coin {coin.coin.name().hex()}: %s", e)
        if len(clawback_coins) > 0:
            await self.spend_clawback_coins(clawback_coins, tx_fee, tx_config)

    async def spend_clawback_coins(
        self,
        clawback_coins: Dict[Coin, ClawbackMetadata],
        fee: uint64,
        tx_config: TXConfig,
        force: bool = False,
        extra_conditions: Tuple[Condition, ...] = tuple(),
    ) -> List[bytes32]:
        assert len(clawback_coins) > 0
        coin_spends: List[CoinSpend] = []
        message: bytes32 = std_hash(b"".join([c.name() for c in clawback_coins.keys()]))
        now: uint64 = uint64(int(time.time()))
        derivation_record: Optional[DerivationRecord] = None
        amount: uint64 = uint64(0)
        for coin, metadata in clawback_coins.items():
            try:
                self.log.info(f"Claiming clawback coin {coin.name().hex()}")
                # Get incoming tx
                incoming_tx = await self.tx_store.get_transaction_record(coin.name())
                assert incoming_tx is not None, f"Cannot find incoming tx for clawback coin {coin.name().hex()}"
                if incoming_tx.sent > 0 and not force:
                    self.log.error(
                        f"Clawback coin {coin.name().hex()} is already in a pending spend bundle. {incoming_tx}"
                    )
                    continue

                recipient_puzhash: bytes32 = metadata.recipient_puzzle_hash
                sender_puzhash: bytes32 = metadata.sender_puzzle_hash
                is_recipient: bool = await metadata.is_recipient(self.puzzle_store)
                if is_recipient:
                    derivation_record = await self.puzzle_store.get_derivation_record_for_puzzle_hash(recipient_puzhash)
                else:
                    derivation_record = await self.puzzle_store.get_derivation_record_for_puzzle_hash(sender_puzhash)
                assert derivation_record is not None
                amount = uint64(amount + coin.amount)
                # Remove the clawback hint since it is unnecessary for the HDD coin
                memos: List[bytes] = [] if len(incoming_tx.memos) == 0 else incoming_tx.memos[0][1][1:]
                inner_puzzle: Program = self.main_wallet.puzzle_for_pk(derivation_record.pubkey)
                inner_solution: Program = self.main_wallet.make_solution(
                    primaries=[
                        Payment(
                            derivation_record.puzzle_hash,
                            uint64(coin.amount),
                            memos,  # Forward memo of the first coin
                        )
                    ],
                    coin_announcements=None if len(coin_spends) > 0 or fee == 0 else {message},
                    conditions=extra_conditions,
                )
                coin_spend: CoinSpend = generate_clawback_spend_bundle(coin, metadata, inner_puzzle, inner_solution)
                coin_spends.append(coin_spend)
                # Update incoming tx to prevent double spend and mark it is pending
                await self.tx_store.increment_sent(incoming_tx.name, "", MempoolInclusionStatus.PENDING, None)
            except Exception as e:
                self.log.error(f"Failed to create clawback spend bundle for {coin.name().hex()}: {e}")
        if len(coin_spends) == 0:
            return []
        spend_bundle: SpendBundle = await self.sign_transaction(coin_spends)
        if fee > 0:
            hddcoin_tx = await self.main_wallet.create_tandem_hdd_tx(
                fee, tx_config, Announcement(coin_spends[0].coin.name(), message)
            )
            assert hddcoin_tx.spend_bundle is not None
            spend_bundle = SpendBundle.aggregate([spend_bundle, hddcoin_tx.spend_bundle])
        assert derivation_record is not None
        tx_record = TransactionRecord(
            confirmed_at_height=uint32(0),
            created_at_time=now,
            to_puzzle_hash=derivation_record.puzzle_hash,
            amount=amount,
            fee_amount=uint64(fee),
            confirmed=False,
            sent=uint32(0),
            spend_bundle=spend_bundle,
            additions=spend_bundle.additions(),
            removals=spend_bundle.removals(),
            wallet_id=uint32(1),
            sent_to=[],
            trade_id=None,
            type=uint32(TransactionType.OUTGOING_CLAWBACK),
            name=spend_bundle.name(),
            memos=list(compute_memos(spend_bundle).items()),
            valid_times=parse_timelock_info(extra_conditions),
        )
        await self.add_pending_transaction(tx_record)
        return [tx_record.name]

    async def filter_spam(self, new_coin_state: List[CoinState]) -> List[CoinState]:
        hdd_spam_amount = self.config.get("hdd_spam_amount", 1000000)

        # No need to filter anything if the filter is set to 1 or 0 mojos
        if hdd_spam_amount <= 1:
            return new_coin_state

        spam_filter_after_n_txs = self.config.get("spam_filter_after_n_txs", 200)
        small_unspent_count = await self.coin_store.count_small_unspent(hdd_spam_amount)

        # if small_unspent_count > spam_filter_after_n_txs:
        filtered_cs: List[CoinState] = []
        is_standard_wallet_phs: Set[bytes32] = set()

        for cs in new_coin_state:
            # Only apply filter to new coins being sent to our wallet, that are very small
            if (
                cs.created_height is not None
                and cs.spent_height is None
                and cs.coin.amount < hdd_spam_amount
                and (cs.coin.puzzle_hash in is_standard_wallet_phs or await self.is_standard_wallet_tx(cs))
            ):
                is_standard_wallet_phs.add(cs.coin.puzzle_hash)
                if small_unspent_count < spam_filter_after_n_txs:
                    filtered_cs.append(cs)
                small_unspent_count += 1
            else:
                filtered_cs.append(cs)
        return filtered_cs

    async def is_standard_wallet_tx(self, coin_state: CoinState) -> bool:
        wallet_identifier = await self.get_wallet_identifier_for_puzzle_hash(coin_state.coin.puzzle_hash)
        return wallet_identifier is not None and wallet_identifier.type == WalletType.STANDARD_WALLET

    async def handle_dao_cat(
        self,
        curried_args: Iterator[Program],
        parent_coin_state: CoinState,
        coin_state: CoinState,
        coin_spend: CoinSpend,
        fork_height: Optional[uint32],
    ) -> Optional[WalletIdentifier]:
        """
        Handle the new coin when it is a DAO CAT
        """
        mod_hash, tail_hash, inner_puzzle = curried_args
        asset_id: bytes32 = bytes32(bytes(tail_hash)[1:])
        for wallet in self.wallets.values():
            if wallet.type() == WalletType.DAO_CAT:
                assert isinstance(wallet, DAOCATWallet)
                if wallet.dao_cat_info.limitations_program_hash == asset_id:
                    return WalletIdentifier.create(wallet)
        # Found a DAO_CAT, but we don't have a wallet for it. Add to unacknowledged
        await self.interested_store.add_unacknowledged_token(
            asset_id,
            CATWallet.default_wallet_name_for_unknown_cat(asset_id.hex()),
            None if parent_coin_state.spent_height is None else uint32(parent_coin_state.spent_height),
            parent_coin_state.coin.puzzle_hash,
        )
        await self.interested_store.add_unacknowledged_coin_state(
            asset_id,
            coin_state,
            fork_height,
        )
        self.state_changed("added_stray_cat")
        return None  # pragma: no cover

    async def handle_cat(
        self,
        parent_data: CATCoinData,
        parent_coin_state: CoinState,
        coin_state: CoinState,
        coin_spend: CoinSpend,
        peer: WSHDDcoinConnection,
        fork_height: Optional[uint32],
    ) -> Optional[WalletIdentifier]:
        """
        Handle the new coin when it is a CAT
        :param parent_data: Parent CAT coin uncurried metadata
        :param parent_coin_state: Parent coin state
        :param coin_state: Current coin state
        :param coin_spend: New coin spend
        :param fork_height: Current block height
        :return: Wallet ID & Wallet Type
        """
        hinted_coin = compute_spend_hints_and_additions(coin_spend)[0][coin_state.coin.name()]
        assert hinted_coin.hint is not None, f"hint missing for coin {hinted_coin.coin}"
        derivation_record = await self.puzzle_store.get_derivation_record_for_puzzle_hash(hinted_coin.hint)

        if derivation_record is None:
            self.log.info(f"Received state for the coin that doesn't belong to us {coin_state}")
            return None
        else:
            our_inner_puzzle: Program = self.main_wallet.puzzle_for_pk(derivation_record.pubkey)
            asset_id: bytes32 = parent_data.tail_program_hash
            cat_puzzle = construct_cat_puzzle(CAT_MOD, asset_id, our_inner_puzzle, CAT_MOD_HASH)
            is_crcat: bool = False
            if cat_puzzle.get_tree_hash() != coin_state.coin.puzzle_hash:
                # Check if it is a CRCAT
                if CRCAT.is_cr_cat(uncurry_puzzle(Program.from_bytes(bytes(coin_spend.puzzle_reveal)))):
                    is_crcat = True
                else:
                    return None  # pragma: no cover
            if is_crcat:
                # Since CRCAT wallet doesn't have derivation path, every CRCAT will go through this code path
                crcat: CRCAT = next(
                    crc for crc in CRCAT.get_next_from_coin_spend(coin_spend) if crc.coin == coin_state.coin
                )

                # Make sure we control the inner puzzle or we control it if it's wrapped in the pending state
                if (
                    await self.puzzle_store.get_derivation_record_for_puzzle_hash(crcat.inner_puzzle_hash) is None
                    and crcat.inner_puzzle_hash
                    != construct_pending_approval_state(
                        hinted_coin.hint,
                        uint64(coin_state.coin.amount),
                    ).get_tree_hash()
                ):
                    self.log.error(f"Unknown CRCAT inner puzzle, coin ID:{crcat.coin.name().hex()}")  # pragma: no cover
                    return None  # pragma: no cover

                # Check if we already have a wallet
                for wallet_info in await self.get_all_wallet_info_entries(wallet_type=WalletType.CRCAT):
                    crcat_info: CRCATInfo = CRCATInfo.from_bytes(bytes.fromhex(wallet_info.data))
                    if crcat_info.limitations_program_hash == asset_id:
                        return WalletIdentifier(wallet_info.id, WalletType(wallet_info.type))

                # We didn't find a matching CR-CAT wallet, but maybe we have a matching CAT wallet that we can convert
                for wallet_info in await self.get_all_wallet_info_entries(wallet_type=WalletType.CAT):
                    cat_info: CATInfo = CATInfo.from_bytes(bytes.fromhex(wallet_info.data))
                    found_cat_wallet = self.wallets[wallet_info.id]
                    assert isinstance(found_cat_wallet, CATWallet)
                    if cat_info.limitations_program_hash == crcat.tail_hash:
                        await CRCATWallet.convert_to_cr(
                            found_cat_wallet,
                            crcat.authorized_providers,
                            ProofsChecker.from_program(uncurry_puzzle(crcat.proofs_checker)),
                        )
                        self.state_changed("converted cat wallet to cr", wallet_info.id)
                        return WalletIdentifier(wallet_info.id, WalletType(WalletType.CRCAT))
            if parent_data.tail_program_hash.hex() in self.default_cats or self.config.get(
                "automatically_add_unknown_cats", False
            ):
                if is_crcat:
                    cat_wallet: Union[CATWallet, CRCATWallet] = await CRCATWallet.get_or_create_wallet_for_cat(
                        self,
                        self.main_wallet,
                        crcat.tail_hash.hex(),
                        authorized_providers=crcat.authorized_providers,
                        proofs_checker=ProofsChecker.from_program(uncurry_puzzle(crcat.proofs_checker)),
                    )
                else:
                    cat_wallet = await CATWallet.get_or_create_wallet_for_cat(
                        self, self.main_wallet, parent_data.tail_program_hash.hex()
                    )
                return WalletIdentifier.create(cat_wallet)
            else:
                # Found unacknowledged CAT, save it in the database.
                await self.interested_store.add_unacknowledged_token(
                    asset_id,
                    CATWallet.default_wallet_name_for_unknown_cat(asset_id.hex()),
                    None if parent_coin_state.spent_height is None else uint32(parent_coin_state.spent_height),
                    parent_coin_state.coin.puzzle_hash,
                )
                await self.interested_store.add_unacknowledged_coin_state(
                    asset_id,
                    coin_state,
                    fork_height,
                )
                self.state_changed("added_stray_cat")
                return None

    async def handle_did(
        self,
        parent_data: DIDCoinData,
        parent_coin_state: CoinState,
        coin_state: CoinState,
        coin_spend: CoinSpend,
        peer: WSHDDcoinConnection,
    ) -> Optional[WalletIdentifier]:
        """
        Handle the new coin when it is a DID
        :param parent_data: Curried data of the DID coin
        :param parent_coin_state: Parent coin state
        :param coin_state: Current coin state
        :param coin_spend: New coin spend
        :return: Wallet ID & Wallet Type
        """

        inner_puzzle_hash = parent_data.p2_puzzle.get_tree_hash()
        self.log.info(f"parent: {parent_coin_state.coin.name()} inner_puzzle_hash for parent is {inner_puzzle_hash}")

        hinted_coin = compute_spend_hints_and_additions(coin_spend)[0][coin_state.coin.name()]
        assert hinted_coin.hint is not None, f"hint missing for coin {hinted_coin.coin}"
        derivation_record = await self.puzzle_store.get_derivation_record_for_puzzle_hash(hinted_coin.hint)

        launch_id: bytes32 = bytes32(parent_data.singleton_struct.rest().first().atom)
        if derivation_record is None:
            self.log.info(f"Received state for the coin that doesn't belong to us {coin_state}")
            # Check if it was owned by us
            # If the puzzle inside is no longer recognised then delete the wallet associated
            removed_wallet_ids = []
            for wallet in self.wallets.values():
                if not isinstance(wallet, DIDWallet):
                    continue
                if (
                    wallet.did_info.origin_coin is not None
                    and launch_id == wallet.did_info.origin_coin.name()
                    and not wallet.did_info.sent_recovery_transaction
                ):
                    await self.user_store.delete_wallet(wallet.id())
                    removed_wallet_ids.append(wallet.id())
            for remove_id in removed_wallet_ids:
                self.wallets.pop(remove_id)
                self.log.info(f"Removed DID wallet {remove_id}, Launch_ID: {launch_id.hex()}")
                self.state_changed("wallet_removed", remove_id)
            return None
        else:
            our_inner_puzzle: Program = self.main_wallet.puzzle_for_pk(derivation_record.pubkey)

            self.log.info(f"Found DID, launch_id {launch_id}.")
            did_puzzle = DID_INNERPUZ_MOD.curry(
                our_inner_puzzle,
                parent_data.recovery_list_hash,
                parent_data.num_verification,
                parent_data.singleton_struct,
                parent_data.metadata,
            )
            full_puzzle = create_singleton_puzzle(did_puzzle, launch_id)
            did_puzzle_empty_recovery = DID_INNERPUZ_MOD.curry(
                our_inner_puzzle,
                Program.to([]).get_tree_hash(),
                uint64(0),
                parent_data.singleton_struct,
                parent_data.metadata,
            )
            full_puzzle_empty_recovery = create_singleton_puzzle(did_puzzle_empty_recovery, launch_id)
            if full_puzzle.get_tree_hash() != coin_state.coin.puzzle_hash:
                if full_puzzle_empty_recovery.get_tree_hash() == coin_state.coin.puzzle_hash:
                    did_puzzle = did_puzzle_empty_recovery
                    self.log.info("DID recovery list was reset by the previous owner.")
                else:
                    self.log.error("DID puzzle hash doesn't match, please check curried parameters.")
                    return None
            # Create DID wallet
            response: List[CoinState] = await self.wallet_node.get_coin_state([launch_id], peer=peer)
            if len(response) == 0:
                self.log.warning(f"Could not find the launch coin with ID: {launch_id}")
                return None
            launch_coin: CoinState = response[0]
            origin_coin = launch_coin.coin

            for wallet in self.wallets.values():
                if wallet.type() == WalletType.DECENTRALIZED_ID:
                    assert isinstance(wallet, DIDWallet)
                    assert wallet.did_info.origin_coin is not None
                    if origin_coin.name() == wallet.did_info.origin_coin.name():
                        return WalletIdentifier.create(wallet)
            if coin_state.spent_height is not None:
                # The first coin we received for DID wallet is spent.
                # This means the wallet is in a resync process, skip the coin
                return None
            did_wallet = await DIDWallet.create_new_did_wallet_from_coin_spend(
                self,
                self.main_wallet,
                launch_coin.coin,
                did_puzzle,
                coin_spend,
                f"DID {encode_puzzle_hash(launch_id, AddressType.DID.hrp(self.config))}",
            )
            wallet_identifier = WalletIdentifier.create(did_wallet)
            self.state_changed("wallet_created", wallet_identifier.id, {"did_id": did_wallet.get_my_DID()})
            return wallet_identifier

    async def get_minter_did(self, launcher_coin: Coin, peer: WSHDDcoinConnection) -> Optional[bytes32]:
        # Get minter DID
        eve_coin = (await self.wallet_node.fetch_children(launcher_coin.name(), peer=peer))[0]
        eve_coin_spend = await fetch_coin_spend_for_coin_state(eve_coin, peer)
        eve_full_puzzle: Program = Program.from_bytes(bytes(eve_coin_spend.puzzle_reveal))
        eve_uncurried_nft: Optional[UncurriedNFT] = UncurriedNFT.uncurry(*eve_full_puzzle.uncurry())
        if eve_uncurried_nft is None:
            raise ValueError("Couldn't get minter DID for NFT")
        if not eve_uncurried_nft.supports_did:
            return None
        minter_did = get_new_owner_did(eve_uncurried_nft, eve_coin_spend.solution.to_program())
        if minter_did == b"":
            minter_did = None
        if minter_did is None:
            # Check if the NFT is a bulk minting
            launcher_parent: List[CoinState] = await self.wallet_node.get_coin_state(
                [launcher_coin.parent_coin_info], peer=peer
            )
            assert (
                launcher_parent is not None
                and len(launcher_parent) == 1
                and launcher_parent[0].spent_height is not None
            )
            did_coin: List[CoinState] = await self.wallet_node.get_coin_state(
                [launcher_parent[0].coin.parent_coin_info], peer=peer
            )
            assert did_coin is not None and len(did_coin) == 1 and did_coin[0].spent_height is not None
            did_spend = await fetch_coin_spend_for_coin_state(did_coin[0], peer)
            puzzle = Program.from_bytes(bytes(did_spend.puzzle_reveal))
            uncurried = uncurry_puzzle(puzzle)
            did_curried_args = match_did_puzzle(uncurried.mod, uncurried.args)
            if did_curried_args is not None:
                p2_puzzle, recovery_list_hash, num_verification, singleton_struct, metadata = did_curried_args
                minter_did = bytes32(bytes(singleton_struct.rest().first())[1:])
        return minter_did

    async def handle_dao_treasury(
        self,
        uncurried_args: Iterator[Program],
        parent_coin_state: CoinState,
        coin_state: CoinState,
        coin_spend: CoinSpend,
    ) -> Optional[WalletIdentifier]:
        self.log.info("Entering dao_treasury handling in WalletStateManager")
        singleton_id = get_singleton_id_from_puzzle(coin_spend.puzzle_reveal)
        for wallet in self.wallets.values():
            if wallet.type() == WalletType.DAO:
                assert isinstance(wallet, DAOWallet)
                if wallet.dao_info.treasury_id == singleton_id:
                    return WalletIdentifier.create(wallet)

        # TODO: If we can't find the wallet for this DAO but we've got here because we're subscribed,
        #        then create the wallet. (see early in dao-wallet commits for how to do this)
        return None  # pragma: no cover

    async def handle_dao_proposal(
        self,
        uncurried_args: Iterator[Program],
        parent_coin_state: CoinState,
        coin_state: CoinState,
        coin_spend: CoinSpend,
    ) -> Optional[WalletIdentifier]:
        (
            # ; second hash
            SELF_HASH,
            PROPOSAL_ID,
            PROPOSED_PUZ_HASH,
            YES_VOTES,
            TOTAL_VOTES,
            # ; first hash
            PROPOSAL_TIMER_MOD_HASH,
            SINGLETON_MOD_HASH,
            SINGLETON_LAUNCHER_PUZHASH,
            CAT_MOD_HASH,
            DAO_FINISHED_STATE_MOD_HASH,
            TREASURY_MOD_HASH,
            LOCKUP_SELF_HASH,
            CAT_TAIL_HASH,
            TREASURY_ID,
        ) = uncurried_args
        for wallet in self.wallets.values():
            if wallet.type() == WalletType.DAO:
                assert isinstance(wallet, DAOWallet)
                if wallet.dao_info.treasury_id == TREASURY_ID.as_atom():
                    assert isinstance(coin_state.created_height, int)
                    await wallet.add_or_update_proposal_info(coin_spend, uint32(coin_state.created_height))
                    return WalletIdentifier.create(wallet)
        return None  # pragma: no cover

    async def handle_dao_finished_proposals(
        self,
        uncurried_args: Iterator[Program],
        parent_coin_state: CoinState,
        coin_state: CoinState,
        coin_spend: CoinSpend,
    ) -> Optional[WalletIdentifier]:
        if coin_state.created_height is None:  # pragma: no cover
            raise ValueError("coin_state argument to handle_dao_finished_proposals cannot have created_height of None")
        (
            SINGLETON_STRUCT,  # (SINGLETON_MOD_HASH, (SINGLETON_ID, LAUNCHER_PUZZLE_HASH))
            FINISHED_STATE_MOD_HASH,
        ) = uncurried_args
        proposal_id = SINGLETON_STRUCT.rest().first().as_atom()
        for wallet in self.wallets.values():
            if wallet.type() == WalletType.DAO:
                assert isinstance(wallet, DAOWallet)
                for proposal_info in wallet.dao_info.proposals_list:
                    if proposal_info.proposal_id == proposal_id:
                        await wallet.add_or_update_proposal_info(coin_spend, uint32(coin_state.created_height))
                        return WalletIdentifier.create(wallet)
        return None

    async def get_dao_wallet_from_coinspend_hint(
        self, coin_spend: CoinSpend, coin_state: CoinState
    ) -> Optional[WalletIdentifier]:
        hinted_coin = compute_spend_hints_and_additions(coin_spend)[0][coin_state.coin.name()]
        if hinted_coin:
            for wallet in self.wallets.values():
                if wallet.type() == WalletType.DAO.value:
                    assert isinstance(wallet, DAOWallet)
                    if get_p2_singleton_puzhash(wallet.dao_info.treasury_id) == hinted_coin.hint:
                        return WalletIdentifier.create(wallet)
        return None

    async def handle_nft(
        self,
        nft_data: NFTCoinData,
    ) -> Optional[WalletIdentifier]:
        """
        Handle the new coin when it is a NFT
        :param nft_data: all necessary data to process a NFT coin
        :return: Wallet ID & Wallet Type
        """
        wallet_identifier = None
        # DID ID determines which NFT wallet should process the NFT
        new_did_id = None
        old_did_id = None
        # P2 puzzle hash determines if we should ignore the NFT
        uncurried_nft: UncurriedNFT = nft_data.uncurried_nft
        old_p2_puzhash = uncurried_nft.p2_puzzle.get_tree_hash()
        metadata, new_p2_puzhash = get_metadata_and_phs(
            uncurried_nft,
            nft_data.parent_coin_spend.solution,
        )
        if uncurried_nft.supports_did:
            new_did_id = get_new_owner_did(uncurried_nft, nft_data.parent_coin_spend.solution.to_program())
            old_did_id = uncurried_nft.owner_did
            if new_did_id is None:
                new_did_id = old_did_id
            if new_did_id == b"":
                new_did_id = None
        self.log.debug(
            "Handling NFT: %s， old DID:%s, new DID:%s, old P2:%s, new P2:%s",
            nft_data.parent_coin_spend,
            old_did_id,
            new_did_id,
            old_p2_puzhash,
            new_p2_puzhash,
        )
        new_derivation_record: Optional[
            DerivationRecord
        ] = await self.puzzle_store.get_derivation_record_for_puzzle_hash(new_p2_puzhash)
        old_derivation_record: Optional[
            DerivationRecord
        ] = await self.puzzle_store.get_derivation_record_for_puzzle_hash(old_p2_puzhash)
        if new_derivation_record is None and old_derivation_record is None:
            self.log.debug(
                "Cannot find a P2 puzzle hash for NFT:%s, this NFT belongs to others.",
                uncurried_nft.singleton_launcher_id.hex(),
            )
            return wallet_identifier
        for nft_wallet in self.wallets.copy().values():
            if not isinstance(nft_wallet, NFTWallet):
                continue
            if nft_wallet.nft_wallet_info.did_id == old_did_id and old_derivation_record is not None:
                self.log.info(
                    "Removing old NFT, NFT_ID:%s, DID_ID:%s",
                    uncurried_nft.singleton_launcher_id.hex(),
                    old_did_id,
                )
                if nft_data.parent_coin_state.spent_height is not None:
                    await nft_wallet.remove_coin(
                        nft_data.parent_coin_spend.coin, uint32(nft_data.parent_coin_state.spent_height)
                    )
                    is_empty = await nft_wallet.is_empty()
                    has_did = False
                    for did_wallet in self.wallets.values():
                        if not isinstance(did_wallet, DIDWallet):
                            continue
                        assert did_wallet.did_info.origin_coin is not None
                        if did_wallet.did_info.origin_coin.name() == old_did_id:
                            has_did = True
                            break
                    if is_empty and nft_wallet.did_id is not None and not has_did:
                        self.log.info(f"No NFT, deleting wallet {nft_wallet.did_id.hex()} ...")
                        await self.user_store.delete_wallet(nft_wallet.wallet_info.id)
                        self.wallets.pop(nft_wallet.wallet_info.id)
            if nft_wallet.nft_wallet_info.did_id == new_did_id and new_derivation_record is not None:
                self.log.info(
                    "Adding new NFT, NFT_ID:%s, DID_ID:%s",
                    uncurried_nft.singleton_launcher_id.hex(),
                    new_did_id,
                )
                wallet_identifier = WalletIdentifier.create(nft_wallet)

        if wallet_identifier is None and new_derivation_record is not None:
            # Cannot find an existed NFT wallet for the new NFT
            self.log.info(
                "Cannot find a NFT wallet for NFT_ID: %s DID_ID: %s, creating a new one.",
                uncurried_nft.singleton_launcher_id,
                new_did_id,
            )
            new_nft_wallet: NFTWallet = await NFTWallet.create_new_nft_wallet(
                self, self.main_wallet, did_id=new_did_id, name="NFT Wallet"
            )
            wallet_identifier = WalletIdentifier.create(new_nft_wallet)
        return wallet_identifier

    async def handle_clawback(
        self,
        metadata: ClawbackMetadata,
        coin_state: CoinState,
        coin_spend: CoinSpend,
        peer: WSHDDcoinConnection,
    ) -> Optional[WalletIdentifier]:
        """
        Handle Clawback coins
        :param metadata: Clawback metadata for spending the merkle coin
        :param coin_state: Clawback merkle coin
        :param coin_spend: Parent coin spend
        :param peer: Fullnode peer
        :return:
        """
        # Record metadata
        assert coin_state.created_height is not None
        is_recipient: Optional[bool] = None
        # Check if the wallet is the sender
        sender_derivation_record: Optional[
            DerivationRecord
        ] = await self.puzzle_store.get_derivation_record_for_puzzle_hash(metadata.sender_puzzle_hash)
        # Check if the wallet is the recipient
        recipient_derivation_record = await self.puzzle_store.get_derivation_record_for_puzzle_hash(
            metadata.recipient_puzzle_hash
        )
        if sender_derivation_record is not None:
            self.log.info("Found Clawback merkle coin %s as the sender.", coin_state.coin.name().hex())
            is_recipient = False
        elif recipient_derivation_record is not None:
            self.log.info("Found Clawback merkle coin %s as the recipient.", coin_state.coin.name().hex())
            is_recipient = True
            # For the recipient we need to manually subscribe the merkle coin
            await self.add_interested_coin_ids([coin_state.coin.name()])
        if is_recipient is not None:
            spend_bundle = SpendBundle([coin_spend], G2Element())
            memos = compute_memos(spend_bundle)
            spent_height: uint32 = uint32(0)
            if coin_state.spent_height is not None:
                self.log.debug("Resync clawback coin: %s", coin_state.coin.name().hex())
                # Resync case
                spent_height = uint32(coin_state.spent_height)
                # Create Clawback outgoing transaction
                created_timestamp = await self.wallet_node.get_timestamp_for_height(uint32(coin_state.spent_height))
                clawback_coin_spend: CoinSpend = await fetch_coin_spend_for_coin_state(coin_state, peer)
                clawback_spend_bundle: SpendBundle = SpendBundle([clawback_coin_spend], G2Element())
                if await self.puzzle_store.puzzle_hash_exists(clawback_spend_bundle.additions()[0].puzzle_hash):
                    tx_record = TransactionRecord(
                        confirmed_at_height=uint32(coin_state.spent_height),
                        created_at_time=created_timestamp,
                        to_puzzle_hash=metadata.sender_puzzle_hash
                        if clawback_spend_bundle.additions()[0].puzzle_hash == metadata.sender_puzzle_hash
                        else metadata.recipient_puzzle_hash,
                        amount=uint64(coin_state.coin.amount),
                        fee_amount=uint64(0),
                        confirmed=True,
                        sent=uint32(0),
                        spend_bundle=clawback_spend_bundle,
                        additions=clawback_spend_bundle.additions(),
                        removals=clawback_spend_bundle.removals(),
                        wallet_id=uint32(1),
                        sent_to=[],
                        trade_id=None,
                        type=uint32(TransactionType.OUTGOING_CLAWBACK),
                        name=clawback_spend_bundle.name(),
                        memos=list(compute_memos(clawback_spend_bundle).items()),
                        valid_times=ConditionValidTimes(),
                    )
                    await self.tx_store.add_transaction_record(tx_record)
            coin_record = WalletCoinRecord(
                coin_state.coin,
                uint32(coin_state.created_height),
                spent_height,
                spent_height != 0,
                False,
                WalletType.STANDARD_WALLET,
                1,
                CoinType.CLAWBACK,
                VersionedBlob(ClawbackVersion.V1.value, bytes(metadata)),
            )
            # Add merkle coin
            await self.coin_store.add_coin_record(coin_record)
            # Add tx record
            # We use TransactionRecord.confirmed to indicate if a Clawback transaction is claimable
            # If the Clawback coin is unspent, confirmed should be false
            created_timestamp = await self.wallet_node.get_timestamp_for_height(uint32(coin_state.created_height))
            tx_record = TransactionRecord(
                confirmed_at_height=uint32(coin_state.created_height),
                created_at_time=uint64(created_timestamp),
                to_puzzle_hash=metadata.recipient_puzzle_hash,
                amount=uint64(coin_state.coin.amount),
                fee_amount=uint64(0),
                confirmed=spent_height != 0,
                sent=uint32(0),
                spend_bundle=None,
                additions=[coin_state.coin],
                removals=[coin_spend.coin],
                wallet_id=uint32(1),
                sent_to=[],
                trade_id=None,
                type=uint32(
                    TransactionType.INCOMING_CLAWBACK_RECEIVE
                    if is_recipient
                    else TransactionType.INCOMING_CLAWBACK_SEND
                ),
                # Use coin ID as the TX ID to mapping with the coin table
                name=coin_record.coin.name(),
                memos=list(memos.items()),
                valid_times=ConditionValidTimes(),
            )
            await self.tx_store.add_transaction_record(tx_record)
        return None

    async def handle_vc(self, vc: VerifiedCredential) -> Optional[WalletIdentifier]:
        # Check the ownership
        derivation_record: Optional[DerivationRecord] = await self.puzzle_store.get_derivation_record_for_puzzle_hash(
            vc.inner_puzzle_hash
        )
        if derivation_record is None:
            self.log.warning(
                f"Verified credential {vc.launcher_id.hex()} is not belong to the current wallet."
            )  # pragma: no cover
            return None  # pragma: no cover
        self.log.info(f"Found verified credential {vc.launcher_id.hex()}.")
        for wallet_info in await self.get_all_wallet_info_entries(wallet_type=WalletType.VC):
            return WalletIdentifier(wallet_info.id, WalletType.VC)
        else:
            # Create a new VC wallet
            vc_wallet = await VCWallet.create_new_vc_wallet(self, self.main_wallet)  # pragma: no cover
            return WalletIdentifier(vc_wallet.id(), WalletType.VC)  # pragma: no cover

    async def _add_coin_states(
        self,
        coin_states: List[CoinState],
        peer: WSHDDcoinConnection,
        fork_height: Optional[uint32],
    ) -> None:
        # TODO: add comment about what this method does
        # Input states should already be sorted by cs_height, with reorgs at the beginning
        curr_h = -1
        for c_state in coin_states:
            last_change_height = last_change_height_cs(c_state)
            if last_change_height < curr_h:
                raise ValueError("Input coin_states is not sorted properly")
            curr_h = last_change_height

        trade_removals = await self.trade_manager.get_coins_of_interest()
        all_unconfirmed: List[TransactionRecord] = await self.tx_store.get_all_unconfirmed()
        used_up_to = -1
        ph_to_index_cache: LRUCache[bytes32, uint32] = LRUCache(100)

        coin_names = [bytes32(coin_state.coin.name()) for coin_state in coin_states]
        local_records = await self.coin_store.get_coin_records(coin_id_filter=HashFilter.include(coin_names))

        for coin_name, coin_state in zip(coin_names, coin_states):
            if peer.closed:
                raise ConnectionError("Connection closed")
            self.log.debug("Add coin state: %s: %s", coin_name, coin_state)
            local_record = local_records.coin_id_to_record.get(coin_name)
            rollback_wallets = None
            try:
                async with self.db_wrapper.writer():
                    rollback_wallets = self.wallets.copy()  # Shallow copy of wallets if writer rolls back the db
                    # This only succeeds if we don't raise out of the transaction
                    await self.retry_store.remove_state(coin_state)

                    wallet_identifier = await self.get_wallet_identifier_for_puzzle_hash(coin_state.coin.puzzle_hash)
                    coin_data: Optional[Streamable] = None
                    # If we already have this coin, & it was spent & confirmed at the same heights, then return (done)
                    if local_record is not None:
                        local_spent = None
                        if local_record.spent_block_height != 0:
                            local_spent = local_record.spent_block_height
                        if (
                            local_spent == coin_state.spent_height
                            and local_record.confirmed_block_height == coin_state.created_height
                        ):
                            continue

                    if coin_state.spent_height is not None and coin_name in trade_removals:
                        await self.trade_manager.coins_of_interest_farmed(coin_state, fork_height, peer)
                    if wallet_identifier is not None:
                        self.log.debug(f"Found existing wallet_identifier: {wallet_identifier}, coin: {coin_name}")
                    elif local_record is not None:
                        wallet_identifier = WalletIdentifier(uint32(local_record.wallet_id), local_record.wallet_type)
                    elif coin_state.created_height is not None:
                        wallet_identifier, coin_data = await self.determine_coin_type(peer, coin_state, fork_height)
                        try:
                            dl_wallet = self.get_dl_wallet()
                        except ValueError:
                            pass
                        else:
                            if (
                                await dl_wallet.get_singleton_record(coin_name) is not None
                                or coin_state.coin.puzzle_hash == MIRROR_PUZZLE_HASH
                            ):
                                wallet_identifier = WalletIdentifier.create(dl_wallet)

                    if wallet_identifier is None:
                        self.log.debug(f"No wallet for coin state: {coin_state}")
                        continue

                    # Update the DB to signal that we used puzzle hashes up to this one
                    derivation_index = ph_to_index_cache.get(coin_state.coin.puzzle_hash)
                    if derivation_index is None:
                        derivation_index = await self.puzzle_store.index_for_puzzle_hash(coin_state.coin.puzzle_hash)
                    if derivation_index is not None:
                        ph_to_index_cache.put(coin_state.coin.puzzle_hash, derivation_index)
                        if derivation_index > used_up_to:
                            await self.puzzle_store.set_used_up_to(derivation_index)
                            used_up_to = derivation_index

                    if coin_state.created_height is None:
                        # TODO implements this coin got reorged
                        # TODO: we need to potentially roll back the pool wallet here
                        pass
                    # if the new coin has not been spent (i.e not ephemeral)
                    elif coin_state.created_height is not None and coin_state.spent_height is None:
                        if local_record is None:
                            await self.coin_added(
                                coin_state.coin,
                                uint32(coin_state.created_height),
                                all_unconfirmed,
                                wallet_identifier.id,
                                wallet_identifier.type,
                                peer,
                                coin_name,
                                coin_data,
                            )

                    # if the coin has been spent
                    elif coin_state.created_height is not None and coin_state.spent_height is not None:
                        self.log.debug("Coin spent: %s", coin_state)
                        children = await self.wallet_node.fetch_children(coin_name, peer=peer, fork_height=fork_height)
                        record = local_record
                        if record is None:
                            farmer_reward = False
                            pool_reward = False
                            tx_type: int
                            if self.is_farmer_reward(uint32(coin_state.created_height), coin_state.coin):
                                farmer_reward = True
                                tx_type = TransactionType.FEE_REWARD.value
                            elif self.is_pool_reward(uint32(coin_state.created_height), coin_state.coin):
                                pool_reward = True
                                tx_type = TransactionType.COINBASE_REWARD.value
                            else:
                                tx_type = TransactionType.INCOMING_TX.value
                            record = WalletCoinRecord(
                                coin_state.coin,
                                uint32(coin_state.created_height),
                                uint32(coin_state.spent_height),
                                True,
                                farmer_reward or pool_reward,
                                wallet_identifier.type,
                                wallet_identifier.id,
                            )
                            await self.coin_store.add_coin_record(record)
                            # Coin first received
                            parent_coin_record: Optional[WalletCoinRecord] = await self.coin_store.get_coin_record(
                                coin_state.coin.parent_coin_info
                            )
                            if (
                                parent_coin_record is not None
                                and wallet_identifier.type == parent_coin_record.wallet_type
                            ):
                                change = True
                            else:
                                change = False

                            if not change:
                                created_timestamp = await self.wallet_node.get_timestamp_for_height(
                                    uint32(coin_state.created_height)
                                )
                                tx_record = TransactionRecord(
                                    confirmed_at_height=uint32(coin_state.created_height),
                                    created_at_time=uint64(created_timestamp),
                                    to_puzzle_hash=(
                                        await self.convert_puzzle_hash(
                                            wallet_identifier.id, coin_state.coin.puzzle_hash
                                        )
                                    ),
                                    amount=uint64(coin_state.coin.amount),
                                    fee_amount=uint64(0),
                                    confirmed=True,
                                    sent=uint32(0),
                                    spend_bundle=None,
                                    additions=[coin_state.coin],
                                    removals=[],
                                    wallet_id=wallet_identifier.id,
                                    sent_to=[],
                                    trade_id=None,
                                    type=uint32(tx_type),
                                    name=bytes32.secret(),
                                    memos=[],
                                    valid_times=ConditionValidTimes(),
                                )
                                await self.tx_store.add_transaction_record(tx_record)

                            additions = [state.coin for state in children]
                            if len(children) > 0:
                                fee = 0

                                to_puzzle_hash = None
                                coin_spend: Optional[CoinSpend] = None
                                clawback_metadata: Optional[ClawbackMetadata] = None
                                # Find coin that doesn't belong to us
                                amount = 0
                                for coin in additions:
                                    derivation_record = await self.puzzle_store.get_derivation_record_for_puzzle_hash(
                                        coin.puzzle_hash
                                    )
                                    if derivation_record is None:  # not change
                                        to_puzzle_hash = coin.puzzle_hash
                                        amount += coin.amount
                                        if coin_spend is None:
                                            # To prevent unnecessary fetch, we only fetch once,
                                            # if there is a child coin that is not owned by the wallet.
                                            coin_spend = await fetch_coin_spend_for_coin_state(coin_state, peer)
                                            # Check if the parent coin is a Clawback coin
                                            puzzle: Program = coin_spend.puzzle_reveal.to_program()
                                            solution: Program = coin_spend.solution.to_program()
                                            uncurried = uncurry_puzzle(puzzle)
                                            clawback_metadata = match_clawback_puzzle(uncurried, puzzle, solution)
                                        if clawback_metadata is not None:
                                            # Add the Clawback coin as the interested coin for the sender
                                            await self.add_interested_coin_ids([coin.name()])
                                    elif wallet_identifier.type == WalletType.CAT:
                                        # We subscribe to change for CATs since they didn't hint previously
                                        await self.add_interested_coin_ids([coin.name()])

                                if to_puzzle_hash is None:
                                    to_puzzle_hash = additions[0].puzzle_hash

                                spent_timestamp = await self.wallet_node.get_timestamp_for_height(
                                    uint32(coin_state.spent_height)
                                )

                                # Reorg rollback adds reorged transactions so it's possible there is tx_record already
                                # Even though we are just adding coin record to the db (after reorg)
                                tx_records: List[TransactionRecord] = []
                                for out_tx_record in all_unconfirmed:
                                    for rem_coin in out_tx_record.removals:
                                        if rem_coin == coin_state.coin:
                                            tx_records.append(out_tx_record)

                                if len(tx_records) > 0:
                                    for tx_record in tx_records:
                                        await self.tx_store.set_confirmed(
                                            tx_record.name, uint32(coin_state.spent_height)
                                        )
                                else:
                                    tx_name = bytes(coin_state.coin.name())
                                    for added_coin in additions:
                                        tx_name += bytes(added_coin.name())
                                    tx_name = std_hash(tx_name)
                                    tx_record = TransactionRecord(
                                        confirmed_at_height=uint32(coin_state.spent_height),
                                        created_at_time=uint64(spent_timestamp),
                                        to_puzzle_hash=(
                                            await self.convert_puzzle_hash(wallet_identifier.id, to_puzzle_hash)
                                        ),
                                        amount=uint64(int(amount)),
                                        fee_amount=uint64(fee),
                                        confirmed=True,
                                        sent=uint32(0),
                                        spend_bundle=None,
                                        additions=additions,
                                        removals=[coin_state.coin],
                                        wallet_id=wallet_identifier.id,
                                        sent_to=[],
                                        trade_id=None,
                                        type=uint32(TransactionType.OUTGOING_TX.value),
                                        name=tx_name,
                                        memos=[],
                                        valid_times=ConditionValidTimes(),
                                    )

                                    await self.tx_store.add_transaction_record(tx_record)
                        else:
                            await self.coin_store.set_spent(coin_name, uint32(coin_state.spent_height))
                            if record.coin_type == CoinType.CLAWBACK:
                                await self.interested_store.remove_interested_coin_id(coin_state.coin.name())
                            confirmed_tx_records: List[TransactionRecord] = []

                            for tx_record in all_unconfirmed:
                                if tx_record.type in CLAWBACK_INCOMING_TRANSACTION_TYPES:
                                    for add_coin in tx_record.additions:
                                        if add_coin == coin_state.coin:
                                            confirmed_tx_records.append(tx_record)
                                else:
                                    for rem_coin in tx_record.removals:
                                        if rem_coin == coin_state.coin:
                                            confirmed_tx_records.append(tx_record)

                            for tx_record in confirmed_tx_records:
                                await self.tx_store.set_confirmed(tx_record.name, uint32(coin_state.spent_height))
                        for unconfirmed_record in all_unconfirmed:
                            for rem_coin in unconfirmed_record.removals:
                                if rem_coin == coin_state.coin:
                                    self.log.info(f"Setting tx_id: {unconfirmed_record.name} to confirmed")
                                    await self.tx_store.set_confirmed(
                                        unconfirmed_record.name, uint32(coin_state.spent_height)
                                    )

                        if record.wallet_type in [WalletType.POOLING_WALLET, WalletType.DAO]:
                            wallet_type_to_class = {WalletType.POOLING_WALLET: PoolWallet, WalletType.DAO: DAOWallet}
                            if coin_state.spent_height is not None and coin_state.coin.amount == uint64(1):
                                singleton_wallet: Union[PoolWallet, DAOWallet] = self.get_wallet(
                                    id=uint32(record.wallet_id), required_type=wallet_type_to_class[record.wallet_type]
                                )
                                curr_coin_state: CoinState = coin_state

                                while curr_coin_state.spent_height is not None:
                                    cs: CoinSpend = await fetch_coin_spend_for_coin_state(curr_coin_state, peer)
                                    success = await singleton_wallet.apply_state_transition(
                                        cs, uint32(curr_coin_state.spent_height)
                                    )
                                    if not success:
                                        break
                                    new_singleton_coin = get_most_recent_singleton_coin_from_coin_spend(cs)
                                    if new_singleton_coin is None:
                                        # No more singleton (maybe destroyed?)
                                        break

                                    coin_name = new_singleton_coin.name()
                                    existing = await self.coin_store.get_coin_record(coin_name)
                                    if existing is None:
                                        await self.coin_added(
                                            new_singleton_coin,
                                            uint32(curr_coin_state.spent_height),
                                            [],
                                            uint32(record.wallet_id),
                                            record.wallet_type,
                                            peer,
                                            coin_name,
                                            coin_data,
                                        )
                                    await self.coin_store.set_spent(
                                        curr_coin_state.coin.name(), uint32(curr_coin_state.spent_height)
                                    )
                                    await self.add_interested_coin_ids([new_singleton_coin.name()])
                                    new_coin_state: List[CoinState] = await self.wallet_node.get_coin_state(
                                        [coin_name], peer=peer, fork_height=fork_height
                                    )
                                    assert len(new_coin_state) == 1
                                    curr_coin_state = new_coin_state[0]
                        if record.wallet_type == WalletType.DATA_LAYER:
                            singleton_spend = await fetch_coin_spend_for_coin_state(coin_state, peer)
                            dl_wallet = self.get_wallet(id=uint32(record.wallet_id), required_type=DataLayerWallet)
                            await dl_wallet.singleton_removed(
                                singleton_spend,
                                uint32(coin_state.spent_height),
                            )

                        elif record.wallet_type == WalletType.NFT:
                            if coin_state.spent_height is not None:
                                nft_wallet = self.get_wallet(id=uint32(record.wallet_id), required_type=NFTWallet)
                                await nft_wallet.remove_coin(coin_state.coin, uint32(coin_state.spent_height))
                        elif record.wallet_type == WalletType.VC:
                            if coin_state.spent_height is not None:
                                vc_wallet = self.get_wallet(id=uint32(record.wallet_id), required_type=VCWallet)
                                await vc_wallet.remove_coin(coin_state.coin, uint32(coin_state.spent_height))

                        # Check if a child is a singleton launcher
                        for child in children:
                            if child.coin.puzzle_hash != SINGLETON_LAUNCHER_HASH:
                                continue
                            if await self.have_a_pool_wallet_with_launched_id(child.coin.name()):
                                continue
                            if child.spent_height is None:
                                # TODO handle spending launcher later block
                                continue
                            launcher_spend = await fetch_coin_spend_for_coin_state(child, peer)
                            if launcher_spend is None:
                                continue
                            try:
                                pool_state = solution_to_pool_state(launcher_spend)
                                assert pool_state is not None
                            except (AssertionError, ValueError) as e:
                                self.log.debug(f"Not a pool wallet launcher {e}, child: {child}")
                                matched, inner_puzhash = await DataLayerWallet.match_dl_launcher(launcher_spend)
                                if (
                                    matched
                                    and inner_puzhash is not None
                                    and (await self.puzzle_store.puzzle_hash_exists(inner_puzhash))
                                ):
                                    try:
                                        dl_wallet = self.get_dl_wallet()
                                    except ValueError:
                                        dl_wallet = await DataLayerWallet.create_new_dl_wallet(
                                            self,
                                        )
                                    await dl_wallet.track_new_launcher_id(
                                        child.coin.name(),
                                        peer,
                                        spend=launcher_spend,
                                        height=uint32(child.spent_height),
                                    )
                                continue

                            # solution_to_pool_state may return None but this may not be an error
                            if pool_state is None:
                                self.log.debug("solution_to_pool_state returned None, ignore and continue")
                                continue

                            pool_wallet = await PoolWallet.create(
                                self,
                                self.main_wallet,
                                child.coin.name(),
                                [launcher_spend],
                                uint32(child.spent_height),
                                name="pool_wallet",
                            )
                            launcher_spend_additions = compute_additions(launcher_spend)
                            assert len(launcher_spend_additions) == 1
                            coin_added = launcher_spend_additions[0]
                            coin_name = coin_added.name()
                            existing = await self.coin_store.get_coin_record(coin_name)
                            if existing is None:
                                await self.coin_added(
                                    coin_added,
                                    uint32(coin_state.spent_height),
                                    [],
                                    pool_wallet.id(),
                                    pool_wallet.type(),
                                    peer,
                                    coin_name,
                                    coin_data,
                                )
                            await self.add_interested_coin_ids([coin_name])

                    else:
                        raise RuntimeError("All cases already handled")  # Logic error, all cases handled
            except Exception as e:
                self.log.exception(f"Failed to add coin_state: {coin_state}, error: {e}")
                if rollback_wallets is not None:
                    self.wallets = rollback_wallets  # Restore since DB will be rolled back by writer
                if isinstance(e, PeerRequestException) or isinstance(e, aiosqlite.Error):
                    await self.retry_store.add_state(coin_state, peer.peer_node_id, fork_height)
                else:
                    await self.retry_store.remove_state(coin_state)
                continue

    async def add_coin_states(
        self,
        coin_states: List[CoinState],
        peer: WSHDDcoinConnection,
        fork_height: Optional[uint32],
    ) -> bool:
        try:
            await self._add_coin_states(coin_states, peer, fork_height)
        except Exception as e:
            log_level = logging.DEBUG if peer.closed else logging.ERROR
            self.log.log(log_level, f"add_coin_states failed - exception {e}, traceback: {traceback.format_exc()}")
            return False

        await self.blockchain.clean_block_records()

        return True

    async def have_a_pool_wallet_with_launched_id(self, launcher_id: bytes32) -> bool:
        for wallet_id, wallet in self.wallets.items():
            if wallet.type() == WalletType.POOLING_WALLET:
                assert isinstance(wallet, PoolWallet)
                if (await wallet.get_current_state()).launcher_id == launcher_id:
                    self.log.warning("Already have, not recreating")
                    return True
        return False

    def is_pool_reward(self, created_height: uint32, coin: Coin) -> bool:
        if coin.amount != calculate_pool_reward(created_height) and coin.amount != calculate_pool_reward(
            uint32(max(0, created_height - 128))
        ):
            # Optimization to avoid the computation below. Any coin that has a different amount is not a pool reward
            return False
        for i in range(0, 30):
            try_height = created_height - i
            if try_height < 0:
                break
            calculated = pool_parent_id(uint32(try_height), self.constants.GENESIS_CHALLENGE)
            if calculated == coin.parent_coin_info:
                return True
        return False

    def is_farmer_reward(self, created_height: uint32, coin: Coin) -> bool:
        if coin.amount < calculate_base_farmer_reward(created_height):
            # Optimization to avoid the computation below. Any coin less than this base amount cannot be farmer reward
            return False
        for i in range(0, 30):
            try_height = created_height - i
            if try_height < 0:
                break
            calculated = farmer_parent_id(uint32(try_height), self.constants.GENESIS_CHALLENGE)
            if calculated == coin.parent_coin_info:
                return True
        return False

    async def get_wallet_identifier_for_puzzle_hash(self, puzzle_hash: bytes32) -> Optional[WalletIdentifier]:
        wallet_identifier = await self.puzzle_store.get_wallet_identifier_for_puzzle_hash(puzzle_hash)
        if wallet_identifier is not None:
            return wallet_identifier

        interested_wallet_id = await self.interested_store.get_interested_puzzle_hash_wallet_id(puzzle_hash=puzzle_hash)
        if interested_wallet_id is not None:
            wallet_id = uint32(interested_wallet_id)
            if wallet_id not in self.wallets.keys():
                self.log.warning(f"Do not have wallet {wallet_id} for puzzle_hash {puzzle_hash}")
                return None
            return WalletIdentifier(uint32(wallet_id), self.wallets[uint32(wallet_id)].type())
        return None

    async def get_wallet_identifier_for_coin(
        self, coin: Coin, hint_dict: Dict[bytes32, bytes32] = {}
    ) -> Optional[WalletIdentifier]:
        wallet_identifier = await self.puzzle_store.get_wallet_identifier_for_puzzle_hash(coin.puzzle_hash)
        if (
            wallet_identifier is None
            and coin.name() in hint_dict
            and await self.puzzle_store.puzzle_hash_exists(hint_dict[coin.name()])
        ):
            wallet_identifier = await self.get_wallet_identifier_for_hinted_coin(coin, hint_dict[coin.name()])
        if wallet_identifier is None:
            coin_record = await self.coin_store.get_coin_record(coin.name())
            if coin_record is not None:
                wallet_identifier = WalletIdentifier(uint32(coin_record.wallet_id), coin_record.wallet_type)

        return wallet_identifier

    async def get_wallet_identifier_for_hinted_coin(self, coin: Coin, hint: bytes32) -> Optional[WalletIdentifier]:
        for wallet in self.wallets.values():
            if await wallet.match_hinted_coin(coin, hint):
                return WalletIdentifier(wallet.id(), wallet.type())
        return None

    async def coin_added(
        self,
        coin: Coin,
        height: uint32,
        all_unconfirmed_transaction_records: List[TransactionRecord],
        wallet_id: uint32,
        wallet_type: WalletType,
        peer: WSHDDcoinConnection,
        coin_name: bytes32,
        coin_data: Optional[Streamable],
    ) -> None:
        """
        Adding coin to DB
        """

        self.log.debug(
            "Adding record to state manager coin: %s at %s wallet_id: %s and type: %s",
            coin,
            height,
            wallet_id,
            wallet_type,
        )

        if self.is_pool_reward(height, coin):
            tx_type = TransactionType.COINBASE_REWARD
        elif self.is_farmer_reward(height, coin):
            tx_type = TransactionType.FEE_REWARD
        else:
            tx_type = TransactionType.INCOMING_TX

        coinbase = tx_type in {TransactionType.FEE_REWARD, TransactionType.COINBASE_REWARD}
        coin_confirmed_transaction = False
        if not coinbase:
            for record in all_unconfirmed_transaction_records:
                if coin in record.additions and not record.confirmed:
                    await self.tx_store.set_confirmed(record.name, height)
                    coin_confirmed_transaction = True
                    break

        parent_coin_record: Optional[WalletCoinRecord] = await self.coin_store.get_coin_record(coin.parent_coin_info)
        change = parent_coin_record is not None and wallet_type.value == parent_coin_record.wallet_type
        # If the coin is from a Clawback spent, we want to add the INCOMING_TX,
        # no matter if there is another TX updated.
        clawback = parent_coin_record is not None and parent_coin_record.coin_type == CoinType.CLAWBACK

        if coinbase or clawback or not coin_confirmed_transaction and not change:
            tx_record = TransactionRecord(
                confirmed_at_height=uint32(height),
                created_at_time=await self.wallet_node.get_timestamp_for_height(height),
                to_puzzle_hash=await self.convert_puzzle_hash(wallet_id, coin.puzzle_hash),
                amount=uint64(coin.amount),
                fee_amount=uint64(0),
                confirmed=True,
                sent=uint32(0),
                spend_bundle=None,
                additions=[coin],
                removals=[],
                wallet_id=wallet_id,
                sent_to=[],
                trade_id=None,
                type=uint32(tx_type),
                name=coin_name,
                memos=[],
                valid_times=ConditionValidTimes(),
            )
            if tx_record.amount > 0:
                await self.tx_store.add_transaction_record(tx_record)

        # We only add normal coins here
        coin_record: WalletCoinRecord = WalletCoinRecord(
            coin, height, uint32(0), False, coinbase, wallet_type, wallet_id
        )

        await self.coin_store.add_coin_record(coin_record, coin_name)

        await self.wallets[wallet_id].coin_added(coin, height, peer, coin_data)

        if wallet_type == WalletType.DAO:
            return

        await self.create_more_puzzle_hashes()

    async def add_pending_transaction(self, tx_record: TransactionRecord) -> None:
        """
        Called from wallet before new transaction is sent to the full_node
        """
        # Wallet node will use this queue to retry sending this transaction until full nodes receives it
        await self.tx_store.add_transaction_record(tx_record)
        all_coins_names = []
        all_coins_names.extend([coin.name() for coin in tx_record.additions])
        all_coins_names.extend([coin.name() for coin in tx_record.removals])

        await self.add_interested_coin_ids(all_coins_names)
        if tx_record.spend_bundle is not None:
            self.tx_pending_changed()
        self.state_changed("pending_transaction", tx_record.wallet_id)

    async def add_transaction(self, tx_record: TransactionRecord) -> None:
        """
        Called from wallet to add transaction that is not being set to full_node
        """
        await self.tx_store.add_transaction_record(tx_record)
        self.state_changed("pending_transaction", tx_record.wallet_id)

    async def remove_from_queue(
        self,
        spendbundle_id: bytes32,
        name: str,
        send_status: MempoolInclusionStatus,
        error: Optional[Err],
    ) -> None:
        """
        Full node received our transaction, no need to keep it in queue anymore, unless there was an error
        """

        updated = await self.tx_store.increment_sent(spendbundle_id, name, send_status, error)
        if updated:
            tx: Optional[TransactionRecord] = await self.get_transaction(spendbundle_id)
            if tx is not None and tx.spend_bundle is not None:
                self.log.info("Checking if we need to cancel trade for tx: %s", tx.name)
                # we're only interested in errors that are not temporary
                if (
                    send_status != MempoolInclusionStatus.SUCCESS
                    and error
                    and error not in (Err.INVALID_FEE_LOW_FEE, Err.INVALID_FEE_TOO_CLOSE_TO_ZERO)
                ):
                    coins_removed = tx.spend_bundle.removals()
                    trade_coins_removed = set()
                    trades = []
                    for removed_coin in coins_removed:
                        trade = await self.trade_manager.get_trade_by_coin(removed_coin)
                        if trade is not None and trade.status in (
                            TradeStatus.PENDING_CONFIRM.value,
                            TradeStatus.PENDING_ACCEPT.value,
                            TradeStatus.PENDING_CANCEL.value,
                        ):
                            if trade not in trades:
                                trades.append(trade)
                            # offer was tied to these coins, lets subscribe to them to get a confirmation to
                            # cancel it if it's confirmed
                            # we send transactions to multiple peers, and in cases when mempool gets
                            # fragmented, it's safest to wait for confirmation from blockchain before setting
                            # offer to failed
                            trade_coins_removed.add(removed_coin.name())
                    if trades != [] and trade_coins_removed != set():
                        if not tx.is_valid():
                            # we've tried to send this transaction to a full node multiple times
                            # but failed, it's safe to assume that it's not going to be accepted
                            # we can mark this offer as failed
                            self.log.info("This offer can't be posted, removing it from pending offers")
                            for trade in trades:
                                await self.trade_manager.fail_pending_offer(trade.trade_id)
                        else:
                            self.log.info(
                                "Subscribing to unspendable offer coins: %s",
                                [x.hex() for x in trade_coins_removed],
                            )
                            await self.add_interested_coin_ids(list(trade_coins_removed))

                    self.state_changed(
                        "tx_update", tx.wallet_id, {"transaction": tx, "error": error.name, "status": send_status.value}
                    )
                else:
                    self.state_changed("tx_update", tx.wallet_id, {"transaction": tx})

    async def get_all_transactions(self, wallet_id: int) -> List[TransactionRecord]:
        """
        Retrieves all confirmed and pending transactions
        """
        records = await self.tx_store.get_all_transactions_for_wallet(wallet_id)
        return records

    async def get_transaction(self, tx_id: bytes32) -> Optional[TransactionRecord]:
        return await self.tx_store.get_transaction_record(tx_id)

    async def get_coin_record_by_wallet_record(self, wr: WalletCoinRecord) -> CoinRecord:
        timestamp: uint64 = await self.wallet_node.get_timestamp_for_height(wr.confirmed_block_height)
        return wr.to_coin_record(timestamp)

    async def get_coin_records_by_coin_ids(self, **kwargs: Any) -> List[CoinRecord]:
        result = await self.coin_store.get_coin_records(**kwargs)
        return [await self.get_coin_record_by_wallet_record(record) for record in result.records]

    async def get_wallet_for_coin(self, coin_id: bytes32) -> Optional[WalletProtocol[Any]]:
        coin_record = await self.coin_store.get_coin_record(coin_id)
        if coin_record is None:
            return None
        wallet_id = uint32(coin_record.wallet_id)
        wallet = self.wallets[wallet_id]
        return wallet

    async def reorg_rollback(self, height: int) -> List[uint32]:
        """
        Rolls back and updates the coin_store and transaction store. It's possible this height
        is the tip, or even beyond the tip.
        """
        await self.retry_store.rollback_to_block(height)
        await self.nft_store.rollback_to_block(height)
        await self.coin_store.rollback_to_block(height)
        await self.interested_store.rollback_to_block(height)
        reorged: List[TransactionRecord] = await self.tx_store.get_transaction_above(height)
        await self.tx_store.rollback_to_block(height)
        for record in reorged:
            if TransactionType(record.type) in [
                TransactionType.OUTGOING_TX,
                TransactionType.OUTGOING_TRADE,
                TransactionType.INCOMING_TRADE,
                TransactionType.OUTGOING_CLAWBACK,
                TransactionType.INCOMING_CLAWBACK_SEND,
                TransactionType.INCOMING_CLAWBACK_RECEIVE,
            ]:
                await self.tx_store.tx_reorged(record)

        # Removes wallets that were created from a blockchain transaction which got reorged.
        remove_ids: List[uint32] = []
        for wallet_id, wallet in self.wallets.items():
            if wallet.type() == WalletType.POOLING_WALLET.value:
                assert isinstance(wallet, PoolWallet)
                remove: bool = await wallet.rewind(height)
                if remove:
                    remove_ids.append(wallet_id)
        for wallet_id in remove_ids:
            await self.user_store.delete_wallet(wallet_id)
            self.state_changed("wallet_removed", wallet_id)

        return remove_ids

    async def _await_closed(self) -> None:
        await self.db_wrapper.close()

    def unlink_db(self) -> None:
        Path(self.db_path).unlink()

    async def get_all_wallet_info_entries(self, wallet_type: Optional[WalletType] = None) -> List[WalletInfo]:
        return await self.user_store.get_all_wallet_info_entries(wallet_type)

    async def get_wallet_for_asset_id(self, asset_id: str) -> Optional[WalletProtocol[Any]]:
        for wallet_id, wallet in self.wallets.items():
            if wallet.type() in (WalletType.CAT, WalletType.CRCAT):
                assert isinstance(wallet, CATWallet)
                if wallet.get_asset_id() == asset_id:
                    return wallet
            elif wallet.type() == WalletType.DATA_LAYER:
                assert isinstance(wallet, DataLayerWallet)
                if await wallet.get_latest_singleton(bytes32.from_hexstr(asset_id)) is not None:
                    return wallet
            elif wallet.type() == WalletType.NFT:
                assert isinstance(wallet, NFTWallet)
                nft_coin = await self.nft_store.get_nft_by_id(bytes32.from_hexstr(asset_id), wallet_id)
                if nft_coin:
                    return wallet
        return None

    async def get_wallet_for_puzzle_info(self, puzzle_driver: PuzzleInfo) -> Optional[WalletProtocol[Any]]:
        for wallet in self.wallets.values():
            match_function = getattr(wallet, "match_puzzle_info", None)
            if match_function is not None and callable(match_function):
                if await match_function(puzzle_driver):
                    return wallet
        return None

    async def create_wallet_for_puzzle_info(self, puzzle_driver: PuzzleInfo, name: Optional[str] = None) -> None:
        if AssetType(puzzle_driver.type()) in self.asset_to_wallet_map:
            await self.asset_to_wallet_map[AssetType(puzzle_driver.type())].create_from_puzzle_info(
                self,
                self.main_wallet,
                puzzle_driver,
                name,
                potential_subclasses={
                    AssetType.CR: CRCATWallet,
                },
            )

    async def add_new_wallet(self, wallet: WalletProtocol[Any]) -> None:
        self.wallets[wallet.id()] = wallet
        await self.create_more_puzzle_hashes()
        self.state_changed("wallet_created")

    async def get_spendable_coins_for_wallet(
        self, wallet_id: int, records: Optional[Set[WalletCoinRecord]] = None
    ) -> Set[WalletCoinRecord]:
        wallet_type = self.wallets[uint32(wallet_id)].type()
        if records is None:
            if wallet_type == WalletType.CRCAT:
                records = await self.coin_store.get_unspent_coins_for_wallet(wallet_id, CoinType.CRCAT)
            else:
                records = await self.coin_store.get_unspent_coins_for_wallet(wallet_id)

        # Coins that are currently part of a transaction
        unconfirmed_tx: List[TransactionRecord] = await self.tx_store.get_unconfirmed_for_wallet(wallet_id)
        removal_dict: Dict[bytes32, Coin] = {}
        for tx in unconfirmed_tx:
            for coin in tx.removals:
                # TODO, "if" might not be necessary once unconfirmed tx doesn't contain coins for other wallets
                if await self.does_coin_belong_to_wallet(coin, wallet_id, tx.hint_dict()):
                    removal_dict[coin.name()] = coin

        # Coins that are part of the trade
        offer_locked_coins: Dict[bytes32, WalletCoinRecord] = await self.trade_manager.get_locked_coins()

        filtered = set()
        for record in records:
            if record.coin.name() in offer_locked_coins:
                continue
            if record.coin.name() in removal_dict:
                continue
            filtered.add(record)

        return filtered

    async def new_peak(self, height: uint32) -> None:
        for wallet_id, wallet in self.wallets.items():
            if wallet.type() == WalletType.POOLING_WALLET:
                assert isinstance(wallet, PoolWallet)
                await wallet.new_peak(height)
        current_time = int(time.time())

        if self.wallet_node.last_wallet_tx_resend_time < current_time - self.wallet_node.wallet_tx_resend_timeout_secs:
            self.tx_pending_changed()

    async def add_interested_puzzle_hashes(self, puzzle_hashes: List[bytes32], wallet_ids: List[int]) -> None:
        # TODO: It's unclear if the intended use for this is that each puzzle hash should store all
        # the elements of wallet_ids. It only stores one wallet_id per puzzle hash in the interested_store
        # but the coin_cache keeps all wallet_ids for each puzzle hash
        for puzzle_hash in puzzle_hashes:
            if puzzle_hash in self.interested_coin_cache:
                wallet_ids_to_add = list({w for w in wallet_ids if w not in self.interested_coin_cache[puzzle_hash]})
                self.interested_coin_cache[puzzle_hash].extend(wallet_ids_to_add)
            else:
                self.interested_coin_cache[puzzle_hash] = list(set(wallet_ids))
        for puzzle_hash, wallet_id in zip(puzzle_hashes, wallet_ids):
            await self.interested_store.add_interested_puzzle_hash(puzzle_hash, wallet_id)
        if len(puzzle_hashes) > 0:
            await self.wallet_node.new_peak_queue.subscribe_to_puzzle_hashes(puzzle_hashes)

    async def add_interested_coin_ids(self, coin_ids: List[bytes32], wallet_ids: List[int] = []) -> None:
        # TODO: FIX: wallet_ids is sometimes populated unexpectedly when called from add_pending_transaction
        for coin_id in coin_ids:
            if coin_id in self.interested_coin_cache:
                # prevent repeated wallet_ids from appearing in the coin cache
                wallet_ids_to_add = list({w for w in wallet_ids if w not in self.interested_coin_cache[coin_id]})
                self.interested_coin_cache[coin_id].extend(wallet_ids_to_add)
            else:
                self.interested_coin_cache[coin_id] = list(set(wallet_ids))
        for coin_id in coin_ids:
            await self.interested_store.add_interested_coin_id(coin_id)
        if len(coin_ids) > 0:
            await self.wallet_node.new_peak_queue.subscribe_to_coin_ids(coin_ids)

    async def delete_trade_transactions(self, trade_id: bytes32) -> None:
        txs: List[TransactionRecord] = await self.tx_store.get_transactions_by_trade_id(trade_id)
        for tx in txs:
            await self.tx_store.delete_transaction_record(tx.name)

    async def convert_puzzle_hash(self, wallet_id: uint32, puzzle_hash: bytes32) -> bytes32:
        wallet = self.wallets[wallet_id]
        # This should be general to wallets but for right now this is just for CATs so we'll add this if
        if wallet.type() in (WalletType.CAT.value, WalletType.CRCAT.value):
            assert isinstance(wallet, CATWallet)
            return await wallet.convert_puzzle_hash(puzzle_hash)

        return puzzle_hash

    def get_dl_wallet(self) -> DataLayerWallet:
        for wallet in self.wallets.values():
            if wallet.type() == WalletType.DATA_LAYER.value:
                assert isinstance(
                    wallet, DataLayerWallet
                ), f"WalletType.DATA_LAYER should be a DataLayerWallet instance got: {type(wallet).__name__}"
                return wallet
        raise ValueError("DataLayerWallet not available")

    async def get_or_create_vc_wallet(self) -> VCWallet:
        for _, wallet in self.wallets.items():
            if WalletType(wallet.type()) == WalletType.VC:
                assert isinstance(wallet, VCWallet)
                vc_wallet: VCWallet = wallet
                break
        else:
            # Create a new VC wallet
            vc_wallet = await VCWallet.create_new_vc_wallet(self, self.main_wallet)

        return vc_wallet

    async def sign_transaction(self, coin_spends: List[CoinSpend]) -> SpendBundle:
        return await sign_coin_spends(
            coin_spends,
            self.get_private_key_for_pubkey,
            self.get_synthetic_private_key_for_puzzle_hash,
            self.constants.AGG_SIG_ME_ADDITIONAL_DATA,
            self.constants.MAX_BLOCK_COST_CLVM,
            [puzzle_hash_for_synthetic_public_key],
        )
