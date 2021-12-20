import asyncio
import re
from unittest.mock import Mock, PropertyMock, call

import pytest

from aiobtclientrpc import _base, _errors, _utils


# AsyncMock was added in Python 3.8
class AsyncMock(Mock):
    def __call__(self, *args, **kwargs):
        async def coro(_sup=super()):
            return _sup.__call__(*args, **kwargs)
        return coro()


class MockRPC(_base.RPCBase):
    name = 'mockbt'
    label = 'MockBT'
    default_url = 'http://localhost:1234/rpc'

    _connect = AsyncMock()
    _disconnect = AsyncMock()
    _call = AsyncMock()


@pytest.mark.parametrize(
    argnames='timeout, exp_timeout, exp_exception',
    argvalues=(
        (1, 1.0, None),
        (2.5, 2.5, None),
        (0, _base.RPCBase.default_timeout, None),
        (None, _base.RPCBase.default_timeout, None),
        (False, _base.RPCBase.default_timeout, None),
        ('foo', None, _errors.ValueError('Not a number')),
    ),
)
def test_timeout(timeout, exp_timeout, exp_exception, mocker):
    rpc = MockRPC()
    rpc.timeout = 123
    mocker.patch.object(rpc, '_invalidate_http_client')
    if exp_exception:
        with pytest.raises(type(exp_exception), match=rf'^{re.escape(str(exp_exception))}$'):
            rpc.timeout = timeout
        assert rpc._invalidate_http_client.call_args_list == []
    else:
        rpc.timeout = timeout
        assert rpc.timeout == exp_timeout
        assert rpc._invalidate_http_client.call_args_list == [call()]


@pytest.mark.parametrize('attribute', ('scheme', 'host', 'port', 'path', 'username', 'password'))
def test_url(attribute, mocker):
    rpc = MockRPC()
    mocker.patch.object(rpc, '_invalidate_http_client')
    assert isinstance(rpc.url, _utils.URL)
    assert rpc._invalidate_http_client.call_args_list == []
    setattr(rpc.url, attribute, '123')
    assert getattr(rpc.url, attribute) == '123'
    assert rpc._invalidate_http_client.call_args_list == [call()]
    rpc.url = 'foo://a:b@bar:456/baz'
    assert rpc.url.with_auth == 'foo://a:b@bar:456/baz'
    assert rpc._invalidate_http_client.call_args_list == [call(), call()]


@pytest.mark.parametrize('attribute', ('scheme', 'host', 'port', 'path', 'username', 'password'))
def test_proxy_url(attribute, mocker):
    rpc = MockRPC()
    mocker.patch.object(rpc, '_invalidate_http_client')
    assert rpc.proxy_url is None
    assert rpc._invalidate_http_client.call_args_list == []

    rpc.proxy_url = 'foo://a:b@bar:456/baz'
    assert rpc.proxy_url.with_auth == 'foo://a:b@bar:456/baz'
    assert rpc._invalidate_http_client.call_args_list == [call()]

    setattr(rpc.proxy_url, attribute, '123')
    assert getattr(rpc.proxy_url, attribute) == '123'
    assert rpc._invalidate_http_client.call_args_list == [call(), call()]

    rpc.proxy_url = None
    assert rpc.proxy_url is None
    assert rpc._invalidate_http_client.call_args_list == [call(), call(), call()]


def test_status():
    rpc = MockRPC()
    assert rpc.status is _utils.ConnectionStatus.disconnected
    rpc._status = _utils.ConnectionStatus.connected
    assert rpc.status is _utils.ConnectionStatus.connected


@pytest.mark.parametrize('name', ('connecting', 'connected', 'disconnected'))
def test_callback(name):
    cb = Mock()
    rpc = MockRPC()

    with pytest.raises(AssertionError):
        getattr(rpc, f'on_{name}')('not callable')

    getattr(rpc, f'on_{name}')(cb, 'foo', bar='baz')
    rpc._call_callback(name)
    assert cb.call_args_list == [call('foo', bar='baz')]


def test_connection_lock():
    rpc = MockRPC()
    for _ in range(3):
        assert rpc._connection_lock is rpc._connection_lock


