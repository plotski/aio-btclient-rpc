import re


class Error(Exception):
    """Base class for all exceptions raised by this package"""

    def __eq__(self, other):
        return (
            type(self) is type(other)
            and str(self) == str(other)
        )

    def __ne__(self, other):
        return not self.__eq__(other)


class RPCError(Error):
    """
    Miscommunication with the RPC service (e.g. unknown method called) or remote
    error message (e.g. requested information about unknown torrent)
    """


class ConnectionError(Error):
    """Failed to connect to the client, e.g. because it isn't running"""

    def __init__(self, msg):
        # python_socks.ProxyConnectionError provides ugly errors messages,
        # e.g. "Could not connect to proxy localhost:1337 [None]".
        msg = re.sub(r'\s+\[.*?\]$', '', str(msg))
        super().__init__(msg)


class TimeoutError(Error, TimeoutError):
    """
    Timeout for sending request and reading response

    Besides :class:`Error`, this is also a subclass of :class:`TimeoutError`.
    """


class AuthenticationError(Error):
    """Failed to prove identity"""


class ValueError(Error, ValueError):
    """
    Invalid value (e.g. port 65536)

    Besides :class:`Error`, this is also a subclass of :class:`ValueError`.
    """
