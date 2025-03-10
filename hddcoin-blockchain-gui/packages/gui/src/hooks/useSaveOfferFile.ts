import fs from 'fs';

import { OfferTradeRecord } from '@hddcoin-network/api';
import { useGetOfferDataMutation } from '@hddcoin-network/api-react';
import { useShowSaveDialog } from '@hddcoin-network/core';

import { suggestedFilenameForOffer } from '../components/offers/utils';
import useAssetIdName from './useAssetIdName';

export type SaveOfferFileHook = (tradeId: string) => Promise<void>;

export default function useSaveOfferFile(): [SaveOfferFileHook] {
  const [getOfferData] = useGetOfferDataMutation();
  const { lookupByAssetId } = useAssetIdName();
  const showSaveDialog = useShowSaveDialog();

  async function saveOfferFile(tradeId: string): Promise<void> {
    const {
      data: response,
    }: {
      data: { offer: string; tradeRecord: OfferTradeRecord; success: boolean };
    } = await getOfferData({ offerId: tradeId });
    const { offer: offerData, tradeRecord, success } = response;
    if (success === true) {
      const dialogOptions = {
        defaultPath: suggestedFilenameForOffer(tradeRecord.summary, lookupByAssetId),
      };
      const result = await showSaveDialog(dialogOptions);
      const { filePath, canceled } = result;

      if (!canceled && filePath) {
        try {
          fs.writeFileSync(filePath, offerData);
        } catch (err) {
          console.error(err);
        }
      }
    }
  }

  return [saveOfferFile];
}
