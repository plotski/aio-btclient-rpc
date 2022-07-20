import re
from unittest.mock import Mock, call

import pytest

from aiobtclientrpc import RPCBase, _errors, _transmission, _utils

from .common import AsyncMock, make_url_parts


@pytest.mark.parametrize(
    argnames='url, exp',
    argvalues=(
        ('',
         {'scheme': 'http', 'host': 'localhost', 'port': '9091', 'path': '/transmission/rpc', 'username': None, 'password': None}),
        ('myhost',
         {'scheme': 'http', 'host': 'myhost', 'port': '9091', 'path': '/transmission/rpc', 'username': None, 'password': None}),
        ('myhost:123',
         {'scheme': 'http', 'host': 'myhost', 'port': '123', 'path': '/transmission/rpc', 'username': None, 'password': None}),
        ('myhost:123/my/path',
         {'scheme': 'http', 'host': 'myhost', 'port': '123', 'path': '/my/path', 'username': None, 'password': None}),
        ('myhost/my/path',
         {'scheme': 'http', 'host': 'myhost', 'port': '9091', 'path': '/my/path', 'username': None, 'password': None}),
        ('foo:bar@myhost',
         {'scheme': 'http', 'host': 'myhost', 'port': '9091', 'path': '/transmission/rpc', 'username': 'foo', 'password': 'bar'}),
        ('foo:bar@myhost:123',
         {'scheme': 'http', 'host': 'myhost', 'port': '123', 'path': '/transmission/rpc', 'username': 'foo', 'password': 'bar'}),
        ('https://myhost',
         {'scheme': 'https', 'host': 'myhost', 'port': '9091', 'path': '/transmission/rpc', 'username': None, 'password': None}),
        ('file://myhost',
         _errors.ValueError('Scheme must be "http" or "https"')),
    ),
    ids=lambda v: str(v),
)
def test_TransmissionURL(url, exp):
    if isinstance(exp, Exception):
        with pytest.raises(type(exp), match=rf'^{re.escape(str(exp))}$'):
            _transmission.TransmissionURL(url)
    else:
        url = _transmission.TransmissionURL(url)
        assert make_url_parts(url) == exp


@pytest.mark.parametrize('url', (None, 'http://a:b@foo:123/custom/path'))
@pytest.mark.parametrize(
    argnames='kwargs',
    argvalues=(
        {},
        {'scheme': 'https'},
        {'host': 'asdf'},
        {'port': '123'},
        {'path': 'some/path'},
        {'username': 'this', 'password': 'that'},
        {'timeout': 123},
        {'proxy_url': 'http://hey:ho@bar:456'},
    ),
    ids=lambda v: str(v),
)
def test_instantiation(kwargs, url):
    if url:
        kwargs['url'] = url
    rpc = _transmission.TransmissionRPC(**kwargs)

    default_url = _utils.URL(_transmission.TransmissionURL.default)
    exp_url = _utils.URL(_transmission.TransmissionURL.default)
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
        _transmission.TransmissionRPC(**kwargs)


@pytest.mark.parametrize(
    argnames='method, tag, parameters, exp_json, exp_exception',
    argvalues=(
        ('foo', None, {}, '{"method": "foo"}', None),
        ('foo', 123.4, {}, '{"method": "foo", "tag": 123}', None),
        ('foo', '123', {}, '{"method": "foo", "tag": 123}', None),
        ('foo', '123.4', {}, '{"method": "foo", "tag": 123}', None),
        ('foo', 123, {'this': 'that'}, '{"method": "foo", "arguments": {"this": "that"}, "tag": 123}', None),
        ('foo', None, {'this': 123}, '{"method": "foo", "arguments": {"this": 123}}', None),
        ('foo', None, {'this': (1, 2, 'three')}, '{"method": "foo", "arguments": {"this": [1, 2, "three"]}}', None),
        ('foo', 'hey', {}, None, _errors.ValueError("Tag must be a number: 'hey'")),
        ('foo', None, {'asdf': Exception()}, None,
         _errors.ValueError("Failed to serialize to JSON: "
                            "{'method': 'foo', 'arguments': {'asdf': Exception()}}")),
    ),
)
@pytest.mark.asyncio
async def test_request_sends_and_receives_expected_data(method, tag, parameters, exp_json, exp_exception, mocker):
    rpc = _transmission.TransmissionRPC()
    mocker.patch.object(rpc, '_send_post_request', AsyncMock(return_value=Mock(status_code=200)))

    if exp_exception:
        with pytest.raises(type(exp_exception), match=rf'^{re.escape(str(exp_exception))}$'):
            await rpc._request(method, tag=tag, **parameters)
        assert rpc._send_post_request.call_args_list == []

    else:
        return_value = await rpc._request(method, tag=tag, **parameters)
        assert return_value is rpc._send_post_request.return_value
        assert rpc._send_post_request.call_args_list == [call(str(rpc.url), data=exp_json)]


