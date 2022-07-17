import abc
import asyncio
import collections
import weakref

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

    default_timeout = 60.0
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
            raise _errors.ValueError('Invalid timeout')
        else:
            self._invalidate_http_client()

    @property
    @abc.abstractmethod
    def URL(self):
        """
        :class:`~.URL` subclass

        Setting properties on an instance of this subclass to invalid values
        should raise :class:`~.ValueError`. For example, :class:`~.RtorrentURL`
        only accepts the schemes ``http``, ``scgi`` or ``file``.
        """

    @property
    def url(self):
        """
        :class:`~.URL` of the RPC interface

        Changing any of the properties will re-connect to the new URL on the
        next :meth:`~.call`.

        If this property is set to a falsy value, :attr:`~.URL.default` is
        used.

        :raise ValueError: if set to an invalid URL
        """
        url = getattr(self, '_url', None)
        if not url:
            url = self._url = type(self).URL(
                url=type(self).URL.default,
                on_change=self._invalidate_http_client,
            )
        return url

    @url.setter
    def url(self, url):
        self._url = type(self).URL(
            url=url if url else type(self).URL.default,
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

    @property
    def is_connected(self):
        """
        `True` if :attr:`status: is :attr:`~.ConnectionStatus.connected`, `False`
        otherwise
        """
        return self.status is _utils.ConnectionStatus.connected

    # Callbacks

    def set_connecting_callback(self, callback, *args, **kwargs):
        """
        Schedule callback to be called when a connection attempt is made

        :param callback: Callable to call

        All remaining arguments are passed to `callback` when it is called.
        """
        assert callable(callback)
        self._connection_callbacks['connecting'].append((callback, args, kwargs))

    def unset_connecting_callback(self, callback):
        """
        Unschedule callback to be called when a connection attempt is made

        :param callback: Callable to call
        """
        assert callable(callback)
        for cb in tuple(self._connection_callbacks['connecting']):
            if cb[0] == callback:
                self._connection_callbacks['connecting'].remove(cb)

    def set_connected_callback(self, callback, *args, **kwargs):
        """
        Schedule callback to be called when a connection attempt was successful

        :param callback: Callable to call

        All remaining arguments are passed to `callback` when it is called.
        """
        assert callable(callback)
        self._connection_callbacks['connected'].append((callback, args, kwargs))

    def unset_connected_callback(self, callback):
        """
        Unschedule callback to be called when a connection attempt was successful

        :param callback: Callable to call
        """
        assert callable(callback)
        for cb in tuple(self._connection_callbacks['connected']):
            if cb[0] == callback:
                self._connection_callbacks['connected'].remove(cb)

    def set_disconnected_callback(self, callback, *args, **kwargs):
        """
        Schedule callback to be called when the connection was lost or a connection
        attempt has failed

        :param callback: Callable to call

        All remaining arguments are passed to `callback` when it is called.
        """
        assert callable(callback)
        self._connection_callbacks['disconnected'].append((callback, args, kwargs))

    def unset_disconnected_callback(self, callback):
        """
        Unschedule callback to be called when the connection was lost or a
        connection attempt has failed

        :param callback: Callable to call
        """
        assert callable(callback)
        for cb in tuple(self._connection_callbacks['disconnected']):
            if cb[0] == callback:
                self._connection_callbacks['disconnected'].remove(cb)

    @_utils.cached_property
    def _connection_callbacks(self):
        return {
            'connecting': [],
            'connected': [],
            'disconnected': [],
        }

    def _call_connection_callbacks(self, name):
        for callback, args, kwargs in self._connection_callbacks[name]:
            callback(*args, **kwargs)

    # RPC methods

    @_utils.cached_property
    def _connection_lock(self):
        return asyncio.Lock()

    async def connect(self):
        """
        Connect to RPC interface

        Do nothing if :attr:`status` indicates we are already connected.

        It is safe to call this method multiple times concurrently. The first
        call will actually connect while the remaining calls wait for the first
        call to finish. If the first call fails, each of the remaining calls
        will become the first call, i.e. it will attempt to connect while the
        others wait for it.

        :raise ConnectionError: if the request failed
        :raise AuthenticationError: if authentication failed
        :raise TimeoutError: if there is no response after :attr:`timeout` seconds
        :raise RPCError: if there is any miscommunication between us and the RPC
            interface
        """
        _log.debug('%s: connect(): Waiting for connection lock (status=%s)', self.label, self.status)
        try:
            async with self._connection_lock:
                _log.debug('%s: connect(): Acquired connection lock (status=%s)', self.label, self.status)
                if self.status is not _utils.ConnectionStatus.connected:
                    self._status = _utils.ConnectionStatus.connecting
                    self._call_connection_callbacks('connecting')
                    try:
                        async with async_timeout.timeout(self.timeout):
                            await self._connect()

                    except Exception as e:
                        _log.debug('%s: Failed to connect: %r', self.label, e)
                        await self._disconnect()
                        self._status = _utils.ConnectionStatus.disconnected
                        self._call_connection_callbacks('disconnected')
                        if isinstance(e, asyncio.TimeoutError):
                            raise _errors.TimeoutError(f'Timeout after {self.timeout} seconds')
                        else:
                            raise

                    else:
                        _log.debug('%s: Connected', self.label)
                        self._status = _utils.ConnectionStatus.connected
                        self._call_connection_callbacks('connected')

        finally:
            _log.debug('%s: connect(): Freed connection lock (status=%s)', self.label, self.status)

    async def disconnect(self):
        """
        Disconnect from RPC interface

        Do nothing if :attr:`status` indicates we are already disconnected.

        It is safe to call this method multiple times concurrently. The first
        call will actually disconnect while the remaining calls wait for the
        first call to finish. If the first call fails, each of the remaining
        call will become the first call, i.e. it will attempt to disconnect
        while the others wait for it.

        :attr:`status` is always :attr:`.ConnectionStatus.disconnected` when
        this method returns, regardless of any raised exceptions.

        :raise AuthenticationError: if authentication failed
        :raise TimeoutError: if there is no response after :attr:`timeout` seconds
        :raise RPCError: if there is any miscommunication between us and the RPC
            interface
        """
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
                        self._call_connection_callbacks('disconnected')

        finally:
            await self._close_http_client()
            _log.debug('%s: disconnect(): Freed connection lock (status=%s)', self.label, self.status)

    async def call(self, *args, **kwargs):
        """
        Call RPC method and return the result

        If :attr:`status` is not :attr:`.ConnectionStatus.connected`, call
        :meth:`connect` first.

        :raise AuthenticationError: if authentication failed
        :raise ConnectionError: if the request failed
        :raise TimeoutError: if there is no response after :attr:`timeout` seconds
        :raise RPCError: if there is any miscommunication between us and the RPC
            interface

        :return: the return value of the RPC method

            This should be decoded bytes, deserialized JSON, etc. Exceptions
            from decoding and deserializing should be raised as
            :class:`~.RPCError`.
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

    # Events

    @_utils.cached_property
    def _event_handlers(self):
        return collections.defaultdict(lambda: [])

    async def add_event_handler(self, event, handler, autoremove=False):
        """
        Call callable when event happens

        :param event: Name or other identifier of the event (refer to the client
            documentation for valid values)
        :param handler: Callable to be called when `event` happens (refer to the
            client documentation for the call signature)
        :param autoremove: Whether `handler` should be unregistered
            automatically after it is garbage collected (see :mod:`weakref`)

        If `handler` is already registered for `event`, do nothing.

        Multiple handlers can be registered for the same event. They will be
        called in the order they are added.

        :raise NotImplementedError: if the client doesn't support events
        """
        assert callable(handler), handler

        if event not in self._event_handlers:
            await self._subscribe(event)

        if autoremove:
            handler_ref = weakref.ref(handler, self._event_handlers[event].remove)
            if handler_ref not in self._event_handlers[event]:
                self._event_handlers[event].append(handler_ref)
                _log.debug('Added handler reference for event %r: %r', event, handler_ref)

        else:
            if handler not in self._event_handlers[event]:
                self._event_handlers[event].append(handler)
                _log.debug('Added handler for event %r: %r', event, handler)

    async def remove_event_handler(self, event, handler):
        """
        Stop calling callable when event happens

        See :meth:`add_event_handler`.

        If `handler` is not registered for `event`, do nothing.

        :raise NotImplementedError: if the client doesn't support events
        """
        event_handlers = self._event_handlers[event]

        # Disconnect `handler` from `event`
        if handler in event_handlers:
            event_handlers.remove(handler)

        # If there aren't any other handlers for `event`, unsubscribe
        if not event_handlers:
            del self._event_handlers[event]
            await self._unsubscribe(event)
            _log.debug('Removed handler for event %r: %r', event, handler)

    async def wait_for_event(self, event):
        """
        Block until event happens

        :param event: Name or other identifier of the event (refer to the client
            documentation for valid values)

        :raise NotImplementedError: if the client doesn't support events
        """
        blocker = asyncio.Event()

        def unblock_blocker(*_, **__):
            blocker.set()

        await self.add_event_handler(event, unblock_blocker)

        try:
            _log.debug('Waiting for event: %r', event)
            await blocker.wait()
            _log.debug('Done waiting for event: %r', event)
        finally:
            await self.remove_event_handler(event, unblock_blocker)

    async def _emit_event(self, event, args=None, kwargs=None):
        # This function is called by subclasses when they receive an event
        args = args or ()
        kwargs = kwargs or {}
        for handler in self._event_handlers[event]:
            # `handler` is a weakref.ref instance if it was registered with
            # `autoremove=True`.
            #
            # NOTE: If we pass `handler` to _log.debug() here, it will keep
            #       another strong reference to `handler` and the test that
            #       covers dead weakrefs will fail.
            if isinstance(handler, weakref.ref):
                handler = handler()
                if handler is None:
                    continue

            # Because this method is likely being called by some background task
            # that is waiting for events, any exception raised by `handler` will
            # go unnoticed, so we stop the loop if that happens.
            # There should be a better way to handle this, but I can't find it.
            try:
                if asyncio.iscoroutinefunction(handler):
                    await handler(*args, **kwargs)
                else:
                    handler(*args, **kwargs)

            except BaseException as e:
                try:
                    loop = asyncio.get_running_loop()
                except RuntimeError:
                    # Loop is already stopped
                    pass
                else:
                    _log.debug('Stopping loop because event handler for %r '
                               'threw an exception: %r', event, e)
                    loop.stop()

                # We probably raise this into the void, but not raising
                # BaseException is really bad.
                raise

    async def _subscribe(self, event):
        # Tell the client to send us a certain type of event
        raise NotImplementedError(f'Events are not supported for {self.label}')

    async def _unsubscribe(self, event):
        # Tell the client to stop sending us a certain type of event
        raise NotImplementedError(f'Events are not supported for {self.label}')

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
        # httpx wants dictionaries as `data` and everything else as `content`
        if data is not None and not isinstance(data, dict):
            content = data
            data = None
        else:
            content = None

        client = await self._get_http_client()
        return await _utils.catch_connection_exceptions(
            client.post(
                timeout=float('inf'),
                url=url,
                headers=self._http_headers,
                data=data,
                content=content,
                files=files,
            ),
        )
