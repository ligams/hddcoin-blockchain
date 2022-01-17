import React from 'react';
import styled from 'styled-components';
import { Trans } from '@lingui/macro';
import { useHistory } from 'react-router-dom';
import { Flex } from '@hddcoin/core';
import { Button, Grid, Typography, Link, Divider } from '@material-ui/core';
import { CardHero } from '@hddcoin/core';
import { HDDappsApplicationsHero as HDDappsApplicationsHeroIcon } from '@hddcoin/icons';

const StyledHDDappsIcon = styled(HDDappsApplicationsHeroIcon)`
  font-size: 4rem;
`;

export default function HDDappsApplications() {
  const history = useHistory();

  function hddAppsOpenExplorer() {
            window.open(
              "https://explorer.hddcoin.org", "_blank");
        }
		
  function hddAppsOpenRoadMap() {
            window.open(
              "https://hddcoin.org/roadmap", "_blank");
        }


  return (
    <Grid container>
      <Grid xs={12} md={12} lg={12} item>
        <CardHero>
		
          <StyledHDDappsIcon color="primary" />
		  
		  <Typography variant="h5">
		    <Trans>
			  HDDcoin Explorer & Roadmap
			</Trans>
          </Typography>
		  
		  <Divider />
		  
          <Typography variant="body1">
            <Trans>              
              Use the HDDcoin Blockchain Explorer to review activities on the blockchain. HDDcoin is working on other projects 
			  including applications and games that will run on the HDDcoin blockchain. Check out our Road Map for more details.     
			  <Link
                target="_blank"
                href="https://hddcoin.org/roadmap"
              >
                Learn more
			 </Link>
            </Trans>
          </Typography>
		  	
		  <Flex gap={1}>
            <Button
              onClick={hddAppsOpenExplorer}
              variant="contained"
              color="primary"
              fullWidth
            >
              <Trans>Open Explorer</Trans>
            </Button>
			
            <Button
              onClick={hddAppsOpenRoadMap}
              variant="outlined"
              color="primary"
              fullWidth
            >
              <Trans>View Roadmap</Trans>
            </Button>
          </Flex>	  
		  
        </CardHero>
      </Grid>
    </Grid>
  );
}
