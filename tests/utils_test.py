import asyncio
import re
from unittest.mock import Mock, PropertyMock, call

import httpx
import httpx_socks
import pytest

from aiobtclientrpc import __project_name__, __version__, _errors, _utils

from .common import AsyncMock


@pytest.mark.asyncio
async def test_get_aioloop_with_running_loop(mocker):
    loop = _utils.get_aioloop()
    assert loop.is_running()
    assert isinstance(loop, asyncio.AbstractEventLoop)

def test_get_aioloop_without_running_loop(mocker):
    loop = _utils.get_aioloop()
    assert isinstance(loop, asyncio.AbstractEventLoop)


def test_clients(mocker):
    import aiobtclientrpc  # isort:skip
    assert _utils.clients() == [
        aiobtclientrpc.DelugeRPC,
        aiobtclientrpc.QbittorrentRPC,
        aiobtclientrpc.RtorrentRPC,
        aiobtclientrpc.TransmissionRPC,
    ]


@pytest.mark.parametrize(
    argnames='names, name, args, kwargs, exp_exception',
    argvalues=(
        (('foo', 'bar', 'baz'), 'foo', (1, 2, 3), {'hey': 'ho'}, None),
        (('foo', 'bar', 'baz'), 'bar', (1, 2, 3), {}, None),
        (('foo', 'bar', 'baz'), 'baz', (), {'hey': 'ho'}, None),
        (('foo', 'bar', 'baz'), 'asdf', (), {}, _errors.ValueError('No such client: asdf')),
    ),
)
def test_client(names, name, args, kwargs, exp_exception, mocker):
    def MockRPC(name):
        cls_mock = Mock()
        cls_mock.configure_mock(name=name)
        return cls_mock

    client_clses = [MockRPC(name) for name in names]
    mocker.patch('aiobtclientrpc._utils.clients', return_value=client_clses)

    if exp_exception:
        with pytest.raises(type(exp_exception), match=rf'^{re.escape(str(exp_exception))}$'):
            _utils.client(name, *args, **kwargs)
        for cls in client_clses:
            assert cls.call_args_list == []

    else:
        return_value = _utils.client(name, *args, **kwargs)
        for cls in client_clses:
            if cls.name == name:
                assert return_value is cls.return_value
                assert cls.call_args_list == [call(*args, **kwargs)]
            else:
                assert return_value is not cls.return_value
                assert cls.call_args_list == []


def test_ConnectionStatus():
    assert _utils.ConnectionStatus('connecting') == _utils.ConnectionStatus.connecting
    assert _utils.ConnectionStatus('connected') == _utils.ConnectionStatus.connected
    assert _utils.ConnectionStatus('disconnected') == _utils.ConnectionStatus.disconnected


def test_cached_property():
    expensive_calculation = Mock(return_value='expensive value')

    class Foo:
        @_utils.cached_property
        def bar(self):
            return expensive_calculation('a', 'b', c='see')

    foo = Foo()
    for _ in range(3):
        assert foo.bar == 'expensive value'
        assert expensive_calculation.call_args_list == [call('a', 'b', c='see')]


def make_url_parts(url):
    return {name: getattr(url, name)
            for name in ('scheme', 'host', 'port', 'path', 'username', 'password')}

