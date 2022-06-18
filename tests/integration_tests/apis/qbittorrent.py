import os
import pprint


class API:
    def __init__(self, client):
        self.client = client
        self._sync_id = 0

    async def _get_sync(self):
        result = await self.client.call('sync/maindata', rid=self._sync_id)
        self._sync_id = result['rid']
        return result

    async def perform_simple_request(self):
        result = await self.client.call('app/preferences')
        print('app/preferences:', result)
        assert result['dht'] is False
        assert result['pex'] is False

    async def get_torrent_list(self):
        result = await self.client.call('torrents/info')
        print('torrents/info:', result)
        infohashes = sorted(torrent['hash'] for torrent in result)
        return infohashes

    STATUS_DOWNLOADING = 'queuedDL'
    STATUS_PAUSED = 'pausedDL'

    async def add_torrent_files(self, torrent_filepaths, as_file=True,
                                download_path='/tmp/some/path', paused=True):
        result = await self._get_sync()
        print('frist sync:\n', pprint.pformat(result))

        # Add torrents
        if as_file:
            result = await self.client.call(
                'torrents/add', {
                    'urls': '\n'.join([
                        os.path.abspath(filepath)
                        for filepath in torrent_filepaths
                    ]),
                    'paused': str(paused).lower(),
                    'savepath': download_path,
                },
            )
        else:
            result = await self.client.call(
                'torrents/add',
                files=[
                    ('filename', (
                        os.path.abspath(filepath),
                        open(filepath, 'rb'),
                        'application/x-bittorrent',
                    ))
                    for filepath in torrent_filepaths
                ],
                options={'savepath': download_path, 'paused': str(paused).lower()},
            )
        print('torrents/add:', result)
        assert result == 'Ok.', result

        # Get added torrent hashes from server
        result = await self._get_sync()
        print('second sync:\n', pprint.pformat(result))
        infohashes = tuple(result['torrents'])

        # Verify torrents were correctly added
        result = await self.client.call('torrents/info', hashes='|'.join(infohashes))
        print('torrent/info:', infohashes, result)
        for torrent in result:
            location = torrent['save_path']
            status = torrent['state']
            assert location == download_path, location
            if paused:
                assert status == self.STATUS_PAUSED, f'{status!r} !== {self.STATUS_PAUSED!r}'
            else:
                assert status == self.STATUS_DOWNLOADING, f'{status!r} !== {self.STATUS_DOWNLOADING!r}'

        return sorted(infohashes)

    async def on_torrent_added(self, handler):
        # Raise NotImplementedError
        await self.client.add_event_handler('<event name>', handler)
