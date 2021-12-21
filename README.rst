``aiobtclientrpc`` provides low-level access to the RPC protocols of BitTorrent
clients.

Features
--------

* Take care of opening and closing the connection and authentication.
* Tunnel the connection through a SOCKS5, SOCKS4 or HTTP proxy.
* Keep track of the connection status and provide changes to a callback.

``aiobtclientrpc`` does not provide any real functionality, e.g. to list or add
torrents. You need to read the documentation (or source code) of the client you
want to send commands to.

Documentation: https://aio-btclient-rpc.readthedocs.io/

Supported BitTorrent Clients
----------------------------

* `qBittorrent`_

..
   * `Transmission`_ (daemon)
   * `rTorrent`_

.. _qBittorrent: https://www.qbittorrent.org/



..
   .. _Transmission: https://transmissionbt.com/
   .. _rTorrent: https://rakshasa.github.io/rtorrent/

License
-------

`GPLv3+ <https://www.gnu.org/licenses/gpl-3.0.en.html>`_
