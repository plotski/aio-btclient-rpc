import json

from . import _base, _errors, _utils

import logging  # isort:skip
_log = logging.getLogger(__name__)


class TransmissionURL(_utils.URL):
    """Transmission RPC URL"""

    default = 'http://localhost:9091/transmission/rpc'

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


class TransmissionRPC(_base.RPCBase):
    """
    RPC client for Transmission

    URL format: ``http[s]://[USERNAME:PASSWORD@]HOST:PORT[/PATH]``

    Reference: https://github.com/transmission/transmission/blob/master/extras/rpc-spec.txt

    **Calling RPC methods**

    RPC methods can be called like python functions:

    >>> client.call("torrent-add", filename="path/to.torrent", paused=True)

    If you need to pass argument names that contain characters that are illegal
    for keyword arguments (e.g. "-"), provide a dictionary:

    >>> client.call(
        "torrent-add",
        {"filename": "file.torrent", "download-dir": "/some/path"},
    )

    If you provide keyword arguments and a dictionary, values from the
    dictionary overload keyword arguments.

    :raise ValueError: if any argument is invalid
    """

    name = 'transmission'
    label = 'Transmission'
    URL = TransmissionURL

    def __init__(
        self,
        url=None,
        *,
        scheme=None,
        host=None,
        port=None,
        path=None,
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
        if path:
            self.url.path = path
        if username:
            self.url.username = username
        if password:
            self.url.password = password

        self.timeout = timeout
        self.proxy_url = proxy_url

    async def _request(self, method, tag=None, **parameters):
        data = {'method': str(method)}
        if parameters:
            data['arguments'] = parameters
        if tag:
            try:
                data['tag'] = int(float(tag))
            except (TypeError, ValueError):
                raise _errors.ValueError(f'Tag must be a number: {tag!r}')

        try:
            data_json = json.dumps(data)
        except Exception:
            raise _errors.ValueError(f'Failed to serialize to JSON: {data}')

        return await self._send_post_request(str(self.url), data=data_json)

    _auth_error_code = 401
    _csrf_error_code = 409
    _csrf_header = 'X-Transmission-Session-Id'

    async def _connect(self):
        # There is no special login procedure, we just make an appropriate
        # request to get the CSRF header and ensure authentication works
        response = await self._request('session-stats')

        if response.status_code == self._csrf_error_code:
            # Store CSRF header
            _log.debug('Setting CSRF header: %s = %s', self._csrf_header, response.headers[self._csrf_header])
            self._http_headers[self._csrf_header] = response.headers[self._csrf_header]
            # Try again with CSRF header
            await self._request('session-stats')

        elif response.status_code == self._auth_error_code:
            raise _errors.AuthenticationError('Authentication failed')

        elif response.status_code != 200:
            raise RuntimeError(f'Unexpected response: {response!r}')

    async def _disconnect(self):
        # Forget CSRF header
        self._http_headers.clear()

    async def _call(self, method, args=None, **kwargs):
        if args:
            kwargs.update(args)
        response = await self._request(method, **kwargs)
        try:
            result = response.json()
        except Exception:
            raise _errors.RPCError(f'Unexpected response: {response.text}')
        else:
            # Translate error message to exception
            if result['result'] != 'success':
                raise _errors.RPCError(result['result'].capitalize())
            else:
                return result
