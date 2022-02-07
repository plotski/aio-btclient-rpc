#!/usr/bin/env python3

import asyncio
import base64
import os
import sys

import logging
from unittest.mock import call

import aiobtclientrpc as rpc


logging.basicConfig(level=logging.DEBUG)
_log = logging.getLogger(__name__)


async def run_tests(
    *,
    client,
    good_calls,
    unknown_method,
):

    def cb(client):
        print('::: Connection status changed to',  client.status)

    client.on_connecting(cb, client)
    client.on_connected(cb, client)
    client.on_disconnected(cb, client)

    async with client:
        print(':::::: RPC URL:', client.url)

        for call in good_calls:
            print(':::::: Gathering:', call)
        results = await asyncio.gather(*(
            client.call(*call.args, **call.kwargs)
            for call in good_calls
        ))
        print(':::::: Gathered results:')
        for result in results:
            print('>>>>>>', result)

        good_call = good_calls[0]
        correct_url = client.url.with_auth
        if client.url.scheme == 'file':
            print(':::::: Setting wrong path')
            client.url.path = '/no/such/path'
        else:
            print(':::::: Setting wrong port')
            client.url.port = 123
        try:
            print(':::::: YOU SHOULD NOT SEE THIS:', await client.call(*good_call.args, **good_call.kwargs))
        except rpc.ConnectionError as e:
            print(':::::: Expected exception:', repr(e))
        else:
            raise RuntimeError('No ConnectionError raised!')
        client.url = correct_url

        if client.proxy_url and client.url.scheme != 'file':
            print(':::::: Setting wrong proxy URL')
            correct_port = client.proxy_url.port
            client.proxy_url.port = '123'
            try:
                print(':::::: YOU SHOULD NOT SEE THIS:', await client.call(*good_call.args, **good_call.kwargs))
            except rpc.ConnectionError as e:
                print(':::::: Expected exception:', repr(e))
            else:
                raise RuntimeError('No ConnectionError raised!')
            client.proxy_url.port = correct_port

        print(':::::: Calling unknown method:', unknown_method)
        try:
            print('YOU SHOULD NOT SEE THIS:', await client.call(unknown_method))
        except rpc.RPCError as e:
            print(':::::: Expected exception:', repr(e))
        else:
            raise RuntimeError('No RPCError raised!')

        print(':::::: Calling known method:', good_call)
        print('>>>>>>', await client.call(*good_call.args, **good_call.kwargs))

    print(':::::: Reconnecting for', good_call)
    async with client:
        print('>>>>>>', await client.call(*good_call.args, **good_call.kwargs))


async def transmission(**client_args):
    await run_tests(
        client=rpc.client('transmission', **client_args),
        good_calls=(
            call('session-stats'),
            call('session-get'),
            call('torrent-add',
                 {'download-dir': '/tmp/some/path'},
                 filename=os.path.abspath('./devtools/setup.torrent'),
                 paused=True,
            ),
            call('torrent-add', metainfo=read_torrent_file('./devtools/aiobtclientrpc.torrent')),
            call('torrent-get', fields=['name']),
            call('torrent-get', ids=['4435ef55af79b350e7b85d5b330a7886a61e3bdf'], fields=['name']),
        ),
        unknown_method='unknown_method',
    )

async def qbittorrent(**client_args):
    await run_tests(
        client=rpc.client('qbittorrent', **client_args),
        good_calls=(
            call('app/version'),
            call('app/buildInfo'),
            call('torrents/add', data={
                'urls': '\n'.join([
                    os.path.abspath('./devtools/setup.torrent'),
                ]),
                'paused': 'true',
                'savepath': 'some/path',
            }),
            call('torrents/add', files=[
                ('filename', (
                    os.path.abspath('./devtools/aiobtclientrpc.torrent'),
                    open('./devtools/aiobtclientrpc.torrent', 'rb'),
                    'application/x-bittorrent',
                ))],
                data={'savepath': 'somewhere/else', 'paused': 'true'},
            ),
            call('torrents/info', data={'hashes': '4435ef55af79b350e7b85d5b330a7886a61e3bdf'}),
            call('torrents/info', data={'hashes': 'd5a34e9eb4709e265f0f03a1c8ab60890dcb94a9|asdf'}),
        ),
        unknown_method='unknown_method',
    )

async def rtorrent(**client_args):
    await run_tests(
        client=rpc.client('rtorrent', **client_args),
        good_calls=(
            call('directory.default'),
            call('strings.encryption'),
            call('dht.statistics'),
            call('load.verbose', '',
                 os.path.abspath('./devtools/setup.torrent'),
                 # Untie torrent from .torrent file so rtorrent doesn't delete
                 # it when the torrent is removed.
                 'd.tied_to_file.set=',
            ),
            call('load.raw_start_verbose', '',
                 open('./devtools/aiobtclientrpc.torrent', 'rb').read(),
                 # Untie torrent from .torrent file so rtorrent doesn't delete
                 # it when the torrent is removed.
                 'd.tied_to_file.set='),
            call('download_list', ''),
            call('d.name', '4435ef55af79b350e7b85d5b330a7886a61e3bdf'),
            call('d.is_active', '4435ef55af79b350e7b85d5b330a7886a61e3bdf'),
            call('d.name', 'd5a34e9eb4709e265f0f03a1c8ab60890dcb94a9'),
            call('d.is_active', 'd5a34e9eb4709e265f0f03a1c8ab60890dcb94a9'),
        ),
        unknown_method='unknown_method',
    )


def read_torrent_file(filepath):
    with open(filepath, 'rb') as f:
        filecontent = f.read()
    return str(base64.b64encode(filecontent), encoding='ascii')


def parse_args(args):
    try:
        client_name = args[0]
    except IndexError:
        print('Missing client name', file=sys.stderr)
        exit(1)

    kwargs = {}
    for arg in args[1:]:
        if '=' not in arg:
            raise ValueError(f'{arg}: Argument syntax is "key=value", e.g. "url=http://localhost:123"')
        else:
            name, value = arg.split('=', maxsplit=1)
            kwargs[name] = value
    return client_name, kwargs

client_name, client_args = parse_args(sys.argv[1:])
client_coro = locals()[client_name]
asyncio.run(client_coro(**client_args))
