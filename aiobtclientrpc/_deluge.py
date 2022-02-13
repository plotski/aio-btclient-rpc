import asyncio
import struct

from . import _base, _errors, _utils

import logging  # isort:skip
_log = logging.getLogger(__name__)


class DelugeRPC(_base.RPCBase):
    """
    RPC client for Deluge

    URL format: http[s]://[USERNAME:PASSWORD@]HOST:PORT

    References:
        https://deluge.readthedocs.io/en/latest/reference/index.html
        https://www.rasterbar.com/products/libtorrent/manual-ref.html
        https://git.deluge-torrent.org/deluge/tree/

    **RPC methods**

    RPC methods are only documented as Deluge code. Look for funtions decorated
    with @export. The RPC method is the module name and the function name
    concatenated with ".".

    For example, the RPC method name of Daemon.get_method_list() in
    deluge/core/daemon.py would be "daemon.get_method_list".

    Arguments for RPC methods must be positional/keyword as specified in the
    function's call signature.

    **Events**

    Like RPC methods, events are not properly documented. You can find event
    names by grepping for the class name ``DelugeEvent``. The names of
    subclasses of ``DelugeEvent`` are also event names.

    :raise ValueError: if any argument is invalid
    """

    name = 'deluge'
    label = 'Deluge'
    default_url = 'localhost:58846'

    def __init__(
        self,
        url=None,
        *,
        host=None,
        port=None,
        username=None,
        password=None,
        timeout=None,
        proxy_url=None,
    ):
        # Set custom or default URL
        self.url = url

        # Update URL
        if host:
            self.url.host = host
        if port:
            self.url.port = port
        if username:
            self.url.username = username
        if password:
            self.url.password = password

        self.timeout = timeout
        self.proxy_url = proxy_url

    async def _connect(self):
        # Close old client
        await self._disconnect()

        # Create new client
        self._client = _DelugeRPCClient(
            host=self.url.host,
            port=self.url.port,
            timeout=self.timeout,
            proxy_url=self.proxy_url,
            event_handler=self._emit_event,
        )
        await _utils.catch_connection_exceptions(
            self._client.login(
                username=self.url.username,
                password=self.url.password,
            ),
        )

    async def _disconnect(self):
        if hasattr(self, '_client'):
            await _utils.catch_connection_exceptions(
                self._client.logout()
            )
            delattr(self, '_client')

    async def _call(self, method, *args, **kwargs):
        return await _utils.catch_connection_exceptions(
            self._client.call(method, *args, **kwargs),
        )

    async def _subscribe(self, event_name):
        _log.debug('Setting interest for event: %r', event_name)
        await self.call('daemon.set_event_interest', [event_name])

    async def _unsubscribe(self, event_name):
        # This is not supported in Deluge, but we can just ignore the event by
        # not having any callbacks. This is handled in RPCBase.
        pass


