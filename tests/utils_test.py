import asyncio
import re
from unittest.mock import Mock, PropertyMock, call

import httpx
import httpx_socks
import pytest

from aiobtclientrpc import __project_name__, __version__, _errors, _utils

from .common import AsyncMock, make_url_parts


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


@pytest.mark.parametrize(
    argnames='url, exp_parts_or_exception',
    argvalues=(
        ('',
         {'scheme': None, 'host': None, 'port': None, 'path': None, 'username': None, 'password': None}),

        # No scheme without path
        ('localhost',
         {'scheme': None, 'host': 'localhost', 'port': None, 'path': None, 'username': None, 'password': None}),
        ('localhost:123',
         {'scheme': None, 'host': 'localhost', 'port': '123', 'path': None, 'username': None, 'password': None}),
        ('foo:bar@localhost:123',
         {'scheme': None, 'host': 'localhost', 'port': '123', 'path': None, 'username': 'foo', 'password': 'bar'}),
        ('foo:@localhost:123',
         {'scheme': None, 'host': 'localhost', 'port': '123', 'path': None, 'username': 'foo', 'password': None}),
        (':bar@localhost:123',
         {'scheme': None, 'host': 'localhost', 'port': '123', 'path': None, 'username': None, 'password': 'bar'}),
        ('localhost:arf',
         _errors.ValueError('Invalid port')),

        # No scheme with path
        ('localhost/some/path',
         {'scheme': None, 'host': 'localhost', 'port': None, 'path': '/some/path', 'username': None, 'password': None}),
        ('localhost:123/some/path',
         {'scheme': None, 'host': 'localhost', 'port': '123', 'path': '/some/path', 'username': None, 'password': None}),
        ('foo:bar@localhost:123/some/path',
         {'scheme': None, 'host': 'localhost', 'port': '123', 'path': '/some/path', 'username': 'foo', 'password': 'bar'}),
        ('foo:@localhost:123/some/path',
         {'scheme': None, 'host': 'localhost', 'port': '123', 'path': '/some/path', 'username': 'foo', 'password': None}),
        (':bar@localhost:123/some/path',
         {'scheme': None, 'host': 'localhost', 'port': '123', 'path': '/some/path', 'username': None, 'password': 'bar'}),
        ('localhost:arf/some/path',
         _errors.ValueError('Invalid port')),

        # Scheme without path
        ('ftp://localhost',
         {'scheme': 'ftp', 'host': 'localhost', 'port': None, 'path': None, 'username': None, 'password': None}),
        ('ftp://localhost:123',
         {'scheme': 'ftp', 'host': 'localhost', 'port': '123', 'path': None, 'username': None, 'password': None}),
        ('ftp://foo:bar@localhost:123',
         {'scheme': 'ftp', 'host': 'localhost', 'port': '123', 'path': None, 'username': 'foo', 'password': 'bar'}),
        ('ftp://foo:@localhost:123',
         {'scheme': 'ftp', 'host': 'localhost', 'port': '123', 'path': None, 'username': 'foo', 'password': None}),
        ('ftp://:bar@localhost:123',
         {'scheme': 'ftp', 'host': 'localhost', 'port': '123', 'path': None, 'username': None, 'password': 'bar'}),
        ('ftp://localhost:arf',
         _errors.ValueError('Invalid port')),

        # Scheme with path
        ('http://localhost/some/path',
         {'scheme': 'http', 'host': 'localhost', 'port': None, 'path': '/some/path', 'username': None, 'password': None}),
        ('http://localhost:123/some/path',
         {'scheme': 'http', 'host': 'localhost', 'port': '123', 'path': '/some/path', 'username': None, 'password': None}),
        ('http://foo:bar@localhost:123/some/path',
         {'scheme': 'http', 'host': 'localhost', 'port': '123', 'path': '/some/path', 'username': 'foo', 'password': 'bar'}),
        ('http://foo:@localhost:123/some/path',
         {'scheme': 'http', 'host': 'localhost', 'port': '123', 'path': '/some/path', 'username': 'foo', 'password': None}),
        ('http://:bar@localhost:123/some/path',
         {'scheme': 'http', 'host': 'localhost', 'port': '123', 'path': '/some/path', 'username': None, 'password': 'bar'}),
        ('http://localhost:arf/some/path',
         _errors.ValueError('Invalid port')),

        # File system path
        ('file://relative/path',
         {'scheme': 'file', 'host': None, 'port': None, 'path': 'relative/path', 'username': None, 'password': None}),
        ('file:///absolute/path',
         {'scheme': 'file', 'host': None, 'port': None, 'path': '/absolute/path', 'username': None, 'password': None}),
        ('file://foo:bar@localhost',
         {'scheme': 'file', 'host': None, 'port': None, 'path': 'foo:bar@localhost', 'username': None, 'password': None}),
        ('file://localhost:123',
         {'scheme': 'file', 'host': None, 'port': None, 'path': 'localhost:123', 'username': None, 'password': None}),
        ('file://localhost:arf',
         {'scheme': 'file', 'host': None, 'port': None, 'path': 'localhost:arf', 'username': None, 'password': None}),
        ('/absolute/path',
         {'scheme': 'file', 'host': None, 'port': None, 'path': '/absolute/path', 'username': None, 'password': None}),
    ),
    ids=lambda v: str(v),
)
def test_URL_parsing(url, exp_parts_or_exception):
    if isinstance(exp_parts_or_exception, Exception):
        exception = exp_parts_or_exception
        with pytest.raises(type(exception), match=rf'^{re.escape(str(exception))}$'):
            _utils.URL(url)
    else:
        url = _utils.URL(url)
        exp_parts = exp_parts_or_exception
        parts = make_url_parts(url)
        assert parts == exp_parts

