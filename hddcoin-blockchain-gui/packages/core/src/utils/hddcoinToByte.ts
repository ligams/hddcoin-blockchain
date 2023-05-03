import BigNumber from 'bignumber.js';

import Unit from '../constants/Unit';
import hddcoinFormatter from './hddcoinFormatter';

export default function hddcoinToByte(hddcoin: string | number | BigNumber): BigNumber {
  return hddcoinFormatter(hddcoin, Unit.HDDCOIN).to(Unit.BYTE).toBigNumber();
}
