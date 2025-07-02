import json
from pathlib import Path

from rocrate_tabular.tabulator import ROCrateTabulator


def read_config(cffile):
    with open(cffile, "r") as cfh:
        return json.load(cfh)


def write_config(cf, cffile):
    with open(cffile, "w") as cfh:
        json.dump(cf, cfh)


def tabulator_init(tmp_path, crate):
    """Does the two-pass build for a given crate but doesn't build tables.
    Returns the tabulator"""
    cwd = Path(tmp_path)
    dbfile = cwd / "sqlite.db"
    conffile = cwd / "config.json"
    tb = ROCrateTabulator()
    tb.crate_to_db(crate, dbfile)
    tb.infer_config()
    tb.write_config(conffile)
    tb.close()
    cf = read_config(conffile)
    cf["tables"] = cf["potential_tables"]
    cf["potential_tables"] = []
    write_config(cf, conffile)
    tb = ROCrateTabulator()
    tb.read_config(conffile)
    tb.crate_to_db(crate, dbfile)
    return tb
