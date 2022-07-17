import re
from unittest.mock import Mock, PropertyMock, call

import pytest

from aiobtclientrpc import RPCBase, _errors, _qbittorrent, _utils

from .common import AsyncMock, make_url_parts


@pytest.mark.parametrize(
    argnames='url, exp',
    argvalues=(
        ('',
         {'scheme': 'http', 'host': 'localhost', 'port': '8080', 'path': None, 'username': None, 'password': None}),
        ('myhost',
         {'scheme': 'http', 'host': 'myhost', 'port': '8080', 'path': None, 'username': None, 'password': None}),
        ('myhost:123',
         {'scheme': 'http', 'host': 'myhost', 'port': '123', 'path': None, 'username': None, 'password': None}),
        ('foo:bar@myhost:123',
         {'scheme': 'http', 'host': 'myhost', 'port': '123', 'path': None, 'username': 'foo', 'password': 'bar'}),
        ('https://myhost',
         {'scheme': 'https', 'host': 'myhost', 'port': '8080', 'path': None, 'username': None, 'password': None}),
        ('https://myhost:123',
         {'scheme': 'https', 'host': 'myhost', 'port': '123', 'path': None, 'username': None, 'password': None}),
        ('https://foo:bar@myhost',
         {'scheme': 'https', 'host': 'myhost', 'port': '8080', 'path': None, 'username': 'foo', 'password': 'bar'}),
        ('file://myhost',
         _errors.ValueError('Scheme must be "http" or "https"')),
        ('myhost/foo',
         _errors.ValueError("qBittorrent URLs don't have a path")),
    ),
    ids=lambda v: str(v),
)
def test_QbittorrentURL(url, exp):
    if isinstance(exp, Exception):
        with pytest.raises(type(exp), match=rf'^{re.escape(str(exp))}$'):
            _qbittorrent.QbittorrentURL(url)
    else:
        url = _qbittorrent.QbittorrentURL(url)
        assert make_url_parts(url) == exp


@pytest.mark.parametrize('url', (None, 'http://a:b@foo:123'))
@pytest.mark.parametrize(
    argnames='kwargs',
    argvalues=(
        {},
        {'scheme': 'https'},
        {'host': 'asdf'},
        {'port': '123'},
        {'username': 'this', 'password': 'that'},
        {'timeout': 123},
        {'proxy_url': 'http://hey:ho@bar:456'},
    ),
    ids=lambda v: str(v),
)
def test_instantiation(kwargs, url):
    if url:
        kwargs['url'] = url
    rpc = _qbittorrent.QbittorrentRPC(**kwargs)

    default_url = _utils.URL(_qbittorrent.QbittorrentURL.default)
    exp_url = _utils.URL(_qbittorrent.QbittorrentURL.default)
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
    assert rpc.proxy_url == (_utils.URL(kwargs['proxy_url']) if 'proxy_url' in kwargs else None)

@pytest.mark.parametrize(
    argnames='kwargs, exp_error',
    argvalues=(
        ({'url': 'bar:baz'}, 'Invalid port'),
        ({'port': (1, 2, 3)}, 'Invalid port'),
        ({'timeout': 'never'}, 'Invalid timeout'),
        ({'proxy_url': 'foo://bar:baz'}, 'Invalid port'),
    ),
    ids=lambda v: str(v),
)
def test_instantiation_with_invalid_argument(kwargs, exp_error):
    with pytest.raises(_errors.ValueError, match=rf'^{re.escape(exp_error)}$'):
        _qbittorrent.QbittorrentRPC(**kwargs)


@pytest.mark.parametrize('username', (None, '', 'a'))
@pytest.mark.parametrize('password', (None, '', 'b'))
@pytest.mark.parametrize(
    argnames='response, exp_exception',
    argvalues=(
        (Mock(status_code=403), _errors.AuthenticationError('Too many failed authentication attempts')),
        (Mock(status_code=200, text='Fails.'), _errors.AuthenticationError('Authentication failed')),
        (Mock(status_code=200, text='The Reason.'), _errors.RPCError('The Reason.')),
        (Mock(status_code=123, text='The Reason.'), _errors.RPCError('The Reason.')),
    ),
    ids=lambda v: str(v),
)
@pytest.mark.asyncio
async def test_connect(response, exp_exception, username, password, mocker):
    rpc = _qbittorrent.QbittorrentRPC()
    rpc.url = f'http://{username if username else ""}:{password if password else ""}@foo:123'

    mocker.patch.object(rpc, '_send_post_request', AsyncMock(return_value=response))

    if exp_exception:
        with pytest.raises(type(exp_exception), match=rf'^{re.escape(str(exp_exception))}$'):
            await rpc._connect()
    else:
        # Raises no exception
        await rpc._connect()

    assert rpc._send_post_request.call_args_list == [call(
        url='http://foo:123/api/v2/auth/login',
        data={
            'username': username if username else '',
            'password': password if password else '',
        },
    )]

