import { Flex, State, StateTypography, TooltipIcon } from '@hddcoin-network/core';
import { Trans } from '@lingui/macro';
import { Typography } from '@mui/material';
import React from 'react';

import PlotNFTStateEnum from '../../constants/PlotNFTState';
import type PlotNFT from '../../types/PlotNFT';

type Props = {
  nft: PlotNFT;
};

export default function PlotNFTState(props: Props) {
  const {
    nft: {
      poolWalletStatus: {
        current: { state },
        target,
      },
    },
  } = props;

  if (!target && state === PlotNFTStateEnum.LEAVING_POOL) {
    return (
      <Flex alignItems="center" gap={1} inline>
        <StateTypography variant="body1" state={State.ERROR}>
          <Trans>Invalid state</Trans>
        </StateTypography>
        <TooltipIcon>
          <Trans>The pool switching operation was cancelled, please try again by changing pool, or self pooling</Trans>
        </TooltipIcon>
      </Flex>
    );
  }

  const isPending = !!target && target.state !== state;
  if (isPending) {
    return (
      <Flex alignItems="center" gap={1} inline>
        <StateTypography variant="body1" state={State.WARNING}>
          <Trans>Pending</Trans>
        </StateTypography>
        <TooltipIcon>
          <Trans>
            PlotNFT is transitioning to (target state). This can take a while. Please do not close the application until
            this is finalized.
          </Trans>
        </TooltipIcon>
      </Flex>
    );
  }

  return (
    <Typography component="div" variant="body1">
      {state === PlotNFTStateEnum.SELF_POOLING && <Trans>Self Pooling</Trans>}
      {state === PlotNFTStateEnum.LEAVING_POOL && <Trans>Leaving Pool</Trans>}
      {state === PlotNFTStateEnum.FARMING_TO_POOL && <Trans>Pooling</Trans>}
    </Typography>
  );
}
