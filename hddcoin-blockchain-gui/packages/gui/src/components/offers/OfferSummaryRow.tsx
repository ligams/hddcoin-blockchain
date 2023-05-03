import { WalletType } from '@hddcoin-network/api';
import { CopyToClipboard, Flex, Link, FormatLargeNumber, TooltipIcon, byteToCATLocaleString } from '@hddcoin-network/core';
import { Plural, t, Trans } from '@lingui/macro';
import { Box, Typography } from '@mui/material';
import React from 'react';
import styled from 'styled-components';

import useAssetIdName from '../../hooks/useAssetIdName';
import useNFTMinterDID from '../../hooks/useNFTMinterDID';
import { launcherIdToNFTId } from '../../util/nfts';
import NFTSummary from '../nfts/NFTSummary';
import { formatAmountForWalletType } from './utils';

/* ========================================================================== */

const StyledTitle = styled(Box)`
  font-size: 0.625rem;
  color: rgba(255, 255, 255, 0.7);
`;

const StyledValue = styled(Box)`
  word-break: break-all;
`;

/* ========================================================================== */

type OfferByteAmountProps = {
  bytes: number;
};

function OfferByteAmount(props: OfferByteAmountProps): React.ReactElement | null {
  const { bytes } = props;

  return (
    <Flex flexDirection="row" flexGrow={1} gap={1}>
      (
      <FormatLargeNumber value={bytes} />
      <Box>
        <Plural value={bytes} one="byte" other="bytes" />
      </Box>
      )
    </Flex>
  );
}

function shouldShowByteAmount(bytes: number, byteThreshold = 1_000_000_000): boolean {
  return byteThreshold > 0 && bytes < byteThreshold;
}

/* ========================================================================== */

type OfferSummaryNFTRowProps = {
  launcherId: string;
  rowNumber?: number;
  showNFTPreview: boolean;
};

export function OfferSummaryNFTRow(props: OfferSummaryNFTRowProps): React.ReactElement {
  const { launcherId, rowNumber, showNFTPreview } = props;
  const nftId = launcherIdToNFTId(launcherId);

  const { didId: minterDID, didName: minterDIDName, isLoading: isLoadingMinterDID } = useNFTMinterDID(nftId);

  return (
    <Flex flexDirection="column" gap={2}>
      <Flex flexDirection="column" gap={1}>
        <Box>
          {!showNFTPreview && (
            <Flex alignItems="center" gap={1}>
              <Typography variant="body1" component="div">
                <Flex flexDirection="row" alignItems="center" gap={1}>
                  {rowNumber !== undefined && (
                    <Typography
                      variant="body1"
                      color="secondary"
                      style={{ fontWeight: 'bold' }}
                    >{`${rowNumber})`}</Typography>
                  )}
                  <Typography>{nftId}</Typography>
                </Flex>
              </Typography>
              {launcherId !== undefined && (
                <TooltipIcon>
                  <Flex flexDirection="column" gap={1}>
                    <Flex flexDirection="column" gap={0}>
                      <Flex>
                        <Box flexGrow={1}>
                          <StyledTitle>NFT ID</StyledTitle>
                        </Box>
                      </Flex>
                      <Flex alignItems="center" gap={1}>
                        <StyledValue>{nftId}</StyledValue>
                        <CopyToClipboard value={nftId} fontSize="small" />
                      </Flex>
                    </Flex>
                    <Flex flexDirection="column" gap={0}>
                      <Flex>
                        <Box flexGrow={1}>
                          <StyledTitle>Launcher ID</StyledTitle>
                        </Box>
                      </Flex>
                      <Flex alignItems="center" gap={1}>
                        <StyledValue>{launcherId}</StyledValue>
                        <CopyToClipboard value={launcherId} fontSize="small" />
                      </Flex>
                    </Flex>
                  </Flex>
                </TooltipIcon>
              )}
            </Flex>
          )}
        </Box>
        {!isLoadingMinterDID && (
          <Typography variant="body2" color="textSecondary">
            <Trans>Minter:</Trans> {minterDIDName ?? minterDID}
          </Typography>
        )}
      </Flex>
      {showNFTPreview && <NFTSummary launcherId={launcherId} />}
    </Flex>
  );
}

/* ========================================================================== */

type OfferSummaryTokenRowProps = {
  assetId: string;
  amount: number;
  rowNumber?: number;
  overrideNFTSellerAmount?: number;
};

export function OfferSummaryTokenRow(props: OfferSummaryTokenRowProps): React.ReactElement {
  const { assetId, amount: originalAmount, rowNumber, overrideNFTSellerAmount } = props;
  const { lookupByAssetId } = useAssetIdName();
  const assetIdInfo = lookupByAssetId(assetId);
  const amount = overrideNFTSellerAmount ?? originalAmount;
  const displayAmount = assetIdInfo
    ? formatAmountForWalletType(amount as number, assetIdInfo.walletType)
    : byteToCATLocaleString(amount);
  const displayName = assetIdInfo?.displayName ?? t`Unknown CAT`;
  const tooltipDisplayName = assetIdInfo?.name ?? t`Unknown CAT`;
  const showByteAmount = assetIdInfo?.walletType === WalletType.STANDARD_WALLET && shouldShowByteAmount(amount);

  return (
    <Flex alignItems="center" gap={1}>
      <Typography variant="body1" component="div">
        <Flex flexDirection="row" alignItems="center" gap={1}>
          {rowNumber !== undefined && (
            <Typography variant="body1" color="secondary" style={{ fontWeight: 'bold' }}>{`${rowNumber})`}</Typography>
          )}
          <Typography>
            {displayAmount} {displayName}
          </Typography>
        </Flex>
      </Typography>
      {showByteAmount && (
        <Typography variant="body1" color="textSecondary" component="div">
          <OfferByteAmount bytes={amount} />
        </Typography>
      )}
      <TooltipIcon>
        <Flex flexDirection="column" gap={1}>
          <Flex flexDirection="column" gap={0}>
            <Flex>
              <Box flexGrow={1}>
                <StyledTitle>Name</StyledTitle>
              </Box>
              {(!assetIdInfo || assetIdInfo?.walletType === WalletType.CAT) && (
                {/* <Link href={`https://www.taildatabase.com/tail/${assetId.toLowerCase()}`} target="_blank">
                  <Trans>Search on Tail Database</Trans>
                </Link> */}
              )}
            </Flex>

            <StyledValue>{tooltipDisplayName}</StyledValue>
          </Flex>
          {(!assetIdInfo || assetIdInfo?.walletType === WalletType.CAT) && (
            <Flex flexDirection="column" gap={0}>
              <StyledTitle>Asset ID</StyledTitle>
              <Flex alignItems="center" gap={1}>
                <StyledValue>{assetId.toLowerCase()}</StyledValue>
                <CopyToClipboard value={assetId.toLowerCase()} fontSize="small" />
              </Flex>
            </Flex>
          )}
        </Flex>
      </TooltipIcon>
    </Flex>
  );
}
