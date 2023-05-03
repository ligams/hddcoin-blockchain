import { WalletType } from '@hddcoin-network/api';
import { useGetWalletBalanceQuery } from '@hddcoin-network/api-react';
import { byteToCATLocaleString, byteToHDDcoinLocaleString, useLocale } from '@hddcoin-network/core';
import { useWallet } from '@hddcoin-network/wallets';
import { Trans } from '@lingui/macro';
import React, { useMemo } from 'react';

export type OfferBuilderWalletBalanceProps = {
  walletId: number;
};

export default function OfferBuilderWalletBalance(props: OfferBuilderWalletBalanceProps) {
  const { walletId } = props;
  const [locale] = useLocale();
  const { data: walletBalance, isLoading: isLoadingWalletBalance } = useGetWalletBalanceQuery({
    walletId,
  });

  const { unit, wallet, loading } = useWallet(walletId);

  const isLoading = isLoadingWalletBalance || loading;

  const hddBalance = useMemo(() => {
    if (isLoading || !wallet || !walletBalance || !('spendableBalance' in walletBalance)) {
      return undefined;
    }

    if (wallet.type === WalletType.STANDARD_WALLET) {
      return byteToHDDcoinLocaleString(walletBalance.spendableBalance, locale);
    }

    if (wallet.type === WalletType.CAT) {
      return byteToCATLocaleString(walletBalance.spendableBalance, locale);
    }

    return undefined;
  }, [isLoading, wallet, walletBalance, locale]);

  if (!isLoading && hddBalance === undefined) {
    return null;
  }

  return (
    <Trans>
      Spendable Balance:{' '}
      {isLoading ? (
        'Loading...'
      ) : (
        <>
          {hddBalance}
          &nbsp;
          {unit?.toUpperCase()}
        </>
      )}
    </Trans>
  );
}
