from __future__ import annotations

import dataclasses
import logging
import time
import traceback
from typing import TYPE_CHECKING, Any, ClassVar, Dict, List, Optional, Set, Tuple, cast

from chia_rs import AugSchemeMPL, G1Element, G2Element
from typing_extensions import Unpack

from hddcoin.consensus.default_constants import DEFAULT_CONSTANTS
from hddcoin.server.ws_connection import WSHDDcoinConnection
from hddcoin.types.announcement import Announcement
from hddcoin.types.blockchain_format.coin import Coin
from hddcoin.types.blockchain_format.program import Program
from hddcoin.types.blockchain_format.sized_bytes import bytes32
from hddcoin.types.coin_spend import compute_additions_with_cost
from hddcoin.types.condition_opcodes import ConditionOpcode
from hddcoin.types.spend_bundle import SpendBundle
from hddcoin.util.byte_types import hexstr_to_bytes
from hddcoin.util.condition_tools import conditions_dict_for_solution, pkm_pairs_for_conditions_dict
from hddcoin.util.errors import Err, ValidationError
from hddcoin.util.hash import std_hash
from hddcoin.util.ints import uint32, uint64, uint128
from hddcoin.wallet.cat_wallet.cat_constants import DEFAULT_CATS
from hddcoin.wallet.cat_wallet.cat_info import CATCoinData, CATInfo, LegacyCATInfo
from hddcoin.wallet.cat_wallet.cat_utils import (
    CAT_MOD,
    SpendableCAT,
    construct_cat_puzzle,
    match_cat_puzzle,
    unsigned_spend_bundle_for_spendable_cats,
)
from hddcoin.wallet.cat_wallet.lineage_store import CATLineageStore
from hddcoin.wallet.coin_selection import select_coins
from hddcoin.wallet.conditions import Condition, ConditionValidTimes, UnknownCondition, parse_timelock_info
from hddcoin.wallet.derivation_record import DerivationRecord
from hddcoin.wallet.lineage_proof import LineageProof
from hddcoin.wallet.outer_puzzles import AssetType
from hddcoin.wallet.payment import Payment
from hddcoin.wallet.puzzle_drivers import PuzzleInfo
from hddcoin.wallet.puzzles.p2_delegated_puzzle_or_hidden_puzzle import (
    DEFAULT_HIDDEN_PUZZLE_HASH,
    calculate_synthetic_secret_key,
)
from hddcoin.wallet.puzzles.tails import ALL_LIMITATIONS_PROGRAMS
from hddcoin.wallet.transaction_record import TransactionRecord
from hddcoin.wallet.uncurried_puzzle import uncurry_puzzle
from hddcoin.wallet.util.compute_memos import compute_memos
from hddcoin.wallet.util.curry_and_treehash import calculate_hash_of_quoted_mod_hash, curry_and_treehash
from hddcoin.wallet.util.transaction_type import TransactionType
from hddcoin.wallet.util.tx_config import CoinSelectionConfig, TXConfig
from hddcoin.wallet.util.wallet_sync_utils import fetch_coin_spend_for_coin_state
from hddcoin.wallet.util.wallet_types import WalletType
from hddcoin.wallet.wallet import Wallet
from hddcoin.wallet.wallet_coin_record import WalletCoinRecord
from hddcoin.wallet.wallet_info import WalletInfo
from hddcoin.wallet.wallet_protocol import GSTOptionalArgs, WalletProtocol

if TYPE_CHECKING:
    from hddcoin.wallet.wallet_state_manager import WalletStateManager

# This should probably not live in this file but it's for experimental right now

CAT_MOD_HASH = CAT_MOD.get_tree_hash()
CAT_MOD_HASH_HASH = Program.to(CAT_MOD_HASH).get_tree_hash()
QUOTED_MOD_HASH = calculate_hash_of_quoted_mod_hash(CAT_MOD_HASH)


def not_ephemeral_additions(sp: SpendBundle) -> List[Coin]:
    removals: Set[Coin] = set()
    for cs in sp.coin_spends:
        removals.add(cs.coin)

    additions: List[Coin] = []
    max_cost = DEFAULT_CONSTANTS.MAX_BLOCK_COST_CLVM
    for cs in sp.coin_spends:
        coins, cost = compute_additions_with_cost(cs, max_cost=max_cost)
        max_cost -= cost
        if max_cost < 0:
            raise ValidationError(Err.BLOCK_COST_EXCEEDS_MAX, "non_ephemeral_additions() for SpendBundle")
        for c in coins:
            if c not in removals:
                additions.append(c)
    return additions


