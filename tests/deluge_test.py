import asyncio
import ssl
import struct
import zlib
from unittest.mock import Mock, call

import pytest
import python_socks
import rencode

from aiobtclientrpc import RPCBase, _deluge, _errors, _utils

from .common import AsyncMock


@pytest.mark.parametrize('url', (None, 'http://a:b@foo:123'))
@pytest.mark.parametrize(
    argnames='kwargs',
    argvalues=(
        {},
        {'host': 'asdf'},
        {'port': '123'},
        {'username': 'this', 'password': 'that'},
        {'timeout': 123},
        {'proxy_url': 'http://hey:ho@bar:456'},
    ),
    ids=lambda v: str(v),
)
def test_DelugeRPC_instantiation(kwargs, url):
    if url:
        kwargs['url'] = url
    rpc = _deluge.DelugeRPC(**kwargs)

    exp_url = _utils.URL(_deluge.DelugeRPC.default_url)
    default_url = _utils.URL(_deluge.DelugeRPC.default_url)
    if url:
        custom_url = _utils.URL(url)
    for name in ('scheme', 'host', 'port', 'path', 'username', 'password'):
        if name in kwargs:
            exp_value = kwargs[name]
        elif url:
            exp_value = getattr(custom_url, name)
        else:
            exp_value = getattr(default_url, name)
        actual_value = getattr(rpc.url, name)
        assert actual_value == exp_value
        setattr(exp_url, name, exp_value)

    assert rpc.url == exp_url
    assert rpc.timeout == kwargs.get('timeout', RPCBase.default_timeout)
    if 'proxy_url' in kwargs:
        assert rpc.proxy_url == _utils.URL(kwargs['proxy_url'])
    else:
        assert rpc.proxy_url is None


@pytest.mark.asyncio
async def test_DelugeRPC_connect(mocker):
    rpc = _deluge.DelugeRPC(url='foo:bar@localhost:123')
    mocker.patch.object(rpc, '_disconnect', AsyncMock())
    DelugeRPCClient_mock = mocker.patch('aiobtclientrpc._deluge._DelugeRPCClient', Mock())
    catch_connection_exceptions_mock = mocker.patch('aiobtclientrpc._utils.catch_connection_exceptions',
                                                    AsyncMock(return_value='catch_connection_exceptions return value'))

    await rpc._connect()

    assert rpc._disconnect.call_args_list == [call()]
    assert rpc._client is DelugeRPCClient_mock.return_value
    assert DelugeRPCClient_mock.call_args_list == [call(
        host=rpc.url.host,
        port=rpc.url.port,
        timeout=rpc.timeout,
        proxy_url=rpc.proxy_url,
        event_handler=rpc._emit_event,
    )]
    assert catch_connection_exceptions_mock.call_args_list == [call(rpc._client.login.return_value)]
    assert rpc._client.login.call_args_list == [call(
        username=rpc.url.username,
        password=rpc.url.password,
    )]


@pytest.mark.parametrize(
    argnames='has_client',
    argvalues=(False, True),
)
@pytest.mark.asyncio
async def test_DelugeRPC_disconnect(has_client, mocker):
    rpc = _deluge.DelugeRPC()
    catch_connection_exceptions_mock = mocker.patch('aiobtclientrpc._utils.catch_connection_exceptions',
                                                    AsyncMock(return_value='catch_connection_exceptions return value'))
    if has_client:
        rpc._client = client_mock = Mock(logout=Mock(return_value='client.logout coroutine'))

        await rpc._disconnect()

        assert catch_connection_exceptions_mock.call_args_list == [call('client.logout coroutine')]
        assert client_mock.logout.call_args_list == [call()]

    assert not hasattr(rpc, '_client')


@pytest.mark.asyncio
async def test_DelugeRPC_call(mocker):
    rpc = _deluge.DelugeRPC()
    catch_connection_exceptions_mock = mocker.patch('aiobtclientrpc._utils.catch_connection_exceptions',
                                                    AsyncMock(return_value='catch_connection_exceptions return value'))
    rpc._client = Mock(call=Mock(return_value='client.call coroutine'))

    return_value = await rpc._call('method_name', 'foo', bar='baz')

    assert return_value is catch_connection_exceptions_mock.return_value
    assert catch_connection_exceptions_mock.call_args_list == [call('client.call coroutine')]
    assert rpc._client.call.call_args_list == [call('method_name', 'foo', bar='baz')]


