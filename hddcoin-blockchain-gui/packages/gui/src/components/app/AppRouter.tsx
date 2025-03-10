import { SelectKey, LayoutHero, LayoutDashboard, Mode, useMode } from '@hddcoin-network/core';
import { WalletAdd, WalletImport, Wallets } from '@hddcoin-network/wallets';
import React from 'react';
import { HashRouter, Routes, Route, Navigate } from 'react-router-dom';

import Block from '../block/Block';
import DashboardSideBar from '../dashboard/DashboardSideBar';
import Farm from '../farm/Farm';
import FullNode from '../fullNode/FullNode';
import NFTs from '../nfts/NFTs';
import { CreateOffer } from '../offers/OfferManager';
import Plot from '../plot/Plot';
import Pool from '../pool/Pool';
import HDDapps from '../hddapps/HDDapps';
import Settings from '../settings/Settings';
import SettingsPanel from '../settings/SettingsPanel';
import VCs from '../vcs/VCs';
import AppProviders from './AppProviders';
import AppStatusHeader from './AppStatusHeader';

export default function AppRouter() {
  const [mode] = useMode();

  return (
    <HashRouter>
      <Routes>
        <Route path="/" element={<AppProviders outlet />}>
          <Route element={<LayoutHero settings={<SettingsPanel />} outlet />}>
            <Route index element={<SelectKey />} />
          </Route>
          <Route element={<LayoutHero settings={<SettingsPanel />} back outlet />}>
            <Route path="wallet/add" element={<WalletAdd />} />
            <Route path="wallet/import" element={<WalletImport />} />
          </Route>
          {mode === Mode.WALLET ? (
            <Route
              element={
                <LayoutDashboard
                  settings={<SettingsPanel />}
                  sidebar={<DashboardSideBar simple />}
                  actions={<AppStatusHeader />}
                  outlet
                />
              }
            >
              <Route path="dashboard" element={<Navigate to="wallets" />} />
              <Route path="dashboard/wallets/*" element={<Wallets />} />
              <Route path="dashboard/offers/*" element={<CreateOffer />} />
              <Route path="dashboard/nfts/*" element={<NFTs />} />
			  <Route path="dashboard/hddapps/*" element={<HDDapps />} />
              <Route path="dashboard/vc/*" element={<VCs />} />
              <Route path="dashboard/*" element={<Navigate to="wallets" />} />
              <Route path="dashboard/settings/*" element={<Settings />} />
            </Route>
          ) : (
            <Route
              element={
                <LayoutDashboard
                  settings={<SettingsPanel />}
                  sidebar={<DashboardSideBar />}
                  actions={<AppStatusHeader />}
                  outlet
                />
              }
            >
              <Route path="dashboard" element={<FullNode />} />
              <Route path="dashboard/block/:headerHash" element={<Block />} />
              <Route path="dashboard/wallets/*" element={<Wallets />} />
              <Route path="dashboard/offers/*" element={<CreateOffer />} />
              <Route path="dashboard/nfts/*" element={<NFTs />} />
              <Route path="dashboard/vc/*" element={<VCs />} />
              <Route path="dashboard/settings/*" element={<Settings />} />
              <Route path="dashboard/plot/*" element={<Plot />} />
              <Route path="dashboard/farm/*" element={<Farm />} />
              <Route path="dashboard/pool/*" element={<Pool />} />
			  <Route path="dashboard/hddapps/*" element={<HDDapps />} />
            </Route>
          )}
        </Route>
        <Route path="*" element={<Navigate to="/" />} />
      </Routes>
    </HashRouter>
  );
}
