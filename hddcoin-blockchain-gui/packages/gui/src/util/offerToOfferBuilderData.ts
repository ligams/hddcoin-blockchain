import { OfferSummaryRecord } from '@hddcoin-network/api';
import { byteToCAT, byteToHDDcoin } from '@hddcoin-network/core';
import BigNumber from 'bignumber.js';

import type OfferBuilderData from '../@types/OfferBuilderData';
import type OfferSummary from '../@types/OfferSummary';
import { launcherIdToNFTId } from './nfts';

export default function offerToOfferBuilderData(
  offerSummary: OfferSummary | OfferSummaryRecord,
  setDefaultOfferedFee?: boolean,
  defaultFee?: string // in bytes
): OfferBuilderData {
  const { fees, offered, requested, infos } = offerSummary;

  const defaultFeeHDD = defaultFee ? byteToHDDcoin(defaultFee).toFixed() : '';

  const offeredHdd: OfferBuilderData['offered']['hdd'] = [];
  const offeredTokens: OfferBuilderData['offered']['tokens'] = [];
  const offeredNfts: OfferBuilderData['offered']['nfts'] = [];
  const offeredFee: OfferBuilderData['offered']['fee'] = setDefaultOfferedFee ? [{ amount: defaultFeeHDD }] : [];
  const requestedHdd: OfferBuilderData['requested']['hdd'] = [];
  const requestedTokens: OfferBuilderData['requested']['tokens'] = [];
  const requestedNfts: OfferBuilderData['requested']['nfts'] = [];

  // processing requested first because it's what you/we will give

  Object.keys(requested).forEach((id) => {
    const amount = new BigNumber(requested[id]);
    const info = infos[id];

    if (info?.type === 'CAT') {
      offeredTokens.push({
        amount: byteToCAT(amount).toFixed(),
        assetId: id,
      });
    } else if (info?.type === 'singleton') {
      offeredNfts.push({
        nftId: launcherIdToNFTId(info.launcherId),
      });
    } else if (id === 'hdd') {
      offeredHdd.push({
        amount: byteToHDDcoin(amount).toFixed(),
      });
    }
  });

  Object.keys(offered).forEach((id) => {
    const amount = new BigNumber(offered[id]);
    const info = infos[id];

    if (info?.type === 'CAT') {
      requestedTokens.push({
        amount: byteToCAT(amount).toFixed(),
        assetId: id,
      });
    } else if (info?.type === 'singleton') {
      requestedNfts.push({
        nftId: launcherIdToNFTId(info.launcherId),
      });
    } else if (id === 'hdd') {
      requestedHdd.push({
        amount: byteToHDDcoin(amount).toFixed(),
      });
    }
  });

  return {
    offered: {
      hdd: offeredHdd,
      tokens: offeredTokens,
      nfts: offeredNfts,
      fee: offeredFee,
    },
    requested: {
      hdd: requestedHdd,
      tokens: requestedTokens,
      nfts: requestedNfts,
      fee: [
        {
          amount: byteToHDDcoin(fees).toFixed(),
        },
      ],
    },
  };
}
