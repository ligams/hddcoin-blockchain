import { WalletType } from '@hddcoin-network/api';
import type { Wallet } from '@hddcoin-network/api';

export default function getWalletPrimaryTitle(wallet: Wallet): string {
  switch (wallet.type) {
    case WalletType.STANDARD_WALLET:
      return 'HDDcoin';
    default:
      return wallet.meta?.name ?? wallet.name;
  }
}
