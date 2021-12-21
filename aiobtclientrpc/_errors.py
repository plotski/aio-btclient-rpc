import re


class Error(Exception):
    """Base class for all exceptions raised by this package"""


class RPCError(Error):
    """Miscommunication with the RPC service, e.g. unknown method called"""


class ConnectionError(Error):
    """Failed to connect to the client, e.g. because it isn't running"""

    def __init__(self, msg):
        # python_socks.ProxyConnectionError provides ugly errors messages,
        # e.g. "Could not connect to proxy localhost:1337 [None]".
        msg = re.sub(r'\s+\[.*?\]$', '', str(msg))
        super().__init__(msg)


class TimeoutError(Error):
    """Timeout for sending request and reading response"""


class AuthenticationError(Error):
    """Failed to prove identity"""


class ValueError(Error, ValueError):
    """
    Invalid value (e.g. port 65536)

    This is a subclass of :class:`Error` and :class:`ValueError`.
    """
