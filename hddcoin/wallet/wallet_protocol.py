from __future__ import annotations

from typing import TYPE_CHECKING, List, Optional, Set, Tuple, TypeVar

from chia_rs import G1Element
from typing_extensions import NotRequired, Protocol, TypedDict

from hddcoin.server.ws_connection import WSHDDcoinConnection
from hddcoin.types.blockchain_format.coin import Coin
from hddcoin.types.blockchain_format.program import Program
from hddcoin.types.blockchain_format.sized_bytes import bytes32
from hddcoin.types.spend_bundle import SpendBundle
from hddcoin.util.ints import uint32, uint64, uint128
from hddcoin.wallet.nft_wallet.nft_info import NFTCoinInfo
from hddcoin.wallet.util.tx_config import CoinSelectionConfig
from hddcoin.wallet.util.wallet_types import WalletType
from hddcoin.wallet.wallet_coin_record import WalletCoinRecord
from hddcoin.wallet.wallet_info import WalletInfo

if TYPE_CHECKING:
    from hddcoin.wallet.wallet_state_manager import WalletStateManager

T = TypeVar("T", contravariant=True)


class WalletProtocol(Protocol[T]):
    @classmethod
    def type(cls) -> WalletType:
        ...

    def id(self) -> uint32:
        ...

    async def coin_added(self, coin: Coin, height: uint32, peer: WSHDDcoinConnection, coin_data: Optional[T]) -> None:
        ...

    async def select_coins(
        self,
        amount: uint64,
        coin_selection_config: CoinSelectionConfig,
    ) -> Set[Coin]:
        ...

    async def get_confirmed_balance(self, record_list: Optional[Set[WalletCoinRecord]] = None) -> uint128:
        ...

    async def get_unconfirmed_balance(self, unspent_records: Optional[Set[WalletCoinRecord]] = None) -> uint128:
        ...

    async def get_spendable_balance(self, unspent_records: Optional[Set[WalletCoinRecord]] = None) -> uint128:
        ...

    async def get_pending_change_balance(self) -> uint64:
        ...

    async def get_max_send_amount(self, records: Optional[Set[WalletCoinRecord]] = None) -> uint128:
        ...

    # not all wallet supports this. To signal support, make
    # require_derivation_paths() return true
    def puzzle_hash_for_pk(self, pubkey: G1Element) -> bytes32:
        ...

    def require_derivation_paths(self) -> bool:
        ...

    def get_name(self) -> str:
        ...

    async def match_hinted_coin(self, coin: Coin, hint: bytes32) -> bool:
        ...

    wallet_info: WalletInfo
    # WalletStateManager is only imported for type hinting thus leaving pylint
    # unable to process this
    wallet_state_manager: WalletStateManager  # pylint: disable=used-before-assignment


class GSTOptionalArgs(TypedDict):
    # DataLayerWallet
    launcher_id: NotRequired[Optional[bytes32]]
    new_root_hash: NotRequired[Optional[bytes32]]
    sign: NotRequired[bool]
    add_pending_singleton: NotRequired[bool]
    announce_new_state: NotRequired[bool]
    # CATWallet
    cat_discrepancy: NotRequired[Optional[Tuple[int, Program, Program]]]
    # NFTWallet
    nft_coin: NotRequired[Optional[NFTCoinInfo]]
    new_owner: NotRequired[Optional[bytes]]
    new_did_inner_hash: NotRequired[Optional[bytes]]
    trade_prices_list: NotRequired[Optional[Program]]
    additional_bundles: NotRequired[List[SpendBundle]]
    metadata_update: NotRequired[Optional[Tuple[str, str]]]
    # CR-CAT Wallet
    add_authorizations_to_cr_cats: NotRequired[bool]
    # VCWallet
    new_proof_hash: NotRequired[Optional[bytes32]]
    provider_inner_puzhash: NotRequired[Optional[bytes32]]
    self_revoke: NotRequired[bool]
    # Wallet
    origin_id: NotRequired[Optional[bytes32]]
    negative_change_allowed: NotRequired[bool]
