__project_name__ = 'aio-btclient-rpc'
__description__ = 'Asynchronous low-level communication with BitTorrent clients'
__homepage__ = 'https://github.com/plotski/aio-btclient-rpc'
__version__ = '0.0.0'
__author__ = 'plotski'
__author_email__ = 'plotski@example.org'

from ._base import RPCBase
from ._errors import *
from ._qbittorrent import QbittorrentRPC
from ._utils import ConnectionStatus, client, clients
