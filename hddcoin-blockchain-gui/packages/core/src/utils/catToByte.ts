import BigNumber from 'bignumber.js';

import Unit from '../constants/Unit';
import hddcoinFormatter from './hddcoinFormatter';

export default function catToByte(cat: string | number | BigNumber): BigNumber {
  return hddcoinFormatter(cat, Unit.CAT).to(Unit.BYTE).toBigNumber();
}
