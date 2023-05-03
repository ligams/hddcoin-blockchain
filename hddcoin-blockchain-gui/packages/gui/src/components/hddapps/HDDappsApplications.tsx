import React from 'react';
import styled from 'styled-components';
import { Trans } from '@lingui/macro';
// import { useHistory } from 'react-router-dom';
import { Flex, Link, CardHero } from '@hddcoin-network/core';
import { Button, Grid, Typography, Divider } from '@mui/material';
import useOpenExternal from '../../hooks/useOpenExternal';
import { HDDappsApplicationsHero as HDDappsApplicationsHeroIcon } from '../../../../icons/src';

const StyledHDDappsIcon = styled(HDDappsApplicationsHeroIcon)`
  font-size: 4rem;
`;

export default function HDDappsApplications() {
  // const history = useHistory();
  const openExternal = useOpenExternal();

  function hddAppsURLbuttonClickExplorer() {
            openExternal('https://explorer.hddcoin.org/');
        }
		
  function hddAppsURLbuttonClickRoadmap() {
            openExternal('https://graphs.hddcoin.org/');
        }

  return (
    <Grid container>
      <Grid xs={12} md={12} lg={12} item>
        <CardHero>
		
          <StyledHDDappsIcon color="primary" />
		  
		  <Typography variant="h5">
		    <Trans>
			  HDDcoin Explorer & Graphs
			</Trans>
          </Typography>
		  
		  <Divider />
		  
          <Typography variant="body1">
            <Trans>              
			{'HDDcoin Blockchain Explorer tracks chain transactions, top holders and pre-farm. HDDcoin Blockchain Graphs charts Netspace, Mempool, Price, ROI, Profitablilty, etc. More services and applications coming up. Review our Road Map for more details. '}
			  <Link
                target="_blank"
                href="https://hddcoin.org/roadmap/"
              >
                Learn more
			 </Link>
            </Trans>
          </Typography>
		  	
		  <Flex gap={1}>
            <Button
              onClick={hddAppsURLbuttonClickExplorer}
              variant="contained"
              color="primary"
              fullWidth
            >
              <Trans>Open Explorer</Trans>
            </Button>
			
            <Button
              onClick={hddAppsURLbuttonClickRoadmap}
              variant="outlined"
              color="primary"
              fullWidth
            >
              <Trans>Open Graphs</Trans>
            </Button>
          </Flex>	  
		  
        </CardHero>
      </Grid>
    </Grid>
  );
}
