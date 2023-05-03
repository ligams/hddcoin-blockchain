import React from 'react';
import styled from 'styled-components';
import { Trans } from '@lingui/macro';
//import { useHistory } from 'react-router-dom';
import { useNavigate } from 'react-router-dom';
import { Flex, CardHero } from '@hddcoin-network/core';
import { Button, Grid, Typography, Divider } from '@mui/material';
import useOpenExternal from '../../hooks/useOpenExternal';
import { HDDappsUtilityHero as HDDappsUtilityHeroIcon } from '../../../../icons/src';

const StyledHDDappsIcon = styled(HDDappsUtilityHeroIcon)`
  font-size: 4rem;
`;

export default function HDDappsUtility() {
  //const history = useHistory();
  const navigate = useNavigate();
  const openExternal = useOpenExternal();

   function hddAppsOpenTerminal() {
	//history.push('/dashboard/hddapps/utilityterminal');
	navigate(`/dashboard/hddapps/hddappsutility`);
  }
  
  function hddAppsURLbuttonClickTest() {
            openExternal('https://hddcoin.org');
        }										
   function hddAppsOpenLogs() {
	//history.push('/dashboard/hddapps/utilitylogs');
	navigate(`/dashboard/hddapps/hddappsutilitylogs`);
  }
  
  return (
    <Grid container>
	  <Grid xs={12} md={12} lg={12} item>
	  
        <CardHero>		  
		  
		  <StyledHDDappsIcon color="primary" />		

          <Typography variant="h5">
            <Trans>
              HDDcoin Utility Tools
            </Trans>
          </Typography>	

		  <Divider />		  
		  
		  <Typography variant="body1">
			<Trans>
			{'The HDDcoin Terminal Utility opens directly in the GUI, enabling users to conveniently work in Command Line. The HDDcoin Client Logs Utility opens directly in the GUI, with the logs updated in real time. More HDDcoin Utility Tools are under development.'}
			</Trans>
		  </Typography>
		  
		  <Flex gap={1}>
            <Button
              //onClick={hddAppsOpenTerminal}
			  onClick={hddAppsURLbuttonClickTest}
              variant="contained"
              color="primary"
              fullWidth
            >
              <Trans>Open Terminal</Trans>
            </Button>
			
            <Button
              //onClick={hddAppsOpenLogs}
			  onClick={hddAppsURLbuttonClickTest}
              variant="outlined"
              color="primary"
              fullWidth
            >
              <Trans>Open Client Logs</Trans>
            </Button>
          </Flex>
		  
        </CardHero>
      </Grid>
    </Grid>
  );
}