default_url_testcases = (
    ('foo:bar@localhost:123/some/path', 'socks://x:y@defaulthost:999/default/path',
     {'scheme': 'socks', 'host': 'localhost', 'port': '123', 'path': '/some/path', 'username': 'foo', 'password': 'bar'}),
    ('http://:bar@localhost:123/some/path', 'socks://x:y@defaulthost:999/default/path',
     {'scheme': 'http', 'host': 'localhost', 'port': '123', 'path': '/some/path', 'username': 'x', 'password': 'bar'}),
    ('http://foo:@localhost:123/some/path', 'socks://x:y@defaulthost:999/default/path',
     {'scheme': 'http', 'host': 'localhost', 'port': '123', 'path': '/some/path', 'username': 'foo', 'password': 'y'}),
    ('http://foo:bar@localhost/some/path', 'socks://x:y@defaulthost:999/default/path',
     {'scheme': 'http', 'host': 'localhost', 'port': '999', 'path': '/some/path', 'username': 'foo', 'password': 'bar'}),
    ('http://foo:bar@localhost:123/', 'socks://x:y@defaulthost:999/default/path',
     {'scheme': 'http', 'host': 'localhost', 'port': '123', 'path': '/', 'username': 'foo', 'password': 'bar'}),
    ('http://foo:bar@localhost:123', 'socks://x:y@defaulthost:999/default/path',
     {'scheme': 'http', 'host': 'localhost', 'port': '123', 'path': '/default/path', 'username': 'foo', 'password': 'bar'}),
    ('http://foo:bar@localhost:asdf', None,
     _errors.ValueError('Invalid port')),
)

@pytest.mark.parametrize('url, default_url, exp_parts_or_exception', default_url_testcases)
def test_URL_default_url_attribute(url, default_url, exp_parts_or_exception):
    class MyURL(_utils.URL):
        default = default_url

    if isinstance(exp_parts_or_exception, Exception):
        exception = exp_parts_or_exception
        with pytest.raises(type(exception), match=rf'^{re.escape(str(exception))}$'):
            MyURL(url)
    else:
        url = MyURL(url)
        exp_parts = exp_parts_or_exception
        parts = make_url_parts(url)
        assert parts == exp_parts

@pytest.mark.parametrize('url, default_url, exp_parts_or_exception', default_url_testcases)
def test_URL_default_url_argument(url, default_url, exp_parts_or_exception):
    class MyURL(_utils.URL):
        default = 'not://the:correct@url:111/to/use'

    if isinstance(exp_parts_or_exception, Exception):
        exception = exp_parts_or_exception
        with pytest.raises(type(exception), match=rf'^{re.escape(str(exception))}$'):
            MyURL(url, default=default_url)
    else:
        url = MyURL(url, default=default_url)
        exp_parts = exp_parts_or_exception
        parts = make_url_parts(url)
        assert parts == exp_parts


