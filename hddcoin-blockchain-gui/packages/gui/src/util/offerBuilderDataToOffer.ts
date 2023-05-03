import type { Wallet } from '@hddcoin-network/api';
import { WalletType } from '@hddcoin-network/api';
import { hddcoinToByte, catToByte } from '@hddcoin-network/core';
import { t } from '@lingui/macro';
import BigNumber from 'bignumber.js';

import type Driver from '../@types/Driver';
import type OfferBuilderData from '../@types/OfferBuilderData';
import findCATWalletByAssetId from './findCATWalletByAssetId';
import hasSpendableBalance from './hasSpendableBalance';
import { prepareNFTOfferFromNFTId } from './prepareNFTOffer';

// Amount exceeds spendable balance
export default async function offerBuilderDataToOffer(
  data: OfferBuilderData,
  wallets: Wallet[],
  validateOnly?: boolean
): Promise<{
  walletIdsAndAmounts?: Record<string, BigNumber>;
  driverDict?: Record<string, any>;
  feeInBytes: BigNumber;
  validateOnly?: boolean;
}> {
  const {
    offered: { hdd: offeredHdd = [], tokens: offeredTokens = [], nfts: offeredNfts = [], fee: [firstFee] = [] },
    requested: { hdd: requestedHdd = [], tokens: requestedTokens = [], nfts: requestedNfts = [] },
  } = data;

  const usedNFTs: string[] = [];

  const feeInBytes = firstFee ? hddcoinToByte(firstFee.amount) : new BigNumber(0);

  const walletIdsAndAmounts: Record<string, BigNumber> = {};
  const driverDict: Record<string, Driver> = {};

  const hasOffer = !!offeredHdd.length || !!offeredTokens.length || !!offeredNfts.length;

  if (!hasOffer) {
    throw new Error(t`Please specify at least one offered asset`);
  }

  await Promise.all(
    offeredHdd.map(async (hdd) => {
      const { amount } = hdd;
      if (!amount || amount === '0') {
        throw new Error(t`Please enter an HDD amount`);
      }

      const wallet = wallets.find((w) => w.type === WalletType.STANDARD_WALLET);
      if (!wallet) {
        throw new Error(t`No standard wallet found`);
      }

      const byteAmount = hddcoinToByte(amount);
      walletIdsAndAmounts[wallet.id] = byteAmount.negated();

      const hasEnoughBalance = await hasSpendableBalance(wallet.id, byteAmount);
      if (!hasEnoughBalance) {
        throw new Error(t`Amount exceeds HDD spendable balance`);
      }
    })
  );

  await Promise.all(
    offeredTokens.map(async (token) => {
      const { assetId, amount } = token;

      if (!assetId) {
        throw new Error(t`Please select an asset for each token`);
      }

      const wallet = findCATWalletByAssetId(wallets, assetId);
      if (!wallet) {
        throw new Error(t`No CAT wallet found for ${assetId} token`);
      }

      if (!amount || amount === '0') {
        throw new Error(t`Please enter an amount for ${wallet.meta?.name} token`);
      }

      const byteAmount = catToByte(amount);
      walletIdsAndAmounts[wallet.id] = byteAmount.negated();

      const hasEnoughBalance = await hasSpendableBalance(wallet.id, byteAmount);
      if (!hasEnoughBalance) {
        throw new Error(t`Amount exceeds spendable balance for ${wallet.meta?.name} token`);
      }
    })
  );

  await Promise.all(
    offeredNfts.map(async ({ nftId }) => {
      if (usedNFTs.includes(nftId)) {
        throw new Error(t`NFT ${nftId} is already used in this offer`);
      }
      usedNFTs.push(nftId);

      const { id, amount, driver } = await prepareNFTOfferFromNFTId(nftId, true);

      walletIdsAndAmounts[id] = amount;
      if (driver) {
        driverDict[id] = driver;
      }
    })
  );

  // requested
  requestedHdd.forEach((hdd) => {
    const { amount } = hdd;
    if (!amount || amount === '0') {
      throw new Error(t`Please enter an HDD amount`);
    }

    const wallet = wallets.find((w) => w.type === WalletType.STANDARD_WALLET);
    if (!wallet) {
      throw new Error(t`No standard wallet found`);
    }

    if (wallet.id in walletIdsAndAmounts) {
      throw new Error(t`Cannot offer and request the same asset`);
    }

    walletIdsAndAmounts[wallet.id] = hddcoinToByte(amount);
  });

  requestedTokens.forEach((token) => {
    const { assetId, amount } = token;

    if (!assetId) {
      throw new Error(t`Please select an asset for each token`);
    }

    const wallet = findCATWalletByAssetId(wallets, assetId);
    if (!wallet) {
      throw new Error(t`No CAT wallet found for ${assetId} token`);
    }

    if (!amount || amount === '0') {
      throw new Error(t`Please enter an amount for ${wallet.meta?.name} token`);
    }

    walletIdsAndAmounts[wallet.id] = catToByte(amount);
  });

  await Promise.all(
    requestedNfts.map(async ({ nftId }) => {
      if (usedNFTs.includes(nftId)) {
        throw new Error(t`NFT ${nftId} is already used in this offer`);
      }
      usedNFTs.push(nftId);

      const { id, amount, driver } = await prepareNFTOfferFromNFTId(nftId, false);

      walletIdsAndAmounts[id] = amount;
      if (driver) {
        driverDict[id] = driver;
      }
    })
  );

  return {
    walletIdsAndAmounts,
    driverDict,
    feeInBytes,
    validateOnly,
  };
}