class CATWallet:
    if TYPE_CHECKING:
        _protocol_check: ClassVar[WalletProtocol[CATCoinData]] = cast("CATWallet", None)

    wallet_state_manager: WalletStateManager
    log: logging.Logger
    wallet_info: WalletInfo
    cat_info: CATInfo
    standard_wallet: Wallet
    lineage_store: CATLineageStore

    @staticmethod
    def default_wallet_name_for_unknown_cat(limitations_program_hash_hex: str) -> str:
        return f"CAT {limitations_program_hash_hex[:16]}..."

    @staticmethod
    async def create_new_cat_wallet(
        wallet_state_manager: WalletStateManager,
        wallet: Wallet,
        cat_tail_info: Dict[str, Any],
        amount: uint64,
        tx_config: TXConfig,
        fee: uint64 = uint64(0),
        name: Optional[str] = None,
    ) -> CATWallet:
        self = CATWallet()
        self.standard_wallet = wallet
        self.log = logging.getLogger(__name__)
        std_wallet_id = self.standard_wallet.wallet_id
        bal = await wallet_state_manager.get_confirmed_balance_for_wallet(std_wallet_id)
        if amount > bal:
            raise ValueError("Not enough balance")
        self.wallet_state_manager = wallet_state_manager

        # We use 00 bytes because it's not optional. We must check this is overridden during issuance.
        empty_bytes = bytes32(32 * b"\0")
        self.cat_info = CATInfo(empty_bytes, None)
        info_as_string = bytes(self.cat_info).hex()
        # If the name is not provided, it will be autogenerated based on the resulting tail hash.
        # For now, give the wallet a temporary name "CAT WALLET" until we get the tail hash
        original_name = name
        if name is None:
            name = "CAT WALLET"

        self.wallet_info = await wallet_state_manager.user_store.create_wallet(name, WalletType.CAT, info_as_string)

        try:
            hddcoin_tx, spend_bundle = await ALL_LIMITATIONS_PROGRAMS[
                cat_tail_info["identifier"]
            ].generate_issuance_bundle(
                self,
                cat_tail_info,
                amount,
                tx_config,
                fee,
            )
            assert self.cat_info.limitations_program_hash != empty_bytes
        except Exception:
            await wallet_state_manager.user_store.delete_wallet(self.id())
            raise
        if spend_bundle is None:
            await wallet_state_manager.user_store.delete_wallet(self.id())
            raise ValueError("Failed to create spend.")

        await self.wallet_state_manager.add_new_wallet(self)

        # If the new CAT name wasn't originally provided, we used a temporary name before issuance
        # since we didn't yet know the TAIL. Now we know the TAIL, we can update the name
        # according to the template name for unknown/new CATs.
        if original_name is None:
            name = self.default_wallet_name_for_unknown_cat(self.cat_info.limitations_program_hash.hex())
            await self.set_name(name)

        # Change and actual CAT coin
        non_ephemeral_coins: List[Coin] = not_ephemeral_additions(spend_bundle)
        cat_coin = None
        puzzle_store = self.wallet_state_manager.puzzle_store
        for c in non_ephemeral_coins:
            wallet_identifier = await puzzle_store.get_wallet_identifier_for_puzzle_hash(c.puzzle_hash)
            if wallet_identifier is None:
                raise ValueError("Internal Error")
            if wallet_identifier.id == self.id():
                cat_coin = c

        if cat_coin is None:
            raise ValueError("Internal Error, unable to generate new CAT coin")
        cat_pid: bytes32 = cat_coin.parent_coin_info

        cat_record = TransactionRecord(
            confirmed_at_height=uint32(0),
            created_at_time=uint64(int(time.time())),
            to_puzzle_hash=(await self.convert_puzzle_hash(cat_coin.puzzle_hash)),
            amount=uint64(cat_coin.amount),
            fee_amount=fee,
            confirmed=False,
            sent=uint32(10),
            spend_bundle=None,
            additions=[cat_coin],
            removals=list(filter(lambda rem: rem.name() == cat_pid, spend_bundle.removals())),
            wallet_id=self.id(),
            sent_to=[],
            trade_id=None,
            type=uint32(TransactionType.INCOMING_TX.value),
            name=bytes32.secret(),
            memos=[],
            valid_times=ConditionValidTimes(),
        )
        hddcoin_tx = dataclasses.replace(hddcoin_tx, spend_bundle=spend_bundle, name=spend_bundle.name())
        await self.standard_wallet.push_transaction(hddcoin_tx)
        await self.standard_wallet.push_transaction(cat_record)
        return self

    @staticmethod
    async def get_or_create_wallet_for_cat(
        wallet_state_manager: WalletStateManager,
        wallet: Wallet,
        limitations_program_hash_hex: str,
        name: Optional[str] = None,
    ) -> CATWallet:
        self = CATWallet()
        self.standard_wallet = wallet
        self.log = logging.getLogger(__name__)

        limitations_program_hash_hex = bytes32.from_hexstr(limitations_program_hash_hex).hex()  # Normalize the format

        for id, w in wallet_state_manager.wallets.items():
            if w.type() == CATWallet.type():
                assert isinstance(w, CATWallet)
                if w.get_asset_id() == limitations_program_hash_hex:
                    self.log.warning("Not creating wallet for already existing CAT wallet")
                    return w

        self.wallet_state_manager = wallet_state_manager
        if limitations_program_hash_hex in DEFAULT_CATS:
            cat_info = DEFAULT_CATS[limitations_program_hash_hex]
            name = cat_info["name"]
        elif name is None:
            name = self.default_wallet_name_for_unknown_cat(limitations_program_hash_hex)

        limitations_program_hash = bytes32(hexstr_to_bytes(limitations_program_hash_hex))
        self.cat_info = CATInfo(limitations_program_hash, None)
        info_as_string = bytes(self.cat_info).hex()
        self.wallet_info = await wallet_state_manager.user_store.create_wallet(name, WalletType.CAT, info_as_string)

        self.lineage_store = await CATLineageStore.create(self.wallet_state_manager.db_wrapper, self.get_asset_id())
        await self.wallet_state_manager.add_new_wallet(self)

        delete: bool = False
        for state in await self.wallet_state_manager.interested_store.get_unacknowledged_states_for_asset_id(
            limitations_program_hash
        ):
            new_peer = self.wallet_state_manager.wallet_node.get_full_node_peer()
            if new_peer is not None:
                delete = True
                peer_id: bytes32 = new_peer.peer_node_id
                await self.wallet_state_manager.retry_store.add_state(state[0], peer_id, state[1])

        if delete:
            await self.wallet_state_manager.interested_store.delete_unacknowledged_states_for_asset_id(
                limitations_program_hash
            )

        return self

    @classmethod
    async def create_from_puzzle_info(
        cls,
        wallet_state_manager: WalletStateManager,
        wallet: Wallet,
        puzzle_driver: PuzzleInfo,
        name: Optional[str] = None,
        # We're hinting this as Any for mypy by should explore adding this to the wallet protocol and hinting properly
        potential_subclasses: Dict[AssetType, Any] = {},
    ) -> Any:
        next_layer: Optional[PuzzleInfo] = puzzle_driver.also()
        if next_layer is not None:
            if AssetType(next_layer.type()) in potential_subclasses:
                return await potential_subclasses[AssetType(next_layer.type())].create_from_puzzle_info(
                    wallet_state_manager,
                    wallet,
                    puzzle_driver,
                    name,
                    potential_subclasses,
                )
        return await cls.get_or_create_wallet_for_cat(
            wallet_state_manager,
            wallet,
            puzzle_driver["tail"].hex(),
            name,
        )

    @staticmethod
    async def create(
        wallet_state_manager: WalletStateManager,
        wallet: Wallet,
        wallet_info: WalletInfo,
    ) -> CATWallet:
        self = CATWallet()

        self.log = logging.getLogger(__name__)

        self.wallet_state_manager = wallet_state_manager
        self.wallet_info = wallet_info
        self.standard_wallet = wallet
        try:
            self.cat_info = CATInfo.from_bytes(hexstr_to_bytes(self.wallet_info.data))
            self.lineage_store = await CATLineageStore.create(self.wallet_state_manager.db_wrapper, self.get_asset_id())
        except AssertionError:
            # Do a migration of the lineage proofs
            cat_info = LegacyCATInfo.from_bytes(hexstr_to_bytes(self.wallet_info.data))
            self.cat_info = CATInfo(cat_info.limitations_program_hash, cat_info.my_tail)
            self.lineage_store = await CATLineageStore.create(self.wallet_state_manager.db_wrapper, self.get_asset_id())
            for coin_id, lineage in cat_info.lineage_proofs:
                await self.add_lineage(coin_id, lineage)
            await self.save_info(self.cat_info)

        return self

    @classmethod
    def type(cls) -> WalletType:
        return WalletType.CAT

    def id(self) -> uint32:
        return self.wallet_info.id

    async def get_confirmed_balance(self, record_list: Optional[Set[WalletCoinRecord]] = None) -> uint128:
        if record_list is None:
            record_list = await self.wallet_state_manager.coin_store.get_unspent_coins_for_wallet(self.id())

        amount: uint128 = uint128(0)
        for record in record_list:
            lineage = await self.get_lineage_proof_for_coin(record.coin)
            if lineage is not None:
                amount = uint128(amount + record.coin.amount)

        self.log.info(f"Confirmed balance for cat wallet {self.id()} is {amount}")
        return uint128(amount)

    async def get_unconfirmed_balance(self, unspent_records: Optional[Set[WalletCoinRecord]] = None) -> uint128:
        return await self.wallet_state_manager.get_unconfirmed_balance(self.id(), unspent_records)

    @property
    def cost_of_single_tx(self) -> int:
        return 30000000  # Estimate

    async def get_max_send_amount(self, records: Optional[Set[WalletCoinRecord]] = None) -> uint128:
        spendable: List[WalletCoinRecord] = list(await self.get_cat_spendable_coins())
        if len(spendable) == 0:
            return uint128(0)
        spendable.sort(reverse=True, key=lambda record: record.coin.amount)

        max_cost = self.wallet_state_manager.constants.MAX_BLOCK_COST_CLVM / 2  # avoid full block TXs
        current_cost = 0
        total_amount = 0
        total_coin_count = 0

        for record in spendable:
            current_cost += self.cost_of_single_tx
            total_amount += record.coin.amount
            total_coin_count += 1
            if current_cost + self.cost_of_single_tx > max_cost:
                break

        return uint128(total_amount)

    def get_name(self) -> str:
        return self.wallet_info.name

    async def set_name(self, new_name: str) -> None:
        new_info = dataclasses.replace(self.wallet_info, name=new_name)
        self.wallet_info = new_info
        await self.wallet_state_manager.user_store.update_wallet(self.wallet_info)

    def get_asset_id(self) -> str:
        return bytes(self.cat_info.limitations_program_hash).hex()

    async def set_tail_program(self, tail_program: str) -> None:
        assert Program.fromhex(tail_program).get_tree_hash() == self.cat_info.limitations_program_hash
        await self.save_info(
            CATInfo(
                self.cat_info.limitations_program_hash,
                Program.fromhex(tail_program),
            )
        )

    async def coin_added(
        self, coin: Coin, height: uint32, peer: WSHDDcoinConnection, parent_coin_data: Optional[CATCoinData]
    ) -> None:
        """Notification from wallet state manager that wallet has been received."""
        self.log.info(f"CAT wallet has been notified that {coin.name().hex()} was added")

        inner_puzzle = await self.inner_puzzle_for_cat_puzhash(coin.puzzle_hash)
        lineage_proof = LineageProof(coin.parent_coin_info, inner_puzzle.get_tree_hash(), uint64(coin.amount))
        await self.add_lineage(coin.name(), lineage_proof)

        lineage = await self.get_lineage_proof_for_coin(coin)

        if lineage is None:
            try:
                if parent_coin_data is None:
                    # The method is not triggered after the determine_coin_type, no pre-fetched data
                    coin_state = await self.wallet_state_manager.wallet_node.get_coin_state(
                        [coin.parent_coin_info], peer=peer
                    )
                    assert coin_state[0].coin.name() == coin.parent_coin_info
                    coin_spend = await fetch_coin_spend_for_coin_state(coin_state[0], peer)
                    cat_curried_args = match_cat_puzzle(uncurry_puzzle(coin_spend.puzzle_reveal.to_program()))
                    if cat_curried_args is not None:
                        cat_mod_hash, tail_program_hash, cat_inner_puzzle = cat_curried_args
                        parent_coin_data = CATCoinData(
                            cat_mod_hash.atom,
                            tail_program_hash.atom,
                            cat_inner_puzzle,
                            coin_state[0].coin.parent_coin_info,
                            uint64(coin_state[0].coin.amount),
                        )
                await self.puzzle_solution_received(coin, parent_coin_data)
            except Exception as e:
                self.log.debug(f"Exception: {e}, traceback: {traceback.format_exc()}")

    async def puzzle_solution_received(self, coin: Coin, parent_coin_data: Optional[CATCoinData]) -> None:
        coin_name = coin.parent_coin_info
        if parent_coin_data is not None:
            assert isinstance(parent_coin_data, CATCoinData)
            data: CATCoinData = parent_coin_data
            self.log.info(f"parent: {coin_name.hex()} inner_puzzle for parent is {data.inner_puzzle}")

            await self.add_lineage(
                coin_name,
                LineageProof(data.parent_coin_id, data.inner_puzzle.get_tree_hash(), data.amount),
            )
        else:
            # The parent is not a CAT which means we need to scrub all of its children from our DB
            child_coin_records = await self.wallet_state_manager.coin_store.get_coin_records_by_parent_id(coin_name)
            if len(child_coin_records) > 0:
                for record in child_coin_records:
                    if record.wallet_id == self.id():
                        await self.wallet_state_manager.coin_store.delete_coin_record(record.coin.name())
                        await self.remove_lineage(record.coin.name())
                        # We also need to make sure there's no record of the transaction
                        await self.wallet_state_manager.tx_store.delete_transaction_record(record.coin.name())

    async def get_new_inner_hash(self) -> bytes32:
        puzzle = await self.get_new_inner_puzzle()
        return puzzle.get_tree_hash()

    async def get_new_inner_puzzle(self) -> Program:
        return await self.standard_wallet.get_new_puzzle()

    async def get_new_puzzlehash(self) -> bytes32:
        return await self.standard_wallet.get_new_puzzlehash()

    async def get_puzzle_hash(self, new: bool) -> bytes32:
        if new:
            return await self.get_new_puzzlehash()
        else:
            record: Optional[
                DerivationRecord
            ] = await self.wallet_state_manager.get_current_derivation_record_for_wallet(self.standard_wallet.id())
            if record is None:
                return await self.get_new_puzzlehash()
            return record.puzzle_hash

    def require_derivation_paths(self) -> bool:
        return True

    def puzzle_for_pk(self, pubkey: G1Element) -> Program:
        inner_puzzle = self.standard_wallet.puzzle_for_pk(pubkey)
        cat_puzzle: Program = construct_cat_puzzle(CAT_MOD, self.cat_info.limitations_program_hash, inner_puzzle)
        return cat_puzzle

    def puzzle_hash_for_pk(self, pubkey: G1Element) -> bytes32:
        inner_puzzle_hash = self.standard_wallet.puzzle_hash_for_pk(pubkey)
        limitations_program_hash_hash = Program.to(self.cat_info.limitations_program_hash).get_tree_hash()
        return curry_and_treehash(QUOTED_MOD_HASH, CAT_MOD_HASH_HASH, limitations_program_hash_hash, inner_puzzle_hash)

    async def get_new_cat_puzzle_hash(self) -> bytes32:
        return (await self.wallet_state_manager.get_unused_derivation_record(self.id())).puzzle_hash

    async def get_spendable_balance(self, records: Optional[Set[WalletCoinRecord]] = None) -> uint128:
        coins = await self.get_cat_spendable_coins(records)
        amount = 0
        for record in coins:
            amount += record.coin.amount

        return uint128(amount)

    async def get_pending_change_balance(self) -> uint64:
        unconfirmed_tx = await self.wallet_state_manager.tx_store.get_unconfirmed_for_wallet(self.id())
        addition_amount = 0
        for record in unconfirmed_tx:
            if not record.is_in_mempool():
                continue
            our_spend = False
            for coin in record.removals:
                if await self.wallet_state_manager.does_coin_belong_to_wallet(coin, self.id()):
                    our_spend = True
                    break

            if our_spend is not True:
                continue

            for coin in record.additions:
                if await self.wallet_state_manager.does_coin_belong_to_wallet(coin, self.id()):
                    addition_amount += coin.amount

        return uint64(addition_amount)

    async def get_cat_spendable_coins(self, records: Optional[Set[WalletCoinRecord]] = None) -> List[WalletCoinRecord]:
        result: List[WalletCoinRecord] = []

        record_list: Set[WalletCoinRecord] = await self.wallet_state_manager.get_spendable_coins_for_wallet(
            self.id(), records
        )

        for record in record_list:
            lineage = await self.get_lineage_proof_for_coin(record.coin)
            if lineage is not None and not lineage.is_none():
                result.append(record)

        return result

    async def select_coins(
        self,
        amount: uint64,
        coin_selection_config: CoinSelectionConfig,
    ) -> Set[Coin]:
        """
        Returns a set of coins that can be used for generating a new transaction.
        Note: Must be called under wallet state manager lock
        """
        spendable_amount: uint128 = await self.get_spendable_balance()
        spendable_coins: List[WalletCoinRecord] = await self.get_cat_spendable_coins()

        # Try to use coins from the store, if there isn't enough of "unused"
        # coins use change coins that are not confirmed yet
        unconfirmed_removals: Dict[bytes32, Coin] = await self.wallet_state_manager.unconfirmed_removals_for_wallet(
            self.id()
        )
        coins = await select_coins(
            spendable_amount,
            coin_selection_config,
            spendable_coins,
            unconfirmed_removals,
            self.log,
            uint128(amount),
        )
        assert sum(c.amount for c in coins) >= amount
        return coins

    async def sign(self, spend_bundle: SpendBundle) -> SpendBundle:
        sigs: List[G2Element] = []
        for spend in spend_bundle.coin_spends:
            args = match_cat_puzzle(uncurry_puzzle(spend.puzzle_reveal.to_program()))
            if args is not None:
                _, _, inner_puzzle = args
                puzzle_hash = inner_puzzle.get_tree_hash()
                private = await self.wallet_state_manager.get_private_key(puzzle_hash)
                synthetic_secret_key = calculate_synthetic_secret_key(private, DEFAULT_HIDDEN_PUZZLE_HASH)
                conditions = conditions_dict_for_solution(
                    spend.puzzle_reveal.to_program(),
                    spend.solution.to_program(),
                    self.wallet_state_manager.constants.MAX_BLOCK_COST_CLVM,
                )
                synthetic_pk = synthetic_secret_key.get_g1()
                for pk, msg in pkm_pairs_for_conditions_dict(
                    conditions, spend.coin, self.wallet_state_manager.constants.AGG_SIG_ME_ADDITIONAL_DATA
                ):
                    try:
                        assert bytes(synthetic_pk) == pk
                        sigs.append(AugSchemeMPL.sign(synthetic_secret_key, msg))
                    except AssertionError:
                        raise ValueError("This spend bundle cannot be signed by the CAT wallet")

        agg_sig = AugSchemeMPL.aggregate(sigs)
        return SpendBundle.aggregate([spend_bundle, SpendBundle([], agg_sig)])

    async def inner_puzzle_for_cat_puzhash(self, cat_hash: bytes32) -> Program:
        record: Optional[
            DerivationRecord
        ] = await self.wallet_state_manager.puzzle_store.get_derivation_record_for_puzzle_hash(cat_hash)
        if record is None:
            raise RuntimeError(f"Missing Derivation Record for CAT puzzle_hash {cat_hash}")
        inner_puzzle: Program = self.standard_wallet.puzzle_for_pk(record.pubkey)
        return inner_puzzle

    async def convert_puzzle_hash(self, puzzle_hash: bytes32) -> bytes32:
        record: Optional[
            DerivationRecord
        ] = await self.wallet_state_manager.puzzle_store.get_derivation_record_for_puzzle_hash(puzzle_hash)
        if record is None:
            return puzzle_hash  # TODO: check if we have a test for this case!
        else:
            return (await self.inner_puzzle_for_cat_puzhash(puzzle_hash)).get_tree_hash()

    async def get_lineage_proof_for_coin(self, coin: Coin) -> Optional[LineageProof]:
        return await self.lineage_store.get_lineage_proof(coin.parent_coin_info)

    async def create_tandem_hdd_tx(
        self,
        fee: uint64,
        amount_to_claim: uint64,
        tx_config: TXConfig,
        announcements_to_assert: Optional[Set[Announcement]] = None,
    ) -> Tuple[TransactionRecord, Optional[Announcement]]:
        """
        This function creates a non-CAT transaction to pay fees, contribute funds for issuance, and absorb melt value.
        It is meant to be called in `generate_unsigned_spendbundle` and as such should be called under the
        wallet_state_manager lock
        """
        announcement = None
        if fee > amount_to_claim:
            hddcoin_coins = await self.standard_wallet.select_coins(
                fee,
                tx_config.coin_selection_config,
            )
            origin_id = list(hddcoin_coins)[0].name()
            [hddcoin_tx] = await self.standard_wallet.generate_signed_transaction(
                uint64(0),
                (await self.standard_wallet.get_puzzle_hash(not tx_config.reuse_puzhash)),
                tx_config,
                fee=uint64(fee - amount_to_claim),
                coins=hddcoin_coins,
                origin_id=origin_id,  # We specify this so that we know the coin that is making the announcement
                negative_change_allowed=False,
                coin_announcements_to_consume=announcements_to_assert if announcements_to_assert is not None else None,
            )
            assert hddcoin_tx.spend_bundle is not None
        else:
            hddcoin_coins = await self.standard_wallet.select_coins(
                fee,
                tx_config.coin_selection_config,
            )
            origin_id = list(hddcoin_coins)[0].name()
            selected_amount = sum([c.amount for c in hddcoin_coins])
            [hddcoin_tx] = await self.standard_wallet.generate_signed_transaction(
                uint64(selected_amount + amount_to_claim - fee),
                (await self.standard_wallet.get_puzzle_hash(not tx_config.reuse_puzhash)),
                tx_config,
                coins=hddcoin_coins,
                negative_change_allowed=True,
                coin_announcements_to_consume=announcements_to_assert if announcements_to_assert is not None else None,
            )
            assert hddcoin_tx.spend_bundle is not None

            message = None
            for spend in hddcoin_tx.spend_bundle.coin_spends:
                if spend.coin.name() == origin_id:
                    conditions = spend.puzzle_reveal.to_program().run(spend.solution.to_program()).as_python()
                    for condition in conditions:
                        if condition[0] == ConditionOpcode.CREATE_COIN_ANNOUNCEMENT:
                            message = condition[1]

            assert message is not None
            announcement = Announcement(origin_id, message)

        return hddcoin_tx, announcement

    async def generate_unsigned_spendbundle(
        self,
        payments: List[Payment],
        tx_config: TXConfig,
        fee: uint64 = uint64(0),
        cat_discrepancy: Optional[Tuple[int, Program, Program]] = None,  # (extra_delta, tail_reveal, tail_solution)
        coins: Optional[Set[Coin]] = None,
        coin_announcements_to_consume: Optional[Set[Announcement]] = None,
        puzzle_announcements_to_consume: Optional[Set[Announcement]] = None,
        extra_conditions: Tuple[Condition, ...] = tuple(),
    ) -> Tuple[SpendBundle, Optional[TransactionRecord]]:
        if coin_announcements_to_consume is not None:
            coin_announcements_bytes: Optional[Set[bytes32]] = {a.name() for a in coin_announcements_to_consume}
        else:
            coin_announcements_bytes = None

        if puzzle_announcements_to_consume is not None:
            puzzle_announcements_bytes: Optional[Set[bytes32]] = {a.name() for a in puzzle_announcements_to_consume}
        else:
            puzzle_announcements_bytes = None

        if cat_discrepancy is not None:
            extra_delta, tail_reveal, tail_solution = cat_discrepancy
        else:
            extra_delta, tail_reveal, tail_solution = 0, Program.to([]), Program.to([])
        payment_amount: int = sum([p.amount for p in payments])
        starting_amount: int = payment_amount - extra_delta
        if coins is None:
            cat_coins = await self.select_coins(
                uint64(starting_amount),
                tx_config.coin_selection_config,
            )
        else:
            cat_coins = coins

        selected_cat_amount = sum([c.amount for c in cat_coins])
        assert selected_cat_amount >= starting_amount

        # Figure out if we need to absorb/melt some HDD as part of this
        regular_hddcoin_to_claim: int = 0
        if payment_amount > starting_amount:
            fee = uint64(fee + payment_amount - starting_amount)
        elif payment_amount < starting_amount:
            regular_hddcoin_to_claim = payment_amount

        need_hddcoin_transaction = (fee > 0 or regular_hddcoin_to_claim > 0) and (fee - regular_hddcoin_to_claim != 0)

        # Calculate standard puzzle solutions
        change = selected_cat_amount - starting_amount
        primaries = payments.copy()

        if change > 0:
            derivation_record = await self.wallet_state_manager.puzzle_store.get_derivation_record_for_puzzle_hash(
                list(cat_coins)[0].puzzle_hash
            )
            if derivation_record is not None and tx_config.reuse_puzhash:
                change_puzhash = self.standard_wallet.puzzle_hash_for_pk(derivation_record.pubkey)
                for payment in payments:
                    if change_puzhash == payment.puzzle_hash and change == payment.amount:
                        # We cannot create two coins has same id, create a new puzhash for the change
                        change_puzhash = await self.get_new_inner_hash()
                        break
            else:
                change_puzhash = await self.get_new_inner_hash()
            primaries.append(Payment(change_puzhash, uint64(change), [change_puzhash]))

        # Loop through the coins we've selected and gather the information we need to spend them
        spendable_cat_list = []
        hddcoin_tx = None
        first = True
        announcement: Announcement

        for coin in cat_coins:
            if cat_discrepancy is not None:
                cat_condition = UnknownCondition(
                    opcode=Program.to(51),
                    args=[
                        Program.to(None),
                        Program.to(-113),
                        tail_reveal,
                        tail_solution,
                    ],
                )
                if first:
                    extra_conditions = (*extra_conditions, cat_condition)
            if first:
                first = False
                announcement = Announcement(coin.name(), std_hash(b"".join([c.name() for c in cat_coins])))
                if need_hddcoin_transaction:
                    if fee > regular_hddcoin_to_claim:
                        hddcoin_tx, _ = await self.create_tandem_hdd_tx(
                            fee,
                            uint64(regular_hddcoin_to_claim),
                            tx_config,
                            announcements_to_assert={announcement},
                        )
                        innersol = self.standard_wallet.make_solution(
                            primaries=primaries,
                            coin_announcements={announcement.message},
                            coin_announcements_to_assert=coin_announcements_bytes,
                            puzzle_announcements_to_assert=puzzle_announcements_bytes,
                            conditions=extra_conditions,
                        )
                    elif regular_hddcoin_to_claim > fee:
                        hddcoin_tx, _ = await self.create_tandem_hdd_tx(
                            fee,
                            uint64(regular_hddcoin_to_claim),
                            tx_config,
                        )
                        innersol = self.standard_wallet.make_solution(
                            primaries=primaries,
                            coin_announcements={announcement.message},
                            coin_announcements_to_assert={announcement.name()},
                            conditions=extra_conditions,
                        )
                else:
                    innersol = self.standard_wallet.make_solution(
                        primaries=primaries,
                        coin_announcements={announcement.message},
                        coin_announcements_to_assert=coin_announcements_bytes,
                        puzzle_announcements_to_assert=puzzle_announcements_bytes,
                        conditions=extra_conditions,
                    )
            else:
                innersol = self.standard_wallet.make_solution(
                    primaries=[],
                    coin_announcements_to_assert={announcement.name()},
                )
            inner_puzzle = await self.inner_puzzle_for_cat_puzhash(coin.puzzle_hash)
            lineage_proof = await self.get_lineage_proof_for_coin(coin)
            assert lineage_proof is not None
            new_spendable_cat = SpendableCAT(
                coin,
                self.cat_info.limitations_program_hash,
                inner_puzzle,
                innersol,
                limitations_solution=tail_solution,
                extra_delta=extra_delta,
                lineage_proof=lineage_proof,
                limitations_program_reveal=tail_reveal,
            )
            spendable_cat_list.append(new_spendable_cat)

        cat_spend_bundle = unsigned_spend_bundle_for_spendable_cats(CAT_MOD, spendable_cat_list)
        hddcoin_spend_bundle = SpendBundle([], G2Element())
        if hddcoin_tx is not None and hddcoin_tx.spend_bundle is not None:
            hddcoin_spend_bundle = hddcoin_tx.spend_bundle

        return (
            SpendBundle.aggregate(
                [
                    cat_spend_bundle,
                    hddcoin_spend_bundle,
                ]
            ),
            hddcoin_tx,
        )

    async def generate_signed_transaction(
        self,
        amounts: List[uint64],
        puzzle_hashes: List[bytes32],
        tx_config: TXConfig,
        fee: uint64 = uint64(0),
        coins: Optional[Set[Coin]] = None,
        ignore_max_send_amount: bool = False,
        memos: Optional[List[List[bytes]]] = None,
        coin_announcements_to_consume: Optional[Set[Announcement]] = None,
        puzzle_announcements_to_consume: Optional[Set[Announcement]] = None,
        extra_conditions: Tuple[Condition, ...] = tuple(),
        **kwargs: Unpack[GSTOptionalArgs],
    ) -> List[TransactionRecord]:
        # (extra_delta, tail_reveal, tail_solution)
        cat_discrepancy: Optional[Tuple[int, Program, Program]] = kwargs.get("cat_discrepancy", None)
        if memos is None:
            memos = [[] for _ in range(len(puzzle_hashes))]

        if not (len(memos) == len(puzzle_hashes) == len(amounts)):
            raise ValueError("Memos, puzzle_hashes, and amounts must have the same length")

        payments = []
        for amount, puzhash, memo_list in zip(amounts, puzzle_hashes, memos):
            memos_with_hint: List[bytes] = [puzhash]
            memos_with_hint.extend(memo_list)
            payments.append(Payment(puzhash, amount, memos_with_hint))

        payment_sum = sum([p.amount for p in payments])
        if not ignore_max_send_amount:
            max_send = await self.get_max_send_amount()
            if payment_sum > max_send:
                raise ValueError(f" Insufficient funds. Your max amount is {max_send} bytes in a single transaction.")
        unsigned_spend_bundle, hddcoin_tx = await self.generate_unsigned_spendbundle(
            payments,
            tx_config,
            fee,
            cat_discrepancy=cat_discrepancy,  # (extra_delta, tail_reveal, tail_solution)
            coins=coins,
            coin_announcements_to_consume=coin_announcements_to_consume,
            puzzle_announcements_to_consume=puzzle_announcements_to_consume,
            extra_conditions=extra_conditions,
        )
        spend_bundle = await self.sign(unsigned_spend_bundle)
        # TODO add support for array in stored records
        tx_list = [
            TransactionRecord(
                confirmed_at_height=uint32(0),
                created_at_time=uint64(int(time.time())),
                to_puzzle_hash=puzzle_hashes[0],
                amount=uint64(payment_sum),
                fee_amount=fee,
                confirmed=False,
                sent=uint32(0),
                spend_bundle=spend_bundle,
                additions=spend_bundle.additions(),
                removals=spend_bundle.removals(),
                wallet_id=self.id(),
                sent_to=[],
                trade_id=None,
                type=uint32(TransactionType.OUTGOING_TX.value),
                name=spend_bundle.name(),
                memos=list(compute_memos(spend_bundle).items()),
                valid_times=parse_timelock_info(extra_conditions),
            )
        ]

        if hddcoin_tx is not None:
            tx_list.append(
                TransactionRecord(
                    confirmed_at_height=hddcoin_tx.confirmed_at_height,
                    created_at_time=hddcoin_tx.created_at_time,
                    to_puzzle_hash=hddcoin_tx.to_puzzle_hash,
                    amount=hddcoin_tx.amount,
                    fee_amount=hddcoin_tx.fee_amount,
                    confirmed=hddcoin_tx.confirmed,
                    sent=hddcoin_tx.sent,
                    spend_bundle=None,
                    additions=hddcoin_tx.additions,
                    removals=hddcoin_tx.removals,
                    wallet_id=hddcoin_tx.wallet_id,
                    sent_to=hddcoin_tx.sent_to,
                    trade_id=hddcoin_tx.trade_id,
                    type=hddcoin_tx.type,
                    name=hddcoin_tx.name,
                    memos=[],
                    valid_times=parse_timelock_info(extra_conditions),
                )
            )
        return tx_list

    async def add_lineage(self, name: bytes32, lineage: Optional[LineageProof]) -> None:
        """
        Lineage proofs are stored as a list of parent coins and the lineage proof you will need if they are the
        parent of the coin you are trying to spend. 'If I'm your parent, here's the info you need to spend yourself'
        """
        self.log.info(f"Adding parent {name.hex()}: {lineage}")
        if lineage is not None:
            await self.lineage_store.add_lineage_proof(name, lineage)

    async def remove_lineage(self, name: bytes32) -> None:
        self.log.info(f"Removing parent {name} (probably had a non-CAT parent)")
        await self.lineage_store.remove_lineage_proof(name)

    async def save_info(self, cat_info: CATInfo) -> None:
        self.cat_info = cat_info
        current_info = self.wallet_info
        data_str = bytes(cat_info).hex()
        wallet_info = WalletInfo(current_info.id, current_info.name, current_info.type, data_str)
        self.wallet_info = wallet_info
        await self.wallet_state_manager.user_store.update_wallet(wallet_info)

    async def match_puzzle_info(self, puzzle_driver: PuzzleInfo) -> bool:
        return (
            AssetType(puzzle_driver.type()) == AssetType.CAT
            and puzzle_driver["tail"] == bytes.fromhex(self.get_asset_id())
            and puzzle_driver.also() is None
        )

    async def get_puzzle_info(self, asset_id: bytes32) -> PuzzleInfo:
        return PuzzleInfo({"type": AssetType.CAT.value, "tail": "0x" + self.get_asset_id()})

    async def get_coins_to_offer(
        self,
        asset_id: Optional[bytes32],
        amount: uint64,
        coin_selection_config: CoinSelectionConfig,
    ) -> Set[Coin]:
        balance = await self.get_confirmed_balance()
        if balance < amount:
            raise Exception(f"insufficient funds in wallet {self.id()}")
        return await self.select_coins(amount, coin_selection_config)

    async def match_hinted_coin(self, coin: Coin, hint: bytes32) -> bool:
        return (
            construct_cat_puzzle(CAT_MOD, self.cat_info.limitations_program_hash, hint).get_tree_hash_precalc(hint)
            == coin.puzzle_hash
        )
