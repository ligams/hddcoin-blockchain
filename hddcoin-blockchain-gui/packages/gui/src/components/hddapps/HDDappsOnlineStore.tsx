import React from 'react';
import styled from 'styled-components';
import { Trans } from '@lingui/macro';
// import { useHistory } from 'react-router-dom';
import { Flex, Link, CardHero } from '@hddcoin-network/core';
import { Button, Grid, Typography, Divider } from '@mui/material';
import useOpenExternal from '../../hooks/useOpenExternal';
import { HDDappsOnlineStoreHero as HDDappsOnlineStoreHeroIcon } from '../../../../icons/src';

const StyledHDDappsIcon = styled(HDDappsOnlineStoreHeroIcon)`
  font-size: 4rem;
`;

export default function HDDappsOnlineStore() {
  // const history = useHistory();
  const openExternal = useOpenExternal();  
  
  function hddAppsURLbuttonClickStore() {
            openExternal('https://store.hddcoin.org/');
        }

  return (
    <Grid container>
      <Grid xs={12} md={12} lg={12} item>
        <CardHero>
		
          <StyledHDDappsIcon color="primary" />		

          <Typography variant="h5">
            <Trans>
              HDDcoin Online Store
            </Trans>
          </Typography>	

		  <Divider />		  
		  
		  <Typography variant="body1">
			<Trans>
			{'Many products on the HDDcoin Online Store are currently ON SALE for a limited time. Go grab your favorite items quickly while these offers last. The default Store payment method is HDD. PayPal and all major Credit/Debit Cards also accepted. '}
			  <Link
                target="_blank"
                href="https://store.hddcoin.org/"
              >
                Learn more
			  </Link>
			</Trans>
		  </Typography>
		  		  		  
		  <Flex gap={1}>
            <Button
              onClick={hddAppsURLbuttonClickStore}
              variant="contained"
              color="primary"
              //fullWidth
            >
              <Trans>Visit Online Store</Trans>
            </Button>
		  </Flex>
		  
        </CardHero>
      </Grid>
    </Grid>
  );
}
