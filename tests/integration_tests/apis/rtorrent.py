import os


class API:
    def __init__(self, client):
        self.client = client

    async def perform_simple_request(self):
        result = await self.client.call('system.listMethods')
        print('system.listMethods:', result)
        assert 'system.listMethods' in result
        assert 'system.multicall' in result
        assert 'load.normal' in result

        result = await self.client.call('dht.statistics')
        print('dht.statistics:', result)
        assert result['dht'] == 'off'

        result = await self.client.call('protocol.pex')
        print('protocol.pex:', result)
        assert result == 0

    async def get_torrent_list(self):
        result = await self.client.call('download_list', '')
        print('download_list:', result)
        infohashes = sorted(infohash.lower() for infohash in result)
        return infohashes

    STATE_PAUSED = 0
    STATE_STARTED = 1

    async def add_torrent_files(self, torrent_filepaths, as_file=True,
                                download_path='/tmp/some/path', paused=False):
        # Add torrents
        calls = []
        if as_file:
            for filepath in torrent_filepaths:
                calls.append({
                    'methodName': 'load.verbose',
                    'params': [
                        '',
                        os.path.abspath(filepath),
                        # Set download location
                        f'd.directory_base.set="{download_path}"',
                        # Untie torrent from .torrent file so rtorrent doesn't
                        # delete it when the torrent is removed.
                        'd.tied_to_file.set='
                    ],
                })
        else:
            for filepath in torrent_filepaths:
                calls.append({
                    'methodName': 'load.raw_start_verbose',
                    'params': [
                        '',
                        open(filepath, 'rb').read(),
                        # Set download location
                        f'd.directory_base.set="{download_path}"',
                        # Untie torrent from .torrent file so rtorrent doesn't
                        # delete it when the torrent is removed.
                        'd.tied_to_file.set='
                    ],
                })
        result = await self.client.call('system.multicall', calls)
        print('load:', result)

        # Get added torrent hashes from server
        infohashes = await self.client.call('download_list', '')
        infohashes = [infohash.lower() for infohash in infohashes]

        # Pause torrents if requested
        cmd = 'stop' if paused else 'start'
        multicall_params = (
            ['main']
            + [f'd.{cmd}={infohash}' for infohash in infohashes]
        )
        result = await self.client.call('d.multicall2', '', multicall_params)
        print('paused:', result)

        # Verify torrents where correctly added
        fields = ('hash', 'state', 'directory_base')
        multicall_params = (
            ['main']
            + [f'd.{field}=' for field in fields]
        )
        result = await self.client.call('d.multicall2', '', multicall_params)
        torrents = [{field: value for field, value in zip(fields, item)}
                    for item in result]
        print('torrents:', torrents)
        for torrent in torrents:
            location = torrent['directory_base']
            state = torrent['state']
            assert location == download_path, f'{location!r} != {download_path!r}'
            if paused:
                assert state == self.STATE_PAUSED, f'{state!r} != {self.STATE_PAUSED!r}'
            else:
                assert state == self.STATE_STARTED, f'{state!r} != {self.STATE_STARTED!r}'

        return sorted(torrent['hash'].lower() for torrent in torrents)

    async def on_torrent_added(self, handler):
        # Raise NotImplementedError
        await self.client.add_event_handler('<event name>', handler)