@pytest.mark.asyncio
async def test_DelugeRPC_subscribe(mocker):
    rpc = _deluge.DelugeRPC()
    mocker.patch.object(rpc, 'call', AsyncMock())
    await rpc._subscribe('foo_event')
    assert rpc.call.call_args_list == [call('daemon.set_event_interest', ['foo_event'])]


@pytest.mark.asyncio
async def test_DelugeRPC_unsubscribe(mocker):
    client = _deluge.DelugeRPC()
    mocker.patch.object(client, 'call', AsyncMock())
    await client._unsubscribe('foo_event')
    assert client.call.call_args_list == []


async def test_DelugeRPCClient_connection_lost():
    client = _deluge._DelugeRPCClient(host='localhost', port=123, timeout=10)
    client._protocol = 'foo'
    client._connection_lost(Exception('is ignored'))
    assert client._protocol is None


@pytest.mark.parametrize('iscoroutinefunction', (True, False))
@pytest.mark.asyncio
async def test_DelugeRPCClient_event_received(iscoroutinefunction, mocker):
    client = _deluge._DelugeRPCClient(host='localhost', port=123, timeout=10, event_handler=Mock())
    mocker.patch.object(client, '_loop')
    mocker.patch('asyncio.iscoroutinefunction', return_value=iscoroutinefunction)

    client._event_received('foo', (1, 2, 3))

    if iscoroutinefunction:
        assert client._event_handler.call_args_list == [call('foo', (1, 2, 3))]
        assert client._loop.create_task.call_args_list == [call(client._event_handler.return_value)]
        assert client._loop.call_soon.call_args_list == []
    else:
        assert client._loop.call_soon.call_args_list == [call(client._event_handler, 'foo', (1, 2, 3))]
        assert client._event_handler.call_args_list == []
        assert client._loop.create_task.call_args_list == []


@pytest.mark.asyncio
async def test_DelugeRPCClient_protocol_factory(mocker):
    DelugeRPCProtocol_mock = mocker.patch('aiobtclientrpc._deluge._DelugeRPCProtocol')
    client = _deluge._DelugeRPCClient(host='localhost', port=123, timeout=10)
    protocol = client._protocol_factory()
    assert protocol is DelugeRPCProtocol_mock.return_value
    assert DelugeRPCProtocol_mock.call_args_list == [call(
        on_connection_lost=client._connection_lost,
        on_event_received=client._event_received,
    )]


@pytest.mark.asyncio
async def test_DelugeRPCClient_create_ssl_context():
    client = _deluge._DelugeRPCClient(host='localhost', port=123, timeout=10)
    ctx = client._create_ssl_context()
    assert isinstance(ctx, ssl.SSLContext)
    assert ctx.check_hostname is False
    assert ctx.verify_mode is ssl.CERT_NONE


@pytest.mark.asyncio
async def test_DelugeRPCClient_login_when_already_logged_in(mocker):
    client = _deluge._DelugeRPCClient(host='localhost', port=123, timeout=10)
    client._protocol = 'mock protocol'

    Proxy_from_url_mock = mocker.patch('python_socks.async_.asyncio.Proxy.from_url', return_value=Mock(
        connect=AsyncMock(),
    ))
    mocker.patch.object(client, '_create_ssl_context')
    catch_connection_exceptions_mock = mocker.patch('aiobtclientrpc._utils.catch_connection_exceptions',
                                                    AsyncMock(return_value=('mock transport', 'mock protocol')))
    mocker.patch.object(client._loop, 'create_connection', Mock())
    mocker.patch.object(client, 'call', AsyncMock())

    await client.login('Username', 'Password')

    assert Proxy_from_url_mock.call_args_list == []
    assert Proxy_from_url_mock.return_value.connect.call_args_list == []
    assert catch_connection_exceptions_mock.call_args_list == []
    assert client._loop.create_connection.call_args_list == []
    assert client.call.call_args_list == []

