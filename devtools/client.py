#!/usr/bin/env python3

import asyncio
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

        print(':::::: Reconnecting:', good_call)
    async with client:
        print('>>>>>>', await client.call(*good_call.args, **good_call.kwargs))


async def transmission():
    await run_tests(
        client=rpc.client(
            'transmission',
            # url='http://fnark:fnorkfnork@localhost:5000/transmission/rpc',
            username='fnark',
            password='fnorkfnork',
            port=5000,
            # port=1234, timeout=1,
            # proxy_url='socks5://localhost:1234',
            # proxy_url='socks5://localhost:1337',
        ),
        good_calls=(
            call('session-stats'),
            call('session-get'),
            call('torrent-add', filename=os.path.abspath('./devtools/setup.torrent')),
            call('torrent-add', filename=os.path.abspath('./devtools/aiobtclientrpc.torrent')),
            call('torrent-get', fields=['name']),
            call('torrent-get', ids=['4435ef55af79b350e7b85d5b330a7886a61e3bdf'], fields=['name']),
        ),
        unknown_method='unknown_method',
    )

async def qbittorrent():
    await run_tests(
        client=rpc.client(
            'qbittorrent',
            url='http://fnark:fnorkfnork@localhost:5000',
            # username='fnark',
            # password='fnorkfnork',
            # port='8081',
            # port=1234, timeout=1,
            # proxy_url='socks5://localhost:1234',
            # proxy_url='socks5://localhost:1337',
        ),
        good_calls=(
            call('app/version'),
            call('app/buildInfo'),
            call('torrents/add', urls=[
                os.path.abspath('./devtools/setup.torrent'),
                os.path.abspath('./devtools/aiobtclientrpc.torrent'),
            ]),
            call('torrents/info', hashes='4435ef55af79b350e7b85d5b330a7886a61e3bdf'),
            call('torrents/info', hashes='d5a34e9eb4709e265f0f03a1c8ab60890dcb94a9|asdf'),
        ),
        unknown_method='unknown_method',
    )

async def rtorrent():
    await run_tests(
        client=rpc.client(
            'rtorrent',
            # url='/tmp/rtorrent/rpc.socket',
            # url='scgi://127.0.0.1:5000',
            # url='scgi://localhost:5000',
            url='http://localhost:5001',
            # proxy_url='socks5://localhost:1337',
            username='fnark',
            password='fnorkfnork',
        ),
        good_calls=(
            call('directory.default'),
            call('strings.encryption'),
            call('dht.statistics'),
            call('load.verbose', '', os.path.abspath('./devtools/*.torrent'),
                 # Untie torrent from .torrent file so rtorrent doesn't delete
                 # it when the torrent is removed.
                 'd.tied_to_file.set='),
            call('download_list', ''),
            call('d.name', '4435ef55af79b350e7b85d5b330a7886a61e3bdf'),
            call('d.name', 'd5a34e9eb4709e265f0f03a1c8ab60890dcb94a9'),
        ),
        unknown_method='unknown_method',
    )


try:
    client_name = sys.argv[1]
except IndexError:
    print('Missing client name', file=sys.stderr)
else:
    client_coro = locals()[client_name]
    asyncio.run(client_coro())
