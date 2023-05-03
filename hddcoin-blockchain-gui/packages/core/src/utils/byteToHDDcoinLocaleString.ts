import BigNumber from 'bignumber.js';

import Unit from '../constants/Unit';
import hddcoinFormatter from './hddcoinFormatter';

export default function byteToHDDcoinLocaleString(byte: string | number | BigNumber, locale?: string) {
  return hddcoinFormatter(byte, Unit.BYTE).to(Unit.HDDCOIN).toLocaleString(locale);
}