@pytest.mark.parametrize(
    argnames='url, new_scheme, exp_before, exp_after',
    argvalues=(
        ('this://a:b@localhost:555/some/path', 'that',
         {'scheme': 'this', 'username': 'a', 'password': 'b', 'host': 'localhost', 'port': '555', 'path': '/some/path'},
         {'scheme': 'that', 'username': 'a', 'password': 'b', 'host': 'localhost', 'port': '555', 'path': '/some/path'}),
        ('this://a:b@localhost:555/some/path', 'FILE',
         {'scheme': 'this', 'username': 'a', 'password': 'b', 'host': 'localhost', 'port': '555', 'path': '/some/path'},
         {'scheme': 'file', 'username': 'a', 'password': 'b', 'host': 'localhost', 'port': '555', 'path': '/some/path'}),
        ('this://a:b@localhost:555/some/path','Socks5',
         {'scheme': 'this', 'username': 'a', 'password': 'b', 'host': 'localhost', 'port': '555', 'path': '/some/path'},
         {'scheme': 'socks5', 'username': 'a', 'password': 'b', 'host': 'localhost', 'port': '555', 'path': '/some/path'}),
        ('this://a:b@localhost:555/some/path', 123,
         {'scheme': 'this', 'username': 'a', 'password': 'b', 'host': 'localhost', 'port': '555', 'path': '/some/path'},
         {'scheme': '123', 'username': 'a', 'password': 'b', 'host': 'localhost', 'port': '555', 'path': '/some/path'}),
        ('this://a:b@localhost:555/some/path', False,
         {'scheme': 'this', 'username': 'a', 'password': 'b', 'host': 'localhost', 'port': '555', 'path': '/some/path'},
         {'scheme': None, 'username': 'a', 'password': 'b', 'host': 'localhost', 'port': '555', 'path': '/some/path'}),
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
    argnames='url, new_host, exp_before, exp_after',
    argvalues=(
        ('this://a:b@localhost:555/some/path', '127.0.0.1',
         {'scheme': 'this', 'username': 'a', 'password': 'b', 'host': 'localhost', 'port': '555', 'path': '/some/path'},
         {'scheme': 'this', 'username': 'a', 'password': 'b', 'host': '127.0.0.1', 'port': '555', 'path': '/some/path'}),
        ('this://a:b@localhost:555/some/path', 123,
         {'scheme': 'this', 'username': 'a', 'password': 'b', 'host': 'localhost', 'port': '555', 'path': '/some/path'},
         {'scheme': 'this', 'username': 'a', 'password': 'b', 'host': '123', 'port': '555', 'path': '/some/path'}),
        ('this://a:b@localhost:555/some/path', None,
         {'scheme': 'this', 'username': 'a', 'password': 'b', 'host': 'localhost', 'port': '555', 'path': '/some/path'},
         {'scheme': 'this', 'username': 'a', 'password': 'b', 'host': None, 'port': '555', 'path': '/some/path'}),
        ('this://a:b@localhost:555/some/path', False,
         {'scheme': 'this', 'username': 'a', 'password': 'b', 'host': 'localhost', 'port': '555', 'path': '/some/path'},
         {'scheme': 'this', 'username': 'a', 'password': 'b', 'host': None, 'port': '555', 'path': '/some/path'}),
    ),
)
def test_URL_host(url, new_host, exp_before, exp_after):
    cb = Mock()
    url = _utils.URL(url, on_change=cb)
    assert cb.call_args_list == []
    assert make_url_parts(url) == exp_before
    url.host = new_host
    assert make_url_parts(url) == exp_after
    assert cb.call_args_list == [call()]


@pytest.mark.parametrize(
    argnames='url, new_port, exp_before, exp_after',
    argvalues=(
        ('this://a:b@localhost:555/some/path', 0,
         {'scheme': 'this', 'username': 'a', 'password': 'b', 'host': 'localhost', 'port': '555', 'path': '/some/path'},
         {'scheme': 'this', 'username': 'a', 'password': 'b', 'host': 'localhost', 'port': None, 'path': '/some/path'}),
        ('this://a:b@localhost:555/some/path', 1,
         {'scheme': 'this', 'username': 'a', 'password': 'b', 'host': 'localhost', 'port': '555', 'path': '/some/path'},
         {'scheme': 'this', 'username': 'a', 'password': 'b', 'host': 'localhost', 'port': '1', 'path': '/some/path'}),
        ('this://a:b@localhost:555/some/path', 65535,
         {'scheme': 'this', 'username': 'a', 'password': 'b', 'host': 'localhost', 'port': '555', 'path': '/some/path'},
         {'scheme': 'this', 'username': 'a', 'password': 'b', 'host': 'localhost', 'port': '65535', 'path': '/some/path'}),
        ('this://a:b@localhost:555/some/path', -1,
         {'scheme': 'this', 'username': 'a', 'password': 'b', 'host': 'localhost', 'port': '555', 'path': '/some/path'},
         _errors.ValueError('Invalid port')),
        ('this://a:b@localhost:555/some/path', '-1',
         {'scheme': 'this', 'username': 'a', 'password': 'b', 'host': 'localhost', 'port': '555', 'path': '/some/path'},
         _errors.ValueError('Invalid port')),
        ('this://a:b@localhost:555/some/path', 65536,
         {'scheme': 'this', 'username': 'a', 'password': 'b', 'host': 'localhost', 'port': '555', 'path': '/some/path'},
         _errors.ValueError('Invalid port')),
        ('this://a:b@localhost:555/some/path', 'foo',
         {'scheme': 'this', 'username': 'a', 'password': 'b', 'host': 'localhost', 'port': '555', 'path': '/some/path'},
         _errors.ValueError('Invalid port')),
        ('this://a:b@localhost:555/some/path', None,
         {'scheme': 'this', 'username': 'a', 'password': 'b', 'host': 'localhost', 'port': '555', 'path': '/some/path'},
         {'scheme': 'this', 'username': 'a', 'password': 'b', 'host': 'localhost', 'port': None, 'path': '/some/path'}),
        ('this://a:b@localhost:555/some/path', False,
         {'scheme': 'this', 'username': 'a', 'password': 'b', 'host': 'localhost', 'port': '555', 'path': '/some/path'},
         {'scheme': 'this', 'username': 'a', 'password': 'b', 'host': 'localhost', 'port': None, 'path': '/some/path'}),
    ),
)
def test_URL_port(url, new_port, exp_before, exp_after):
    cb = Mock()
    url = _utils.URL(url, on_change=cb)
    original_port = url.port
    assert cb.call_args_list == []
    assert make_url_parts(url) == exp_before
    if isinstance(exp_after, Exception):
        with pytest.raises(type(exp_after), match=rf'^{re.escape(str(exp_after))}$'):
            url.port = new_port
        assert url.port == original_port
        assert cb.call_args_list == []
    else:
        url.port = new_port
        assert make_url_parts(url) == exp_after
        assert cb.call_args_list == [call()]


@pytest.mark.parametrize(
    argnames='url, new_path, exp_before, exp_after',
    argvalues=(
        ('this://a:b@localhost:555/some/path', 'other/path',
         {'scheme': 'this', 'username': 'a', 'password': 'b', 'host': 'localhost', 'port': '555', 'path': '/some/path'},
         {'scheme': 'this', 'username': 'a', 'password': 'b', 'host': 'localhost', 'port': '555', 'path': 'other/path'}),
        ('this://a:b@localhost:555/some/path', '/other/path',
         {'scheme': 'this', 'username': 'a', 'password': 'b', 'host': 'localhost', 'port': '555', 'path': '/some/path'},
         {'scheme': 'this', 'username': 'a', 'password': 'b', 'host': 'localhost', 'port': '555', 'path': '/other/path'}),
        ('this://a:b@localhost:555/some/path', 123,
         {'scheme': 'this', 'username': 'a', 'password': 'b', 'host': 'localhost', 'port': '555', 'path': '/some/path'},
         {'scheme': 'this', 'username': 'a', 'password': 'b', 'host': 'localhost', 'port': '555', 'path': '123'}),
        ('this://a:b@localhost:555/some/path', None,
         {'scheme': 'this', 'username': 'a', 'password': 'b', 'host': 'localhost', 'port': '555', 'path': '/some/path'},
         {'scheme': 'this', 'username': 'a', 'password': 'b', 'host': 'localhost', 'port': '555', 'path': None}),
        ('this://a:b@localhost:555/some/path', False,
         {'scheme': 'this', 'username': 'a', 'password': 'b', 'host': 'localhost', 'port': '555', 'path': '/some/path'},
         {'scheme': 'this', 'username': 'a', 'password': 'b', 'host': 'localhost', 'port': '555', 'path': None}),
    ),
)
def test_URL_path(url, new_path, exp_before, exp_after):
    cb = Mock()
    url = _utils.URL(url, on_change=cb)
    assert cb.call_args_list == []
    assert make_url_parts(url) == exp_before
    url.path = new_path
    assert make_url_parts(url) == exp_after
    assert cb.call_args_list == [call()]


@pytest.mark.parametrize(
    argnames='url, new_username, exp_before, exp_after',
    argvalues=(
        ('this://a:b@localhost:555/some/path', 'x',
         {'scheme': 'this', 'username': 'a', 'password': 'b', 'host': 'localhost', 'port': '555', 'path': '/some/path'},
         {'scheme': 'this', 'username': 'x', 'password': 'b', 'host': 'localhost', 'port': '555', 'path': '/some/path'}),
        ('this://a:b@localhost:555/some/path', 123,
         {'scheme': 'this', 'username': 'a', 'password': 'b', 'host': 'localhost', 'port': '555', 'path': '/some/path'},
         {'scheme': 'this', 'username': '123', 'password': 'b', 'host': 'localhost', 'port': '555', 'path': '/some/path'}),
        ('this://a:b@localhost:555/some/path', None,
         {'scheme': 'this', 'username': 'a', 'password': 'b', 'host': 'localhost', 'port': '555', 'path': '/some/path'},
         {'scheme': 'this', 'username': None, 'password': 'b', 'host': 'localhost', 'port': '555', 'path': '/some/path'}),
        ('this://a:b@localhost:555/some/path', False,
         {'scheme': 'this', 'username': 'a', 'password': 'b', 'host': 'localhost', 'port': '555', 'path': '/some/path'},
         {'scheme': 'this', 'username': None, 'password': 'b', 'host': 'localhost', 'port': '555', 'path': '/some/path'}),
    ),
)
def test_URL_username(url, new_username, exp_before, exp_after):
    cb = Mock()
    url = _utils.URL(url, on_change=cb)
    assert cb.call_args_list == []
    assert make_url_parts(url) == exp_before
    url.username = new_username
    assert make_url_parts(url) == exp_after
    assert cb.call_args_list == [call()]


@pytest.mark.parametrize(
    argnames='url, new_password, exp_before, exp_after',
    argvalues=(
        ('this://a:b@localhost:555/some/path', 'x',
         {'scheme': 'this', 'username': 'a', 'password': 'b', 'host': 'localhost', 'port': '555', 'path': '/some/path'},
         {'scheme': 'this', 'username': 'a', 'password': 'x', 'host': 'localhost', 'port': '555', 'path': '/some/path'}),
        ('this://a:b@localhost:555/some/path', 123,
         {'scheme': 'this', 'username': 'a', 'password': 'b', 'host': 'localhost', 'port': '555', 'path': '/some/path'},
         {'scheme': 'this', 'username': 'a', 'password': '123', 'host': 'localhost', 'port': '555', 'path': '/some/path'}),
        ('this://a:b@localhost:555/some/path', None,
         {'scheme': 'this', 'username': 'a', 'password': 'b', 'host': 'localhost', 'port': '555', 'path': '/some/path'},
         {'scheme': 'this', 'username': 'a', 'password': None, 'host': 'localhost', 'port': '555', 'path': '/some/path'}),
        ('this://a:b@localhost:555/some/path', False,
         {'scheme': 'this', 'username': 'a', 'password': 'b', 'host': 'localhost', 'port': '555', 'path': '/some/path'},
         {'scheme': 'this', 'username': 'a', 'password': None, 'host': 'localhost', 'port': '555', 'path': '/some/path'}),
    ),
)
def test_URL_password(url, new_password, exp_before, exp_after):
    cb = Mock()
    url = _utils.URL(url, on_change=cb)
    assert cb.call_args_list == []
    assert make_url_parts(url) == exp_before
    url.password = new_password
    assert make_url_parts(url) == exp_after
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

@pytest.mark.parametrize('on_change', (None, Mock()))
def test_URL_repr_without_on_change_callback(on_change, mocker):
    url = _utils.URL('this://localhost', on_change=on_change)
    mocker.patch.object(type(url), 'without_auth', PropertyMock(return_value='mocked URL'))
    if on_change:
        assert repr(url) == f"URL('mocked URL', on_change={on_change!r})"
    else:
        assert repr(url) == "URL('mocked URL')"


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
