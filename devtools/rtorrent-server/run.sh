#!/bin/bash

set -o nounset   # Don't allow unset variables
set -o errexit   # Exit if any command fails

mode="$1"

homedir="$(realpath "$(dirname "$0")")"
workdir=/tmp/aiobtclientrpc-rtorrent
socketfile="$workdir/rpc.socket"
configfile="$workdir/rtorrent.connection.rc"

scgi_port=5000
http_port=5001

nginxdir="$(realpath "$(dirname "$0")")/nginx"
nginxpidfile="$workdir/nginx.pid"
nginxconfigfile="$workdir/nginx.conf"
htpasswdfile="$workdir/htpasswd"

source "$(dirname "$homedir")/auth"

mkdir -p "$workdir" "$nginxdir"

rm -f "$configfile"

function config_socket() {
    echo "network.scgi.open_local = $socketfile" >> "$configfile"
    echo 'schedule2 = scgi_permission,0,0,"execute.nothrow=chmod,\"go-rwx,o=\",'"$socketfile"'"' >> "$configfile"
}

function config_scgi_server() {
    echo "network.scgi.open_port = 127.0.0.1:$scgi_port" >> "$configfile"
}

function kill_http_server() {
    if [[ -e "$nginxpidfile" ]]; then
        kill "$(cat "$nginxpidfile")"
    fi
}

function run_http_server() {
    if [ ! -z "$username" ]; then
        echo "$password" | htpasswd -i -c "$htpasswdfile" "$username"
    else
        rm -f "$htpasswdfile"
    fi

    cat <<-EOF > "$nginxconfigfile"
	error_log ${workdir}/nginx.error.log;
	pid ${nginxpidfile};

	events {
	    worker_connections 768;
	}

	http {
	    server {
	        listen 127.0.0.1:${http_port};
	        error_log ${workdir}/nginx.error.log;
	        access_log ${workdir}/nginx.access.log;

	        auth_basic "Restricted";
	        auth_basic_user_file ${htpasswdfile};

	        location /RPC2 {
	           include $nginxdir/scgi_params;
	           scgi_pass unix:${socketfile};
	        }
	    }
	}
	EOF

    /usr/sbin/nginx -c "$nginxconfigfile"
    trap kill_http_server EXIT

    echo "### NGINX CONFIG"
    cat $nginxconfigfile
}



if [[ "$mode" = "socket" ]]; then
    echo "###### SOCKET MODE"
    config_socket
elif [[ "$mode" = "scgi" ]]; then
    echo "###### SCGI MODE"
    config_scgi_server
elif [[ "$mode" = "http" ]]; then
    echo "###### HTTP MODE"
    config_socket
    run_http_server
else
    echo "Unknown mode: $mode" >&2
fi

echo "### RTORRENT CONFIG"
cat $configfile

rtorrent -d "$workdir/downloads" -s "$workdir" -o "import=$configfile" -o "import=$homedir/rtorrent.rc"