@pytest.mark.parametrize(
    argnames='raised_exception, exp_exception',
    argvalues=(
        (None, None),
        (asyncio.TimeoutError('Timeout'), _errors.TimeoutError(f'Timeout after {_utils.DEFAULT_TIMEOUT} seconds')),
        (_errors.RPCError('No dice'), _errors.RPCError('No dice')),
        (RuntimeError('Unexpected error'), RuntimeError('Unexpected error')),
    ),
    ids=lambda v: str(v),
)
@pytest.mark.asyncio
async def test_connect(raised_exception, exp_exception, mocker):
    rpc = MockRPC()
    cbs = Mock()
    cbs._call_callback = Mock()
    cbs._connect = AsyncMock()
    cbs._disconnect = AsyncMock()
    mocker.patch.object(rpc, '_call_callback', cbs._call_callback)
    mocker.patch.object(rpc, '_connect', cbs._connect)
    mocker.patch.object(rpc, '_disconnect', cbs._disconnect)

    # Connect multiple times concurrently
    connect_calls = (rpc.connect(), rpc.connect())
    # The last connect() call succeeds
    cbs._connect.side_effect = ([raised_exception] * (len(connect_calls) - 1)) + [None]
    if exp_exception:
        with pytest.raises(type(exp_exception), match=rf'^{re.escape(str(exp_exception))}$'):
            await asyncio.gather(*connect_calls)
    else:
        await asyncio.gather(*connect_calls)

    if exp_exception:
        exp_calls_per_connection_attempt = [
            call._call_callback('connecting'),
            call._connect(),
            call._disconnect(),
            call._call_callback('disconnected'),
        ]
        assert cbs.mock_calls == (
            exp_calls_per_connection_attempt
            * (len(connect_calls) - 1)
        ) + [
            call._call_callback('connecting'),
            call._connect(),
            call._call_callback('connected'),
        ]
    else:
        assert cbs.mock_calls == [
            call._call_callback('connecting'),
            call._connect(),
            call._call_callback('connected'),
        ]
    assert rpc.status is _utils.ConnectionStatus.connected


@pytest.mark.parametrize('status', (_utils.ConnectionStatus.connected, _utils.ConnectionStatus.connecting))
@pytest.mark.parametrize(
    argnames='raised_exception, exp_exception',
    argvalues=(
        (None, None),
        (asyncio.TimeoutError('Timeout'), _errors.TimeoutError(f'Timeout after {_utils.DEFAULT_TIMEOUT} seconds')),
        (_errors.RPCError('No dice'), _errors.RPCError('No dice')),
        (RuntimeError('Unexpected error'), RuntimeError('Unexpected error')),
    ))
@pytest.mark.asyncio
async def test_disconnect(raised_exception, exp_exception, status, mocker):
    rpc = MockRPC()
    rpc._status = status
    cbs = Mock()
    cbs._call_callback = Mock()
    cbs._disconnect = AsyncMock()
    cbs._close_http_client = AsyncMock()
    mocker.patch.object(rpc, '_call_callback', cbs._call_callback)
    mocker.patch.object(rpc, '_disconnect', cbs._disconnect)
    mocker.patch.object(rpc, '_close_http_client', cbs._close_http_client)

    # Disconnect multiple times concurrently
    disconnect_calls = (rpc.disconnect(), rpc.disconnect(), rpc.disconnect(), rpc.disconnect())
    cbs._disconnect.side_effect = raised_exception
    if exp_exception:
        with pytest.raises(type(exp_exception), match=rf'^{re.escape(str(exp_exception))}$'):
            await asyncio.gather(*disconnect_calls)
    else:
        await asyncio.gather(*disconnect_calls)

    # Disconnecting always succeeds, even if it fails
    assert cbs.mock_calls == [
        call._disconnect(),
        call._close_http_client(),
        call._call_callback('disconnected'),
    ]
    assert rpc.status is _utils.ConnectionStatus.disconnected


@pytest.mark.parametrize(
    argnames='status, exp_connect_calls, raised_exception, exp_exception',
    argvalues=(
        (_utils.ConnectionStatus.connecting, [call()], None, None),
        (_utils.ConnectionStatus.connected, [], None, None),
        (_utils.ConnectionStatus.disconnected, [call()], None, None),
        (_utils.ConnectionStatus.connected, [],
         asyncio.TimeoutError('Timeout'), _errors.TimeoutError(f'Timeout after {_utils.DEFAULT_TIMEOUT} seconds')),
    ),
)
@pytest.mark.asyncio
async def test_call(status, exp_connect_calls, raised_exception, exp_exception, mocker):
    rpc = MockRPC()
    rpc._status = status
    mocker.patch.object(rpc, 'connect', AsyncMock())
    mocker.patch.object(rpc, '_call', AsyncMock(side_effect=raised_exception))

    if exp_exception:
        with pytest.raises(type(exp_exception), match=rf'^{re.escape(str(exp_exception))}$'):
            await rpc.call('foo', bar='baz', x=24)
    else:
        return_value = await rpc.call('foo', bar='baz', x=24)
        assert return_value is rpc._call.return_value
    assert rpc.connect.call_args_list == exp_connect_calls
    assert rpc._call.call_args_list == [call('foo', bar='baz', x=24)]