@pytest.mark.parametrize(
    argnames='responses, exp_send_request_call_count, exp_exception',
    argvalues=(
        (
            [
                Mock(status_code=_transmission.TransmissionRPC._csrf_error_code,
                     headers={_transmission.TransmissionRPC._csrf_header: 'd34db33f'}),
                Mock(status_code=200),
            ],
            2,
            None
        ),
        (
            [
                Mock(status_code=_transmission.TransmissionRPC._csrf_error_code,
                     headers={_transmission.TransmissionRPC._csrf_header: 'd34db33f'}),
                Mock(status_code=_transmission.TransmissionRPC._csrf_error_code,
                     headers={_transmission.TransmissionRPC._csrf_header: 'd34db33f'},
                     __repr__=Mock(return_value='this should be HTTP status code 200')),
                Mock(status_code=200),
            ],
            2,
            RuntimeError('Unexpected response: this should be HTTP status code 200'),
        ),
        (
            [
                Mock(status_code=_transmission.TransmissionRPC._auth_error_code),
                Mock(status_code=200),
            ],
            1,
            _errors.AuthenticationError('Authentication failed'),
        ),
        (
            [
                Mock(status_code=123, __repr__=Mock(return_value='unexpected HTTP status code')),
            ],
            1,
            RuntimeError('Unexpected response: unexpected HTTP status code'),
        ),
    ),
    ids=lambda v: repr(v),
)
@pytest.mark.asyncio
async def test_request_handles_HTTP_status_codes(responses, exp_send_request_call_count, exp_exception, mocker):
    rpc = _transmission.TransmissionRPC()
    mocker.patch.object(rpc, '_send_post_request', AsyncMock(side_effect=responses))

    if exp_exception:
        with pytest.raises(type(exp_exception), match=rf'^{re.escape(str(exp_exception))}$'):
            await rpc._request('foo')
    else:
        return_value = await rpc._request('foo')
        assert return_value is responses[-1]

    assert rpc._send_post_request.call_args_list == [
        call(str(rpc.url), data='{"method": "foo"}'),
    ] * exp_send_request_call_count


@pytest.mark.asyncio
async def test_connect(mocker):
    rpc = _transmission.TransmissionRPC()
    mocker.patch.object(rpc, '_request', AsyncMock())
    await rpc._connect()
    assert rpc._request.call_args_list == [call('session-stats')]


@pytest.mark.asyncio
async def test_disconnect():
    rpc = _transmission.TransmissionRPC()
    rpc._http_headers.update({'foo': 'bar', 'baz': 123})
    assert rpc._http_headers == {'foo': 'bar', 'baz': 123}
    await rpc._disconnect()
    assert rpc._http_headers == {}


@pytest.mark.parametrize(
    argnames='method, args, kwargs, exp_params, response, exp_exception',
    argvalues=(
        (
            'some_method',
            None,
            {'foo': 'bar'},
            {'foo': 'bar'},
            Mock(json=Mock(side_effect=ValueError()), text='The Error.'),
            _errors.RPCError('Unexpected response: The Error.'),
        ),
        (
            'some_method',
            None,
            {'foo': 'bar'},
            {'foo': 'bar'},
            Mock(json=Mock(return_value={'result': 'no success'})),
            _errors.RPCError('No success'),
        ),
        (
            'some_method',
            None,
            {'foo': 'bar'},
            {'foo': 'bar'},
            Mock(json=Mock(return_value={'result': 'success'})),
            None,
        ),
        (
            'some_method',
            {'impossible-keyword': 'important value', 'hey': 'HO!'},
            {'foo': 'bar', 'hey': 'ho'},
            {'foo': 'bar', 'hey': 'HO!', 'impossible-keyword': 'important value'},
            Mock(json=Mock(return_value={'result': 'success'})),
            None,
        ),
    ),
    ids=lambda v: str(v),
)
@pytest.mark.asyncio
async def test_call(method, args, kwargs, exp_params, response, exp_exception, mocker):
    rpc = _transmission.TransmissionRPC()
    mocker.patch.object(rpc, '_request', AsyncMock(return_value=response))

    if exp_exception:
        with pytest.raises(type(exp_exception), match=rf'^{re.escape(str(exp_exception))}$'):
            await rpc._call(method, args=args, **kwargs)
    else:
        return_value = await rpc._call(method, args=args, **kwargs)
        assert return_value is response.json.return_value

    assert rpc._request.call_args_list == [call(method, **exp_params)]