@pytest.mark.parametrize(
    argnames='url, default_scheme, exp_parts_or_exception',
    argvalues=(
        # No scheme without path
        ('localhost', None,
         {'scheme': None, 'host': 'localhost', 'port': None, 'path': None, 'username': None, 'password': None}),
        ('localhost:123', None,
         {'scheme': None, 'host': 'localhost', 'port': '123', 'path': None, 'username': None, 'password': None}),
        ('foo:bar@localhost:123', None,
         {'scheme': None, 'host': 'localhost', 'port': '123', 'path': None, 'username': 'foo', 'password': 'bar'}),
        ('foo:@localhost:123', None,
         {'scheme': None, 'host': 'localhost', 'port': '123', 'path': None, 'username': 'foo', 'password': None}),
        (':bar@localhost:123', None,
         {'scheme': None, 'host': 'localhost', 'port': '123', 'path': None, 'username': None, 'password': 'bar'}),
        ('localhost:arf', None,
         _errors.ValueError('Invalid port')),

        # No scheme with path
        ('localhost/some/path', None,
         {'scheme': None, 'host': 'localhost', 'port': None, 'path': '/some/path', 'username': None, 'password': None}),
        ('localhost:123/some/path', None,
         {'scheme': None, 'host': 'localhost', 'port': '123', 'path': '/some/path', 'username': None, 'password': None}),
        ('foo:bar@localhost:123/some/path', None,
         {'scheme': None, 'host': 'localhost', 'port': '123', 'path': '/some/path', 'username': 'foo', 'password': 'bar'}),
        ('foo:@localhost:123/some/path', None,
         {'scheme': None, 'host': 'localhost', 'port': '123', 'path': '/some/path', 'username': 'foo', 'password': None}),
        (':bar@localhost:123/some/path', None,
         {'scheme': None, 'host': 'localhost', 'port': '123', 'path': '/some/path', 'username': None, 'password': 'bar'}),
        ('localhost:arf/some/path', None,
         _errors.ValueError('Invalid port')),

        # Scheme without path
        ('ftp://localhost', None,
         {'scheme': 'ftp', 'host': 'localhost', 'port': None, 'path': None, 'username': None, 'password': None}),
        ('ftp://localhost:123', None,
         {'scheme': 'ftp', 'host': 'localhost', 'port': '123', 'path': None, 'username': None, 'password': None}),
        ('ftp://foo:bar@localhost:123', None,
         {'scheme': 'ftp', 'host': 'localhost', 'port': '123', 'path': None, 'username': 'foo', 'password': 'bar'}),
        ('ftp://foo:@localhost:123', None,
         {'scheme': 'ftp', 'host': 'localhost', 'port': '123', 'path': None, 'username': 'foo', 'password': None}),
        ('ftp://:bar@localhost:123', None,
         {'scheme': 'ftp', 'host': 'localhost', 'port': '123', 'path': None, 'username': None, 'password': 'bar'}),
        ('ftp://localhost:arf', None,
         _errors.ValueError('Invalid port')),

        # Scheme with path
        ('http://localhost/some/path', None,
         {'scheme': 'http', 'host': 'localhost', 'port': None, 'path': '/some/path', 'username': None, 'password': None}),
        ('http://localhost:123/some/path', None,
         {'scheme': 'http', 'host': 'localhost', 'port': '123', 'path': '/some/path', 'username': None, 'password': None}),
        ('http://foo:bar@localhost:123/some/path', None,
         {'scheme': 'http', 'host': 'localhost', 'port': '123', 'path': '/some/path', 'username': 'foo', 'password': 'bar'}),
        ('http://foo:@localhost:123/some/path', None,
         {'scheme': 'http', 'host': 'localhost', 'port': '123', 'path': '/some/path', 'username': 'foo', 'password': None}),
        ('http://:bar@localhost:123/some/path', None,
         {'scheme': 'http', 'host': 'localhost', 'port': '123', 'path': '/some/path', 'username': None, 'password': 'bar'}),
        ('http://localhost:arf/some/path', None,
         _errors.ValueError('Invalid port')),

        # File system path
        ('file://relative/path', None,
         {'scheme': 'file', 'host': None, 'port': None, 'path': 'relative/path', 'username': None, 'password': None}),
        ('file:///absolute/path', None,
         {'scheme': 'file', 'host': None, 'port': None, 'path': '/absolute/path', 'username': None, 'password': None}),
        ('file://foo:bar@localhost', None,
         {'scheme': 'file', 'host': None, 'port': None, 'path': 'foo:bar@localhost', 'username': None, 'password': None}),
        ('file://localhost:123', None,
         {'scheme': 'file', 'host': None, 'port': None, 'path': 'localhost:123', 'username': None, 'password': None}),
        ('file://localhost:arf', None,
         {'scheme': 'file', 'host': None, 'port': None, 'path': 'localhost:arf', 'username': None, 'password': None}),
        ('localhost', 'file',
         {'scheme': 'file', 'host': None, 'port': None, 'path': 'localhost', 'username': None, 'password': None}),
        ('/absolute/path', None,
         {'scheme': 'file', 'host': None, 'port': None, 'path': '/absolute/path', 'username': None, 'password': None}),

        # Default scheme
        ('foo:bar@localhost:123/some/path', 'socks',
         {'scheme': 'socks', 'host': 'localhost', 'port': '123', 'path': '/some/path', 'username': 'foo', 'password': 'bar'}),
        ('http://foo:bar@localhost:123/some/path', 'socks',
         {'scheme': 'http', 'host': 'localhost', 'port': '123', 'path': '/some/path', 'username': 'foo', 'password': 'bar'}),
    ),
    ids=lambda v: str(v),
)
def test_URL_with_valid_value(url, default_scheme, exp_parts_or_exception):
    def make_url(url, default_scheme):
        if default_scheme:
            return _utils.URL(url, default_scheme=default_scheme)
        else:
            return _utils.URL(url)

    if isinstance(exp_parts_or_exception, Exception):
        exception = exp_parts_or_exception
        with pytest.raises(type(exception), match=rf'^{re.escape(str(exception))}$'):
            make_url(url, default_scheme)

    else:
        url = make_url(url, default_scheme)
        exp_parts = exp_parts_or_exception
        parts = make_url_parts(url)
        assert parts == exp_parts


