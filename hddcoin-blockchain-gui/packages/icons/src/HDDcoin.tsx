import { SvgIcon, SvgIconProps } from '@mui/material';
import React from 'react';

import HDDcoinBlackIcon from './images/hddcoin-black.svg';
import HDDcoinIcon from './images/hddcoin.svg';

export default function Keys(props: SvgIconProps) {
  return <SvgIcon component={HDDcoinIcon} viewBox="0 0 150 58" {...props} />;
}

export function HDDcoinBlack(props: SvgIconProps) {
  return <SvgIcon component={HDDcoinBlackIcon} viewBox="0 0 100 39" sx={{ width: '100px', height: '39px' }} {...props} />;
}
