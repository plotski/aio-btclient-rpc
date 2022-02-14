import os
import textwrap

from .. import common

name = 'deluge'

username = 'fnark'
password = 'fnorkfnork'
rpcport = '50100'


def get_configpath(home):
    configdir = home / 'deluged'
    os.makedirs(configdir, exist_ok=True)

    with open(configdir / 'auth', 'w') as f:
        f.write(f'{username}:{password}:10\n')

    with open(configdir / 'core.conf', 'w') as f:
        f.write(textwrap.dedent(rf'''
        {{
            "file": 1,
            "format": 1
        }}{{
            "add_paused": true,
            "allow_remote": false,
            "daemon_port": {rpcport},
            "download_location": "{home}/downloads",
            "move_completed_path": "{home}/downloads",
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
            "torrentfiles_location": "{home}/torrents",
            "dht": false,
            "lsd": false,
            "natpmp": false,
            "upnp": false,
            "utpex": false
        }}
        ''').strip())
    return configdir


def run(tmp_path):
    home = common.get_home(name, tmp_path)
    configpath = get_configpath(home)
    return {
        'server_name': 'deluge',
        'server_start_cmd': f'deluged --loglevel info --do-not-daemonize --config "{configpath}"',
        'server_url': f'{username}:{password}@localhost:{rpcport}',
        'client_name': 'deluge',
    }
