import React from 'react';
import styled from 'styled-components';
import { Trans } from '@lingui/macro';
// import { useHistory } from 'react-router-dom';
import { Flex, Link, CardHero } from '@hddcoin-network/core';
import { Button, Grid, Typography, Divider } from '@mui/material';
import useOpenExternal from '../../hooks/useOpenExternal';
import { HDDappsExchangeTradingHero as HDDappsExchangeTradingHeroIcon } from '../../../../icons/src';

const StyledHDDappsIcon = styled(HDDappsExchangeTradingHeroIcon)`
  font-size: 4rem;
`;

export default function HDDappsExchangeTrading() {
  // const history = useHistory();
  const openExternal = useOpenExternal();
		
  function hddAppsURLbuttonClickExchanges() {
            openExternal('https://hddcoin.org/exchanges/');
        }

  function hddAppsURLbuttonClickHDDswap() {
            openExternal('https://hddswap.com/');
        }

  return (
    <Grid container>
      <Grid xs={12} md={12} lg={12} item>
        <CardHero>
		
          <StyledHDDappsIcon color="primary" />
		  
		  <Typography variant="h5">
		    <Trans>
			  HDDcoin Exchange Trading
			</Trans>
          </Typography>
		  
		  <Divider />
		  
          <Typography variant="body1">
            <Trans>              
			{'HDD Cryptocurrency trading pairs is currently available on several Centralized/Decentralized Exchanges. Visit the Exchange Trading section of our Website to find out more. Please do take all necessary precautions if you choose to utilize these services. '}
			  <Link
                target="_blank"
                href="https://hddcoin.org/exchanges/"
              >
                Learn more
			 </Link>
            </Trans>
          </Typography>
		  	
		  <Flex gap={1}>
		  
            <Button
              onClick={hddAppsURLbuttonClickExchanges}
              variant="contained"
              color="primary"
              fullWidth
            >
              <Trans>Find Exchanges</Trans>
            </Button>
			
			<Button
              onClick={hddAppsURLbuttonClickHDDswap}
              variant="outlined"
              color="primary"
              fullWidth
            >
              <Trans>Try HDD Swap</Trans>
            </Button>
			
          </Flex>	  
		  
        </CardHero>
      </Grid>
    </Grid>
  );
}
