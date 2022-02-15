``aiobtclientrpc`` provides low-level access to the RPC protocols of BitTorrent
clients.

Features
--------

* Connect automatically on first RPC method call
* Tunnel the client connection through a proxy (SOCKS5, SOCKS4, HTTP tunnel)
* Keep track of the connection status and provide changes to a callback

``aiobtclientrpc`` does not implement any useful RPC methods, e.g. to get a
torrent list. You need to read the documentation or source code of the client
you want to send commands to.

| Documentation: https://aio-btclient-rpc.readthedocs.io/
| Repository: https://github.com/plotski/aio-btclient-rpc

Supported BitTorrent Clients
----------------------------

* `Deluge`_
* `qBittorrent`_
* `Transmission`_ (daemon)
* `rTorrent`_

.. _Deluge: https://www.deluge-torrent.org/
.. _qBittorrent: https://www.qbittorrent.org/
.. _Transmission: https://transmissionbt.com/
.. _rTorrent: https://rakshasa.github.io/rtorrent/

License
-------

`GPLv3+ <https://www.gnu.org/licenses/gpl-3.0.en.html>`_
