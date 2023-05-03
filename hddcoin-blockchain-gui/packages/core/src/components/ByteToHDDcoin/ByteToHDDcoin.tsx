import BigNumber from 'bignumber.js';
import React from 'react';

import useCurrencyCode from '../../hooks/useCurrencyCode';
import byteToHDDcoin from '../../utils/byteToHDDcoinLocaleString';
import FormatLargeNumber from '../FormatLargeNumber';

export type ByteToHDDcoinProps = {
  value: number | BigNumber;
};

export default function ByteToHDDcoin(props: ByteToHDDcoinProps) {
  const { value } = props;
  const currencyCode = useCurrencyCode();
  const updatedValue = byteToHDDcoin(value);

  return (
    <>
      <FormatLargeNumber value={updatedValue} />
      &nbsp;{currencyCode ?? ''}
    </>
  );
}
