import { CardStep, ConfirmDialog, Link, Select, StateColor, useOpenDialog } from '@hddcoin-network/core';
import { Trans } from '@lingui/macro';
import { Grid, FormControl, Typography, InputLabel, MenuItem, FormHelperText } from '@mui/material';
import React, { useEffect, useState } from 'react';
import { useFormContext } from 'react-hook-form';
import styled from 'styled-components';

import { getPlotSizeOptions } from '../../../constants/plotSizes';
import Plotter from '../../../types/Plotter';

const MIN_MAINNET_K_SIZE = 32;

const StyledFormHelperText = styled(FormHelperText)`
  color: ${StateColor.WARNING};
`;

type Props = {
  step: number;
  plotter: Plotter;
};

export default function PlotAddChooseSize(props: Props) {
  const { step, plotter } = props;
  const { watch, setValue } = useFormContext();
  const openDialog = useOpenDialog();

  const plotterName = watch('plotterName');
  const plotSize = watch('plotSize');
  const overrideK = watch('overrideK');
  const isKLow = plotSize < MIN_MAINNET_K_SIZE;

  const [allowedPlotSizes, setAllowedPlotSizes] = useState(
    getPlotSizeOptions(plotterName).filter((option) => plotter.options.kSizes.includes(option.value))
  );

  useEffect(() => {
    setAllowedPlotSizes(
      getPlotSizeOptions(plotterName).filter((option) => plotter.options.kSizes.includes(option.value))
    );
  }, [plotter.options.kSizes, plotterName]);

  useEffect(() => {
    async function getConfirmation() {
      const canUse = await openDialog(
        <ConfirmDialog
          title={<Trans>The minimum required size for mainnet is k=32</Trans>}
          confirmTitle={<Trans>Yes</Trans>}
          confirmColor="danger"
        >
          <Trans>Are you sure you want to use k={plotSize}?</Trans>
        </ConfirmDialog>
      );

      if (canUse) {
        setValue('overrideK', true);
      } else {
        setValue('plotSize', 32);
      }
    }

    if (plotSize === 25) {
      if (!overrideK) {
        getConfirmation();
      }
    } else {
      setValue('overrideK', false);
    }
  }, [plotSize, overrideK, setValue, openDialog]);

  return (
    <CardStep step={step} title={<Trans>Choose Plot Size</Trans>}>
      <Typography variant="subtitle1">
        <Trans>
          {
            'You do not need to be synced or connected to plot. Temporary files are created during the plotting process which exceed the size of the final plot files. Make sure you have enough space. '
          }
          <Link target="_blank" href="https://github.com/HDDcoin-Network/hddcoin-blockchain/wiki/k-sizes">
            Learn more
          </Link>
        </Trans>
      </Typography>

      <Grid container>
        <Grid xs={12} sm={10} md={8} lg={8} item>
          <FormControl variant="filled" fullWidth>
            <InputLabel required focused>
              <Trans>Plot Size</Trans>
            </InputLabel>
            <Select name="plotSize">
              {allowedPlotSizes.map((option) => (
                <MenuItem value={option.value} key={option.value}>
                  {option.label}
                </MenuItem>
              ))}
            </Select>
            {isKLow && (
              <StyledFormHelperText>
                <Trans>The minimum required size for mainnet is k=32</Trans>
              </StyledFormHelperText>
            )}
          </FormControl>
        </Grid>
      </Grid>
    </CardStep>
  );
}
