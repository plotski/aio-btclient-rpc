import re
from unittest.mock import Mock, PropertyMock, call

import httpx
import httpx_socks
import pytest

from aiobtclientrpc import __project_name__, __version__, _errors, _utils


class AsyncMock(Mock):
    def __call__(self, *args, **kwargs):
        async def coro(_sup=super()):
            return _sup.__call__(*args, **kwargs)
        return coro()


def test_clients(mocker):
    import aiobtclientrpc
    assert _utils.clients() == [
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


@pytest.mark.parametrize(
    argnames='url, exp_parts',
    argvalues=(
        # File scheme
        ('file://rel/path', {'scheme': 'file', 'path': 'rel/path'}),
        ('file://rel//dirty/..//path/', {'scheme': 'file', 'path': 'rel//dirty/..//path/'}),
        ('file:///abs/dirty/..//path/', {'scheme': 'file', 'path': '/abs/dirty/..//path/'}),

        # File scheme with username and/or password
        ('file://:bar@rel/path', {'scheme': 'file', 'path': ':bar@rel/path'}),
        ('file://foo:@/abs/path', {'scheme': 'file', 'path': 'foo:@/abs/path'}),
        ('file://foo:bar@rel/path', {'scheme': 'file', 'path': 'foo:bar@rel/path'}),

        # Non-file scheme
        ('http://foo', {'scheme': 'http', 'host': 'foo'}),
        ('http://foo/a/path', {'scheme': 'http', 'host': 'foo', 'path': '/a/path'}),
        ('http://foo//dirty/../path/', {'scheme': 'http', 'host': 'foo', 'path': '/path'}),
        ('http://foo:123', {'scheme': 'http', 'host': 'foo', 'port': '123'}),
        ('http://foo:123/a/path', {'scheme': 'http', 'host': 'foo', 'port': '123', 'path': '/a/path'}),
        ('http://foo:123/dirty/../path/', {'scheme': 'http', 'host': 'foo', 'port': '123', 'path': '/path'}),

        # Non-file scheme with username and/or password
        ('http://a:b@foo', {'scheme': 'http', 'host': 'foo', 'username': 'a', 'password': 'b'}),
        ('http://a:@foo', {'scheme': 'http', 'host': 'foo', 'username': 'a'}),
        ('http://:b@foo', {'scheme': 'http', 'host': 'foo', 'password': 'b'}),
        ('http://a:b@foo/z', {'scheme': 'http', 'host': 'foo', 'path': '/z', 'username': 'a', 'password': 'b'}),
        ('http://a:b@foo:9', {'scheme': 'http', 'host': 'foo', 'port': '9', 'username': 'a', 'password': 'b'}),
        ('http://a:@foo:9', {'scheme': 'http', 'host': 'foo', 'port': '9', 'username': 'a'}),
        ('http://:b@foo:9', {'scheme': 'http', 'host': 'foo', 'port': '9', 'password': 'b'}),
        ('http://a:b@foo:9/z', {'scheme': 'http', 'host': 'foo', 'port': '9', 'path': '/z', 'username': 'a', 'password': 'b'}),

        # No scheme
        ('rel/path', {'scheme': 'file', 'path': 'rel/path'}),
        ('rel//dirty..///path/', {'scheme': 'file', 'path': 'rel//dirty..///path/'}),
        ('/abs/path', {'scheme': 'file', 'path': '/abs/path'}),
        ('/abs/dirty//..//path/', {'scheme': 'file', 'path': '/abs/dirty//..//path/'}),
        ('foo:123', {'scheme': '{default_scheme}', 'host': 'foo', 'port': '123'}),
        ('foo:123/path', {'scheme': '{default_scheme}', 'host': 'foo', 'port': '123', 'path': '/path'}),
        ('foo:123/more/path', {'scheme': '{default_scheme}', 'host': 'foo', 'port': '123', 'path': '/more/path'}),

        # No scheme with username and/or password
        ('a:b@rel/path', {'scheme': 'file', 'path': 'a:b@rel/path'}),
        ('a:@rel/path', {'scheme': 'file', 'path': 'a:@rel/path'}),
        (':b@rel/path', {'scheme': 'file', 'path': ':b@rel/path'}),
        ('a:b@rel//dirty..///path/', {'scheme': 'file', 'path': 'a:b@rel//dirty..///path/'}),
        ('a:@rel//dirty..///path/', {'scheme': 'file', 'path': 'a:@rel//dirty..///path/'}),
        (':b@rel//dirty..///path/', {'scheme': 'file', 'path': ':b@rel//dirty..///path/'}),
        ('a:b@/rel/path', {'scheme': 'file', 'path': 'a:b@/rel/path'}),
        ('a:@/rel/path', {'scheme': 'file', 'path': 'a:@/rel/path'}),
        (':b@/rel/path', {'scheme': 'file', 'path': ':b@/rel/path'}),
        ('a:b@foo:123', {'scheme': '{default_scheme}', 'host': 'foo', 'port': '123', 'username': 'a', 'password': 'b'}),
        ('a:@foo:123', {'scheme': '{default_scheme}', 'host': 'foo', 'port': '123', 'username': 'a'}),
        (':b@foo:123', {'scheme': '{default_scheme}', 'host': 'foo', 'port': '123', 'password': 'b'}),
        ('a:b@foo:123/path', {'scheme': '{default_scheme}', 'host': 'foo', 'port': '123', 'path': '/path', 'username': 'a', 'password': 'b'}),
        ('a:@foo:123/path', {'scheme': '{default_scheme}', 'host': 'foo', 'port': '123', 'path': '/path', 'username': 'a'}),
        (':b@foo:123/path', {'scheme': '{default_scheme}', 'host': 'foo', 'port': '123', 'path': '/path', 'password': 'b'}),
    ),
)
@pytest.mark.parametrize('default_scheme', (None, 'asdf'))
def test_URL_with_valid_value(default_scheme, url, exp_parts):
    if default_scheme:
        url = _utils.URL(url, default_scheme=default_scheme)
    else:
        url = _utils.URL(url)

    attrnames = ('scheme', 'host', 'port', 'path', 'username', 'password')
    parts = {
        name: getattr(url, name)
        for name in attrnames
    }
    exp_parts = {
        name: exp_parts.get(name, None)
        for name in attrnames
    }
    default_scheme = default_scheme or 'http'
    exp_parts['scheme'] = exp_parts['scheme'].format(default_scheme=default_scheme)
    assert parts == exp_parts

@pytest.mark.parametrize(
    argnames='url, exp_exception',
    argvalues=(
        ('http://localhost:65536', _errors.ValueError('Invalid port')),
        ('http://localhost:hello', _errors.ValueError('Invalid port')),
    ),
)
def test_URL_with_invalid_value(url, exp_exception):
    with pytest.raises(type(exp_exception), match=rf'^{re.escape(str(exp_exception))}$'):
        _utils.URL(url)


@pytest.mark.parametrize(
    argnames='scheme, exp_scheme',
    argvalues=(
        ('http', 'http'),
        ('Http', 'http'),
        ('HTTP', 'http'),
        ('Socks5', 'socks5'),
        (123, '123'),
        (False, 'false'),
    ),
)
def test_URL_scheme(scheme, exp_scheme):
    cb = Mock()
    url = _utils.URL('this://a:b@localhost:555/some/path', on_change=cb)
    assert cb.call_args_list == []
    assert url.scheme == 'this'
    url.scheme = scheme
    assert url.scheme == exp_scheme
    assert cb.call_args_list == [call()]


@pytest.mark.parametrize(
    argnames='host, exp_host',
    argvalues=(
        ('127.0.0.1', '127.0.0.1'),
        (123, '123'),
        (None, None),
        (False, None),
        (True, 'True'),
    ),
)
def test_URL_host(host, exp_host):
    cb = Mock()
    url = _utils.URL('this://a:b@localhost:555/some/path', on_change=cb)
    assert cb.call_args_list == []
    assert url.host == 'localhost'
    url.host = host
    assert url.host == exp_host
    assert cb.call_args_list == [call()]


@pytest.mark.parametrize(
    argnames='port, exp_port, exp_exception',
    argvalues=(
        (-1, None, _errors.ValueError('Invalid port')),
        (0, None, None),
        (None, None, None),
        (False, None, None),
        (-1, None, _errors.ValueError('Invalid port')),
        ('-1', None, _errors.ValueError('Invalid port')),
        (1, '1', None),
        ('1', '1', None),
        (65535, '65535', None),
        ('65535', '65535', None),
        (65536, None, _errors.ValueError('Invalid port')),
        ('65536', None, _errors.ValueError('Invalid port')),
        ('foo', None, _errors.ValueError('Invalid port')),
    ),
)
def test_URL_port(port, exp_port, exp_exception):
    cb = Mock()
    url = _utils.URL('this://a:b@localhost:555/some/path', on_change=cb)
    assert cb.call_args_list == []
    assert url.port == '555'
    if exp_exception:
        with pytest.raises(type(exp_exception), match=rf'^{re.escape(str(exp_exception))}$'):
            url.port = port
        assert url.port == '555'
        assert cb.call_args_list == []
    else:
        url.port = port
        assert url.port == exp_port
        assert cb.call_args_list == [call()]


@pytest.mark.parametrize(
    argnames='path, exp_path',
    argvalues=(
        ('path', 'path'),
        ('/path', '/path'),
        ('/more/path', '/more/path'),
        (123, '123'),
    ),
)
def test_URL_path(path, exp_path):
    cb = Mock()
    url = _utils.URL('this://a:b@localhost:555/initial/path', on_change=cb)
    assert cb.call_args_list == []
    assert url.path == '/initial/path'
    url.path = path
    assert url.path == exp_path
    assert cb.call_args_list == [call()]


@pytest.mark.parametrize(
    argnames='username, exp_username',
    argvalues=(
        ('foo', 'foo'),
        ('Foo', 'Foo'),
        (123, '123'),
    ),
)
def test_URL_username(username, exp_username):
    cb = Mock()
    url = _utils.URL('this://a:b@localhost:555/some/path', on_change=cb)
    assert cb.call_args_list == []
    assert url.username == 'a'
    url.username = username
    assert url.username == exp_username
    assert cb.call_args_list == [call()]


@pytest.mark.parametrize(
    argnames='password, exp_password',
    argvalues=(
        ('foo', 'foo'),
        ('Foo', 'Foo'),
        (123, '123'),
    ),
)
def test_URL_password(password, exp_password):
    cb = Mock()
    url = _utils.URL('this://a:b@localhost:555/some/path', on_change=cb)
    assert cb.call_args_list == []
    assert url.password == 'b'
    url.password = password
    assert url.password == exp_password
    assert cb.call_args_list == [call()]


@pytest.mark.parametrize('auth', ('a:b@', ':b@', 'a:@', ''))
@pytest.mark.parametrize(
    argnames='url, exp_url',
    argvalues=(
        ('http://{auth}localhost', 'http://localhost'),
        ('http://{auth}localhost:1234', 'http://localhost:1234'),
        ('http://{auth}localhost/some/path', 'http://localhost/some/path'),
        ('http://{auth}localhost:1234/some/path', 'http://localhost:1234/some/path'),
        ('file://{auth}localhost', 'file://{auth}localhost'),
        ('file://{auth}localhost:1234', 'file://{auth}localhost:1234'),
        ('file://{auth}localhost/some/path', 'file://{auth}localhost/some/path'),
        ('file://{auth}localhost:1234/some/path', 'file://{auth}localhost:1234/some/path'),
    ),
)
def test_URL_without_auth(url, auth, exp_url):
    url = _utils.URL(url.format(auth=auth))
    assert url.without_auth == exp_url.format(auth=auth)
    if auth and not exp_url.startswith('file://'):
        exp_username, exp_password = auth[:-1].split(':')
        assert url.username == (exp_username or None)
        assert url.password == (exp_password or None)
    else:
        assert url.username is None
        assert url.password is None


@pytest.mark.parametrize('auth', ('a:b@', ':b@', 'a:@', ''))
@pytest.mark.parametrize(
    argnames='url, exp_url',
    argvalues=(
        ('http://{auth}localhost', 'http://{auth}localhost'),
        ('http://{auth}localhost:1234', 'http://{auth}localhost:1234'),
        ('http://{auth}localhost/some/path', 'http://{auth}localhost/some/path'),
        ('http://{auth}localhost:1234/some/path', 'http://{auth}localhost:1234/some/path'),
        ('file://{auth}localhost', 'file://{auth}localhost'),
        ('file://{auth}localhost:1234', 'file://{auth}localhost:1234'),
        ('file://{auth}localhost/some/path', 'file://{auth}localhost/some/path'),
        ('file://{auth}localhost:1234/some/path', 'file://{auth}localhost:1234/some/path'),
    ),
)
def test_URL_with_auth(url, auth, exp_url):
    url = _utils.URL(url.format(auth=auth))
    assert url.with_auth == exp_url.format(auth=auth)
    if auth and not exp_url.startswith('file://'):
        exp_username, exp_password = auth[:-1].split(':')
        assert url.username == (exp_username or None)
        assert url.password == (exp_password or None)
    else:
        assert url.username is None
        assert url.password is None


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
        assert _utils.URL(url1) == url2
        assert url1 == _utils.URL(url2)
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
        (OSError('Fail'), _errors.ConnectionError('Fail')),
        (OSError(123, 'Fail'), _errors.ConnectionError('Fail')),
    ),
    ids=lambda v: str(v),
)
@pytest.mark.asyncio
async def test_catch_http_exceptions(raised_exception, exp_exception, mocker):
    coro_function = AsyncMock(side_effect=raised_exception)
    if exp_exception:
        with pytest.raises(type(exp_exception), match=rf'^{re.escape(str(exp_exception))}$'):
            await _utils.catch_http_exceptions(coro_function())
    else:
        return_value = await _utils.catch_http_exceptions(coro_function())
        assert return_value is coro_function.return_value
