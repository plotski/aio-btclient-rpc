import os

from .. import common


class API:
    def __init__(self, client):
        self.client = client
        self._sync_id = 0

    async def perform_simple_request(self):
        result = await self.client.call('core.get_config')
        print('daemon.get_config:', result)
        assert result['dht'] is False
        assert result['utpex'] is False

    async def get_torrent_list(self):
        result = await self.client.call('core.get_torrents_status', filter_dict={}, keys=['name'])
        print('core.get_torrents_status:', result)
        infohashes = sorted(result.keys())
        return infohashes

    async def add_torrent_files(self, torrent_filepaths, as_file=True,
                                download_path='/tmp/some/path', paused=True):
        # Register event handler for added torrents
        torrents_added = []

        def on_torrent_added(infohash, from_state_):
            print('torrent added:', infohash, from_state_)
            torrents_added.append(infohash)

        await self.client.add_event_handler('TorrentAddedEvent', on_torrent_added)

        # Add torrents (as_file is ignored because Deluge doesn't accept file
        # paths)
        for filepath in torrent_filepaths:
            result = await self.client.call(
                'core.add_torrent_file',
                filename=os.path.basename(filepath),
                filedump=common.read_torrent_file(filepath),
                options={
                    'add_paused': paused,
                    'save_path': download_path,
                },
            )
            print('core.add_torrent_file_async', result)

        assert torrents_added

        # Verify torrents were correctly added
        result = await self.client.call(
            'core.get_torrents_status',
            filter_dict={'id': torrents_added},
            keys=['paused', 'save_path'],
        )
        print('core.get_torrents_status:', torrents_added, result)
        for infohash, torrent in result.items():
            assert torrent['save_path'] == download_path, torrent['save_path']
            if paused:
                assert torrent['paused'] is True, repr(torrent['paused'])
            else:
                assert torrent['paused'] is False, repr(torrent['paused'])

        return sorted(torrents_added)

    async def on_torrent_added(self, handler):
        def handler_wrapper(infohash, *args, **kwargs):
            handler(infohash)
        await self.client.add_event_handler('TorrentAddedEvent', handler_wrapper)

    async def wait_for_torrent_added(self):
        await self.client.wait_for_event('TorrentAddedEvent')
