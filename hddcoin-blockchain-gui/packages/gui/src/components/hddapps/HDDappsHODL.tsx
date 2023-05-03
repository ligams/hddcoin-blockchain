import React from 'react';
import styled from 'styled-components';
import { Trans } from '@lingui/macro';
// import { useHistory } from 'react-router-dom';
import { useNavigate } from 'react-router-dom';
import { Flex, Link, CardHero } from '@hddcoin-network/core';
import { Button, Grid, Typography, Divider } from '@mui/material';
import useOpenExternal from '../../hooks/useOpenExternal';
import { HDDappsHODLHero as HDDappsHODLHeroIcon } from '../../../../icons/src';

const StyledHDDappsIcon = styled(HDDappsHODLHeroIcon)`
  font-size: 4rem;
`;

export default function HDDappsHODL() {
  //const history = useHistory();
  const navigate = useNavigate();
  const openExternal = useOpenExternal();
  
   function hddAppsOpenHODLTerminal() {
    //history.push('/dashboard/hodlterminal/HODLterminal');
	// history.push('/dashboard/hddapps/hodlterminal');
	navigate(`/dashboard/hddapps/hddappshodlterminal`);
	//navigate(`/dashboard/hodlterminal/HODLterminal`);
  }

  function hddAppsURLbuttonClickHODL() {
            openExternal('https://hddcoin.org/hodl');
        }
        
  function hddAppsURLbuttonClickAction() {
            openExternal('https://hddcoin.org');
        }
  
  return (
    <Grid container>
	  <Grid xs={12} md={12} lg={12} item>
	  
        <CardHero>		  
		  
		  <StyledHDDappsIcon color="primary" />		

          <Typography variant="h5">
            <Trans>
              HDDcoin HODL Program
            </Trans>
          </Typography>	

		  <Divider />		  
		  
		  <Typography variant="body1">		
			
			<Trans>
			  {'HDDcoin HODL offers coin holders the opportunity to earn rewards on HDD locked in a contract for specific durations. Contracts are secured and managed 100% on-chain using a Smart Coin coded in CLVM (the on-chain programming language used by HDDcoin). '}
			  <Link
                target="_blank"
                href="https://hddcoin.org/hodl/"
			  >
				Learn more
			  </Link>
			</Trans>
			
		  </Typography>
		  
		  <Flex gap={1}>
		    {/*
            <Button
              //onClick={hddAppsOpenHODLTerminal}
			  onClick={hddAppsURLbuttonClickAction}
              variant="contained"
              color="primary"
              fullWidth
            >
              <Trans>Open HODL Terminal</Trans>
            </Button>
			*/}
            <Button
              onClick={hddAppsURLbuttonClickHODL}
              variant="contained"
              color="primary"
              //fullWidth
            >
              <Trans>Learn about HODL</Trans>
            </Button>
			
          </Flex>
		  
        </CardHero>
      </Grid>
    </Grid>
  );
}