@pytest.mark.asyncio
async def test_DelugeRPCClient_login_with_proxy_url(mocker):
    client = _deluge._DelugeRPCClient(
        host='localhost',
        port=123,
        timeout=10,
        proxy_url=_utils.URL('socks5://localhost:456'),
    )
    client._protocol = None

    Proxy_from_url_mock = mocker.patch('python_socks.async_.asyncio.Proxy.from_url', return_value=Mock(
        connect=AsyncMock(),
    ))
    mocker.patch.object(client, '_create_ssl_context')
    catch_connection_exceptions_mock = mocker.patch('aiobtclientrpc._utils.catch_connection_exceptions',
                                                    AsyncMock(return_value=('mock transport', 'mock protocol')))
    mocker.patch.object(client._loop, 'create_connection', Mock())
    mocker.patch.object(client, 'call', AsyncMock(side_effect=(
        'mock client_version',
        'mock login response',
    )))

    await client.login('Username', 'Password')

    assert Proxy_from_url_mock.call_args_list == [call(client._proxy_url.with_auth)]
    assert Proxy_from_url_mock.return_value.connect.call_args_list == [call(dest_host=client._host, dest_port=client._port)]
    assert catch_connection_exceptions_mock.call_args_list == [call(client._loop.create_connection.return_value)]
    assert client._loop.create_connection.call_args_list == [call(
        sock=Proxy_from_url_mock.return_value.connect.return_value,
        server_hostname=client._host,
        protocol_factory=client._protocol_factory,
        ssl=client._create_ssl_context.return_value,
    )]
    assert client.call.call_args_list == [
        call('daemon.info'),
        call('daemon.login', 'Username', 'Password', client_version='mock client_version'),
    ]

@pytest.mark.asyncio
async def test_DelugeRPCClient_login_with_bad_proxy_url(mocker):
    client = _deluge._DelugeRPCClient(
        host='localhost',
        port=123,
        timeout=10,
        proxy_url=_utils.URL('socks5://localhost:456'),
    )
    client._protocol = None

    Proxy_from_url_mock = mocker.patch('python_socks.async_.asyncio.Proxy.from_url',
                                       side_effect=ValueError('bad proxy url'))
    mocker.patch.object(client, '_create_ssl_context')
    catch_connection_exceptions_mock = mocker.patch('aiobtclientrpc._utils.catch_connection_exceptions',
                                                    AsyncMock(return_value=('mock transport', 'mock protocol')))
    mocker.patch.object(client._loop, 'create_connection', Mock())
    mocker.patch.object(client, 'call', AsyncMock(side_effect=(
        'mock client_version',
        'mock login response',
    )))

    with pytest.raises(_errors.ValueError, match=r'^bad proxy url$'):
        await client.login('Username', 'Password')

    assert Proxy_from_url_mock.call_args_list == [call(client._proxy_url.with_auth)]
    assert Proxy_from_url_mock.return_value.connect.call_args_list == []
    assert catch_connection_exceptions_mock.call_args_list == []
    assert client._loop.create_connection.call_args_list == []
    assert client.call.call_args_list == []

@pytest.mark.asyncio
async def test_DelugeRPCClient_login_with_bad_proxy_connection(mocker):
    client = _deluge._DelugeRPCClient(
        host='localhost',
        port=123,
        timeout=10,
        proxy_url=_utils.URL('socks5://localhost:456'),
    )
    client._protocol = None

    Proxy_from_url_mock = mocker.patch('python_socks.async_.asyncio.Proxy.from_url', return_value=Mock(
        connect=AsyncMock(side_effect=python_socks.ProxyError('bad proxy connection')),
    ))
    mocker.patch.object(client, '_create_ssl_context')
    catch_connection_exceptions_mock = mocker.patch('aiobtclientrpc._utils.catch_connection_exceptions',
                                                    AsyncMock(return_value=('mock transport', 'mock protocol')))
    mocker.patch.object(client._loop, 'create_connection', Mock())
    mocker.patch.object(client, 'call', AsyncMock(side_effect=(
        'mock client_version',
        'mock login response',
    )))

    with pytest.raises(_errors.ConnectionError, match=r'^bad proxy connection$'):
        await client.login('Username', 'Password')

    assert Proxy_from_url_mock.call_args_list == [call(client._proxy_url.with_auth)]
    assert Proxy_from_url_mock.return_value.connect.call_args_list == [call(dest_host=client._host, dest_port=client._port)]
    assert catch_connection_exceptions_mock.call_args_list == []
    assert client._loop.create_connection.call_args_list == []
    assert client.call.call_args_list == []

