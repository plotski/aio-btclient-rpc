import asyncio
import sys
import time
from unittest.mock import Mock, call, patch

import pytest

import aiobtclientrpc

from . import common, proxyserver

import logging  # isort:skip
_log = logging.getLogger(__name__)


@pytest.mark.asyncio
async def test_authentication_error(api, tmp_path):
    if not api.client.url.username:
        pytest.skip(f'No authentication: {api.client.url}')

    else:
        async with api.client:
            await api.perform_simple_request()

        correct_username = api.client.url.username
        api.client.url.username = 'wrong_username'
        async with api.client:
            with pytest.raises(aiobtclientrpc.AuthenticationError, match=r'^Authentication failed$'):
                await api.perform_simple_request()
        api.client.url.username = correct_username

        correct_password = api.client.url.password
        api.client.url.password = 'wrong_password'
        async with api.client:
            with pytest.raises(aiobtclientrpc.AuthenticationError, match=r'^Authentication failed$'):
                await api.perform_simple_request()
        api.client.url.password = correct_password

        async with api.client:
            await api.perform_simple_request()


@pytest.mark.asyncio
async def test_api_as_context_manager(api, tmp_path):
    for _ in range(3):
        async with api.client:
            await api.perform_simple_request()


@pytest.mark.parametrize('paused', (True, False), ids=lambda paused: 'paused' if paused else 'started')
@pytest.mark.parametrize('as_file', (True, False), ids=lambda as_file: 'as_file' if as_file else 'as_bytes')
@pytest.mark.asyncio
async def test_add_torrents(as_file, paused, api, tmp_path):
    infohashes = sorted([
        '4435ef55af79b350e7b85d5b330a7886a61e3bdf',
        'd5a34e9eb4709e265f0f03a1c8ab60890dcb94a9',
    ])

    try:
        return_value = await api.add_torrent_files(
            torrent_filepaths=(
                common.get_torrent_filepath(infohashes[0]),
                common.get_torrent_filepath(infohashes[1]),
            ),
            as_file=as_file,
            paused=paused,
        )
        assert return_value == infohashes
        torrent_list = await api.get_torrent_list()
        assert torrent_list == infohashes

    finally:
        await api.client.disconnect()


@pytest.mark.skipif(sys.version_info < (3, 8), reason='Avoid BrokenResourceError on Python 3.7')
@pytest.mark.parametrize(
    argnames='start_proxy',
    argvalues=proxyserver.proxies,
)
@pytest.mark.asyncio
async def test_proxy(start_proxy, api, tmp_path):
    with start_proxy() as proxy_url:
        api.client.proxy_url = proxy_url
        _log.debug('proxy started: %s', api.client.proxy_url)

        # Setting a proxy for a file:// URL shouldn't raise immediately (maybe
        # the URL is changed right after), but it should raise when a request is
        # made with an invalid protocol/proxy combination.
        if api.client.url.scheme == 'file':
            with pytest.raises(aiobtclientrpc.ValueError, match=rf'^You cannot use a proxy to connect to {api.client.url}$'):
                await api.perform_simple_request()
            return
        else:
            await api.perform_simple_request()

        _log.debug('stopping proxy: %s', api.client.proxy_url)
    _log.debug('proxy stopped: %s', api.client.proxy_url)

    # Proxy is now stopped while client still thinks it's connected
    if api.client.name == 'deluge':
        exp_error = r'^Connection lost$'
    else:
        exp_error = rf'^Could not connect to proxy {api.client.proxy_url.host}:{api.client.proxy_url.port}$'
    with pytest.raises(aiobtclientrpc.ConnectionError, match=exp_error):
        await api.perform_simple_request()

    # Start proxy again and client should use it
    with start_proxy() as proxy_url:
        _log.debug('proxy started again: %s', proxy_url)
        await api.perform_simple_request()
        _log.debug('stopping proxy: %s', api.client.proxy_url)
    _log.debug('proxy stopped: %s', api.client.proxy_url)

    _log.debug('disconnecting client')
    try:
        await api.client.disconnect()
    except aiobtclientrpc.ConnectionError:
        # qbittorrent's API has a logout() method, so we expect a
        # ConnectionError due to the proxy being down. The other clients don't
        # have a logout() method.
        if api.client.name == 'qbittorrent':
            pass
        else:
            raise

    _log.debug('client is now disconnected')