@pytest.mark.parametrize(
    argnames='url, new_scheme, exp_before, exp_after',
    argvalues=(
        ('this://a:b@localhost:555/some/path', 'that',
         {'scheme': 'this', 'username': 'a', 'password': 'b', 'host': 'localhost', 'port': '555', 'path': '/some/path'},
         {'scheme': 'that', 'username': 'a', 'password': 'b', 'host': 'localhost', 'port': '555', 'path': '/some/path'}),
        ('this://a:b@localhost:555/some/path', 'THAT',
         {'scheme': 'this', 'username': 'a', 'password': 'b', 'host': 'localhost', 'port': '555', 'path': '/some/path'},
         {'scheme': 'that', 'username': 'a', 'password': 'b', 'host': 'localhost', 'port': '555', 'path': '/some/path'}),
        ('this://a:b@localhost:555/some/path','Socks5',
         {'scheme': 'this', 'username': 'a', 'password': 'b', 'host': 'localhost', 'port': '555', 'path': '/some/path'},
         {'scheme': 'socks5', 'username': 'a', 'password': 'b', 'host': 'localhost', 'port': '555', 'path': '/some/path'}),
        ('this://a:b@localhost:555/some/path', 123,
         {'scheme': 'this', 'username': 'a', 'password': 'b', 'host': 'localhost', 'port': '555', 'path': '/some/path'},
         {'scheme': '123', 'username': 'a', 'password': 'b', 'host': 'localhost', 'port': '555', 'path': '/some/path'}),
        ('this://a:b@localhost:555/some/path', False,
         {'scheme': 'this', 'username': 'a', 'password': 'b', 'host': 'localhost', 'port': '555', 'path': '/some/path'},
         {'scheme': None, 'username': 'a', 'password': 'b', 'host': 'localhost', 'port': '555', 'path': '/some/path'}),
        ('this://a:b@localhost:555/some/path', 'file',
         {'scheme': 'this', 'username': 'a', 'password': 'b', 'host': 'localhost', 'port': '555', 'path': '/some/path'},
         {'scheme': 'file', 'username': None, 'password': None, 'host': None, 'port': None, 'path': 'a:b@localhost:555/some/path'}),
    ),
)
def test_URL_scheme(url, new_scheme, exp_before, exp_after):
    cb = Mock()
    url = _utils.URL(url, on_change=cb)
    assert cb.call_args_list == []
    assert make_url_parts(url) == exp_before
    url.scheme = new_scheme
    assert make_url_parts(url) == exp_after
    assert cb.call_args_list == [call()]


@pytest.mark.parametrize(
    argnames='url, host, exp_host',
    argvalues=(
        ('this://a:b@localhost:555/some/path', 'nonlocalhost', 'nonlocalhost'),
        ('this://a:b@localhost:555/some/path', '127.0.0.1', '127.0.0.1'),
        ('this://a:b@localhost:555/some/path', 123, '123'),
        ('this://a:b@localhost:555/some/path', None, None),
        ('this://a:b@localhost:555/some/path', False, None),
        ('this://a:b@localhost:555/some/path', True, 'True'),
        ('file:///some/path', 'the.host', None),
    ),
)
def test_URL_host(url, host, exp_host):
    cb = Mock()
    url = _utils.URL(url, on_change=cb)
    assert url.host == _utils.URL(url).host
    assert cb.call_args_list == []
    url.host = host
    assert url.host == exp_host
    assert cb.call_args_list == [call()]


