import { Flex, LayoutDashboardSub } from '@hddcoin-network/core';
import React from 'react';
import { Route, Routes } from 'react-router-dom';
import { Trans } from '@lingui/macro';
import { Grid, Typography } from '@mui/material';

/* import LayoutMain from '../../../../core/src/components/LayoutMain'; */
import HDDappsHODL from './HDDappsHODL';
/* import HDDappsHODLTerminal from './HDDappsHODLTerminal'; */
import HDDappsUtility from './HDDappsUtility';
/* import HDDappsUtilityTerminal from './HDDappsUtilityTerminal'; */
/* import HDDappsUtilityLogs from './HDDappsUtilityLogs'; */

import HDDappsOnlineStore from './HDDappsOnlineStore';
import HDDappsNFTMarketPlace from './HDDappsNFTMarketPlace';
import HDDappsExchangeTrading from './HDDappsExchangeTrading';
import HDDappsApplications from './HDDappsApplications';
import HDDappsThirdPartyHDDBet from './HDDappsThirdPartyHDDBet';
import HDDappsThirdPartyOtherApps from './HDDappsThirdPartyOtherApps';
import { HDDappsHeaderTarget } from './HDDappsHeader';
import { HDDappsHeaderSource } from './HDDappsHeader';

export default function HDDapps() {
  return (
    <LayoutDashboardSub>
      <Flex flexDirection="column" gap={2}>
        <Typography variant="h5" gutterBottom>
          <Trans>HDDcoin Applications and Utilities</Trans>
        </Typography>
        <Flex flexDirection="column" gap={1} alignItems="center">
          <Routes>
            <Route index element={
              <div>
                <Grid container spacing={4} alignItems="stretch">
					<Grid item xs={12} sm={6} md={6}>
					  <HDDappsHODL headerTag={HDDappsHeaderSource} />
					</Grid> 
                  <Grid item xs={12} sm={6} md={6}>
                    <HDDappsOnlineStore headerTag={HDDappsHeaderSource} />
                  </Grid>
                  <Grid item xs={12} sm={6} md={6}>
                    <HDDappsNFTMarketPlace headerTag={HDDappsHeaderSource} />
                  </Grid>
                  <Grid item xs={12} sm={6} md={6}>
                    <HDDappsExchangeTrading headerTag={HDDappsHeaderSource} />
                  </Grid>
				  {/*
				  <Grid item xs={12} sm={6} md={6}>
					  <HDDappsUtility headerTag={HDDappsHeaderSource} />
				  </Grid> 
				  */}
                  <Grid item xs={12} sm={6} md={6}>
                    <HDDappsApplications headerTag={HDDappsHeaderSource} />
                  </Grid>
                  <Grid item xs={12} sm={6} md={6}>
					<HDDappsThirdPartyOtherApps headerTag={HDDappsHeaderSource} />
                  </Grid>
				  {/*
                  <Grid item xs={12} sm={6} md={6}>
					<HDDappsThirdPartyHDDBet headerTag={HDDappsHeaderSource} />
                  </Grid>
				  */}
                </Grid>
              </div>
			}/>
            {/* 
			  <Route path="hodlterminal" element={<HDDappsHODLTerminal />} />
			  <Route "utilityterminal" element={<HDDappsUtilityTerminal />} />
			  <Route path="utilitylogs" element={<HDDappsUtilityLogs />} /> 
			*/}
          </Routes>
        </Flex>
      </Flex>
    </LayoutDashboardSub>
  );
}
