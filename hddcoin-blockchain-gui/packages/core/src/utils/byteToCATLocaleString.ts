import BigNumber from 'bignumber.js';

import Unit from '../constants/Unit';
import hddcoinFormatter from './hddcoinFormatter';

export default function byteToCATLocaleString(byte: string | number | BigNumber, locale?: string) {
  return hddcoinFormatter(byte, Unit.BYTE).to(Unit.CAT).toLocaleString(locale);
}