class _DelugeRPCClient:
    def __init__(self, host, port, timeout, proxy_url=None, event_handler=None):
        self._host = str(host)
        self._port = int(port)
        self._timeout = float(timeout)
        self._proxy_url = proxy_url

        self._loop = _utils.get_aioloop()
        self._protocol = None
        self._event_handler = event_handler

    def _connection_lost(self, exception):
        self._protocol = None

    def _event_received(self, event_name, args):
        if asyncio.iscoroutinefunction(self._event_handler):
            coro = self._event_handler(event_name, args)
            self._loop.create_task(coro)
        else:
            self._loop.call_soon(self._event_handler, event_name, args)

    def _protocol_factory(self):
        return _DelugeRPCProtocol(
            on_connection_lost=self._connection_lost,
            on_event_received=self._event_received,
        )

    def _create_ssl_context(self):
        import ssl  # isort:skip
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        return ctx

    async def login(self, username, password):
        if not self._protocol:
            if self._proxy_url:
                try:
                    import python_socks.async_.asyncio  # isort:skip
                    proxy = python_socks.async_.asyncio.Proxy.from_url(self._proxy_url.with_auth)
                except ValueError as e:
                    raise _errors.ValueError(e)

                try:
                    sock = await proxy.connect(dest_host=self._host, dest_port=self._port)
                except python_socks.ProxyError as e:
                    raise _errors.ConnectionError(e)

                create_connection_kwargs = {
                    'sock': sock,
                    'server_hostname': self._host,
                    'protocol_factory': self._protocol_factory,
                    'ssl': self._create_ssl_context(),
                }
            else:
                create_connection_kwargs = {
                    'host': self._host,
                    'port': self._port,
                    'protocol_factory': self._protocol_factory,
                    'ssl': self._create_ssl_context(),
                }

            transport_, self._protocol = await _utils.catch_connection_exceptions(
                self._loop.create_connection(**create_connection_kwargs)
            )

            # The server expects a client_version kwarg when calling
            # daemon.login. We pretend to be the official client in case the
            # server attempts to derive capabilities from the client_version.
            daemon_version = await self.call('daemon.info')
            _log.debug('Logging in as %r', username)
            auth_level_ = await self.call(
                'daemon.login',
                username,
                password,
                client_version=daemon_version,
            )
            _log.debug('auth level: %r', auth_level_)

    async def logout(self):
        if self._protocol:
            _log.debug('Logging out')
            self._protocol.close()

    async def call(self, method, *args, **kwargs):
        request = _DelugeRPCRequest(
            method=method,
            args=args,
            kwargs=kwargs,
        )
        return await self._protocol.send_request(request)


