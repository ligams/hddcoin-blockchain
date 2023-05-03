import { useGetFarmedAmountQuery } from '@hddcoin-network/api-react';
import { useCurrencyCode, byteToHDDcoinLocaleString, CardSimple, useLocale } from '@hddcoin-network/core';
import { Trans } from '@lingui/macro';
import React, { useMemo } from 'react';

export default function FarmCardTotalHDDcoinFarmed() {
  const currencyCode = useCurrencyCode();
  const [locale] = useLocale();
  const { data, isLoading, error } = useGetFarmedAmountQuery();

  const farmedAmount = data?.farmedAmount;

  const totalHDDcoinFarmed = useMemo(() => {
    if (farmedAmount !== undefined) {
      return (
        <>
          {byteToHDDcoinLocaleString(farmedAmount, locale)}
          &nbsp;
          {currencyCode}
        </>
      );
    }
    return undefined;
  }, [farmedAmount, locale, currencyCode]);

  return (
    <CardSimple title={<Trans>Total HDDcoin Farmed</Trans>} value={totalHDDcoinFarmed} loading={isLoading} error={error} />
  );
}
