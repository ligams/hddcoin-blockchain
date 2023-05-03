import { SvgIcon, SvgIconProps } from '@mui/material';
import React from 'react';

import HDDcoinIcon from './images/hddcoin.svg';

export default function Keys(props: SvgIconProps) {
  return <SvgIcon component={HDDcoinIcon} viewBox="0 0 150 58" {...props} />;
}
