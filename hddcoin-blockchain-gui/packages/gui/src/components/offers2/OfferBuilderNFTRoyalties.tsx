import type { NFTInfo } from '@hddcoin-network/api';
import { useGetCatListQuery } from '@hddcoin-network/api-react';
import {
  CopyToClipboard,
  Flex,
  FormatLargeNumber,
  Loading,
  Tooltip,
  TooltipIcon,
  Truncate,
  useCurrencyCode,
  byteToHDDcoin,
  byteToHDDcoinLocaleString,
  byteToCAT,
  byteToCATLocaleString,
} from '@hddcoin-network/core';
import { Trans } from '@lingui/macro';
import { Box, Typography } from '@mui/material';
import React, { useMemo } from 'react';
import styled from 'styled-components';

import useOfferBuilderContext from '../../hooks/useOfferBuilderContext';

const StyledTitle = styled(Box)`
  font-size: 0.625rem;
  color: rgba(255, 255, 255, 0.7);
`;

const StyledValue = styled(Box)`
  word-break: break-all;
`;

export type OfferBuilderNFTRoyaltiesProps = {
  nft?: NFTInfo;
  offering?: boolean;
};

export default function OfferBuilderNFTRoyalties(props: OfferBuilderNFTRoyaltiesProps) {
  const { nft, offering = false } = props;

  const { requestedRoyalties, offeredRoyalties, isCalculatingRoyalties } = useOfferBuilderContext();
  const { data: catList, isLoading: isLoadingCATs } = useGetCatListQuery();
  const currencyCode = useCurrencyCode();

  const isLoading = isCalculatingRoyalties || isLoadingCATs;
  const royalties = (offering ? offeredRoyalties : requestedRoyalties)?.[nft.$nftId];
  const hasRoyalties = nft.royaltyPercentage > 0;

  const rows = useMemo(
    () =>
      royalties?.map((royalty) => {
        const { address, amount, asset } = royalty;
        const assetLowerCase = asset.toLowerCase();

        if (assetLowerCase === 'hdd' || assetLowerCase === currencyCode.toUpperCase()) {
          return {
            address,
            amount: byteToHDDcoin(amount),
            amountString: byteToHDDcoinLocaleString(amount),
            symbol: currencyCode.toUpperCase(),
            displaySymbol: currencyCode.toUpperCase(),
          };
        }

        const cat = catList?.find((catItem) => catItem.assetId === asset);
        if (cat) {
          return {
            address,
            amount: byteToCAT(amount),
            amountString: byteToCATLocaleString(amount),
            symbol: cat.symbol,
            displaySymbol: cat.symbol,
          };
        }

        return {
          address,
          amount: byteToCAT(amount),
          amountString: byteToCATLocaleString(amount),
          symbol: assetLowerCase,
          displaySymbol: <Truncate>{assetLowerCase}</Truncate>,
        };
      }),
    [royalties, catList, currencyCode]
  );

  return (
    <Flex flexDirection="column" flexGrow={1} gap={2}>
      <Flex flexDirection="row" alignItems="center">
        <Typography variant="h6">Royalties</Typography>
        &nbsp;
        <TooltipIcon>
          <Trans>
            Royalties are built into the NFT, so they will automatically be accounted for when the offer is
            created/accepted.
          </Trans>
        </TooltipIcon>
      </Flex>
      {isLoading ? (
        <Loading center />
      ) : hasRoyalties ? (
        <Flex flexDirection="column" gap={1}>
          {nft.royaltyPercentage > 0 && (
            <Flex flexDirection="row" gap={1}>
              <Typography variant="body1">Percentage:</Typography>
              <Typography variant="body1">{nft.royaltyPercentage / 100.0}%</Typography>
            </Flex>
          )}
          {royalties?.length ? (
            <Flex flexDirection="column" gap={0.5}>
              {rows?.map(({ address, amount, amountString, symbol, displaySymbol }) => (
                <Tooltip
                  key={`${address}-${amountString}-${symbol}`}
                  title={
                    <Flex flexDirection="column" gap={1}>
                      <Flex flexDirection="column" gap={0}>
                        <Flex>
                          <Box flexGrow={1}>
                            <StyledTitle>
                              <Trans>Amount</Trans>
                            </StyledTitle>
                          </Box>
                        </Flex>
                        <Flex alignItems="center" gap={1}>
                          <StyledValue>{amountString}</StyledValue>
                          <CopyToClipboard value={amountString} fontSize="small" invertColor />
                        </Flex>
                      </Flex>
                      <Flex flexDirection="column" gap={0}>
                        <Flex>
                          <Box flexGrow={1}>
                            <StyledTitle>Asset ID</StyledTitle>
                          </Box>
                        </Flex>
                        <Flex alignItems="center" gap={1}>
                          <StyledValue>{symbol}</StyledValue>
                          <CopyToClipboard value={symbol} fontSize="small" invertColor />
                        </Flex>
                      </Flex>
                      <Flex flexDirection="column" gap={0}>
                        <Flex>
                          <Box flexGrow={1}>
                            <StyledTitle>Royalty Address</StyledTitle>
                          </Box>
                        </Flex>
                        <Flex alignItems="center" gap={1}>
                          <StyledValue>{address}</StyledValue>
                          <CopyToClipboard value={address} fontSize="small" invertColor />
                        </Flex>
                      </Flex>
                    </Flex>
                  }
                >
                  <Typography variant="body2" color="textSecondary" noWrap>
                    <Flex key={`${address}-${amount}`} flexDirection="row" gap={1} alignItems="baseline">
                      <Typography variant="body2" color="textSecondary">
                        <FormatLargeNumber value={amount} />
                      </Typography>
                      <Typography variant="body2" color="textSecondary" noWrap>
                        {displaySymbol}
                      </Typography>
                    </Flex>
                  </Typography>
                </Tooltip>
              ))}
            </Flex>
          ) : null}
        </Flex>
      ) : (
        <Typography variant="body1" color="textSecondary">
          <Trans>NFT has no royalties</Trans>
        </Typography>
      )}
    </Flex>
  );
}