class _DelugeRPCProtocol(asyncio.Protocol):
    PROTOCOL_VERSION = 1
    # See https://docs.python.org/3/library/struct.html#format-strings
    MESSAGE_HEADER_FORMAT = '!BI'
    MESSAGE_HEADER_SIZE = struct.calcsize(MESSAGE_HEADER_FORMAT)

    RPC_RESPONSE = 1
    RPC_ERROR = 2
    RPC_EVENT = 3

    def __init__(
            self,
            on_connection_made=None,
            on_connection_lost=None,
            on_event_received=None,
    ):
        self._on_connection_made = on_connection_made
        self._on_connection_lost = on_connection_lost
        self._on_event_received = on_event_received
        self._reset_internal_state()

    def _reset_internal_state(self):
        self._transport = None
        self._buffer = b''
        self._message_length = 0
        self._requests = {}
        _DelugeRPCRequest.reset_id()

    def connection_made(self, transport):
        _log.debug('Made connection: %r', transport)
        self._transport = transport
        if self._on_connection_made:
            self._on_connection_made()

    def connection_lost(self, exception):
        _log.debug('Lost connection: %r', exception)

        # Don't leave any ongoing requests hanging
        request_exception = exception or _errors.ConnectionError('Connection lost')
        for request in self._requests.values():
            if not request.future.done():
                request.future.set_exception(request_exception)
        self._requests.clear()

        self.close()
        self._reset_internal_state()

        if self._on_connection_lost:
            self._on_connection_lost(exception)

    def close(self):
        if self._transport:
            self._transport.close()

    def data_received(self, data):
        self._buffer += data

        while len(self._buffer) >= self.MESSAGE_HEADER_SIZE:
            if self._message_length == 0:
                self._handle_new_message()

            if len(self._buffer) >= self._message_length:
                self._handle_complete_message()
            else:
                break

    def _handle_new_message(self):
        # Read header bytes
        header = self._buffer[:self.MESSAGE_HEADER_SIZE]
        # Remove the header from the buffer
        self._buffer = self._buffer[self.MESSAGE_HEADER_SIZE:]
        # Unpack header bytes into usable objects
        protocol_version, self._message_length = struct.unpack(self.MESSAGE_HEADER_FORMAT, header)
        if protocol_version != self.PROTOCOL_VERSION:
            raise RuntimeError(f'Unsupported protocol version: {protocol_version}')

    def _handle_complete_message(self):
        # Consume message from buffer
        data = self._buffer[:self._message_length]
        self._buffer = self._buffer[self._message_length:]
        self._message_length = 0

        # Decode message
        import rencode, zlib  # isort:skip
        msg = rencode.loads(zlib.decompress(data), decode_utf8=True)
        msg_type = msg[0]

        # Handle message
        if msg_type == self.RPC_EVENT:
            event = msg[1]
            args = msg[2]
            _log.debug('RPC_EVENT: %s(%s)', event, ', '.join(repr(arg) for arg in args))
            if self._on_event_received:
                self._on_event_received(event, args)

        elif msg_type == self.RPC_ERROR:
            _log.debug('RPC_ERROR: %r', msg)
            request_id, exc_clsname, exc_posargs, exc_kwargs, traceback = msg[1:6]
            exc = self._create_rpc_error(exc_clsname, exc_posargs, exc_kwargs, traceback)
            self._set_response(request_id, exc)

        elif msg_type == self.RPC_RESPONSE:
            _log.debug('RPC_RESPONSE: %r', msg)
            request_id, response = msg[1:]
            self._set_response(request_id, response)

        else:
            raise RuntimeError(f'Unknown RPC message type: {msg_type!r}')

    def _create_rpc_error(self, clsname, posargs, kwargs, traceback):
        if clsname == 'BadLoginError':
            exc = _errors.AuthenticationError('Authentication failed')
        elif clsname == 'NotAuthorizedError':
            msg = 'Not authorized'
            if len(posargs) >= 2:
                auth_level, auth_level_required = posargs[:2]
                msg += f': Your authorization level is {auth_level}, but you need {auth_level_required}'
            exc = _errors.AuthenticationError(msg)
        elif posargs and posargs[0]:
            exc = _errors.RPCError(posargs[0])
        elif clsname:
            exc = _errors.RPCError(clsname)
        else:
            exc = _errors.RPCError('Unknown error')
        _log.debug('Server traceback for %r:\n%s', exc, traceback)
        return exc

    def _set_response(self, request_id, response):
        _log.debug('Setting response for request #%s: %r', request_id, response)
        try:
            request = self._requests[request_id]
        except KeyError:
            raise RuntimeError(f'Got response to unknown request #{request_id}: {response!r}')

        try:
            if request.future.done():
                raise RuntimeError(f'Request #{request_id} already has a response')
            else:
                if isinstance(response, BaseException):
                    request.future.set_exception(response)
                else:
                    request.future.set_result(response)
        finally:
            del self._requests[request_id]

    def _transfer_messages(self, *data):
        import rencode, zlib  # isort:skip
        body = zlib.compress(rencode.dumps(data))
        body_len = len(body)
        packed = struct.pack(
            f'{self.MESSAGE_HEADER_FORMAT}{body_len}s',
            self.PROTOCOL_VERSION,
            body_len,
            body,
        )
        self._transport.write(packed)

    def send_request(self, request):
        _log.debug('Sending request #%d: %r', request.id, request)
        self._requests[request.id] = request
        self._transfer_messages(request.format_message())
        return request.future


class _DelugeRPCRequest:
    _next_id = 0

    def __init__(self, *, method, args, kwargs):
        self.method = str(method)
        self.args = tuple(args)
        self.kwargs = dict(kwargs)
        self.future = asyncio.Future()
        self.id = type(self)._next_id
        type(self)._next_id += 1

    @classmethod
    def reset_id(cls):
        """Reset automatically incremented :attr:`id` to ``0``"""
        cls._next_id = 0

    def format_message(self):
        """Return properly formatted request"""
        return (self.id, self.method, self.args, self.kwargs)

    def __repr__(self):
        text = f'ID#{self.id}:{self.method}('
        posargs = ', '.join((repr(arg) for arg in self.args))
        kwargs = ', '.join((f'{k}={v!r}' for k, v in self.kwargs.items()))
        args = ', '.join((x for x in (posargs, kwargs) if x))
        if args:
            text += args
        text += ')'
        return text

    def __eq__(self, other):
        return (
            type(other) is type(self)
            and self.method == other.method
            and self.args == other.args
            and self.kwargs == other.kwargs
        )

    def __ne__(self, other):
        return not self.__eq__(other)
