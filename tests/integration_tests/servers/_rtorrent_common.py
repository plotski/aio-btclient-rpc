from .. import common


def get_common_configpath(name, tmp_path):
    configpath = common.get_home(name, tmp_path) / 'rtorrent.rc'
    logpath = common.get_home(name, tmp_path) / 'rtorrent.log'
    with open(configpath, 'w') as f:
        f.write(f'method.insert = cfg.logfile, private|const|string, (cat,"{logpath}")\n')
        f.write('print = (cat, "Logging to ",(cfg.logfile))\n')
        f.write('log.open_file = "log", (cfg.logfile)\n')
        f.write('log.add_output = "debug", "log"\n')

        # Return path to item data (never empty, unlike `d.base_path`);
        # multi-file items return a path ending with a '/'.
        f.write('method.insert = d.data_path, simple,\\\n')
        f.write('    "if=(d.is_multi_file),\\\n')
        f.write('        (cat, (d.directory)),\\\n')
        f.write('        (cat, (d.directory), /, (d.name))"\n')

        f.write('dht.mode.set = off\n')
        f.write('protocol.pex.set = no\n')
    return configpath
