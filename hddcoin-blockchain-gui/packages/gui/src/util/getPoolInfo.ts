import type { PoolInfo } from '@hddcoin-network/api';
import { toCamelCase } from '@hddcoin-network/api';

export default async function getPoolInfo(poolUrl: string): PoolInfo {
  const url = `${poolUrl}/pool_info`;
  const response = await fetch(url);
  const data = await response.json();

  return toCamelCase(data);
}
