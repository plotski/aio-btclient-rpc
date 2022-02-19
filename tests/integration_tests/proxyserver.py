"""
https://github.com/abhinavsingh/proxy.py/blob/develop/examples/https_connect_tunnel.py

:copyright: (c) 2013-present by Abhinav Singh and contributors.
:license: BSD, see LICENSE for more details.
"""

import contextlib

from proxy import Proxy
from proxy.core.base import BaseTcpTunnelHandler
from proxy.http.responses import (PROXY_TUNNEL_ESTABLISHED_RESPONSE_PKT,
                                  PROXY_TUNNEL_UNSUPPORTED_SCHEME)


class _HttpsConnectTunnelHandler(BaseTcpTunnelHandler):
    """HTTP[S] CONNECT tunnel."""

    def handle_data(self, data):
        # Queue for upstream if connection has been established
        if self.upstream and self.upstream._conn is not None:
            self.upstream.queue(data)
            return None

        # Parse client request
        self.request.parse(data)

        # Drop the request if not a CONNECT request
        if not self.request.is_https_tunnel:
            self.work.queue(PROXY_TUNNEL_UNSUPPORTED_SCHEME)
            return True

        # CONNECT requests are short and we need not worry about
        # receiving partial request bodies here.
        assert self.request.is_complete

        # Establish connection with upstream
        try:
            self.connect_upstream()
        except OSError as e:
            # Close client connection
            import logging
            logging.getLogger(__name__).debug('Failed to connect to upstream: %r', e)
            raise
            # return True
        else:
            # Queue tunnel established response to client
            self.work.queue(PROXY_TUNNEL_ESTABLISHED_RESPONSE_PKT)


@contextlib.contextmanager
def http_proxy(port=60100):
    with Proxy(
        work_klass=_HttpsConnectTunnelHandler,
        port=port,
        num_workers=1,
    ):
        yield f'http://localhost:{port}'

# TODO: Add SOCKS4/5 proxies. proxy.py doesn't seem to support them currently.

proxies = (http_proxy,)
