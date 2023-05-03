#!/usr/bin/env bash
# Pre remove script for the UI .deb to clean up the symlinks from the installer

set -e

unlink /usr/bin/hddcoin || true
unlink /usr/bin/hddcoin-blockchain || true
