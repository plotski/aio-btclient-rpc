from . import _base, _errors

import logging  # isort:skip
_log = logging.getLogger(__name__)


class QbittorrentRPC(_base.RPCBase):
    """
    RPC client for qBittorrent

    Reference: https://github.com/qbittorrent/qBittorrent/wiki/WebUI-API-(qBittorrent-4.1)

    :raise ValueError: if any argument is invalid
    """

    name = 'qbittorrent'
    label = 'qBittorrent'
    default_url = 'http://localhost:8080'

    def __init__(
        self,
        url=None,
        *,
        scheme=None,
        host=None,
        port=None,
        username=None,
        password=None,
        timeout=None,
        proxy_url=None,
    ):
        # Set custom or default URL
        self.url = url

        # Update URL
        if scheme:
            self.url.scheme = scheme
        if host:
            self.url.host = host
        if port:
            self.url.port = port
        if username:
            self.url.username = username
        if password:
            self.url.password = password

        self.timeout = timeout
        self.proxy_url = proxy_url

    async def _connect(self):
        response = await self._send_post_request(
            url=f'{self.url}/api/v2/auth/login',
            data={
                'username': self.url.username or '',
                'password': self.url.password or '',
            },
        )

        if response.status_code == 403:
            raise _errors.AuthenticationError('Too many failed authentication attempts')
        elif response.text == 'Fails.':
            raise _errors.AuthenticationError('Authentication failed')
        elif response.text != 'Ok.':
            raise _errors.RPCError(response.text)

    async def _disconnect(self):
        await self._send_post_request(f'{self.url}/api/v2/auth/logout')

    async def _call(self, method, **parameters):
        response = await self._send_post_request(
            url=f'{self.url}/api/v2/{method}',
            data=parameters,
        )

        if response.status_code == 404:
            raise _errors.RPCError('Unknown RPC method')
        elif response.status_code != 200:
            raise _errors.RPCError(response.text)

        try:
            return response.json()
        except ValueError:
            return response.text
