import os


def get_home(name, tmp_path):
    homepath = tmp_path / f'{name}.home'
    homepath.mkdir(parents=True, exist_ok=True)
    return homepath


def get_torrent_filepath(infohash):
    torrents_dirpath = os.path.join(os.path.dirname(__file__), 'torrents')
    return os.path.join(torrents_dirpath, f'{infohash}.torrent')
