import type { Wallet } from '@hddcoin-network/api';
import { useGetWalletsQuery } from '@hddcoin-network/api-react';
import { Flex } from '@hddcoin-network/core';
import { Trans } from '@lingui/macro';
import { Grid } from '@mui/material';
import React from 'react';
import { useWatch } from 'react-hook-form';

import OfferBuilderAmountWithRoyalties from './OfferBuilderAmountWithRoyalties';
import OfferBuilderValue from './OfferBuilderValue';
import OfferBuilderWalletAmount from './OfferBuilderWalletAmount';

export type OfferBuilderTokenProps = {
  name: string;
  onRemove?: () => void;
  usedAssets?: string[];
  hideBalance?: boolean;
  amountWithRoyalties?: string;
  royaltyPayments?: Record<string, any>[];
};

export default function OfferBuilderToken(props: OfferBuilderTokenProps) {
  const { name, onRemove, usedAssets, hideBalance, amountWithRoyalties, royaltyPayments } = props;

  const assetIdFieldName = `${name}.assetId`;
  const assetId = useWatch({
    name: assetIdFieldName,
  });
  const value = useWatch({
    name: `${name}.amount`,
  });

  const { data: wallets } = useGetWalletsQuery();
  const wallet = wallets?.find((walletItem: Wallet) => walletItem.meta?.assetId?.toLowerCase() === assetId);
  const warnUnknownCAT = assetId && !wallet;

  return (
    <Flex flexDirection="column" gap={2}>
      <Grid spacing={3} container>
        <Grid xs={12} md={5} item>
          <OfferBuilderWalletAmount
            name={`${name}.amount`}
            walletId={wallet?.id}
            showAmountInBytes={false}
            hideBalance={hideBalance}
          />
        </Grid>
        <Grid xs={12} md={7} item>
          <OfferBuilderValue
            name={assetIdFieldName}
            type="token"
            label={<Trans>Asset Type</Trans>}
            usedAssets={usedAssets}
            onRemove={onRemove}
            warnUnknownCAT={warnUnknownCAT}
          />
        </Grid>
      </Grid>
      {royaltyPayments && amountWithRoyalties && (
        <OfferBuilderAmountWithRoyalties
          originalAmount={value}
          totalAmount={amountWithRoyalties}
          royaltyPayments={royaltyPayments}
        />
      )}
    </Flex>
  );
}
