#!/bin/bash

homedir="$(realpath "$(dirname "$0")")"
workdir=/tmp/aiobtclientrpc-qbittorrent
rpc_port=5000
source "$(dirname "$homedir")/auth"

mkdir -p "$workdir/config"

cat <<-EOF > "$workdir/qBittorrent/config/qBittorrent.conf"
[Preferences]
Bittorrent\DHT=false
Connection\UPnP=false
WebUI\Address=127.0.0.1
WebUI\Enabled=true
WebUI\Port=$rpc_port
WebUI\Username=$username
WebUI\Password_PBKDF2="@ByteArray(jY/oa1dGG36Smm6tsWCKOw==:9/f0Ll63VoNHwb4b/oS/J9zskcFUPauW1i0REUY8pChwMvbIR97RKzVpftDO5wHKERCtCU3pWxXQLcL+6i/Ndw==)"

[Network]
PortForwardingEnabled=false

[BitTorrent]
Session\DHTEnabled=false
Session\DefaultSavePath=$workdir/downloads

[LegalNotice]
Accepted=true
EOF

qbittorrent --profile="$workdir"
