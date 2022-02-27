from . import _base, _errors, _utils

import logging  # isort:skip
_log = logging.getLogger(__name__)


class QbittorrentURL(_utils.URL):
    """qBittorrent RPC URL"""

    default = 'http://localhost:8080'

    @property
    def scheme(self):
        """Valid schemes: ``http``, ``https``"""
        return super().scheme

    @scheme.setter
    def scheme(self, scheme):
        if scheme and scheme.lower() not in ('http', 'https'):
            raise _errors.ValueError('Scheme must be "http" or "https"')
        else:
            _utils.URL.scheme.fset(self, scheme)

    @property
    def path(self):
        """Always `None`"""
        return super().path

    @path.setter
    def path(self, path):
        if path:
            raise _errors.ValueError("qBittorrent URLs don't have a path")
        else:
            _utils.URL.path.fset(self, path)


class QbittorrentRPC(_base.RPCBase):
    """
    RPC client for qBittorrent

    URL format: http[s]://[USERNAME:PASSWORD@]HOST:PORT

    Reference: https://github.com/qbittorrent/qBittorrent/wiki/WebUI-API-(qBittorrent-4.1)

    **Calling RPC methods**

    Passing arguments as keywords:

    >>> call(
    >>>     "torrents/info",
    >>>     hashes="|".join([
    >>>         "d5a34e9eb4709e265f0f03a1c8ab60890dcb94a9",
    >>>         "4435ef55af79b350e7b85d5b330a7886a61e3bdf",
    >>>     ]),
    >>>     sort="size",
    >>>     limit=20,
    >>> )

    Passing arguments as dictionary:

    >>> call(
    >>>     "torrents/info",
    >>>     {
    >>>         "hashes": "|".join([
    >>>             "d5a34e9eb4709e265f0f03a1c8ab60890dcb94a9",
    >>>             "4435ef55af79b350e7b85d5b330a7886a61e3bdf",
    >>>         ]),
    >>>         "sort": "size",
    >>>         "limit" 20,
    >>>     },
    >>> )

    Passing arguments as both keywords and dictionary (keyword values are
    overloaded by dictionary values):

    >>> call(
    >>>     "torrents/info",
    >>>     data={
    >>>         "hashes": "|".join([
    >>>             "d5a34e9eb4709e265f0f03a1c8ab60890dcb94a9",
    >>>             "4435ef55af79b350e7b85d5b330a7886a61e3bdf",
    >>>         ]),
    >>>         "sort": "size",
    >>>     },
    >>>     limit=20,
    >>> )

    The ``files`` argument is special. It is used to add torrents:

    >>> call(
    >>>     'torrents/add',
    >>>     files=[
    >>>         ('filename', (
    >>>             os.path.abspath('path/to/1.torrent'),
    >>>             open('path/to/1.torrent', 'rb'),
    >>>             'application/x-bittorrent',
    >>>         )),
    >>>         ('filename', (
    >>>             os.path.abspath('path/to/2.torrent'),
    >>>             open('path/to/2.torrent', 'rb'),
    >>>             'application/x-bittorrent',
    >>>         )),
    >>>     ],
    >>>     data={
    >>>         'savepath': 'special/download/path',
    >>>         'paused': 'true',
    >>>     },
    >>> )

    :raise ValueError: if any argument is invalid
    """

    name = 'qbittorrent'
    label = 'qBittorrent'
    URL = QbittorrentURL

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

    async def _call(self, method, data=None, files=None, **kwargs):
        # Merge dictionary arguments with keyword arguments
        if data:
            kwargs.update(data)

        # POST request expects "data" and "files" arguments
        send_post_request_kwargs = {}
        if kwargs:
            send_post_request_kwargs['data'] = kwargs
        if files:
            send_post_request_kwargs['files'] = files

        response = await self._send_post_request(
            url=f'{self.url}/api/v2/{method}',
            **send_post_request_kwargs,
        )

        if response.status_code == 404:
            raise _errors.RPCError('Unknown RPC method')
        elif response.status_code != 200:
            raise _errors.RPCError(response.text)

        try:
            return response.json()
        except ValueError:
            return response.text