@pytest.mark.parametrize(
    argnames='url, port, exp_port, exp_exception',
    argvalues=(
        ('this://a:b@localhost:555/some/path', -1, None, _errors.ValueError('Invalid port')),
        ('this://a:b@localhost:555/some/path', 0, None, None),
        ('this://a:b@localhost:555/some/path', None, None, None),
        ('this://a:b@localhost:555/some/path', False, None, None),
        ('this://a:b@localhost:555/some/path', -1, None, _errors.ValueError('Invalid port')),
        ('this://a:b@localhost:555/some/path', '-1', None, _errors.ValueError('Invalid port')),
        ('this://a:b@localhost:555/some/path', 1, '1', None),
        ('this://a:b@localhost:555/some/path', '1', '1', None),
        ('this://a:b@localhost:555/some/path', 65535, '65535', None),
        ('this://a:b@localhost:555/some/path', '65535', '65535', None),
        ('this://a:b@localhost:555/some/path', 65536, None, _errors.ValueError('Invalid port')),
        ('this://a:b@localhost:555/some/path', '65536', None, _errors.ValueError('Invalid port')),
        ('this://a:b@localhost:555/some/path', 'foo', None, _errors.ValueError('Invalid port')),
        ('file:///some/path', 1234, None, None),
    ),
)
def test_URL_port(url, port, exp_port, exp_exception):
    original_port = _utils.URL(url).port
    cb = Mock()
    url = _utils.URL(url, on_change=cb)
    assert cb.call_args_list == []
    assert url.port == original_port
    if exp_exception:
        with pytest.raises(type(exp_exception), match=rf'^{re.escape(str(exp_exception))}$'):
            url.port = port
        assert url.port == original_port
        assert cb.call_args_list == []
    else:
        url.port = port
        assert url.port == exp_port
        assert cb.call_args_list == [call()]


@pytest.mark.parametrize(
    argnames='url, path, exp_path',
    argvalues=(
        ('this://a:b@localhost:555/initial/path', 'path', 'path'),
        ('this://a:b@localhost:555/initial/path', '/path', '/path'),
        ('this://a:b@localhost:555/initial/path', '/more/path', '/more/path'),
        ('this://a:b@localhost:555/initial/path', 123, '123'),
        ('file:///some/path', 'another/path', 'another/path'),
    ),
)
def test_URL_path(url, path, exp_path):
    original_path = _utils.URL(url).path
    cb = Mock()
    url = _utils.URL(url, on_change=cb)
    assert cb.call_args_list == []
    assert url.path == original_path
    url.path = path
    assert url.path == exp_path
    assert cb.call_args_list == [call()]


@pytest.mark.parametrize(
    argnames='url, username, exp_username',
    argvalues=(
        ('this://a:b@localhost:555/some/path', 'foo', 'foo'),
        ('this://a:b@localhost:555/some/path', 'Foo', 'Foo'),
        ('this://a:b@localhost:555/some/path', 123, '123'),
        ('file:///some/path', 'Asdf', None),
    ),
)
def test_URL_username(url, username, exp_username):
    original_username = _utils.URL(url).username
    cb = Mock()
    url = _utils.URL(url, on_change=cb)
    assert cb.call_args_list == []
    assert url.username == original_username
    url.username = username
    assert url.username == exp_username
    assert cb.call_args_list == [call()]


@pytest.mark.parametrize(
    argnames='url, password, exp_password',
    argvalues=(
        ('this://a:b@localhost:555/some/path', 'foo', 'foo'),
        ('this://a:b@localhost:555/some/path', 'Foo', 'Foo'),
        ('this://a:b@localhost:555/some/path', 123, '123'),
        ('file:///some/path', 'ASDF', None),
    ),
)
def test_URL_password(url, password, exp_password):
    original_password = _utils.URL(url).password
    cb = Mock()
    url = _utils.URL(url, on_change=cb)
    assert cb.call_args_list == []
    assert url.password == original_password
    url.password = password
    assert url.password == exp_password
    assert cb.call_args_list == [call()]


