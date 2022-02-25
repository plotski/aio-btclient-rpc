import asyncio
import enum
import inspect
import os
import re

from . import __project_name__, __version__, _errors

import logging  # isort:skip
_log = logging.getLogger(__name__)


def get_aioloop():
    """Return :class:`asyncio.AbstractEventLoop` instance"""
    # https://docs.python.org/3.10/library/asyncio-eventloop.html
    try:
        return asyncio.get_running_loop()
    except AttributeError:
        # Python 3.6 doesn't have get_running_loop()
        return asyncio.get_event_loop()
    except RuntimeError:
        # "no running event loop"
        # We need a loop before the application has started. We can't use
        # get_event_loop(), because that is going to be an alias for
        # get_running_loop() in Python >= 3.10. This is what get_event_loop()
        # does internally in Python 3.6.
        return asyncio.get_event_loop_policy().get_event_loop()


def clients():
    """Return list of :class:`~.RPCBase` subclasses"""
    import aiobtclientrpc  # isort:skip
    basecls = aiobtclientrpc.RPCBase
    subclses = set()
    for name, value in inspect.getmembers(aiobtclientrpc):
        if (
            value is not basecls and
            isinstance(value, type) and
            issubclass(value, basecls)
        ):
            subclses.add(value)
    return sorted(subclses, key=lambda cls: cls.name)


def client(name, *args, **kwargs):
    """
    Convenience function to instantiate a :class:`~.RPCBase` subclass

    :param str name: :attr:`~.RPCBase.name` of the client
    :param args: Positional arguments to pass to the :class:`~.RPCBase` subclass
    :param kwargs: Keyword arguments to pass to the :class:`~.RPCBase` subclass

    :raise ValueError: if there is no :class:`~.RPCBase` subclass with a
        matching `name`

    :return: :class:`~.RPCBase` instance
    """
    for cls in clients():
        if cls.name == name:
            return cls(*args, **kwargs)
    raise _errors.ValueError(f'No such client: {name}')


