import abc
import asyncio
import xmlrpc.client

from . import _base, _errors, _utils

import logging  # isort:skip
_log = logging.getLogger(__name__)


class RtorrentURL(_utils.URL):
    """rTorrent RPC URL"""

    default = 'scgi://127.0.0.1:5000'

    @property
    def scheme(self):
        """Valid schemes: ``file``, ``scgi``, ``http``, ``https``"""
        return super().scheme

    @scheme.setter
    def scheme(self, scheme):
        if not scheme or str(scheme).lower() in ('file', 'scgi', 'http', 'https'):
            _utils.URL.scheme.fset(self, scheme)
        else:
            raise _errors.ValueError('Scheme must be "file", "scgi", "http" or "https"')

    @_utils.URL.host.setter
    def host(self, host):
        if host and self.scheme == 'file':
            raise _errors.ValueError(f"{self.scheme} URLs don't have a host")
        else:
            _utils.URL.host.fset(self, host)

    @_utils.URL.port.setter
    def port(self, port):
        if port and self.scheme == 'file':
            raise _errors.ValueError(f"{self.scheme} URLs don't have a port")
        else:
            _utils.URL.port.fset(self, port)

    @_utils.URL.username.setter
    def username(self, username):
        if username and self.scheme in ('file', 'scgi'):
            raise _errors.ValueError(f"{self.scheme} URLs don't have a username")
        else:
            _utils.URL.username.fset(self, username)

    @_utils.URL.password.setter
    def password(self, password):
        if password and self.scheme in ('file', 'scgi'):
            raise _errors.ValueError(f"{self.scheme} URLs don't have a password")
        else:
            _utils.URL.password.fset(self, password)

    @_utils.URL.path.setter
    def path(self, path):
        if path and self.scheme == 'scgi':
            raise _errors.ValueError(f"{self.scheme} URLs don't have a path")
        else:
            _utils.URL.path.fset(self, path)


class RtorrentRPC(_base.RPCBase):
    """
    RPC client for rTorrent

    URL formats:
        * http[s]://[USERNAME:PASSWORD@]HOST:PORT[/PATH]
        * scgi://HOST:PORT[/PATH]
        * file://[SOCKET PATH]

    References:
        * https://github.com/rakshasa/rtorrent/wiki/rTorrent-0.9-Comprehensive-Command-list-(WIP)
        * https://docs.python.org/3/library/xmlrpc.client.html
        * https://github.com/rakshasa/rtorrent/wiki/RPC-Setup-XMLRPC

    :raise ValueError: if any argument is invalid
    """

    name = 'rtorrent'
    label = 'rTorrent'
    URL = RtorrentURL

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
        if scheme is not None:
            self.url.scheme = scheme
        if host is not None:
            self.url.host = host
        if port is not None:
            self.url.port = port
        if username is not None:
            self.url.username = username
        if password is not None:
            self.url.password = password

        self.timeout = timeout
        self.proxy_url = proxy_url

    async def _connect(self):
        # Close old proxy
        await self._disconnect()

        # Create new XMLRPC proxy
        self._xmlrpc = _AsyncServerProxy(
            url=self.url,
            proxy_url=self.proxy_url,
        )

        # Maybe raise connection/authentication error
        await self._call('system.pid')

    async def _disconnect(self):
        if hasattr(self, '_xmlrpc'):
            await self._xmlrpc.close()
            delattr(self, '_xmlrpc')

    async def _call(self, method, *args):
        try:
            return await _utils.catch_connection_exceptions(
                self._xmlrpc.call(method, *args),
            )

        except xmlrpc.client.ProtocolError as e:
            if e.errcode == 401:
                raise _errors.AuthenticationError('Authentication failed')
            else:
                msg = e.errmsg if e.errmsg else str(e)
                raise _errors.RPCError(msg)

        except xmlrpc.client.Fault as e:
            raise _errors.RPCError(e.faultString)


class _AsyncServerProxy:
    def __init__(self, url, proxy_url=None):
        if url.scheme in ('http', 'https'):
            self._transport = _HttpTransport(
                url=url,
                proxy_url=proxy_url,
            )
        elif url.scheme == 'scgi':
            self._transport = _ScgiHostTransport(
                url=url,
                proxy_url=proxy_url,
            )
        elif url.scheme == 'file' and url.path:
            if proxy_url:
                raise _errors.ValueError(f'You cannot use a proxy to connect to {url}')
            else:
                self._transport = _ScgiSocketTransport(url=url)
        else:
            raise _errors.ValueError(f'Unsupported protocol: {url}')

    async def call(self, method_name, *params):
        request_data = xmlrpc.client.dumps(
            params,
            method_name,
            encoding='utf-8',
            allow_none=False,
        ).encode('utf-8', 'xmlcharrefreplace')

        # Return asynchronous iterator over chunks of bytes
        chunks = self._transport.request(request_data)
        return await self._parse_response(chunks)

    async def _parse_response(self, chunks):
        p, u = xmlrpc.client.getparser()
        async for chunk in chunks:
            p.feed(chunk)
        p.close()
        return_value = u.close()

        if len(return_value) == 1:
            return return_value[0]
        else:
            return return_value

    async def close(self):
        await self._transport.close()


