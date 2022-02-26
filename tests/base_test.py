import asyncio
import re
from unittest.mock import Mock, PropertyMock, call

import pytest

from aiobtclientrpc import _base, _errors, _utils

from .common import AsyncMock


class MockURL(_utils.URL):
    pass


class MockRPC(_base.RPCBase):
    name = 'mockbt'
    label = 'MockBT'
    URL = MockURL

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
        ('foo', None, _errors.ValueError('Invalid timeout')),
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
    assert isinstance(rpc.url, MockURL)
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


@pytest.mark.parametrize('kwargs', ({}, {'foo': 'bar'}))
@pytest.mark.parametrize('args', ((), (1, 2, 3)))
@pytest.mark.parametrize('name', ('connecting', 'connected', 'disconnected'))
def test_connection_callbacks(name, args, kwargs):
    rpc = MockRPC()

    with pytest.raises(AssertionError):
        getattr(rpc, f'set_{name}_callback')('not callable')
    with pytest.raises(AssertionError):
        getattr(rpc, f'unset_{name}_callback')('not callable')

    # Register callback
    callbacks = (Mock(), Mock(), Mock())
    for cb in callbacks:
        getattr(rpc, f'set_{name}_callback')(cb, *args, **kwargs)

    # Call all available callbacks
    rpc._call_connection_callbacks(name)
    others = [n for n in ('connecting', 'connected', 'disconnected') if n != name]
    for other in others:
        rpc._call_connection_callbacks(other)

    assert callbacks[0].call_args_list == [call(*args, **kwargs)]
    assert callbacks[1].call_args_list == [call(*args, **kwargs)]
    assert callbacks[2].call_args_list == [call(*args, **kwargs)]

    # Deregister callback
    getattr(rpc, f'unset_{name}_callback')(callbacks[1])

    # Call all available callbacks
    rpc._call_connection_callbacks(name)
    others = [n for n in ('connecting', 'connected', 'disconnected') if n != name]
    for other in others:
        rpc._call_connection_callbacks(other)

    assert callbacks[0].call_args_list == [call(*args, **kwargs), call(*args, **kwargs)]
    assert callbacks[1].call_args_list == [call(*args, **kwargs)]
    assert callbacks[2].call_args_list == [call(*args, **kwargs), call(*args, **kwargs)]


def test_connection_lock():
    rpc = MockRPC()
    for _ in range(3):
        assert rpc._connection_lock is rpc._connection_lock


@pytest.mark.parametrize(
    argnames='raised_exception, exp_exception',
    argvalues=(
        (None, None),
        (asyncio.TimeoutError('Timeout'), _errors.TimeoutError(f'Timeout after {_base.RPCBase.default_timeout} seconds')),
        (_errors.RPCError('No dice'), _errors.RPCError('No dice')),
        (RuntimeError('Unexpected error'), RuntimeError('Unexpected error')),
    ),
    ids=lambda v: str(v),
)
@pytest.mark.asyncio
async def test_connect(raised_exception, exp_exception, mocker):
    rpc = MockRPC()
    cbs = Mock()
    cbs._call_connection_callbacks = Mock()
    cbs._connect = AsyncMock()
    cbs._disconnect = AsyncMock()
    mocker.patch.object(rpc, '_call_connection_callbacks', cbs._call_connection_callbacks)
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
            call._call_connection_callbacks('connecting'),
            call._connect(),
            call._disconnect(),
            call._call_connection_callbacks('disconnected'),
        ]
        assert cbs.mock_calls == (
            exp_calls_per_connection_attempt
            * (len(connect_calls) - 1)
        ) + [
            call._call_connection_callbacks('connecting'),
            call._connect(),
            call._call_connection_callbacks('connected'),
        ]
    else:
        assert cbs.mock_calls == [
            call._call_connection_callbacks('connecting'),
            call._connect(),
            call._call_connection_callbacks('connected'),
        ]
    assert rpc.status is _utils.ConnectionStatus.connected


