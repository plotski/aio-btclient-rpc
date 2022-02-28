``aio-btclient-rpc`` provides low-level access to the RPC protocols of
BitTorrent clients. It is supposed to be the basis for a high-level library. If
you want to use this directly, you need to read the documentation or source code
of each client.

Features
--------

* Tunnel the client connection through a proxy (SOCKS5, SOCKS4, HTTP tunnel)
* Event handlers, e.g. when a torrent was added (Deluge only)
* Connect automatically on any RPC method call
* Keep track of the connection status and provide changes to a callback

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
