"""
Asynchronous low-level communication with BitTorrent clients
"""

__project_name__ = 'aio-btclient-rpc'
__description__ = 'Asynchronous low-level communication with BitTorrent clients'
__homepage__ = 'https://github.com/plotski/aio-btclient-rpc'
__version__ = '0.1.0'
__author__ = 'plotski'
__author_email__ = 'plotski@example.org'

# isort:skip_file

from ._base import RPCBase
from ._errors import *

from ._deluge import DelugeRPC, DelugeURL
from ._qbittorrent import QbittorrentRPC, QbittorrentURL
from ._rtorrent import RtorrentRPC, RtorrentURL
from ._transmission import TransmissionRPC, TransmissionURL

from ._utils import URL, ConnectionStatus, client, clients
