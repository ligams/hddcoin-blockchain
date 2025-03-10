import BigNumber from 'bignumber.js';

import type Unit from '../constants/Unit';
import UnitValue from '../constants/UnitValue';
import bigNumberToLocaleString from './bigNumberToLocaleString';

class HDDcoin {
  readonly value: BigNumber;

  readonly unit: Unit;

  constructor(value: number | string | BigNumber, unit: Unit) {
    const stringValue = value === '' || value === '.' || value === null || value === undefined ? '0' : value.toString();

    this.value = new BigNumber(stringValue);
    this.unit = unit;
  }

  to(newUnit: Unit) {
    const fromUnitValue = UnitValue[this.unit];
    const toUnitValue = UnitValue[newUnit];

    const amountInFromUnit = this.value.times(fromUnitValue.toString());
    const newValue = amountInFromUnit.div(toUnitValue.toString());

    return new HDDcoin(newValue, newUnit);
  }

  toFixed(decimals: number): string {
    return this.value.toFixed(decimals);
  }

  toString(): string {
    return this.value.toString();
  }

  toBigNumber(): BigNumber {
    return this.value;
  }

  toLocaleString(locale?: string): string {
    return bigNumberToLocaleString(this.value, locale);
  }
}

export default function hddcoinFormatter(value: number | string | BigNumber, unit: Unit) {
  return new HDDcoin(value, unit);
}
