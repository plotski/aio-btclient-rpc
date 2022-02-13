from .. import common

name = 'transmission'

username = 'fnark'
password = 'fnorkfnork'
rpcport = '50400'


def run(tmp_path):
    home = common.get_home(name, tmp_path)
    return {
        'server_name': 'transmission',
        'server_start_cmd': (
            'transmission-daemon --log-debug --foreground '
            f'--auth --username "{username}" --password "{password}" '
            f'--config-dir "{home}/config/" '
            f'--download-dir "{home}/downloads/" '
            f'--rpc-bind-address 127.0.0.1 --port "{rpcport}" '
            '--peerport 54321 --no-portmap --no-dht --paused'
        ),
        'server_url': f'http://{username}:{password}@localhost:{rpcport}/transmission/rpc',
        'client_name': 'transmission',
    }