@pytest.mark.asyncio
async def test_context_manager_behaviour(mocker):
    rpc = MockRPC()
    mocker.patch.object(rpc, 'disconnect', AsyncMock())
    mocker.patch.object(rpc, '_close_http_client', AsyncMock())

    # Context manager is reusable
    for i in range(3):
        assert rpc.disconnect.call_args_list == [call()] * i
        assert rpc._close_http_client.call_args_list == [call()] * i
        async with rpc as target:
            assert target is rpc
        assert rpc.disconnect.call_args_list == [call()] * (i + 1)
        assert rpc._close_http_client.call_args_list == [call()] * (i + 1)


def test_http_headers():
    rpc = MockRPC()
    for i in range(3):
        assert rpc._http_headers is rpc._http_headers

    # Python 3.10 added the attribute name to the error message
    with pytest.raises(AttributeError, match=r"^can't set attribute(?: '_http_headers'|)$"):
        rpc._http_headers = 'asdf'


@pytest.mark.parametrize('client_is_invalidated', (None, False, True))
@pytest.mark.parametrize('client', (None, Mock()))
@pytest.mark.parametrize('proxy_url', (None, 'mock proxy url'))
@pytest.mark.asyncio
async def test_get_http_client(client_is_invalidated, client, proxy_url, mocker):
    calls = Mock(_close_http_client=AsyncMock())
    rpc = MockRPC()
    if client_is_invalidated is not None:
        rpc._http_client_is_invalidated = client_is_invalidated
    if client:
        rpc._http_client = client
    mocker.patch.object(rpc, '_close_http_client', calls._close_http_client)
    mocker.patch('aiobtclientrpc._utils.create_http_client', calls.create_http_client)
    mocker.patch.object(type(rpc), 'proxy_url', PropertyMock(return_value=Mock(with_auth=proxy_url)))

    return_value = await rpc._get_http_client()
    if client_is_invalidated:
        if client:
            assert calls.mock_calls == [
                call._close_http_client(),
            ]
            assert return_value is client
        else:
            assert calls.mock_calls == [
                call._close_http_client(),
                call.create_http_client(
                    auth=(rpc.url.username, rpc.url.password),
                    proxy_url=proxy_url,
                ),
            ]
            assert return_value is calls.create_http_client.return_value
    else:
        if client:
            assert calls.mock_calls == []
            assert return_value is client
        else:
            assert calls.mock_calls == [
                call.create_http_client(
                    auth=(rpc.url.username, rpc.url.password),
                    proxy_url=proxy_url,
                ),
            ]
            assert return_value is calls.create_http_client.return_value


@pytest.mark.parametrize('client', (None, Mock(aclose=AsyncMock())))
@pytest.mark.asyncio
async def test_close_http_client(client):
    rpc = MockRPC()
    if client is not None:
        rpc._http_client = client
    await rpc._close_http_client()
    if client is not None:
        assert client.aclose.call_args_list == [call()]
    assert not hasattr(rpc, '_http_client')


@pytest.mark.parametrize(
    argnames='has_client, exp_http_client_is_invalidated',
    argvalues=(
        (False, None),
        (True, True),
    ),
)
def test_invalidate_http_client(has_client, exp_http_client_is_invalidated):
    rpc = MockRPC()
    if has_client:
        rpc._http_client = Mock()
    rpc._invalidate_http_client()
    if not exp_http_client_is_invalidated:
        assert not hasattr(rpc, '_http_client_is_invalidated')
    else:
        assert rpc._http_client_is_invalidated is True

    assert rpc.status is _utils.ConnectionStatus.disconnected


@pytest.mark.asyncio
async def test_send_post_request(mocker):
    rpc = MockRPC()
    client = Mock(post=Mock())
    mocker.patch.object(rpc, '_get_http_client', AsyncMock(return_value=client))
    catch_http_exceptions_mock = mocker.patch('aiobtclientrpc._utils.catch_http_exceptions', AsyncMock())
    rpc._http_headers['foo'] = 'bar'

    return_value = await rpc._send_post_request(
        url='mock url',
        data='mock data',
        files='mock files',
    )

    assert return_value is catch_http_exceptions_mock.return_value
    assert rpc._get_http_client.call_args_list == [call()]
    assert catch_http_exceptions_mock.call_args_list == [call(client.post.return_value)]
    assert client.post.call_args_list == [call(
        url='mock url',
        headers={'foo': 'bar'},
        data='mock data',
        files='mock files',
    )]