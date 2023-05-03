import { useGetTotalHarvestersSummaryQuery } from '@hddcoin-network/api-react';
import { FormatLargeNumber, CardSimple } from '@hddcoin-network/core';
import { Trans } from '@lingui/macro';
import React from 'react';

export default function PlotCardNotFound() {
  const { noKeyFilenames, initializedHarvesters, isLoading } = useGetTotalHarvestersSummaryQuery();

  return (
    <CardSimple
      title={<Trans>Plots With Missing Keys</Trans>}
      value={<FormatLargeNumber value={noKeyFilenames} />}
      loading={isLoading || !initializedHarvesters}
    />
  );
}
