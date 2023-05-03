import React from 'react';
import styled from 'styled-components';
import { Trans } from '@lingui/macro';
// import { useHistory } from 'react-router-dom';
import { Flex, Link, CardHero } from '@hddcoin-network/core';
import { Button, Grid, Typography, Divider } from '@mui/material';
import useOpenExternal from '../../hooks/useOpenExternal';
import { HDDappsThirdPartyOtherAppsHero as HDDappsThirdPartyOtherAppsHeroIcon } from '../../../../icons/src';

const StyledHDDappsIcon = styled(HDDappsThirdPartyOtherAppsHeroIcon)`
  font-size: 4rem;
`;

export default function HDDappsThirdPartyOtherApps() {
  // const history = useHistory();
  const openExternal = useOpenExternal();
    
  function hddAppsURLbuttonClickThirdPartyDApps() {
            openExternal('https://hddcoin.org/dapps/');
        }

  function hddAppsURLbuttonClickThirdPartyBet() {
            openExternal('https://hddcoin.bet/');
        }
		
  return (
    <Grid container>
      <Grid xs={12} md={12} lg={12} item>
        <CardHero>
		
          <StyledHDDappsIcon color="primary" />
		  
		  <Typography variant="h5">
		    <Trans>
			  Third Party DApps
			</Trans>
          </Typography>
		  
		  <Divider />
		  
          <Typography variant="body1">
            <Trans>              
						
			{'The HDDcoin platform is available for building Decentralized Applications, and developers in the community are working on Projects which run on the HDDcoin blockchain. Please note these are non-affiliated, third-party application, services and utilities. '}
			
			  <Link
                target="_blank"
                href="https://hddcoin.org/dapps/"
              >
                Learn more
			 </Link>
			
            </Trans>
          </Typography>
			
		  <Flex gap={1}>
            <Button
              onClick={hddAppsURLbuttonClickThirdPartyDApps}
              variant="contained"
              color="primary"
              fullWidth
            >
              <Trans>Find HDDcoin DApps</Trans>
            </Button>
			
            <Button
              onClick={hddAppsURLbuttonClickThirdPartyBet}
              variant="outlined"
              color="primary"
              fullWidth
            >
              <Trans>Try Bet on HDD</Trans>
            </Button>
          </Flex>	    
		  
        </CardHero>
      </Grid>
    </Grid>
  );
}
