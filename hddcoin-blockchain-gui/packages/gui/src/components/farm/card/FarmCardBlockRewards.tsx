import { useGetFarmedAmountQuery } from '@hddcoin-network/api-react';
import { useCurrencyCode, byteToHDDcoinLocaleString, CardSimple, useLocale } from '@hddcoin-network/core';
import { Trans } from '@lingui/macro';
import BigNumber from 'bignumber.js';
import React, { useMemo } from 'react';

export default function FarmCardBlockRewards() {
  const currencyCode = useCurrencyCode();
  const [locale] = useLocale();
  const { data, isLoading, error } = useGetFarmedAmountQuery();

  const farmerRewardAmount = data?.farmerRewardAmount;
  const poolRewardAmount = data?.poolRewardAmount;

  const blockRewards = useMemo(() => {
    if (farmerRewardAmount !== undefined && poolRewardAmount !== undefined) {
      const val = new BigNumber(farmerRewardAmount).plus(new BigNumber(poolRewardAmount));

      return (
        <>
          {byteToHDDcoinLocaleString(val, locale)}
          &nbsp;
          {currencyCode}
        </>
      );
    }
    return undefined;
  }, [farmerRewardAmount, poolRewardAmount, locale, currencyCode]);

  return (
    <CardSimple
      title={<Trans>Block Rewards</Trans>}
      description={<Trans>Without fees</Trans>}
      value={blockRewards}
      loading={isLoading}
      error={error}
    />
  );
}
