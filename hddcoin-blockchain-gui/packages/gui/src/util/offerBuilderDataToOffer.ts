import type { Wallet } from '@hddcoin-network/api';
import { WalletType } from '@hddcoin-network/api';
import { hddcoinToByte, catToByte } from '@hddcoin-network/core';
import { t } from '@lingui/macro';
import BigNumber from 'bignumber.js';

import type Driver from '../@types/Driver';
import type OfferBuilderData from '../@types/OfferBuilderData';
import type { OfferTradeRecordFormatted } from '../hooks/useWalletOffers';
import findCATWalletByAssetId from './findCATWalletByAssetId';
import { getBalance, WalletBalanceFormatted } from './hasSpendableBalance';
import { prepareNFTOfferFromNFTId } from './prepareNFTOffer';

// Status of existing assets in offers
// A combination of `type` and `assetId` must be unique through an array of `AssetStatusForOffer`.
export type AssetStatusForOffer = {
  type: 'HDD' | 'CAT' | 'SINGLETON';
  assetId: string;
  assetName?: string; // Used just for labeling
  nftId?: string;
  lockedAmount: BigNumber;
  spendingAmount: BigNumber;
  spendableAmount: BigNumber;
  confirmedAmount: BigNumber;
  // - alsoUsedInNewOfferWithoutConflict
  //   The same asset is also offered in new offer but the amount is sufficient.
  //   Even existing offers are all settled, new offer won't fail because of lacked coin amount.
  // - conflictsWithNewOffer
  //   The same asset is also offered in new offer and only one of existing offers or new offer
  //   can be settled because not enough amount is spendable.
  status: '' | 'alsoUsedInNewOfferWithoutConflict' | 'conflictsWithNewOffer';
  relevantOffers: OfferTradeRecordFormatted[];
};

export type OfferBuilderDataToOfferParams = {
  data: OfferBuilderData;
  wallets: Wallet[];
  offers: OfferTradeRecordFormatted[];
  validateOnly?: boolean;
  considerNftRoyalty?: boolean;
  allowEmptyOfferColumn?: boolean;
  allowUnknownRequestedCATs?: boolean;
};