@pytest.mark.asyncio
async def test_DelugeRPCClient_login_without_proxy_url(mocker):
    client = _deluge._DelugeRPCClient(
        host='localhost',
        port=123,
        timeout=10,
    )
    client._protocol = None

    Proxy_from_url_mock = mocker.patch('python_socks.async_.asyncio.Proxy.from_url', return_value=Mock(
        connect=AsyncMock(),
    ))
    mocker.patch.object(client, '_create_ssl_context')
    catch_connection_exceptions_mock = mocker.patch('aiobtclientrpc._utils.catch_connection_exceptions',
                                                    AsyncMock(return_value=('mock transport', 'mock protocol')))
    mocker.patch.object(client._loop, 'create_connection', Mock())
    mocker.patch.object(client, 'call', AsyncMock(side_effect=(
        'mock client_version',
        'mock login response',
    )))

    await client.login('Username', 'Password')

    assert Proxy_from_url_mock.call_args_list == []
    assert Proxy_from_url_mock.return_value.connect.call_args_list == []
    assert catch_connection_exceptions_mock.call_args_list == [call(client._loop.create_connection.return_value)]
    assert client._loop.create_connection.call_args_list == [call(
        host=client._host,
        port=client._port,
        protocol_factory=client._protocol_factory,
        ssl=client._create_ssl_context.return_value,
    )]
    assert client.call.call_args_list == [
        call('daemon.info'),
        call('daemon.login', 'Username', 'Password', client_version='mock client_version'),
    ]


@pytest.mark.parametrize('protocol', (None, Mock()))
@pytest.mark.asyncio
async def test_DelugeRPCClient_logout(protocol, mocker):
    client = _deluge._DelugeRPCClient(host='localhost', port=123, timeout=10)
    mocker.patch.object(client, '_protocol', protocol)
    await client.logout()
    if protocol:
        assert client._protocol.close.call_args_list == [call()]


@pytest.mark.asyncio
async def test_DelugeRPCClient_call(mocker):
    client = _deluge._DelugeRPCClient(host='localhost', port=123, timeout=10)
    mocker.patch.object(client, '_protocol', Mock(send_request=AsyncMock()))
    return_value = await client.call('mock_method', 1, 2, 3, a='b')
    assert return_value is client._protocol.send_request.return_value
    exp_request = _deluge._DelugeRPCRequest(
        method='mock_method',
        args=(1, 2, 3),
        kwargs={'a': 'b'},
    )
    assert client._protocol.send_request.call_args_list == [call(exp_request)]


def test_DelugeRPCProtocol_initialization(mocker):
    on_connection_made = Mock()
    on_connection_lost = Mock()
    on_event_received = Mock()
    mocker.patch('aiobtclientrpc._deluge._DelugeRPCProtocol._reset_internal_state')
    protocol = _deluge._DelugeRPCProtocol(
        on_connection_made=on_connection_made,
        on_connection_lost=on_connection_lost,
        on_event_received=on_event_received,
    )
    assert protocol._on_connection_made is on_connection_made
    assert protocol._on_connection_lost is on_connection_lost
    assert protocol._on_event_received is on_event_received
    assert protocol._reset_internal_state.call_args_list == [call()]


def test_DelugeRPCProtocol_reset_internal_state(mocker):
    protocol = _deluge._DelugeRPCProtocol()
    protocol._transport = 'mock transport'
    protocol._buffer = b'partial messag'
    protocol._message_length = 123
    protocol._requests = {52: Mock(), 53: Mock()}
    _deluge._DelugeRPCRequest._next_id = 456

    protocol._reset_internal_state()

    assert protocol._transport is None
    assert protocol._buffer == b''
    assert protocol._message_length == 0
    assert protocol._requests == {}
    assert _deluge._DelugeRPCRequest._next_id == 0


