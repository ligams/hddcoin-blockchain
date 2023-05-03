import type { Wallet } from '@hddcoin-network/api';
import { WalletType } from '@hddcoin-network/api';
import { byteToCATLocaleString, byteToHDDcoinLocaleString, useLocale } from '@hddcoin-network/core';
import BigNumber from 'bignumber.js';
import { useMemo } from 'react';

export default function useWalletHumanValue(
  wallet: Wallet,
  value?: string | number | BigNumber,
  unit?: string
): string {
  const [locale] = useLocale();

  return useMemo(() => {
    if (wallet && value !== undefined) {
      const localisedValue =
        wallet.type === WalletType.CAT ? byteToCATLocaleString(value, locale) : byteToHDDcoinLocaleString(value, locale);

      return `${localisedValue} ${unit}`;
    }

    return '';
  }, [wallet, value, unit, locale]);
}
