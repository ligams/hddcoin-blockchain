import BigNumber from 'bignumber.js';

import Unit from '../constants/Unit';
import hddcoinFormatter from './hddcoinFormatter';

export default function byteToCAT(byte: string | number | BigNumber): BigNumber {
  return hddcoinFormatter(byte, Unit.BYTE).to(Unit.CAT).toBigNumber();
}
