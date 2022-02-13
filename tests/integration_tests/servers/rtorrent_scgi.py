from .. import common
from . import _rtorrent_common

name = 'rtorrent_scgi'
rpcport = '50301'


def get_scgi_configpath(tmp_path):
    configpath = common.get_home(name, tmp_path) / 'rtorrent.scgi.rc'
    with open(configpath, 'w') as f:
        f.write(f'network.scgi.open_port = 127.0.0.1:{rpcport}\n')
    return configpath


def run(tmp_path):
    homepath = common.get_home(name, tmp_path)
    return {
        'server_name': name,
        'server_start_cmd': (
            'rtorrent '
            '-o system.daemon.set=true '
            f'-d "{homepath}/downloads" '
            f'-s "{homepath}" '
            f'-o "import={_rtorrent_common.get_common_configpath(name, tmp_path)}" '
            f'-o "import={get_scgi_configpath(tmp_path)}" '
        ),
        'server_stop_cmd': (
            'bash -c "'
            f'kill $(cut -d + -f 2 "{homepath}/rtorrent.lock")'
            '"'
        ),
        'server_url': f'scgi://localhost:{rpcport}',
        'client_name': 'rtorrent',
    }
