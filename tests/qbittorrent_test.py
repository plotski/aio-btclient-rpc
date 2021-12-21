import re
from unittest.mock import Mock, call

import pytest

from aiobtclientrpc import _errors, _qbittorrent, _utils


class AsyncMock(Mock):
    def __call__(self, *args, **kwargs):
        async def coro(_sup=super()):
            return _sup.__call__(*args, **kwargs)
        return coro()


@pytest.mark.parametrize('url', (None, 'http://a:b@foo:123'))
@pytest.mark.parametrize(
    argnames='kwargs',
    argvalues=(
        {},
        {'scheme': 'asdf'},
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

    exp_url = _utils.URL(_qbittorrent.QbittorrentRPC.default_url)
    default_url = _utils.URL(_qbittorrent.QbittorrentRPC.default_url)
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
    assert rpc.timeout == kwargs.get('timeout', _utils.DEFAULT_TIMEOUT)
    assert rpc.proxy_url == kwargs.get('proxy_url', None)


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

@pytest.mark.parametrize('exception', (None, _errors.ConnectionError('Something')))
@pytest.mark.asyncio
async def test_disconnect(exception, mocker):
    rpc = _qbittorrent.QbittorrentRPC()
    rpc.url = 'http://a:b@foo:123'

    mocker.patch.object(rpc, '_send_post_request', AsyncMock(side_effect=exception))
    if exception:
        with pytest.raises(type(exception), match=rf'^{re.escape(str(exception))}$'):
            await rpc._disconnect()
    else:
        await rpc._disconnect()

    assert rpc._send_post_request.call_args_list == [call(
        'http://foo:123/api/v2/auth/logout',
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
async def test_call(response, exp_exception, exp_return_value, mocker):
    rpc = _qbittorrent.QbittorrentRPC()
    rpc.url = 'http://a:b@foo:123'
    method = 'do_this'
    parameters = {'foo': 'bar'}

    mocker.patch.object(rpc, '_send_post_request', AsyncMock(return_value=response))

    if exp_exception:
        with pytest.raises(type(exp_exception), match=rf'^{re.escape(str(exp_exception))}$'):
            await rpc._call(method, **parameters)
    else:
        return_value = await rpc._call(method, **parameters)
        assert return_value is exp_return_value

    assert rpc._send_post_request.call_args_list == [call(
        f'http://foo:123/api/v2/{method}',
        data=parameters,
    )]
