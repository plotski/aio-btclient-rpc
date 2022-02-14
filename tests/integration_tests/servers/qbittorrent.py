import textwrap

from .. import common

name = 'qbittorrent'

username = 'fnark'
password = 'fnorkfnork'
rpcport = '50200'


def get_configpath(home):
    configpath = home / 'qBittorrent/config/qBittorrent.conf'
    configpath.parent.mkdir(parents=True, exist_ok=True)
    with open(configpath, 'w') as f:
        f.write(textwrap.dedent(rf'''
        [Preferences]
        Bittorrent\DHT=false
        Connection\UPnP=false
        WebUI\Address=127.0.0.1
        WebUI\Enabled=true
        WebUI\Port={rpcport}
        WebUI\Username={username}
        WebUI\Password_PBKDF2="@ByteArray(jY/oa1dGG36Smm6tsWCKOw==:9/f0Ll63VoNHwb4b/oS/J9zskcFUPauW1i0REUY8pChwMvbIR97RKzVpftDO5wHKERCtCU3pWxXQLcL+6i/Ndw==)"

        [Network]
        PortForwardingEnabled=false

        [BitTorrent]
        Session\DHTEnabled=false
        Session\PeXEnabled=false
        Session\DefaultSavePath={home}/downloads

        [LegalNotice]
        Accepted=true
        ''').strip())
    return configpath


def run(tmp_path):
    home = common.get_home(name, tmp_path)
    get_configpath(home)
    return {
        'server_name': 'qbittorrent',
        'server_start_cmd': f'qbittorrent-nox --profile="{home}"',
        'server_url': f'{username}:{password}@localhost:{rpcport}',
        'client_name': 'qbittorrent',
    }