class TransportBase(abc.ABC):
    @abc.abstractmethod
    async def request(self, data):
        """
        Send request and return asynchronous iterator over chunks of bytes
        """

    @abc.abstractmethod
    async def close(self):
        """Close any existing connections"""


class _HttpTransport(TransportBase):
    """Connect via reverse HTTP proxy"""

    def __init__(self, url, proxy_url=None):
        if url.scheme not in ('http', 'https'):
            raise _errors.ValueError(f'Unsupported protocol: {url.scheme}')
        else:
            if not url.path:
                url.path = '/RPC2'
            # Username and password are stored in self._http_client
            self._url = url.without_auth

        self._request_lock = asyncio.Lock()
        self._http_client = _utils.create_http_client(
            auth=(url.username, url.password),
            proxy_url=proxy_url.with_auth if proxy_url else None,
        )

    async def close(self):
        async with self._request_lock:
            await self._http_client.aclose()

    async def request(self, data):
        async with self._request_lock:
            aiterator = self._request(data)
            async for chunk in aiterator:
                yield chunk

    async def _request(self, data):
        async with self._http_client.stream('POST', self._url, content=data) as response:
            if response.status_code != 200:
                raise xmlrpc.client.ProtocolError(
                    url=self._url,
                    errcode=response.status_code,
                    errmsg=response.reason_phrase,
                    headers=response.headers,
                )
            else:
                aiterator = response.aiter_bytes()
                async for chunk in aiterator:
                    yield chunk


class _ScgiTransportBase(TransportBase, abc.ABC):
    """Base class for SCGI transports (network.scgi.*)"""

    async def close(self):
        pass

    async def request(self, data):
        reader, writer = await self._get_reader_writer()
        await self._send(writer, data)
        async for chunk in self._read(reader, writer, 1024):
            yield chunk

    @abc.abstractmethod
    async def _get_reader_writer(self):
        """Return `(:class:`StreamReader`, :class:`StreamWriter`)` tuple"""

    async def _read(self, reader, writer, chunk_size):
        try:
            headers_delim = b'\r\n\r\n'
            headers_done = False
            combined_headers = b''

            while True:
                chunk = await reader.read(chunk_size)
                if not chunk:
                    break
                elif headers_done:
                    # Headers are already fully read
                    yield chunk
                else:
                    combined_headers += chunk
                    if headers_delim in combined_headers:
                        # Find and remove HTTP headers
                        payload_start = combined_headers.index(headers_delim) + len(headers_delim)
                        first_payload_chunk = combined_headers[payload_start:]
                        if first_payload_chunk:
                            yield first_payload_chunk
                        headers_done = True
                        combined_headers = b''
        finally:
            writer.close()
            await writer.wait_closed()

    async def _send(self, writer, data):
        data_encoded = self._encode_request(data)
        writer.write(data_encoded)
        await writer.drain()

    def _encode_request(self, data):
        def encode_header(key, value):
            return key + b'\x00' + value + b'\x00'

        headers = (
            encode_header(b'CONTENT_LENGTH', str(len(data)).encode('utf-8'))
            + encode_header(b'SCGI', b'1')
            + encode_header(b'REQUEST_METHOD', b'POST')
            + encode_header(b'REQUEST_URI', self._path)
        )
        request = (
            str(len(headers)).encode('utf-8')
            + b':'
            + headers
            + b','
            + data
        )
        return request


class _ScgiHostTransport(_ScgiTransportBase):
    """Connect directly to rTorrent (network.scgi.open_port)"""

    def __init__(self, url, proxy_url=None):
        if url.scheme != 'scgi':
            raise _errors.ValueError(f'Unsupported protocol: {url.scheme}')
        self._host = url.host
        if not url.port:
            raise _errors.ValueError('No port specified')
        else:
            self._port = int(url.port)
        self._path = (url.path or '/RPC2').encode('utf-8')
        self._proxy_url = proxy_url

    async def _get_reader_writer(self):
        if self._proxy_url:
            import python_socks.async_.asyncio  # isort:skip
            try:
                proxy = python_socks.async_.asyncio.Proxy.from_url(self._proxy_url.with_auth)
            except ValueError as e:
                raise _errors.ValueError(e)
            sock = await proxy.connect(dest_host=self._host, dest_port=self._port)
            open_connection_kwargs = {
                'sock': sock,
            }
        else:
            open_connection_kwargs = {
                'host': self._host,
                'port': self._port,
            }

        reader, writer = await asyncio.open_connection(**open_connection_kwargs)
        return reader, writer


class _ScgiSocketTransport(_ScgiTransportBase):
    """Connect directly to rTorrent (network.scgi.open_local)"""

    def __init__(self, url):
        if url.scheme != 'file':
            raise _errors.ValueError(f'Unsupported protocol: {url.scheme}')
        self._socket_path = url.path
        self._path = b'/RPC2'

    async def _get_reader_writer(self):
        reader, writer = await asyncio.open_unix_connection(path=self._socket_path)
        return reader, writer