@pytest.mark.parametrize('on_connection_made', (False, True))
def test_DelugeRPCProtocol_connection_made(on_connection_made, mocker):
    protocol = _deluge._DelugeRPCProtocol(
        on_connection_made=Mock() if on_connection_made else None,
    )
    transport = Mock()
    protocol.connection_made(transport)
    assert protocol._transport is transport
    if on_connection_made:
        assert protocol._on_connection_made.call_args_list == [call()]


@pytest.mark.parametrize('on_connection_lost', (False, True))
@pytest.mark.parametrize(
    argnames='exception, exp_exception',
    argvalues=(
        (None, _errors.ConnectionError('Connection lost')),
        (_errors.RPCError('error message'), _errors.RPCError('error message')),
    ),
    ids=lambda v: repr(v),
)
def test_DelugeRPCProtocol_connection_lost(exception, exp_exception, on_connection_lost, mocker):
    protocol = _deluge._DelugeRPCProtocol(
        on_connection_lost=Mock() if on_connection_lost else None,
    )
    mocker.patch.object(protocol, 'close')
    mocker.patch.object(protocol, '_reset_internal_state')
    _deluge._DelugeRPCRequest._next_id = 123
    finished_request = Mock(future=Mock(done=Mock(return_value=True)))
    unfinished_request = Mock(future=Mock(done=Mock(return_value=False)))
    protocol._requests = {
        23: finished_request,
        24: unfinished_request
    }

    protocol.connection_lost(exception)

    assert finished_request.future.set_exception.call_args_list == []
    assert finished_request.future.set_result.call_args_list == []
    assert unfinished_request.future.set_exception.call_args_list == [call(exp_exception)]
    assert unfinished_request.future.set_result.call_args_list == []
    assert protocol._requests == {}
    assert protocol.close.call_args_list == [call()]
    assert protocol._reset_internal_state.call_args_list == [call()]
    if on_connection_lost:
        assert protocol._on_connection_lost.call_args_list == [call()]


@pytest.mark.parametrize(
    argnames='transport, exp_calls',
    argvalues=(
        (None, []),
        (Mock(), [call()]),
    ),
)
def test_DelugeRPCProtocol_close(transport, exp_calls, mocker):
    protocol = _deluge._DelugeRPCProtocol()
    mocker.patch.object(protocol, '_transport', transport)
    protocol.close()
    if transport:
        assert protocol._transport.close.call_args_list == exp_calls
    else:
        assert protocol._transport is None


def test_DelugeRPCProtocol_data_received_ignores_short_buffer(mocker):
    protocol = _deluge._DelugeRPCProtocol()
    mocker.patch.object(protocol, '_handle_new_message')
    mocker.patch.object(protocol, '_handle_complete_message')

    protocol._buffer = b'x'
    protocol._message_length = 123
    protocol.data_received(b'')

    assert protocol._handle_new_message.call_args_list == []
    assert protocol._handle_complete_message.call_args_list == []
    assert protocol._message_length == 123
    assert protocol._buffer == b'x'

def test_DelugeRPCProtocol_data_received_reads_new_message(mocker):
    protocol = _deluge._DelugeRPCProtocol()
    mocker.patch.object(protocol, '_handle_new_message',
                        side_effect=lambda: setattr(protocol, '_message_length', 123))
    mocker.patch.object(protocol, '_handle_complete_message',
                        side_effect=lambda: setattr(protocol, '_buffer', b''))

    protocol._buffer = b'x' * protocol.MESSAGE_HEADER_SIZE
    protocol._message_length = 0
    protocol.data_received(b'more data')
    assert protocol._handle_new_message.call_args_list == [call()]
    assert protocol._handle_complete_message.call_args_list == []

def test_DelugeRPCProtocol_data_received_reads_complete_message(mocker):
    protocol = _deluge._DelugeRPCProtocol()
    mocker.patch.object(protocol, '_handle_new_message',
                        side_effect=lambda: setattr(protocol, '_message_length', 123))
    mocker.patch.object(protocol, '_handle_complete_message',
                        side_effect=lambda: setattr(protocol, '_buffer', b''))

    protocol._message_length = 33
    protocol._buffer = b'x' * 30
    protocol.data_received(b'more data')
    assert protocol._handle_new_message.call_args_list == []
    assert protocol._handle_complete_message.call_args_list == [call()]


