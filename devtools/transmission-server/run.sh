#!/bin/bash

if [ "$1" = "--ui" ]; then
    run_ui=true
else
    run_ui=false
fi

homedir="$(realpath "$(dirname "$0")")"
workdir=/tmp/transmission.aiobtclientrpc
rpc_port=5000
source "$(dirname "$homedir")/auth"

mkdir -p "$workdir"


function run_transmission_daemon() {
    transmission-daemon \
        "$@" \
        --pid-file "$workdir/pid" \
        --config-dir "$workdir/config/" \
        --download-dir "$workdir/downloads/" \
        --auth --username "$username" --password "$password" \
        --rpc-bind-address 127.0.0.1 --port "$rpc_port" \
        --peerport 54321 --no-portmap --no-dht \
        --paused
}


if [ "$run_ui" = "true" ]; then
    run_transmission_daemon &
    stig \
        --no-rc-file \
        set connect.url fnark:fnorkfnork@localhost:5000 \
        and set tui.poll 1 \
        and tab -C \
        and ls
    kill "$(cat "$workdir/pid")"
else
    run_transmission_daemon --log-debug --foreground
fi
