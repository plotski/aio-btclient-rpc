#!/bin/bash

if [ "$1" = "--ui" ]; then
    run_ui=true
else
    run_ui=false
fi

set -o nounset   # Don't allow unset variables

homedir="$(realpath "$(dirname "$0")")"
workdir=/tmp/deluge.aiobtclientrpc
configdir="$workdir/config"
rpc_port=5000
source "$(dirname "$homedir")/auth"

mkdir -p "$workdir/config"

echo "$username:$password:10" > "$configdir/auth"

cat <<-EOF > "$configdir/core.conf"
{
    "file": 1,
    "format": 1
}{
    "add_paused": true,
    "allow_remote": false,
    "daemon_port": 5000,
    "download_location": "$workdir/downloads",
    "move_completed_path": "$workdir/downloads",
    "listen_ports": [
        54321,
        54322
    ],
    "new_release_check": false,
    "outgoing_interface": "",
    "outgoing_ports": [
        0,
        0
    ],
    "random_outgoing_ports": false,
    "random_port": false,
    "torrentfiles_location": "$workdir/torrents",
    "dht": false,
    "lsd": false,
    "natpmp": false,
    "upnp": false,
    "utpex": false
}
EOF

cat <<-EOF > "$configdir/gtk3ui.conf"
{
    "file": 1,
    "format": 1
}{
    "autoadd_queued": true,
    "autoconnect": true,
    "autoconnect_host_id": "d52e54e6ec084822bda81d626e2e70e7",
    "autostart_localhost": false,
    "check_new_releases": false,
    "close_to_tray": false,
    "enable_system_tray": false,
    "show_connection_manager_on_start": false,
    "show_new_releases": false,
    "standalone": false,
    "start_in_tray": false
}
EOF

cat <<-EOF > "$configdir/hostlist.conf"
{
    "file": 3,
    "format": 1
}{
    "hosts": [
        [
            "d52e54e6ec084822bda81d626e2e70e7",
            "127.0.0.1",
            $rpc_port,
            "$username",
            "$password"
        ]
    ]
}
EOF

if [ "$run_ui" = "true" ]; then
    deluge-gtk --config "$configdir" &
    delugegtk_pid="$!"
else
    delugegtk_pid="no_such_pid"
fi

deluged --loglevel info --do-not-daemonize --config "$configdir"

if [ -e "/proc/$delugegtk_pid" ]; then
    kill "$delugegtk_pid"
fi