class ConnectionStatus(enum.Enum):
    """Current state of the client connection"""

    connecting = 'connecting'
    """Attempting to connect"""

    connected = 'connected'
    """Connection was established"""

    disconnected = 'disconnected'
    """Connection was either lost or terminated"""


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
    URL to an RPC interface

    This implementation attempts to parse URLs more intuitively instead of
    following any specs. For example ``"localhost:1234"`` is interpreted as
    ``host=localhost, port=1234`` instead of ``scheme=localhost, path=1234``.

    :param str default_scheme: Scheme to use when the URL doesn't provide one
        and a host/IP is detected (i.e. it's not a file:// URL)
    :param callable on_change: Callback that is called with no arguments when
        any property is modified

    :raise ValueError: if `url` is invalid
    """

    _scheme_regex = re.compile(r'^(.*?)://')
    _auth_regex = re.compile(r'^(.*?):(.*?)@')
    _host_regex = re.compile(r'^(.*?)(?=/|:|$)')
    _port_regex = re.compile(r'^:(.*?)(?=/|$)')

    def __init__(self, url, default_scheme=None, on_change=None):
        # Don't trigger any changes until we finished parsing the initial value
        self._on_change = None

        # Set defaults
        self._scheme = str(default_scheme) if default_scheme else None
        self._username = None
        self._password = None
        self._host = None
        self._port = None
        self._path = None

        url = str(url).strip()

        # Scheme
        match = self._scheme_regex.search(url)
        if match:
            self.scheme = match.group(1)
            url = self._scheme_regex.sub('', url)
        elif default_scheme:
            self.scheme = default_scheme

        # Assume file system path if URL starts with path separator
        if self.scheme is None and url.startswith(os.sep):
            self.scheme = 'file'

        # File system paths don't have authentication, port, etc
        if self.scheme == 'file':
            self.path = url

        else:
            # Authentication
            match = self._auth_regex.search(url)
            if match:
                self.username = match.group(1)
                self.password = match.group(2)
                url = self._auth_regex.sub('', url)

            # Host
            match = self._host_regex.search(url)
            if match:
                self.host = match.group(1)
                url = self._host_regex.sub('', url)

            # Port
            match = self._port_regex.search(url)
            if match:
                self.port = match.group(1)
                url = self._port_regex.sub('', url)

            # Path
            self.path = url

        # Parsing is complete, enable on_change callback
        self._on_change = on_change

    @property
    def scheme(self):
        """Scheme (e.g. ``"http"`` or ``"file"``)"""
        return self._scheme

    @scheme.setter
    def scheme(self, scheme):
        if not scheme:
            self._scheme = None
        else:
            self._scheme = str(scheme).lower()

        if self._on_change:
            self._on_change()

    @property
    def host(self):
        """Host name or IP address or `None`"""
        return self._host

    @host.setter
    def host(self, host):
        if not host:
            self._host = None
        else:
            self._host = str(host)

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
        """File system path or request path or `None`"""
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
        if not username:
            self._username = None
        else:
            self._username = str(username)

        if self._on_change:
            self._on_change()

    @property
    def password(self):
        """Password for authentication"""
        return self._password

    @password.setter
    def password(self, password):
        if not password:
            self._password = None
        else:
            self._password = str(password)

        if self._on_change:
            self._on_change()

    @property
    def without_auth(self):
        """URL string without :attr:`username` and :attr:`password`"""
        return self._as_string(with_auth=False)

    @property
    def with_auth(self):
        """URL string with :attr:`username` and :attr:`password`"""
        return self._as_string(with_auth=True)

    def _as_string(self, with_auth=False):
        parts = []

        if self.scheme:
            parts.append(f'{self.scheme}://')

        if with_auth:
            if self.username or self.password:
                parts.append(f'{self.username or ""}:{self.password or ""}@')

        if self.host:
            parts.append(self.host)

        if self.port:
            parts.append(f':{self.port}')

        if self.path:
            parts.append(self.path)

        return ''.join(parts)

    def __str__(self):
        return self.without_auth

    def __eq__(self, other):
        if isinstance(other, type(self)):
            return self.with_auth == other.with_auth
        else:
            return NotImplemented

    def __ne__(self, other):
        eq = self.__eq__(other)
        return NotImplemented if eq is NotImplemented else not eq

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
    import httpx  # isort:skip

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
        import httpx_socks  # isort:skip
        kwargs['transport'] = httpx_socks.AsyncProxyTransport.from_url(proxy_url)

    return httpx.AsyncClient(**kwargs)


async def catch_connection_exceptions(coro):
    """
    Turn exceptions from network requests into :class:`~.ConnectionError`

    Proxy exceptions are also caught.

    The error message should be user-friendly.

    :param coro: Awaitable that performs a network request

    :return: return value of `coro`

    :raise ConnectionError: if any relevant exception is raised
    """
    import httpx, httpx_socks  # isort:skip

    try:
        return await coro
    except httpx.HTTPError as e:
        raise _errors.ConnectionError(e)
    except httpx_socks.ProxyError as e:
        raise _errors.ConnectionError(e)
    except ConnectionAbortedError:
        raise _errors.ConnectionError('Connection aborted')
    except ConnectionRefusedError:
        raise _errors.ConnectionError('Connection refused')
    except ConnectionResetError:
        raise _errors.ConnectionError('Connection reset')
    except OSError as e:
        # Any low-level exceptions and httpx_socks.ProxyConnectionError, which
        # is a subclass of OSError.
        msg = e.strerror if e.strerror else str(e)
        if not msg:
            msg = 'Unknown error'
        else:
            # Extract actual error, e.g. from
            # [Errno 111] Connect call failed ('::1', 5001, 0, 0)
            # Multiple exceptions: [Errno 111] Connect call failed ('::1', 5001, 0, 0),
            #                      [Errno 111] Connect call failed ('127.0.0.1', 5001)
            match = re.search(r'\[Errno \d+\]\s*(.*?)\s*(?:\[|\(|$)', msg)
            if match:
                msg = match.group(1)
        raise _errors.ConnectionError(msg)
