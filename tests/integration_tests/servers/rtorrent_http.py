import shlex
import subprocess
import textwrap

from .. import common
from . import _rtorrent_common, rtorrent_socket

name = 'rtorrent_http'

username = 'fnark'
password = 'fnorkfnork'
# username = ''
# password = ''
httpport = '50302'


def get_http_home(tmp_path):
    return common.get_home(name, tmp_path) / 'nginx'


def get_http_pidfile_path(tmp_path):
    return get_http_home(tmp_path) / 'nginx.pid'


def run_http_server(tmp_path):
    http_home = get_http_home(tmp_path)
    http_home.mkdir(parents=True, exist_ok=True)
    nginx_configpath = http_home / 'nginx.conf'
    scgi_params_path = http_home / 'scgi_params'
    htpasswd_path = http_home / 'htpasswd'
    socketfile = rtorrent_socket.get_socketpath(tmp_path)
    stdouterr_path = http_home / 'stdouterr'

    if username:
        proc = subprocess.run(
            shlex.split(f'htpasswd -i -c "{htpasswd_path}" "{username}"'),
            text=True,
            input=password,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT
        )
        assert htpasswd_path.exists(), proc.stdout

        auth_config = textwrap.dedent(rf'''
            auth_basic "Restricted";
            auth_basic_user_file {htpasswd_path};
        ''').strip()

    else:
        auth_config = ''

    with open(nginx_configpath, 'w') as f:
        f.write(textwrap.dedent(rf'''
        error_log {http_home}/nginx.error.log;
        pid {get_http_pidfile_path(tmp_path)};

        events {{
            worker_connections 768;
        }}

        http {{
            server {{
                listen 127.0.0.1:{httpport};
                error_log {http_home}/nginx.error.log;
                access_log {http_home}/nginx.access.log;

                {auth_config}

                location /RPC2 {{
                   include {scgi_params_path};
                   scgi_pass unix:{socketfile};
                }}
            }}
        }}
        ''').strip())

    with open(scgi_params_path, 'w') as f:
        f.write(textwrap.dedent(r'''
        scgi_param  REQUEST_METHOD     $request_method;
        scgi_param  REQUEST_URI        $request_uri;
        scgi_param  QUERY_STRING       $query_string;
        scgi_param  CONTENT_TYPE       $content_type;

        scgi_param  DOCUMENT_URI       $document_uri;
        scgi_param  DOCUMENT_ROOT      $document_root;
        scgi_param  SCGI               1;
        scgi_param  SERVER_PROTOCOL    $server_protocol;
        scgi_param  REQUEST_SCHEME     $scheme;
        scgi_param  HTTPS              $https if_not_empty;

        scgi_param  REMOTE_ADDR        $remote_addr;
        scgi_param  REMOTE_PORT        $remote_port;
        scgi_param  SERVER_PORT        $server_port;
        scgi_param  SERVER_NAME        $server_name;
        ''').strip())

    subprocess.Popen(
        ('/usr/sbin/nginx', '-c', nginx_configpath),
        shell=False,
        stdout=open(stdouterr_path, 'w'),
        stderr=subprocess.STDOUT,
    )


def run(tmp_path):
    home = common.get_home(name, tmp_path)

    run_http_server(tmp_path)

    if username:
        server_url = f'http://{username}:{password}@localhost:{httpport}'
    else:
        server_url = f'http://localhost:{httpport}'

    return {
        'server_name': name,
        'server_start_cmd': (
            'rtorrent '
            '-o system.daemon.set=true '
            f'-d "{home}/downloads" '
            f'-s "{home}" '
            f'-o "import={_rtorrent_common.get_common_configpath(name, tmp_path)}" '
            f'-o "import={rtorrent_socket.get_socket_configpath(tmp_path)}" '
        ),
        'server_stop_cmd': (
            'bash -c "'
            f'kill $(cut -d + -f 2 "{home}/rtorrent.lock") '
            '; '
            f'kill $(cat "{get_http_pidfile_path(tmp_path)}") '
            '"'
        ),
        'server_url': server_url,
        'client_name': 'rtorrent',
    }