def pack_message(body, protocol_version=_deluge._DelugeRPCProtocol.PROTOCOL_VERSION):
    return struct.pack(
        f'{_deluge._DelugeRPCProtocol.MESSAGE_HEADER_FORMAT}{len(body)}s',
        protocol_version,
        len(body),
        body,
    )


def test_DelugeRPCProtocol_handle_new_message_gets_unexpected_protocol_version(mocker):
    protocol = _deluge._DelugeRPCProtocol()
    body = b'foo'
    protocol._buffer = pack_message(body, protocol_version=29)
    with pytest.raises(RuntimeError, match='^Unsupported protocol version: 29$'):
        protocol._handle_new_message()

def test_DelugeRPCProtocol_handle_new_message_consumes_header(mocker):
    protocol = _deluge._DelugeRPCProtocol()
    body = b'foo'
    protocol._buffer = pack_message(body, protocol_version=protocol.PROTOCOL_VERSION)
    protocol._handle_new_message()
    assert protocol._message_length == len(body)
    assert protocol._buffer == body


@pytest.mark.parametrize('on_event_received', (None, Mock()))
def test_DelugeRPCProtocol_handle_complete_message_gets_RPC_EVENT(on_event_received, mocker):
    protocol = _deluge._DelugeRPCProtocol(
        on_event_received=on_event_received,
    )
    mocker.patch.object(protocol, '_create_rpc_error')
    mocker.patch.object(protocol, '_set_response')

    args = ('arg1', 'órg2', 'ärg3')
    msg = (protocol.RPC_EVENT, 'MockEventName', args)
    data = zlib.compress(rencode.dumps(msg))
    protocol._buffer = data + b'remaining data'
    protocol._message_length = len(data)

    protocol._handle_complete_message()

    if on_event_received:
        assert protocol._on_event_received.call_args_list == [call('MockEventName', args)]
    else:
        assert protocol._on_event_received is None
    assert protocol._create_rpc_error.call_args_list == []
    assert protocol._set_response.call_args_list == []
    assert protocol._buffer == b'remaining data'
    assert protocol._message_length == 0

def test_DelugeRPCProtocol_handle_complete_message_gets_RPC_ERROR(mocker):
    protocol = _deluge._DelugeRPCProtocol(
        on_event_received=Mock(),
    )
    mocker.patch.object(protocol, '_create_rpc_error')
    mocker.patch.object(protocol, '_set_response')

    request_id = 123
    exc_clsname = 'MockError'
    exc_posargs = ('arg1', 'órg2', 'ärg3')
    exc_kwargs = {'foo': 'bar'}
    traceback = 'mock traceback'
    msg = (protocol.RPC_ERROR, request_id, exc_clsname, exc_posargs, exc_kwargs, traceback)
    data = zlib.compress(rencode.dumps(msg))
    protocol._buffer = data + b'remaining data'
    protocol._message_length = len(data)

    protocol._handle_complete_message()

    assert protocol._create_rpc_error.call_args_list == [call(exc_clsname, exc_posargs, exc_kwargs, traceback)]
    assert protocol._set_response.call_args_list == [call(request_id, protocol._create_rpc_error.return_value)]
    assert protocol._on_event_received.call_args_list == []
    assert protocol._buffer == b'remaining data'
    assert protocol._message_length == 0

def test_DelugeRPCProtocol_handle_complete_message_gets_RPC_RESPONSE(mocker):
    protocol = _deluge._DelugeRPCProtocol(
        on_event_received=Mock(),
    )
    mocker.patch.object(protocol, '_create_rpc_error')
    mocker.patch.object(protocol, '_set_response')

    request_id = 123
    response = ('arg1', 'órg2', 'ärg3')
    msg = (protocol.RPC_RESPONSE, request_id, response)
    data = zlib.compress(rencode.dumps(msg))
    protocol._buffer = data + b'remaining data'
    protocol._message_length = len(data)

    protocol._handle_complete_message()

    assert protocol._create_rpc_error.call_args_list == []
    assert protocol._set_response.call_args_list == [call(request_id, response)]
    assert protocol._on_event_received.call_args_list == []
    assert protocol._buffer == b'remaining data'
    assert protocol._message_length == 0