@pytest.mark.parametrize('status', (
    _utils.ConnectionStatus.connecting,
    _utils.ConnectionStatus.connected,
    _utils.ConnectionStatus.disconnected,
), ids=lambda v: str(v),
)
@pytest.mark.parametrize(
    argnames='raised_exception, exp_exception',
    argvalues=(
        (None, None),
        (asyncio.TimeoutError('Timeout'), _errors.TimeoutError(f'Timeout after {_base.RPCBase.default_timeout} seconds')),
        (_errors.ConnectionError('Connection lost'), _errors.ConnectionError('Connection lost')),
        (_errors.AuthenticationError('Password was changed'), _errors.AuthenticationError('Password was changed')),
        (_errors.RPCError('No dice'), _errors.RPCError('No dice')),
        (RuntimeError('Unexpected error'), RuntimeError('Unexpected error')),
    ),
    ids=lambda v: str(v),
)
@pytest.mark.asyncio
async def test_disconnect(raised_exception, exp_exception, status, mocker):
    rpc = MockRPC()
    rpc._status = status
    cbs = Mock()
    cbs._call_connection_callbacks = Mock()
    cbs._disconnect = AsyncMock()
    cbs._close_http_client = AsyncMock()
    mocker.patch.object(rpc, '_call_connection_callbacks', cbs._call_connection_callbacks)
    mocker.patch.object(rpc, '_disconnect', cbs._disconnect)
    mocker.patch.object(rpc, '_close_http_client', cbs._close_http_client)

    # Disconnect multiple times concurrently
    disconnect_calls = (rpc.disconnect(), rpc.disconnect(), rpc.disconnect(), rpc.disconnect())
    cbs._disconnect.side_effect = raised_exception
    if exp_exception and status is not _utils.ConnectionStatus.disconnected:
        with pytest.raises(type(exp_exception), match=rf'^{re.escape(str(exp_exception))}$'):
            await asyncio.gather(*disconnect_calls)
    else:
        await asyncio.gather(*disconnect_calls)

    if status is _utils.ConnectionStatus.disconnected:
        # We were already disconnected, but because we are thorough, we made
        # extra sure the HTTP client was closed.
        assert cbs.mock_calls == [
            call._close_http_client(),
        ] * len(disconnect_calls)

    else:
        # _disconnect() and the callback are only called if we weren't already
        # disconnected. The first rpc.disconnect() did the trick and the others
        # just closed the client (which should do nothing if it's already
        # closed).
        assert cbs.mock_calls == [
            call._disconnect(),
            call._call_connection_callbacks('disconnected'),
            call._close_http_client(),
        ] + ([call._close_http_client()] * (len(disconnect_calls) - 1))

    assert rpc.status is _utils.ConnectionStatus.disconnected


