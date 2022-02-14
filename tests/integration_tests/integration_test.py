import pytest

import aiobtclientrpc

from . import common


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
            paused=False,
        )
        assert return_value == infohashes
        torrent_list = await api.get_torrent_list()
        assert torrent_list == infohashes

    finally:
        await api.client.disconnect()