def test_DelugeRPCProtocol_handle_complete_message_gets_unknown_msg_type(mocker):
    protocol = _deluge._DelugeRPCProtocol(
        on_event_received=Mock(),
    )
    mocker.patch.object(protocol, '_create_rpc_error')
    mocker.patch.object(protocol, '_set_response')

    request_id = 123
    response = ('arg1', 'órg2', 'ärg3')
    msg = ('gnarf', request_id, response)
    data = zlib.compress(rencode.dumps(msg))
    protocol._buffer = data + b'remaining data'
    protocol._message_length = len(data)

    with pytest.raises(RuntimeError, match="^Unknown RPC message type: 'gnarf'$"):
        protocol._handle_complete_message()

    assert protocol._create_rpc_error.call_args_list == []
    assert protocol._set_response.call_args_list == []
    assert protocol._on_event_received.call_args_list == []
    assert protocol._buffer == b'remaining data'
    assert protocol._message_length == 0


@pytest.mark.parametrize(
    argnames='clsname, posargs, kwargs, traceback, exp_exception',
    argvalues=(
        ('BadLoginError', (), {}, 'mock traceback',
         _errors.AuthenticationError('Authentication failed')),
        ('NotAuthorizedError', (), {}, 'mock traceback',
         _errors.AuthenticationError('Not authorized')),
        ('NotAuthorizedError', (5, 7), {}, 'mock traceback',
         _errors.AuthenticationError('Not authorized: Your authorization level is 5, but you need 7')),
        ('AnyError', ('An error message',), {}, 'mock traceback',
         _errors.RPCError('An error message')),
        ('AnyError', (), {}, 'mock traceback',
         _errors.RPCError('AnyError')),
        ('', (), {}, 'mock traceback',
         _errors.RPCError('Unknown error')),
    ),
)
def test_DelugeRPCProtocol_create_rpc_error(clsname, posargs, kwargs, traceback, exp_exception):
    protocol = _deluge._DelugeRPCProtocol()
    exc = protocol._create_rpc_error(clsname, posargs, kwargs, traceback)
    assert type(exc) is type(exp_exception)
    assert str(exc) == str(exp_exception)


def test_DelugeRPCProtocol_set_response_fails_to_find_request_id():
    protocol = _deluge._DelugeRPCProtocol()
    response = 'mock response'
    assert '123' not in protocol._requests
    with pytest.raises(RuntimeError, match=rf"^Got response to unknown request #123: {response!r}$"):
        protocol._set_response('123', response)
    assert '123' not in protocol._requests

def test_DelugeRPCProtocol_set_response_gets_request_with_finished_future():
    protocol = _deluge._DelugeRPCProtocol()
    request = Mock(
        id=123,
        future=Mock(done=Mock(return_value=True)),
    )
    response = 'mock response'
    protocol._requests[request.id] = request
    with pytest.raises(RuntimeError, match=r'^Request #123 already has a response$'):
        protocol._set_response(request.id, response)
    assert request.future.set_exception.call_args_list == []
    assert request.future.set_result.call_args_list == []
    assert request.id not in protocol._requests

def test_DelugeRPCProtocol_set_response_sets_exception():
    protocol = _deluge._DelugeRPCProtocol()
    request = Mock(
        id=123,
        future=Mock(done=Mock(return_value=False)),
    )
    response = TypeError('This is the error message')
    protocol._requests[request.id] = request
    protocol._set_response(request.id, response)
    assert request.future.set_exception.call_args_list == [call(response)]
    assert request.future.set_result.call_args_list == []
    assert request.id not in protocol._requests

def test_DelugeRPCProtocol_set_response_sets_result():
    protocol = _deluge._DelugeRPCProtocol()
    request = Mock(
        id=123,
        future=Mock(done=Mock(return_value=False)),
    )
    response = 'This is the response'
    protocol._requests[request.id] = request
    protocol._set_response(request.id, response)
    assert request.future.set_exception.call_args_list == []
    assert request.future.set_result.call_args_list == [call(response)]
    assert request.id not in protocol._requests

