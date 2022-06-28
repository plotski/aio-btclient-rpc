import re


class Error(Exception):
    """Base class for all exceptions raised by this package"""

    def __eq__(self, other):
        return (
            type(self) is type(other)
            and str(self) == str(other)
        )


class RPCError(Error):
    """
    Generic RPC error

    This can be some kind of miscommunication with the RPC service (e.g. unknown
    method called, invalid or missing argument, etc), which should be a
    considered a bug. But it can also be a normal error message (e.g. unknown
    torrent), that should be communicated to the user.
    """

    def translate(self, map):
        r"""
        Turn this exception into another one based on regular expressions

        :param map: Mapping of regular expression strings to target exception
            instances

        Each regular expression is matched aagainst the error message of the
        instance (i.e. ``str(self)``). The corresponding target exception of the
        first matching regular expression is returned.

        >>> RPCError("foo is bad").translate({
        >>>     r"^foo": ValueError("Foo is something"),
        >>>     r"is bad$": TypeError("Something is bad"),
        >>> })
        ValueError('bad: Foo')

        If there are no matches, the instance (``self``) is returned.

        >>> RPCError("foo is bad").translate({
        >>>     r"Hello?": ValueError("Anybody out there?"),
        >>> })
        RPCError("foo is bad")

        If the matching target exception is a ``(exception_class, message)``
        tuple, any group references in ``message`` are substituted with the
        groups from the matching regular expression and
        ``exception_class(message_with_group_substitutions)`` is returned.

        >>> for e in (RPCError("foo is bad"), RPCError("bar is bad"), RPCError("bar is silly")):
        >>>     e.translate({
        >>>         r"^(\w+) is (\w+)$": (ValueError, r"\2: \1"),
        >>>     })
        ValueError('bad: foo')
        ValueError('bad: bar')
        ValueError('silly: bar')
        """
        self_msg = str(self)
        for regex, to_exc in map.items():
            match = re.search(regex, self_msg)
            if match:
                if isinstance(to_exc, tuple) and len(to_exc) == 2:
                    to_cls, to_msg = to_exc
                    # Replace group references (\1, \g<1>, \g<name>) in `to_msg`
                    return to_cls(match.expand(to_msg))
                else:
                    return to_exc
        return self


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
