#!/usr/bin/env bash
# Post install script for the UI .rpm to place symlinks in places to allow the CLI to work similarly in both versions

set -e

ln -s /opt/hddcoin/resources/app.asar.unpacked/daemon/hddcoin /usr/bin/hddcoin || true
ln -s /opt/hddcoin/hddcoin-blockchain /usr/bin/hddcoin-blockchain || true