// Amount exceeds spendable balance
export default async function offerBuilderDataToOffer({
  data,
  wallets,
  offers,
  validateOnly = false,
  considerNftRoyalty = false,
  allowEmptyOfferColumn = false,
  allowUnknownRequestedCATs = false,
}: OfferBuilderDataToOfferParams): Promise<{
  walletIdsAndAmounts?: Record<string, BigNumber>;
  driverDict?: Record<string, any>;
  feeInBytes: BigNumber;
  validateOnly?: boolean;
  assetsToUnlock: AssetStatusForOffer[];
}> {
  const {
    offered: { hdd: offeredHdd = [], tokens: offeredTokens = [], nfts: offeredNfts = [], fee: [firstFee] = [] },
    requested: { hdd: requestedHdd = [], tokens: requestedTokens = [], nfts: requestedNfts = [] },
  } = data;

  const usedNFTs: string[] = [];

  const feeInBytes = firstFee ? hddcoinToByte(firstFee.amount) : new BigNumber(0);

  const walletIdsAndAmounts: Record<string, BigNumber> = {};
  const driverDict: Record<string, Driver> = {};

  if (!allowEmptyOfferColumn) {
    const hasOffer = !!offeredHdd.length || !!offeredTokens.length || !!offeredNfts.length;

    if (!hasOffer) {
      throw new Error(t`Please specify at least one offered asset`);
    }
  }

  const pendingOffers: AssetStatusForOffer[] = [];

  for (let i = 0; i < offers.length; i++) {
    const o = offers[i];
    if (o.isMyOffer && o.status === 'PENDING_ACCEPT') {
      const assetIds = Object.keys(o.pending) as string[];
      for (let k = 0; k < assetIds.length; k++) {
        const assetId = assetIds[k];
        const lockedAmount = new BigNumber(o.pending[assetId]);
        if (assetId.toUpperCase() === 'HDD' || assetId.toUpperCase() === 'UNKNOWN') {
          // 'UNKNOWN' is the diff between removals and additions of coins in this offer
          // It is assumed to be the amount of the 'fee'
          const idx = pendingOffers.findIndex((po) => po.type === 'HDD');
          if (idx > -1) {
            pendingOffers[idx].lockedAmount = pendingOffers[idx].lockedAmount.plus(lockedAmount);
            pendingOffers[idx].relevantOffers.push(o);
            if (pendingOffers[idx].assetId.toUpperCase() !== assetId.toUpperCase()) {
              // Now we can distinguish that we have hdd spending which is only HDD, only Fee or both HDD and Fee
              pendingOffers[idx].assetId = 'HDD+FEE';
            }
          } else {
            pendingOffers.push({
              type: 'HDD',
              assetId,
              assetName: 'HDD',
              lockedAmount,
              status: '',
              spendingAmount: new BigNumber(0),
              spendableAmount: new BigNumber(0),
              confirmedAmount: new BigNumber(0),
              relevantOffers: [o],
            });
          }
        } else {
          const info = o.summary.infos[assetId];
          const type = info.type.toUpperCase() as 'CAT' | 'SINGLETON';
          const idx = pendingOffers.findIndex((po) => po.type === type && po.assetId === assetId);
          if (idx > -1) {
            pendingOffers[idx].lockedAmount = pendingOffers[idx].lockedAmount.plus(lockedAmount);
            pendingOffers[idx].relevantOffers.push(o);
          } else {
            pendingOffers.push({
              type,
              assetId,
              lockedAmount,
              status: '',
              spendingAmount: new BigNumber(0),
              spendableAmount: new BigNumber(0),
              confirmedAmount: new BigNumber(0),
              relevantOffers: [o],
            });
          }
        }
      }
    }
  }

  let standardWallet: Wallet | undefined;
  let standardWalletBalance: WalletBalanceFormatted | undefined;
  let pendingHddOffer: AssetStatusForOffer | undefined;
  let pendingHdd = new BigNumber(0);
  if (offeredHdd.length > 0 || feeInBytes.gt(0)) {
    standardWallet = wallets.find((w) => w.type === WalletType.STANDARD_WALLET);
    for (let i = 0; i < pendingOffers.length; i++) {
      const po = pendingOffers[i];
      if (po.type === 'HDD') {
        pendingHddOffer = po;
        pendingHdd = po.lockedAmount;
        break;
      }
    }
    if (standardWallet) {
      standardWalletBalance = await getBalance(standardWallet.id);
    }
  }

  // offeredHdd.length should be always 0 or 1
  const hddTasks = offeredHdd.map(async (hdd) => {
    const { amount } = hdd;
    if (!amount || amount === '0') {
      throw new Error(t`Please enter an HDD amount`);
    }
    if (!standardWallet || !standardWalletBalance) {
      throw new Error(t`No standard wallet found`);
    }

    const byteAmount = hddcoinToByte(amount);
    walletIdsAndAmounts[standardWallet.id] = byteAmount.negated();

    const spendableBalance = new BigNumber(standardWalletBalance.spendableBalance);
    const hasEnoughTotalBalance = spendableBalance.plus(pendingHdd).minus(feeInBytes).gte(byteAmount);
    if (!hasEnoughTotalBalance) {
      throw new Error(t`Amount exceeds HDD total balance`);
    }

    if (pendingHddOffer) {
      // Assuming offeredHdd.length is always less then or equal to 1
      pendingHddOffer.spendingAmount = byteAmount.plus(feeInBytes);
      pendingHddOffer.spendableAmount = spendableBalance;
      pendingHddOffer.confirmedAmount = new BigNumber(standardWalletBalance.confirmedWalletBalance);
      const hasEnoughSpendableBalance = spendableBalance.gte(pendingHddOffer.spendingAmount);
      if (!hasEnoughSpendableBalance) {
        pendingHddOffer.status = 'conflictsWithNewOffer';
      } else {
        pendingHddOffer.status = 'alsoUsedInNewOfferWithoutConflict';
      }
    }
  });
  // Treat fee as hdd spending
  if (offeredHdd.length === 0 && feeInBytes.gt(0)) {
    if (!standardWallet || !standardWalletBalance) {
      throw new Error(t`No standard wallet found`);
    }

    const spendableBalance = new BigNumber(standardWalletBalance.spendableBalance);
    const hasEnoughTotalBalance = spendableBalance.gte(feeInBytes);
    if (!hasEnoughTotalBalance) {
      throw new Error(t`Fee exceeds HDD total balance`);
    }
    if (pendingHddOffer) {
      pendingHddOffer.spendingAmount = feeInBytes;
      pendingHddOffer.spendableAmount = spendableBalance;
      pendingHddOffer.confirmedAmount = new BigNumber(standardWalletBalance.confirmedWalletBalance);
      const hasEnoughSpendableBalance = spendableBalance.gte(pendingHddOffer.spendingAmount);
      if (!hasEnoughSpendableBalance) {
        pendingHddOffer.status = 'conflictsWithNewOffer';
      } else {
        pendingHddOffer.status = 'alsoUsedInNewOfferWithoutConflict';
      }
    }
  }

  const tokenTasks = offeredTokens.map(async (token) => {
    const { assetId, amount } = token;

    if (!assetId) {
      throw new Error(t`Please select an asset for each token`);
    }

    const catWallet = findCATWalletByAssetId(wallets, assetId);
    if (!catWallet) {
      throw new Error(t`No CAT wallet found for ${assetId} token`);
    }

    const catName = catWallet.meta?.name || 'Unknown token';

    if (!amount || amount === '0') {
      throw new Error(t`Please enter an amount for ${catName} token`);
    }

    const byteAmount = catToByte(amount);
    walletIdsAndAmounts[catWallet.id] = byteAmount.negated();

    const pendingCatOffer = pendingOffers.find((po) => po.type === 'CAT' && po.assetId === assetId);
    const pendingCat = pendingCatOffer ? pendingCatOffer.lockedAmount : new BigNumber(0);

    const walletBalance = await getBalance(catWallet.id);
    const spendableBalance = new BigNumber(walletBalance.spendableBalance);
    const hasEnoughTotalBalance = spendableBalance.plus(pendingCat).gte(byteAmount);
    if (!hasEnoughTotalBalance) {
      throw new Error(t`Amount exceeds total balance for ${catName} token`);
    }

    if (pendingCatOffer) {
      // Assuming no duplicate of `assetId` exists in `offeredTokens`
      pendingCatOffer.spendingAmount = byteAmount;
      pendingCatOffer.spendableAmount = spendableBalance;
      pendingCatOffer.confirmedAmount = new BigNumber(walletBalance.confirmedWalletBalance);
      pendingCatOffer.assetName = catName;
      const hasEnoughSpendableBalance = spendableBalance.gte(byteAmount);
      if (!hasEnoughSpendableBalance) {
        pendingCatOffer.status = 'conflictsWithNewOffer';
      } else {
        pendingCatOffer.status = 'alsoUsedInNewOfferWithoutConflict';
      }
    }
  });

  const nftTasks = offeredNfts.map(async ({ nftId }) => {
    if (usedNFTs.includes(nftId)) {
      throw new Error(t`NFT ${nftId} is already used in this offer`);
    }
    usedNFTs.push(nftId);

    const { id, amount, driver } = await prepareNFTOfferFromNFTId(nftId, true);

    walletIdsAndAmounts[id] = amount;
    if (driver) {
      driverDict[id] = driver;
    }

    const pendingNft = pendingOffers.find((po) => po.type === 'SINGLETON' && po.assetId === id);
    if (pendingNft) {
      pendingNft.nftId = nftId;
      pendingNft.spendingAmount = new BigNumber(1);
      pendingNft.assetName = `NFT ${nftId}`;
      // Currently offered NFT is not locked upon creating offer so status should be 'alsoUsedInNewOfferWithoutConflict'.
      pendingNft.status = 'alsoUsedInNewOfferWithoutConflict';
    }
  });

  await Promise.all([...hddTasks, ...tokenTasks, ...nftTasks]);

  // requested
  requestedHdd.forEach((hdd) => {
    const { amount } = hdd;

    // For one-sided offers where nothing is requested, we allow the amount to be '0'
    // and skip adding an entry to the walletIdsAndAmounts object.
    //
    // If the amount is blank '', we prompt the user to enter an amount.
    if (amount === '0') {
      return;
    }

    if (!amount) {
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

    if (!allowUnknownRequestedCATs) {
      const wallet = findCATWalletByAssetId(wallets, assetId);
      if (!wallet) {
        throw new Error(t`No CAT wallet found for ${assetId} token`);
      }

      if (!amount || amount === '0') {
        throw new Error(t`Please enter an amount for ${wallet.meta?.name} token`);
      }

      walletIdsAndAmounts[wallet.id] = catToByte(amount);
    }
  });

  const prepareNftTasks = requestedNfts.map(async ({ nftId }) => {
    if (usedNFTs.includes(nftId)) {
      throw new Error(t`NFT ${nftId} is already used in this offer`);
    }
    usedNFTs.push(nftId);

    const { id, amount, driver } = await prepareNFTOfferFromNFTId(nftId, false);

    walletIdsAndAmounts[id] = amount;
    if (driver) {
      driverDict[id] = driver;

      if (considerNftRoyalty && pendingHddOffer) {
        const royaltyPercentageStr = driver.also.also?.transfer_program.royalty_percentage;
        if (royaltyPercentageStr) {
          const royaltyMultiplier = 1 + +royaltyPercentageStr / 10_000;
          const spendingHdd = pendingHddOffer.spendingAmount.minus(feeInBytes);
          const newSpendingHdd = spendingHdd.multipliedBy(royaltyMultiplier).plus(feeInBytes);
          pendingHddOffer.spendingAmount = newSpendingHdd;

          const hasEnoughSpendableBalance = pendingHddOffer.spendableAmount.gte(pendingHddOffer.spendingAmount);
          if (!hasEnoughSpendableBalance) {
            pendingHddOffer.status = 'conflictsWithNewOffer';
          } else {
            pendingHddOffer.status = 'alsoUsedInNewOfferWithoutConflict';
          }
        }
      }
    }
  });

  await Promise.all(prepareNftTasks);

  return {
    walletIdsAndAmounts,
    driverDict,
    feeInBytes,
    validateOnly,
    assetsToUnlock: pendingOffers.filter((po) => po.spendingAmount.gt(0)),
  };
}
