import asyncio
import inspect
import types
from unittest.mock import Mock, NonCallableMock


# AsyncMock was added in Python 3.8
class AsyncMock(Mock):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Make asyncio.iscoroutine[function]() work
        code_mock = NonCallableMock(spec_set=types.CodeType)
        code_mock.co_flags = inspect.CO_COROUTINE
        self.__dict__['__code__'] = code_mock
        self.__dict__['_is_coroutine'] = asyncio.coroutines._is_coroutine

    async def __call__(self, *args, **kwargs):
        return super().__call__(*args, **kwargs)


def make_url_parts(url):
    return {name: getattr(url, name)
            for name in ('scheme', 'host', 'port', 'path', 'username', 'password')}
