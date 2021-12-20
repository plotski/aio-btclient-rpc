import enum
import os
import re
import urllib.parse

from . import __project_name__, __version__, _errors

import logging  # isort:skip
_log = logging.getLogger(__name__)


DEFAULT_TIMEOUT = 5.0
"""Default request timeout in seconds"""


class ConnectionStatus(enum.Enum):
    """Current state of the client connection"""
    connecting = 'connecting'
    connected = 'connected'
    disconnected = 'disconnected'


def cached_property(fget):
    """Property that is replaces itself with its value on first access"""
    class _cached_property():
        def __init__(self, fget):
            self._fget = fget
            self._property_name = fget.__name__

        def __get__(self, obj, cls):
            value = self._fget(obj)
            setattr(obj, self._property_name, value)
            return value

    return _cached_property(fget)


class URL:
    """
    URL that is used to locate the RPC interface

    This implementation attempts to parse URLs more intuitively instead of
    following any specs. For example ``"localhost:1234"`` is interpreted as
    ``host=localhost, port=1234`` and not ``scheme=localhost, path=1234``.

    :param str default_scheme: Scheme to use when the URL doesn't provide one
        and a host/IP is detected (i.e. it's not a file:// URL)
    :param callable on_change: Callback that is called with no arguments when
        any property is modified

    :raise ValueError: if `url` is invalid
    """

    def __init__(self, url, default_scheme='http', on_change=None):
        url = str(url).strip()
        if not re.search(r'^[a-zA-Z0-9]+://', url):
            # Try to autodetect scheme
            if re.search(
                (
                    r'^(?:[a-zA-Z0-9\.]*:[a-zA-Z0-9\.]*@|)'  # Username and password
                    r'[a-zA-Z0-9\.]+:\d+(?:/|$)'             # Host/IP and port
                ),
                url,
            ):
                # Looks like hostname/IP and port
                url = str(default_scheme) + '://' + url
            else:
                # Looks like file path
                url = 'file://' + url

        if url.startswith('file://'):
            # urllib.parse.ursplit() interprets things like port and
            # username/password for file:// URLs
            parsed = {
                'scheme': 'file',
                'hostname': None,
                'port': None,
                'path': url.split('://', maxsplit=1)[1],
                'username': None,
                'password': None,
            }

        else:
            split_result = urllib.parse.urlsplit(url)

            # Translate ValueError from invalid port
            try:
                split_result.port
            except ValueError:
                raise _errors.ValueError('Invalid port')

            # Convert SplitResult to dictionary to make it mutable
            parsed = {
                key: str(getattr(split_result, key)) if getattr(split_result, key) else None
                for key in ('scheme', 'hostname', 'port', 'path', 'username', 'password')
            }

            # Normalize non-file path (normalizing file path can change its
            # meaning if it contains a symbolic link)
            if parsed['path']:
                parsed['path'] = '/' + os.path.normpath(parsed['path']).lstrip('/')

        # Don't call callback during initialization
        self._on_change = None
        self.scheme = parsed['scheme']
        self.host = parsed['hostname']
        self.port = parsed['port']
        self.path = parsed['path']
        self.username = parsed['username']
        self.password = parsed['password']
        self._on_change = on_change

    @property
    def scheme(self):
        """Scheme (e.g. ``"http"`` or ``"file"``)"""
        return self._scheme

    @scheme.setter
    def scheme(self, scheme):
        self._scheme = str(scheme).lower()
        if self._on_change:
            self._on_change()

    @property
    def host(self):
        """Host name or IP address or `None`"""
        return self._host

    @host.setter
    def host(self, host):
        self._host = str(host) if host else None
        if self._on_change:
            self._on_change()

    @property
    def port(self):
        """Port number or `None`"""
        return self._port

    @port.setter
    def port(self, port):
        if not port:
            self._port = None
        else:
            try:
                port = int(port)
            except (ValueError, TypeError):
                raise _errors.ValueError('Invalid port')
            else:
                if not 1 <= port <= 65535:
                    raise _errors.ValueError('Invalid port')
                else:
                    self._port = str(port)
        if self._on_change:
            self._on_change()

    @property
    def path(self):
        """File system path or request path or None"""
        return self._path

    @path.setter
    def path(self, path):
        self._path = str(path) if path else None
        if self._on_change:
            self._on_change()

    @property
    def username(self):
        """Username for authentication"""
        return self._username

    @username.setter
    def username(self, username):
        self._username = str(username) if username else None
        if self._on_change:
            self._on_change()

    @property
    def password(self):
        """Password for authentication"""
        return self._password

    @password.setter
    def password(self, password):
        self._password = str(password) if password else None
        if self._on_change:
            self._on_change()

    @property
    def without_auth(self):
        """URL string without username and password"""
        parts = [self.scheme + '://']
        if self.host:
            parts.append(self.host)
        if self.port:
            parts.append(':' + self.port)
        if self.path:
            parts.append(self.path)
        return ''.join(parts)

    @property
    def with_auth(self):
        """URL string with username and password"""
        parts = [self.scheme + '://']
        if self.username and self.password:
            parts.append(f'{self.username}:{self.password}@')
        elif self.username:
            parts.append(self.username + ':@')
        elif self.password:
            parts.append(':' + self.password + '@')
        if self.host:
            parts.append(self.host)
        if self.port:
            parts.append(':' + self.port)
        if self.path:
            parts.append(self.path)
        return ''.join(parts)

    def __str__(self):
        return self.without_auth

    def __repr__(self):
        text = f'{type(self).__name__}({str(self)!r}'
        if self._on_change:
            text += f', on_change={self._on_change!r}'
        text += ')'
        return text


def create_http_client(*, auth=(None, None), proxy_url=None):
    """
    Return :class:`httpx.AsyncClient` instance

    :param auth: Basic auth credentials as `(username, password)` tuple; if
        either value is falsy, don't do authentication
    :param proxy_url: URL to a SOCKS4, SOCKS5 or HTTP proxy
    """
    import httpx

    kwargs = {
        # Because not all transports are HTTP-based, timeouts are produced by
        # the RPCBase class
        'timeout': None,
        'headers': {
            'User-Agent': f'{__project_name__} {__version__}',
        },
    }

    # Basic auth
    username, password = auth
    if username and password:
        kwargs['auth'] = httpx.BasicAuth(username, password)

    # SOCKS[4|5] or HTTP proxy
    if proxy_url:
        import httpx_socks

        kwargs['transport'] = httpx_socks.AsyncProxyTransport.from_url(proxy_url)

    return httpx.AsyncClient(**kwargs)


async def catch_http_exceptions(coro):
    """
    Turn HTTP exceptions from `coro` into :class:`~.ConnectionError`

    Proxy exceptions are also caught.
    """
    import httpx
    import httpx_socks

    try:
        return await coro
    except httpx.HTTPError as e:
        raise _errors.ConnectionError(e)
    except httpx_socks.ProxyError as e:
        raise _errors.ConnectionError(e)
    except OSError as e:
        # Any low-level exceptions and httpx_socks.ProxyConnectionError, which
        # is a subclass of OSError.
        msg = e.strerror if e.strerror else str(e)
        raise _errors.ConnectionError(msg)
