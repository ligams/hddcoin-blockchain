import type { NFTInfo } from '@hddcoin-network/api';
import { useTransferNFTMutation } from '@hddcoin-network/api-react';
import {
  Button,
  ButtonLoading,
  EstimatedFee,
  FeeTxType,
  Form,
  Flex,
  TextField,
  hddcoinToByte,
  useCurrencyCode,
  useOpenDialog,
  validAddress,
  useShowError,
} from '@hddcoin-network/core';
import { Trans } from '@lingui/macro';
import { Dialog, DialogActions, DialogContent, DialogContentText, DialogTitle, Typography } from '@mui/material';
import React from 'react';
import { useForm } from 'react-hook-form';

import NFTSummary from './NFTSummary';
import NFTTransferConfirmationDialog from './NFTTransferConfirmationDialog';

/* ========================================================================== */
/*                              NFTTransferResult                             */
/* ========================================================================== */

export type NFTTransferResult = {
  transferInfo?: {
    nftAssetId: string;
    destination: string;
    fee: string;
  };
  error?: string;
};

/* ========================================================================== */
/*                      NFT Transfer Confirmation Dialog                      */
/* ========================================================================== */

/* ========================================================================== */
/*                         NFT Transfer Action (Form)                         */
/* ========================================================================== */

type NFTTransferFormData = {
  destination: string;
  fee: string;
};

type NFTTransferActionProps = {
  nfts: NFTInfo[];
  destination?: string;
  onComplete?: (result?: NFTTransferResult) => void;
};

export default function NFTTransferAction(props: NFTTransferActionProps) {
  const { nfts, destination = '', onComplete } = props;

  const [transferNFT, { isLoading: isTransferNFTLoading }] = useTransferNFTMutation();
  const openDialog = useOpenDialog();
  const showError = useShowError();
  const currencyCode = useCurrencyCode();
  const methods = useForm<NFTTransferFormData>({
    shouldUnregister: false,
    defaultValues: {
      destination,
      fee: '',
    },
  });

  async function handleClose() {
    if (onComplete) {
      onComplete(); // No result provided if the user cancels out of the dialog
    }
  }

  async function handleSubmit(formData: NFTTransferFormData) {
    const { destination: destinationLocal, fee } = formData;
    const feeInBytes = hddcoinToByte(fee || 0);

    try {
      if (!currencyCode) {
        throw new Error('Selected network address prefix is not defined');
      }
      validAddress(destinationLocal, [currencyCode.toLowerCase()]);
    } catch (error) {
      showError(error);
      return;
    }

    const description = nfts.length > 1 && (
      <Trans>
        Once you initiate this transfer, you will not be able to cancel the transaction. Are you sure you want to
        transfer {nfts.length} NFTs?
      </Trans>
    );

    const confirmation = await openDialog(
      <NFTTransferConfirmationDialog destination={destinationLocal} fee={fee} description={description} />
    );

    if (confirmation) {
      let success;
      let errorMessage;

      try {
        await transferNFT({
          walletId: nfts[0].walletId,
          nftCoinIds: nfts.map((nft: NFTInfo) => nft.nftCoinId),
          targetAddress: destinationLocal,
          fee: feeInBytes,
        }).unwrap();
        success = true;
        errorMessage = undefined;
      } catch (err: any) {
        success = false;
        errorMessage = err.message;
      }

      if (onComplete) {
        onComplete({
          success,
          error: errorMessage,
        });
      }
    }
  }

  function renderNFTPreview() {
    if (nfts.length === 1) {
      return (
        <Flex flexDirection="column" gap={1}>
          <NFTSummary launcherId={nfts[0].launcherId} />
        </Flex>
      );
    }
    return null;
  }

  return (
    <Form methods={methods} onSubmit={handleSubmit}>
      <Flex flexDirection="column" gap={3}>
        {renderNFTPreview()}
        <TextField
          name="destination"
          variant="filled"
          color="secondary"
          fullWidth
          label={<Trans>Send to Address</Trans>}
          disabled={isTransferNFTLoading}
          required
        />
        <EstimatedFee
          id="filled-secondary"
          variant="filled"
          name="fee"
          color="secondary"
          label={<Trans>Fee</Trans>}
          disabled={isTransferNFTLoading}
          txType={FeeTxType.transferNFT}
          fullWidth
        />
        <DialogActions>
          <Flex flexDirection="row" gap={3}>
            <Button onClick={handleClose} color="secondary" variant="outlined" autoFocus>
              <Trans>Close</Trans>
            </Button>
            <ButtonLoading type="submit" autoFocus color="primary" variant="contained" loading={isTransferNFTLoading}>
              <Trans>Transfer</Trans>
            </ButtonLoading>
          </Flex>
        </DialogActions>
      </Flex>
    </Form>
  );
}

/* ========================================================================== */
/*                             NFT Transfer Dialog                            */
/* ========================================================================== */

type NFTTransferDialogProps = {
  open?: boolean;
  onClose?: (value: any) => void;
  onComplete?: (result?: NFTTransferResult) => void;
  nfts: NFTInfo[];
  destination?: string;
};

export function NFTTransferDialog(props: NFTTransferDialogProps) {
  const { open, onClose, onComplete, nfts, destination, ...rest } = props;

  function handleClose() {
    if (onClose) onClose(false);
  }

  function handleCompletion(result?: NFTTransferResult) {
    if (onClose) onClose(true);
    if (onComplete) {
      onComplete(result);
    }
  }

  return (
    <Dialog
      open={open}
      onClose={handleClose}
      aria-labelledby="nft-transfer-dialog-title"
      aria-describedby="nft-transfer-dialog-description"
      maxWidth="sm"
      fullWidth
      {...rest}
    >
      <DialogTitle id="nft-transfer-dialog-title">
        <Flex flexDirection="row" gap={1}>
          <Typography variant="h6">
            <Trans>Transfer NFT</Trans>
          </Typography>
        </Flex>
      </DialogTitle>
      <DialogContent>
        <Flex flexDirection="column" gap={3}>
          <DialogContentText id="nft-transfer-dialog-description">
            {nfts.length > 1 ? (
              <Trans id="Would you like to transfer {count} NFTs to a new owner?" values={{ count: nfts.length }} />
            ) : (
              <Trans>Would you like to transfer the specified NFT to a new owner?</Trans>
            )}
          </DialogContentText>
          <NFTTransferAction nfts={nfts} destination={destination} onComplete={handleCompletion} />
        </Flex>
      </DialogContent>
    </Dialog>
  );
}
