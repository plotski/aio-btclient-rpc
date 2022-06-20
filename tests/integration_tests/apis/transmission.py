import asyncio
import os

from .. import common


class API:
    def __init__(self, client):
        self.client = client

    async def perform_simple_request(self):
        result = await self.client.call('session-get')
        print('session-get:', result)
        assert result['result'] == 'success'
        assert result['arguments']['dht-enabled'] is False

    async def get_torrent_list(self):
        result = await self.client.call('torrent-get', fields=['hashString'])
        print('torrent-get:', result)
        infohashes = [torrent['hashString']
                      for torrent in result['arguments']['torrents']]
        return sorted(infohashes)

    TR_STATUS_STOPPED = 0
    TR_STATUS_CHECK_WAIT = 1
    TR_STATUS_CHECK = 2
    TR_STATUS_DOWNLOAD_WAIT = 3
    TR_STATUS_DOWNLOAD = 4
    TR_STATUS_SEED_WAIT = 5
    TR_STATUS_SEED = 6

    async def add_torrent_files(self, torrent_filepaths, as_file=True,
                                download_path='/tmp/some/path', paused=True):
        # Add torrents
        infohashes = []
        for filepath in torrent_filepaths:
            if as_file:
                result = await self.client.call(
                    'torrent-add',
                    {'download-dir': download_path},
                    filename=os.path.abspath(filepath),
                    paused=paused,
                )
                print('torrent-add:', result)
            else:
                result = await self.client.call(
                    'torrent-add',
                    {'download-dir': download_path},
                    metainfo=common.read_torrent_file(filepath),
                    paused=paused,
                )
                print('torrent-add:', result)
            infohashes.append(
                result['arguments']['torrent-added']['hashString'].lower()
            )

        # Wait for the server to finish verifying
        await asyncio.sleep(0.5)

        # Verify torrents where correctly added
        result = await self.client.call('torrent-get', ids=infohashes, fields=['status', 'downloadDir'])
        print('torrent-get:', infohashes, result)
        for torrent in result['arguments']['torrents']:
            location = torrent['downloadDir']
            status = torrent['status']
            assert location == download_path, location
            if paused:
                assert status == self.TR_STATUS_STOPPED, f'{status!r} != {self.TR_STATUS_STOPPED!r}'
            else:
                assert status == self.TR_STATUS_DOWNLOAD, f'{status!r} != {self.TR_STATUS_DOWNLOAD!r}'

        return sorted(infohashes)

    async def on_torrent_added(self, handler):
        # Raise NotImplementedError
        await self.client.add_event_handler('<event name>', handler)

    async def wait_for_torrent_added(self):
        # Raise NotImplementedError
        await self.client.wait_for_event('<event name>')
