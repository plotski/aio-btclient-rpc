#!/bin/bash

set -o nounset   # Don't allow unset variables
set -o errexit   # Exit if any command fails

homedir="$(realpath "$(dirname "$0")")"
workdir=/tmp/aiobtclientrpc-transmission
rpc_port=5000
source "$(dirname "$homedir")/auth"

mkdir -p "$workdir"

transmission-daemon --log-debug --foreground \
                    --auth --username "$username" --password "$password" \
                    --config-dir "$workdir/config/" \
                    --download-dir "$workdir/downloads/" \
                    --rpc-bind-address 127.0.0.1 --port "$rpc_port" \
                    --peerport 54321 --no-portmap --no-dht \
                    --paused