@pytest.mark.parametrize(
    argnames='status, exp_connect_calls, raised_exception, exp_exception',
    argvalues=(
        (_utils.ConnectionStatus.connecting, [call()], None, None),
        (_utils.ConnectionStatus.connected, [], None, None),
        (_utils.ConnectionStatus.disconnected, [call()], None, None),
        (_utils.ConnectionStatus.connected, [],
         asyncio.TimeoutError('Timeout'), _errors.TimeoutError(f'Timeout after {_base.RPCBase.default_timeout} seconds')),
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
async def test_set_event_handler_only_accepts_callable_handlers(mocker):
    rpc = MockRPC()
    mocker.patch.object(rpc, '_subscribe', AsyncMock())
    with pytest.raises(AssertionError, match='^not callable$'):
        await rpc.set_event_handler('foo', 'not callable')
    assert rpc._subscribe.call_args_list == []
    assert rpc._event_handlers == {}

@pytest.mark.asyncio
async def test_set_event_handler_subscribes_to_event(mocker):
    rpc = MockRPC()
    mocker.patch.object(rpc, '_subscribe', AsyncMock())
    await rpc.set_event_handler('foo', Mock())
    assert rpc._subscribe.call_args_list == [call('foo')]
    await rpc.set_event_handler('bar', Mock())
    assert rpc._subscribe.call_args_list == [call('foo'), call('bar')]
    await rpc.set_event_handler('foo', Mock())
    assert rpc._subscribe.call_args_list == [call('foo'), call('bar')]
    await rpc.set_event_handler('bar', Mock())
    assert rpc._subscribe.call_args_list == [call('foo'), call('bar')]
    await rpc.set_event_handler('baz', Mock())
    assert rpc._subscribe.call_args_list == [call('foo'), call('bar'), call('baz')]

@pytest.mark.asyncio
async def test_set_event_handler_associates_handler_with_event(mocker):
    rpc = MockRPC()
    mocker.patch.object(rpc, '_subscribe', AsyncMock())
    rpc._event_handlers.clear()
    handler1, handler2 = Mock(), Mock()

    await rpc.set_event_handler('foo', handler1)
    assert rpc._event_handlers == {'foo': [handler1]}
    await rpc.set_event_handler('foo', handler2)
    assert rpc._event_handlers == {'foo': [handler1, handler2]}
    await rpc.set_event_handler('foo', handler1)
    assert rpc._event_handlers == {'foo': [handler1, handler2]}
    await rpc.set_event_handler('bar', handler1)
    assert rpc._event_handlers == {'foo': [handler1, handler2], 'bar': [handler1]}
    await rpc.set_event_handler('bar', handler2)
    assert rpc._event_handlers == {'foo': [handler1, handler2], 'bar': [handler1, handler2]}
    await rpc.set_event_handler('bar', handler2)
    assert rpc._event_handlers == {'foo': [handler1, handler2], 'bar': [handler1, handler2]}


@pytest.mark.asyncio
async def test_unset_event_handler(mocker):
    rpc = MockRPC()
    mocker.patch.object(rpc, '_unsubscribe', AsyncMock())
    handler1, handler2, handler_ = Mock(), Mock(), Mock()
    rpc._event_handlers.clear()
    rpc._event_handlers.update({'foo': [handler1, handler2], 'bar': [handler2]})

    await rpc.unset_event_handler('foo', handler_)
    assert rpc._event_handlers == {'foo': [handler1, handler2], 'bar': [handler2]}
    assert rpc._unsubscribe.call_args_list == []

    await rpc.unset_event_handler('bar', handler_)
    assert rpc._event_handlers == {'foo': [handler1, handler2], 'bar': [handler2]}
    assert rpc._unsubscribe.call_args_list == []

    await rpc.unset_event_handler('foo', handler1)
    assert rpc._event_handlers == {'foo': [handler2], 'bar': [handler2]}
    assert rpc._unsubscribe.call_args_list == []

    await rpc.unset_event_handler('foo', handler2)
    assert rpc._event_handlers == {'bar': [handler2]}
    assert rpc._unsubscribe.call_args_list == [call('foo')]

    await rpc.unset_event_handler('bar', handler2)
    assert rpc._event_handlers == {}
    assert rpc._unsubscribe.call_args_list == [call('foo'), call('bar')]


@pytest.mark.asyncio
async def test_emit_event(mocker):
    rpc = MockRPC()
    mocker.patch.object(rpc, '_unsubscribe', AsyncMock())
    mocks = Mock()
    mocks.handler1 = Mock()
    mocks.handler2 = AsyncMock()
    mocks.handler3 = Mock()
    mocks.handler4 = AsyncMock()
    rpc._event_handlers.clear()
    rpc._event_handlers.update({
        'foo': [mocks.handler1, mocks.handler2],
        'bar': [mocks.handler3, mocks.handler4],
    })

    await rpc._emit_event('foo', (1, 2, 3), {'this': 'that'})
    assert mocks.mock_calls == [
        call.handler1(1, 2, 3, this='that'),
        call.handler2(1, 2, 3, this='that'),
    ]
    mocks.reset_mock()
    await rpc._emit_event('bar', (4, 5, 6), {'hey': 'ho'})
    assert mocks.mock_calls == [
        call.handler3(4, 5, 6, hey='ho'),
        call.handler4(4, 5, 6, hey='ho'),
    ]


def test_event_handlers(mocker):
    rpc = MockRPC()
    assert rpc._event_handlers is rpc._event_handlers


@pytest.mark.asyncio
async def test_subscribe(mocker):
    rpc = MockRPC()
    with pytest.raises(NotImplementedError, match=rf'^Events are not supported for {rpc.label}$'):
        await rpc._subscribe('asdf')


@pytest.mark.asyncio
async def test_unsubscribe(mocker):
    rpc = MockRPC()
    with pytest.raises(NotImplementedError, match=rf'^Events are not supported for {rpc.label}$'):
        await rpc._unsubscribe('asdf')


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


@pytest.mark.parametrize(
    argnames='data, exp_kwargs',
    argvalues=(
        (None, {'data': None, 'content': None}),
        ({'foo': 'bar'}, {'data': {'foo': 'bar'}, 'content': None}),
        (['foo', 'bar'], {'data': None, 'content': ['foo', 'bar']}),
        ('foo bar', {'data': None, 'content': 'foo bar'}),
    ),
    ids=lambda v: str(v),
)
@pytest.mark.asyncio
async def test_send_post_request(data, exp_kwargs, mocker):
    rpc = MockRPC()
    client = Mock(post=Mock())
    mocker.patch.object(rpc, '_get_http_client', AsyncMock(return_value=client))
    catch_connection_exceptions_mock = mocker.patch('aiobtclientrpc._utils.catch_connection_exceptions', AsyncMock())
    rpc._http_headers['foo'] = 'bar'

    return_value = await rpc._send_post_request(
        url='mock url',
        data=data,
        files='mock files',
    )

    assert return_value is catch_connection_exceptions_mock.return_value
    assert rpc._get_http_client.call_args_list == [call()]
    assert catch_connection_exceptions_mock.call_args_list == [call(client.post.return_value)]
    assert client.post.call_args_list == [call(
        url='mock url',
        headers={'foo': 'bar'},
        files='mock files',
        **exp_kwargs,
    )]