@pytest.mark.parametrize('path, exp_path', (('', ''), ('/some/path', '/some/path')))
@pytest.mark.parametrize('port, exp_port', (('', ''), (':123', ':123')))
@pytest.mark.parametrize(
    argnames='url, exp_url',
    argvalues=(
        ('http://a:b@localhost{port}{path}', 'http://localhost{exp_port}{exp_path}'),
        ('http://:b@localhost{port}{path}', 'http://localhost{exp_port}{exp_path}'),
        ('http://a:@localhost{port}{path}', 'http://localhost{exp_port}{exp_path}'),
        ('http://:@localhost{port}{path}', 'http://localhost{exp_port}{exp_path}'),
        ('http://localhost{port}{path}', 'http://localhost{exp_port}{exp_path}'),

        # For file:// URLs, "username:password@" has no special meaning
        ('file://a:b@localhost{port}{path}', 'file://a:b@localhost{exp_port}{exp_path}'),
        ('file://:b@localhost{port}{path}', 'file://:b@localhost{exp_port}{exp_path}'),
        ('file://a:@localhost{port}{path}', 'file://a:@localhost{exp_port}{exp_path}'),
        ('file://:@localhost{port}{path}', 'file://:@localhost{exp_port}{exp_path}'),
        ('file://localhost{port}{path}', 'file://localhost{exp_port}{exp_path}'),
    ),
)
def test_URL_without_auth(url, exp_url, port, exp_port, path, exp_path):
    url = _utils.URL(url.format(port=port, path=path))
    url_without_auth = url.without_auth
    exp_url_without_auth = exp_url.format(exp_port=exp_port, exp_path=exp_path)
    assert url_without_auth == exp_url_without_auth


@pytest.mark.parametrize('path, exp_path', (('', ''), ('/some/path', '/some/path')))
@pytest.mark.parametrize('port, exp_port', (('', ''), (':123', ':123')))
@pytest.mark.parametrize(
    argnames='url, exp_url',
    argvalues=(
        ('http://a:b@localhost{port}{path}', 'http://a:b@localhost{exp_port}{exp_path}'),
        ('http://:b@localhost{port}{path}', 'http://:b@localhost{exp_port}{exp_path}'),
        ('http://a:@localhost{port}{path}', 'http://a:@localhost{exp_port}{exp_path}'),
        ('http://:@localhost{port}{path}', 'http://localhost{exp_port}{exp_path}'),
        ('http://localhost{port}{path}', 'http://localhost{exp_port}{exp_path}'),

        # For file:// URLs, "username:password@" has no special meaning
        ('file://a:b@localhost{port}{path}', 'file://a:b@localhost{exp_port}{exp_path}'),
        ('file://:b@localhost{port}{path}', 'file://:b@localhost{exp_port}{exp_path}'),
        ('file://a:@localhost{port}{path}', 'file://a:@localhost{exp_port}{exp_path}'),
        ('file://:@localhost{port}{path}', 'file://:@localhost{exp_port}{exp_path}'),
        ('file://localhost{port}{path}', 'file://localhost{exp_port}{exp_path}'),
    ),
)
def test_URL_with_auth(url, exp_url, port, exp_port, path, exp_path):
    url = _utils.URL(url.format(port=port, path=path))
    url_with_auth = url.with_auth
    exp_url_with_auth = exp_url.format(exp_port=exp_port, exp_path=exp_path)
    assert url_with_auth == exp_url_with_auth


@pytest.mark.parametrize(
    argnames='url1, url2, exp_equal',
    argvalues=(
        ('http://a:b@localhost:1234/some/path', 'http://a:b@localhost:1234/some/path', True),
        ('http://a:b@localhost:1234/some/path', 'http://a:b@localhost:1234/other/path', False),
        ('http://a:b@localhost:1234/some/path', 'http://a:b@localhost:1235/some/path', False),
        ('http://a:b@localhost:1234/some/path', 'http://a:b@localhoft:1234/some/path', False),
        ('http://a:b@localhost:1234/some/path', 'http://a:c@localhost:1234/some/path', False),
        ('http://a:b@localhost:1234/some/path', 'http://c:b@localhost:1234/some/path', False),
        ('http://a:b@localhost:1234/some/path', 'ftp://a:b@localhost:1234/some/path', False),
        ('http://a:b@localhost:1234/some/path', Mock(), NotImplemented),
    ),
)
def test_URL_equality(url1, url2, exp_equal, mocker):
    if exp_equal is True:
        assert _utils.URL(url1) == _utils.URL(url2)
        assert _utils.URL(url1) != url2
        assert url1 != _utils.URL(url2)
    elif exp_equal is False:
        assert _utils.URL(url1) != _utils.URL(url2)
        assert _utils.URL(url1) != url2
        assert url1 != _utils.URL(url2)
    else:
        assert _utils.URL(url1).__eq__(url2) is NotImplemented
        assert _utils.URL(url1).__ne__(url2) is NotImplemented


