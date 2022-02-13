from .. import common
from . import _rtorrent_common

name = 'rtorrent_socket'


def get_socketpath(tmp_path):
    return common.get_home(name, tmp_path) / 'rpc.socket'


def get_socket_configpath(tmp_path):
    configpath = common.get_home(name, tmp_path) / 'rtorrent.socket.rc'
    with open(configpath, 'w') as f:
        f.write(f'network.scgi.open_local = {get_socketpath(tmp_path)}\n')
        f.write(
            'schedule2 = scgi_permission,0,0,'
            + r'"execute.nothrow=chmod,\"g+w,o=\",'
            + str(get_socketpath(tmp_path))
            + '"\n'
        )
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
            f'-o "import={get_socket_configpath(tmp_path)}" '
        ),
        'server_stop_cmd': (
            'bash -c "'
            f'kill $(cut -d + -f 2 "{homepath}/rtorrent.lock")'
            '"'
        ),
        'server_url': f'file:///{get_socketpath(tmp_path)}',
        'client_name': 'rtorrent',
    }