@pytest.mark.parametrize('is_connected', (True, False))
@pytest.mark.parametrize('exception', (
    None,
    _errors.ConnectionError('Ignored'),
    _errors.TimeoutError('Raised'),
    _errors.AuthenticationError('Raised'),
    RuntimeError('Raised'),
))
@pytest.mark.asyncio
async def test_disconnect(exception, is_connected, mocker):
    rpc = _qbittorrent.QbittorrentRPC()
    rpc.url = 'http://a:b@foo:123'

    mocker.patch.object(type(rpc), 'is_connected', PropertyMock(return_value=is_connected))
    mocker.patch.object(rpc, '_send_post_request', AsyncMock(side_effect=exception))
    if is_connected and exception and not isinstance(exception, _errors.ConnectionError):
        with pytest.raises(type(exception), match=rf'^{re.escape(str(exception))}$'):
            await rpc._disconnect()
    else:
        await rpc._disconnect()

    if is_connected:
        assert rpc._send_post_request.call_args_list == [call(
            'http://foo:123/api/v2/auth/logout',
        )]
    else:
        assert rpc._send_post_request.call_args_list == []


@pytest.mark.parametrize(
    argnames='options, files, kwargs, exp_send_post_request_kwargs',
    argvalues=(
        (None, None, {}, {}),
        ({'dict': 'data'}, {}, {}, {'data': {'dict': 'data'}}),
        ({}, {'the': 'files'}, {}, {'files': {'the': 'files'}}),
        ({}, {}, {'kw': 'data'}, {'data': {'kw': 'data'}}),
        ({'dict': 'data'}, {'the': 'files'}, {},
         {'data': {'dict': 'data'}, 'files': {'the': 'files'}}),
        ({}, {'the': 'files'}, {'kw': 'data'},
         {'data': {'kw': 'data'}, 'files': {'the': 'files'}}),
        ({'dict': 'data', 'more': 'DATA'}, {}, {'kw': 'data', 'more': 'data'},
         {'data': {'kw': 'data', 'more': 'DATA', 'dict': 'data'}}),
        ({'dict': 'data', 'more': 'DATA'}, {'the': 'files'}, {'kw': 'data', 'more': 'data'},
         {'data': {'kw': 'data', 'more': 'DATA', 'dict': 'data'}, 'files': {'the': 'files'}}),
    ),
    ids=lambda v: str(v),
)
@pytest.mark.asyncio
async def test_call_merges_arguments(options, files, kwargs, exp_send_post_request_kwargs, mocker):
    rpc = _qbittorrent.QbittorrentRPC()
    rpc.url = 'http://a:b@foo:123'
    method = 'do_this'

    mocker.patch.object(rpc, '_send_post_request', AsyncMock(
        return_value=Mock(status_code=200, json=Mock(return_value='mock json data')),
    ))

    await rpc._call(method, options=options, files=files, **kwargs)

    assert rpc._send_post_request.call_args_list == [call(
        url=f'http://foo:123/api/v2/{method}',
        **exp_send_post_request_kwargs,
    )]


@pytest.mark.parametrize(
    argnames='response, exp_exception, exp_return_value',
    argvalues=(
        (Mock(status_code=404), _errors.RPCError('Unknown RPC method'), None),
        (Mock(status_code=123, text='The Error.'), _errors.RPCError('The Error.'), None),
        (Mock(status_code=200, text='The Text.', json=Mock(side_effect=ValueError())), None, 'The Text.'),
        (Mock(status_code=200, json=Mock(return_value='The JSON.')), None, 'The JSON.'),
    ),
    ids=lambda v: str(v),
)
@pytest.mark.asyncio
async def test_call_handles_exceptions(response, exp_exception, exp_return_value, mocker):
    rpc = _qbittorrent.QbittorrentRPC()
    rpc.url = 'http://a:b@foo:123'
    method = 'do_this'

    mocker.patch.object(rpc, '_send_post_request', AsyncMock(return_value=response))

    if exp_exception:
        with pytest.raises(type(exp_exception), match=rf'^{re.escape(str(exp_exception))}$'):
            await rpc._call(method)
    else:
        return_value = await rpc._call(method)
        assert return_value is exp_return_value

    assert rpc._send_post_request.call_args_list == [call(
        url=f'http://foo:123/api/v2/{method}',
    )]
