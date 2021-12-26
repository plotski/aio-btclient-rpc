Usage
=====

For each supported BitTorrent client there is a subclass of
:class:`~.aiobtclientrpc.RPCBase`. These behave almost identically, except for
the :meth:`~.aiobtclientrpc.RPCBase.call` method, which takes different
arguments depending on the client.

It is recommended to use an asynchronous context
manager. :meth:`~.aiobtclientrpc.RPCBase.call` automatically calls
:meth:`~.aiobtclientrpc.RPCBase.connect` if required and
:meth:`~.aiobtclientrpc.RPCBase.disconnect` is called at the end of the context
manager block.

.. code-block:: python

    async with aiobtclientrpc.QbittorrentRPC(
        url="http://localhost:8080",
        username="foo",
        password="bar",
    ) as client:
        print(await client.call("app/version"))

You can also :meth:`~.aiobtclientrpc.RPCBase.connect` and
:meth:`~.aiobtclientrpc.RPCBase.disconnect` manually. Keep in mind that
:meth:`~.aiobtclientrpc.RPCBase.disconnect` must always be called.

.. code-block:: python

    client = aiobtclientrpc.QbittorrentRPC("http://localhost:8080")
    try:
        await client.connect()
        print(await client.call("app/version"))
    finally:
        await client.disconnect()

:func:`~.aiobtclientrpc.client` is a convenience function that takes a client
:attr:`~.aiobtclientrpc.RPCBase.name` and instantiates the corresponding class.

.. code-block:: python

    async with aiobtclientrpc.client(
        name="qbittorrent",
        url="http://localhost:8080",
    ) as client:
        print(await client.call("app/version"))

:class:`~.aiobtclientrpc.RPCBase` instances can be re-used as asynchronous
context managers. But this may be very inefficient because of the additional
calls to :meth:`~.aiobtclientrpc.RPCBase.connect` and
:meth:`~.aiobtclientrpc.RPCBase.disconnect`.

.. code-block:: python

   client = aiobtclientrpc.client("qbittorrent", "http://localhost:8081")
   async with client:
       print(client.call("app/version"))
   async with client:
       print(client.call("app/buildInfo"))
   async with client:
       hashes = [
           "232f5ac38b049470589905bc3a34a9f57f8d3d1d",
           "9dfe40bd5e3dba3ca464e0d94c4c3d4e1869b70e",
       ]
       print(client.call("torrents/info", hashes="|".join(hashes)))

To better understand what's going on, set the :mod:`logging` level to ``DEBUG``
or higher.

.. code-block:: python

    import logging
    logging.basicConfig(level=logging.DEBUG)