def test_URL_str(mocker):
    url = _utils.URL('this://localhost')
    mocker.patch.object(type(url), 'without_auth', PropertyMock(return_value='mocked URL'))
    assert str(url) == 'mocked URL'


def test_URL_repr_without_on_change_callback(mocker):
    url = _utils.URL('this://localhost')
    mocker.patch.object(type(url), 'without_auth', PropertyMock(return_value='mocked URL'))
    assert repr(url) == "URL('mocked URL')"

def test_URL_repr_with_on_change_callback(mocker):
    cb = Mock()
    url = _utils.URL('this://localhost', on_change=cb)
    mocker.patch.object(type(url), 'without_auth', PropertyMock(return_value='mocked URL'))
    assert repr(url) == f"URL('mocked URL', on_change={cb!r})"


@pytest.mark.parametrize('proxy_url', (None, 'socks5://foo.bar'))
@pytest.mark.parametrize(
    argnames='username, password',
    argvalues=(
        (None, None),
        ('', ''),
        ('foo', None),
        ('', 'bar'),
        ('foo', 'bar'),
    ),
)
def test_create_http_client(username, password, proxy_url, mocker):
    AsyncClient_mock = mocker.patch('httpx.AsyncClient')
    BasicAuth_mock = mocker.patch('httpx.BasicAuth')
    AsyncProxyTransport_mock = mocker.patch('httpx_socks.AsyncProxyTransport')

    client = _utils.create_http_client(auth=(username, password), proxy_url=proxy_url)
    assert client is AsyncClient_mock.return_value

    exp_AsyncClient_kwargs = {
        'timeout': None,
        'headers': {'User-Agent': f'{__project_name__} {__version__}'},
    }
    if username and password:
        assert BasicAuth_mock.call_args_list == [call(username, password)]
        exp_AsyncClient_kwargs['auth'] = BasicAuth_mock.return_value

    if proxy_url:
        assert AsyncProxyTransport_mock.from_url.call_args_list == [call(proxy_url)]
        exp_AsyncClient_kwargs['transport'] = AsyncProxyTransport_mock.from_url.return_value

    assert AsyncClient_mock.call_args_list == [call(**exp_AsyncClient_kwargs)]


@pytest.mark.parametrize(
    argnames='raised_exception, exp_exception',
    argvalues=(
        (httpx.HTTPError('Fail'), _errors.ConnectionError('Fail')),
        (httpx_socks.ProxyError('Fail'), _errors.ConnectionError('Fail')),
        (ConnectionAbortedError(), _errors.ConnectionError('Connection aborted')),
        (ConnectionRefusedError(), _errors.ConnectionError('Connection refused')),
        (ConnectionResetError(), _errors.ConnectionError('Connection reset')),
        (OSError(123, 'Fail'), _errors.ConnectionError('Fail')),
        (OSError('Fail'), _errors.ConnectionError('Fail')),
        (OSError(), _errors.ConnectionError('Unknown error')),
        (OSError("[Errno 123] Error message ('127.0.0.1', 345, 0, 0)"),
         _errors.ConnectionError('Error message')),
        (OSError("Multiple exceptions: [Errno 123] Error message ('::1', 456, 0, 0), "
                 "[Errno 123] Error message ('127.0.0.1', 456)"),
         _errors.ConnectionError('Error message')),
    ),
    ids=lambda v: str(v),
)
@pytest.mark.asyncio
async def test_catch_connection_exceptions(raised_exception, exp_exception, mocker):
    coro_function = AsyncMock(side_effect=raised_exception)
    if exp_exception:
        with pytest.raises(type(exp_exception), match=rf'^{re.escape(str(exp_exception))}$'):
            await _utils.catch_connection_exceptions(coro_function())
    else:
        return_value = await _utils.catch_connection_exceptions(coro_function())
        assert return_value is coro_function.return_value
