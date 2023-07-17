import BigNumber from 'bignumber.js';
import React from 'react';

import byteToCAT from '../../utils/byteToCATLocaleString';
import FormatLargeNumber from '../FormatLargeNumber';

export type ByteToCATProps = {
  value: number | BigNumber;
  currencyCode: string;
};

export default function ByteToCAT(props: ByteToCATProps) {
  const { value, currencyCode } = props;
  const updatedValue = byteToCAT(value);

  return (
    <>
      <FormatLargeNumber value={updatedValue} />
      &nbsp;{currencyCode}
    </>
  );
}