@pytest.mark.asyncio
async def test_timeout(api, tmp_path):
    # Call the original client._call() method after a nap
    def make_delayed_call(delay, real_call_method=api.client._call):
        async def delayed_call(*args, **kwargs):
            print(time.monotonic(), 'sleeping', delay, 'seconds')
            await asyncio.sleep(delay)
            print(time.monotonic(), 'calling', real_call_method)
            return await real_call_method(*args, **kwargs)

        return delayed_call

    async def connect():
        # Connect without delay
        if not api.client.is_connected:
            print(time.monotonic(), 'connecting')
            await api.client.connect()
            print(time.monotonic(), 'connected')

    # We must connect now because we don't want any autoconnecting behaviour
    # with artifically delayed responses as connect() performs an unpredictable
    # amount of requests. We must set the timeout before connecting manually
    # because it invalidates an existing connection.
    api.client.timeout = 1
    await connect()

    try:
        with patch.object(api.client, '_call', make_delayed_call(0.5)):
            await api.perform_simple_request()

        with patch.object(api.client, '_call', make_delayed_call(100)):
            with pytest.raises(aiobtclientrpc.TimeoutError, match=rf'^Timeout after {api.client.timeout} seconds$'):
                await api.perform_simple_request()
    finally:
        await api.client.disconnect()


@pytest.mark.asyncio
async def test_event_subscriptions_survive_reconnecting(api, tmp_path):
    infohashes = sorted([
        '4435ef55af79b350e7b85d5b330a7886a61e3bdf',
        'd5a34e9eb4709e265f0f03a1c8ab60890dcb94a9',
    ])

    torrent_added_handler = Mock()

    async with api.client:
        try:
            await api.on_torrent_added(torrent_added_handler)
        except NotImplementedError as e:
            assert str(e) == f'Events are not supported for {api.client.label}'
            pytest.skip(str(e))
        else:
            await api.add_torrent_files(
                torrent_filepaths=[common.get_torrent_filepath(infohashes[0])],
            )
            assert torrent_added_handler.call_args_list == [
                call(infohashes[0]),
            ]

    # Re-connect and check if torrent_added_handler() is still called
    async with api.client:
        await api.add_torrent_files(
            torrent_filepaths=[common.get_torrent_filepath(infohashes[1])],
        )
        assert torrent_added_handler.call_args_list == [
            call(infohashes[0]),
            call(infohashes[1]),
        ]


@pytest.mark.asyncio
async def test_waiting_for_event(api, tmp_path):
    infohashes = sorted([
        '4435ef55af79b350e7b85d5b330a7886a61e3bdf',
        'd5a34e9eb4709e265f0f03a1c8ab60890dcb94a9',
    ])

    async with api.client:
        coros = [
            api.wait_for_torrent_added(),
            api.add_torrent_files(
                torrent_filepaths=[
                    common.get_torrent_filepath(infohash)
                    for infohash in infohashes
                ],
            ),
        ]

        return_values = await asyncio.gather(*coros, return_exceptions=True)
        assert len(return_values) == 2
        wait_for_torrent_added_return_value = return_values[0]
        add_torrent_files_return_value = return_values[1]

        if wait_for_torrent_added_return_value is not None:
            assert type(wait_for_torrent_added_return_value) is NotImplementedError
            assert str(wait_for_torrent_added_return_value) == f'Events are not supported for {api.client.label}'
            pytest.skip(str(wait_for_torrent_added_return_value))

        else:
            assert add_torrent_files_return_value == infohashes