def test_DelugeRPCProtocol_set_response_removes_request_on_unexpected_exception():
    protocol = _deluge._DelugeRPCProtocol()
    request = Mock(
        id=123,
        future=Mock(done=Mock(side_effect=ValueError('Oops'))),
    )
    response = 'This is the response'
    protocol._requests[request.id] = request
    with pytest.raises(ValueError, match=r'^Oops$'):
        protocol._set_response(request.id, response)
    assert request.future.set_exception.call_args_list == []
    assert request.future.set_result.call_args_list == []
    assert request.id not in protocol._requests


def test_DelugeRPCProtocol_transfer_message(mocker):
    mock_data = 'the data'
    mock_data_compressed = zlib.compress(rencode.dumps((mock_data,)))
    mock_data_packed = pack_message(mock_data_compressed)
    protocol = _deluge._DelugeRPCProtocol()
    mocker.patch.object(protocol, '_transport')
    protocol._transfer_messages(mock_data)
    assert protocol._transport.write.call_args_list == [call(mock_data_packed)]


def test_DelugeRPCProtocol_send_request(mocker):
    protocol = _deluge._DelugeRPCProtocol()
    mocker.patch.object(protocol, '_transfer_messages')
    request = Mock(id=123)
    return_value = protocol.send_request(request)
    assert protocol._requests[request.id] is request
    assert protocol._transfer_messages.call_args_list == [call(request.format_message())]
    assert return_value is request.future


@pytest.mark.asyncio
async def test_DelugeRPCRequest():
    _deluge._DelugeRPCRequest.reset_id()
    for _ in range(3):
        for i in range(10):
            request = _deluge._DelugeRPCRequest(
                method='method.name',
                args=['arg1', 'arg2'],
                kwargs=(('foo', 'bar'), ('baz', 'arf')),
            )
            assert request.id == i
            assert request.args == ('arg1', 'arg2')
            assert request.kwargs == {'foo': 'bar', 'baz': 'arf'}
            assert asyncio.isfuture(request.future)
            assert request.format_message() == (
                request.id,
                request.method,
                request.args,
                request.kwargs,
            )
        _deluge._DelugeRPCRequest.reset_id()

@pytest.mark.parametrize('kwargs', ({}, {'foo': 'bar'}, {'foo': 'bar', 'baz': 'arf'}))
@pytest.mark.parametrize('args', ((), ('arg1',), ('arg1', 'arg2')))
@pytest.mark.asyncio
async def test_DelugeRPCRequest_repr(kwargs, args):
    request = _deluge._DelugeRPCRequest(
        method='method.name',
        args=args,
        kwargs=kwargs,
    )
    exp_repr = f'ID#{request.id}:{request.method}('
    if args:
        exp_repr += ', '.join((f'{a!r}' for a in request.args))
    if kwargs:
        if args:
            exp_repr += ', '
        exp_repr += ', '.join((f'{k}={v!r}' for k, v in request.kwargs.items()))
    exp_repr += ')'
    assert repr(request) == exp_repr

@pytest.mark.parametrize(
    argnames='a, b, exp_equal',
    argvalues=(
        (
            {'method': 'method1', 'args': (1, 2, 3), 'kwargs': {'foo': 'bar'}},
            {'method': 'method1', 'args': (1, 2, 3), 'kwargs': {'foo': 'bar'}},
            True,
        ),
        (
            {'method': 'method1', 'args': (1, 2, 3), 'kwargs': {'foo': 'bar'}},
            {'method': 'method2', 'args': (1, 2, 3), 'kwargs': {'foo': 'bar'}},
            False,
        ),
        (
            {'method': 'method1', 'args': (1, 2, 3), 'kwargs': {'foo': 'bar'}},
            {'method': 'method1', 'args': (1, 2), 'kwargs': {'foo': 'bar'}},
            False,
        ),
        (
            {'method': 'method1', 'args': (1, 2, 3), 'kwargs': {'foo': 'bar'}},
            {'method': 'method1', 'args': (1, 2, 3), 'kwargs': {'foo': 'Bar'}},
            False,
        ),
    ),
    ids=lambda v: str(v),
)
@pytest.mark.asyncio
async def test_DelugeRPCRequest_equality(a, b, exp_equal, event_loop):
    if exp_equal:
        assert _deluge._DelugeRPCRequest(**a) == _deluge._DelugeRPCRequest(**b)
    else:
        assert _deluge._DelugeRPCRequest(**a) != _deluge._DelugeRPCRequest(**b)
