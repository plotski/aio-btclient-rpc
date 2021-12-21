import abc
import asyncio

import async_timeout

from . import _errors, _utils

import logging  # isort:skip
_log = logging.getLogger(__name__)


class RPCBase(abc.ABC):
    """Base class for BitTorrent client RPC interfaces"""

    # Abstract methods

    @abc.abstractmethod
    async def _connect(self):
        """Connect to RPC interface"""

    @abc.abstractmethod
    async def _disconnect(self):
        """
        Disconnect from RPC interface

        This method should not raise an exception if it fails. For example, if
        the service at :attr:`url` is down, we can't logout, which shouldn't be
        an error.
        """

    @abc.abstractmethod
    async def _call(self):
        """Call RPC method"""

    # Abstract properties

    @property
    @abc.abstractmethod
    def name(self):
        """Lowercase name of the BitTorrent client"""

    @property
    @abc.abstractmethod
    def label(self):
        """Properly capitalized :attr:`name` of the BitTorrent client"""

    # Properties

    default_timeout = 5.0
    """Default :attr:`timeout`"""

    @property
    def timeout(self):
        """
        Timeout in seconds for RPC calls

        If this property is set to a falsy value, :attr:`default_timeout` is
        used.

        :raise ValueError: if set to something that can't be coerced into a
            :class:`float`
        """
        return getattr(self, '_timeout', self.default_timeout)

    @timeout.setter
    def timeout(self, timeout):
        try:
            self._timeout = float(timeout) if timeout else self.default_timeout
        except (TypeError, ValueError):
            raise _errors.ValueError('Not a number')
        else:
            self._invalidate_http_client()

    @property
    @abc.abstractmethod
    def default_url(self):
        """Default :attr:`url`"""

    @property
    def url(self):
        """
        :class:`~.URL` to the RPC interface

        Changing any of the properties will re-connect to the new URL on the
        next :meth:`~.call`.

        If this property is set to a falsy value, :attr:`default_url` is used.

        :raise ValueError: if set to an invalid URL
        """
        url = getattr(self, '_url', None)
        if not url:
            url = self._url = _utils.URL(
                url=self.default_url,
                on_change=self._invalidate_http_client,
            )
        return url

    @url.setter
    def url(self, url):
        self._url = _utils.URL(
            url=url if url else self.default_url,
            on_change=self._invalidate_http_client,
        )
        self._invalidate_http_client()

    @property
    def proxy_url(self):
        """
        SOCKS5, SOCKS4 or HTTP proxy :class:`~.URL` for tunneling the RPC connection

        If this property is set to a falsy value, no proxy is used.

        :raise ValueError: if set to an invalid URL
        """
        return getattr(self, '_proxy_url', None)

    @proxy_url.setter
    def proxy_url(self, proxy_url):
        if proxy_url:
            self._proxy_url = _utils.URL(
                url=proxy_url,
                on_change=self._invalidate_http_client,
            )
        else:
            self._proxy_url = None
        self._invalidate_http_client()

    @property
    def status(self):
        """:class:`~.ConnectionStatus` enum"""
        return getattr(self, '_status', _utils.ConnectionStatus.disconnected)

    # Callbacks

    def on_connecting(self, callback, *args, **kwargs):
        """
        Set callback to call when an attempt to connect to the RPC interface is made

        :param callback: Callable to call

        All remaining arguments are passed to `callback` when it is called.
        """
        assert callable(callback)
        self._on_connecting = (callback, args, kwargs)

    def on_connected(self, callback, *args, **kwargs):
        """
        Set callback to call when connecting to the RPC interface succeeded

        :param callback: Callable to call

        All remaining arguments are passed to `callback` when it is called.
        """
        assert callable(callback)
        self._on_connected = (callback, args, kwargs)

    def on_disconnected(self, callback, *args, **kwargs):
        """
        Set callback to call when the connection to the RPC interface is lost

        :param callback: Callable to call

        All remaining arguments are passed to `callback` when it is called.
        """
        assert callable(callback)
        self._on_disconnected = (callback, args, kwargs)

    def _call_callback(self, name):
        callback, args, kwargs = getattr(self, f'_on_{name}', (None, None, None))
        if callback:
            callback(*args, **kwargs)

    # RPC methods

    @_utils.cached_property
    def _connection_lock(self):
        return asyncio.Lock()

    async def connect(self):
        """Connect to RPC interface"""
        _log.debug('%s: connect(): Waiting for connection lock (status=%s)', self.label, self.status)
        try:
            async with self._connection_lock:
                _log.debug('%s: connect(): Acquired connection lock (status=%s)', self.label, self.status)
                if self.status is not _utils.ConnectionStatus.connected:
                    self._status = _utils.ConnectionStatus.connecting
                    self._call_callback('connecting')
                    try:
                        async with async_timeout.timeout(self.timeout):
                            await self._connect()

                    except Exception as e:
                        _log.debug('%s: Failed to connect: %r', self.label, e)
                        await self._disconnect()
                        self._status = _utils.ConnectionStatus.disconnected
                        self._call_callback('disconnected')
                        if isinstance(e, asyncio.TimeoutError):
                            raise _errors.TimeoutError(f'Timeout after {self.timeout} seconds')
                        else:
                            raise

                    else:
                        _log.debug('%s: Connected', self.label)
                        self._status = _utils.ConnectionStatus.connected
                        self._call_callback('connected')

        finally:
            _log.debug('%s: connect(): Freed connection lock (status=%s)', self.label, self.status)

    async def disconnect(self):
        """Disconnect from RPC interface"""
        _log.debug('%s: disconnect(): Waiting for connection lock (status=%s)', self.label, self.status)
        try:
            async with self._connection_lock:
                _log.debug('%s: disconnect(): Acquired connection lock (status=%s)', self.label, self.status)
                if self.status is not _utils.ConnectionStatus.disconnected:
                    try:
                        async with async_timeout.timeout(self.timeout):
                            await self._disconnect()

                    except asyncio.TimeoutError:
                        _log.debug('%s: disconnect(): Timeout', self.label)
                        raise _errors.TimeoutError(f'Timeout after {self.timeout} seconds')

                    finally:
                        self._status = _utils.ConnectionStatus.disconnected
                        self._call_callback('disconnected')

        finally:
            await self._close_http_client()
            _log.debug('%s: disconnect(): Freed connection lock (status=%s)', self.label, self.status)

    async def call(self, *args, **kwargs):
        """
        Call RPC method and return the result

        This method first calls :meth:`connect` unless we are already connected.
        """
        _log.debug('%s: [%s] Calling: %s, %s', self.label, self.status, args, kwargs)
        if self.status is not _utils.ConnectionStatus.connected:
            _log.debug('%s: Auto-connecting', self.label)
            await self.connect()

        try:
            async with async_timeout.timeout(self.timeout):
                return await self._call(*args, **kwargs)

        except asyncio.TimeoutError:
            _log.debug('%s: call(): Timeout', self.label)
            raise _errors.TimeoutError(f'Timeout after {self.timeout} seconds')

    # Context manager

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        _log.debug('%s: Disconnecting at end of context manager', self.label)
        await self.disconnect()
        # Make extra sure the HTTP client is closed
        await self._close_http_client()

    # HTTP client

    @property
    def _http_headers(self):
        """
        Headers that are sent on HTTP requests

        Subclass instances should modify these headers as they please. They are
        automatically combined with any obligatory headers.
        """
        headers = getattr(self, '__http_headers', None)
        if headers is None:
            headers = {}
            setattr(self, '__http_headers', headers)
        return headers

    async def _get_http_client(self):
        if getattr(self, '_http_client_is_invalidated', False):
            delattr(self, '_http_client_is_invalidated')
            _log.debug('%s: HTTP client was invalidated', self.label)
            await self._close_http_client()

        if not hasattr(self, '_http_client'):
            proxy_url = self.proxy_url.with_auth if self.proxy_url else None
            self._http_client = _utils.create_http_client(
                auth=(self.url.username, self.url.password),
                proxy_url=proxy_url,
            )
            _log.debug('%s: Created new HTTP client: %r', self.label, self._http_client)
        return self._http_client

    async def _close_http_client(self):
        if hasattr(self, '_http_client'):
            _log.debug('%s: Closing HTTP client: %r', self.label, self._http_client)
            await self._http_client.aclose()
            delattr(self, '_http_client')

    def _invalidate_http_client(self):
        if hasattr(self, '_http_client'):
            _log.debug('%s: HTTP client is now invalidated: %r', self.label, self._http_client)
            self._http_client_is_invalidated = True
        self._status = _utils.ConnectionStatus.disconnected

    async def _send_post_request(self, url, data=None, files=None):
        client = await self._get_http_client()
        return await _utils.catch_http_exceptions(
            client.post(
                url=url,
                headers=self._http_headers,
                data=data,
                files=files,
            ),
        )
