from pathlib import Path
from rocrate_tabular.tabulator import ROCrateTabulator, parse_args, main
from tinycrate.tinycrate import TinyCrate
from collections import defaultdict
from util import read_config, write_config


def test_smoke_cli(crates, tmp_path):
    cwd = Path(tmp_path)
    dbfile = cwd / "sqlite.db"
    conffile = cwd / "config.json"
    args = parse_args(["-c", str(conffile), crates["minimal"], str(dbfile)])
    main(args)


def test_minimal(crates, tmp_path):
    """Basically tests whether imports work"""
    dbfile = Path(tmp_path) / "sqlite.db"
    tb = ROCrateTabulator()
    tb.crate_to_db(crates["minimal"], dbfile)


def test_config(crates, tmp_path):
    """Test that the first-pass config can be read"""
    cwd = Path(tmp_path)
    dbfile = cwd / "sqlite.db"
    conffile = cwd / "config.json"
    tb = ROCrateTabulator()
    tb.crate_to_db(crates["minimal"], dbfile)
    tb.infer_config()
    tb.write_config(conffile)
    tb.close()  # for Windows
    # smoke test to make sure another tabulator can read the config
    tb2 = ROCrateTabulator()
    tb2.crate_to_db(crates["minimal"], dbfile)
    tb2.load_config(conffile)


def test_one_to_lots(crates, tmp_path):
    cwd = Path(tmp_path)
    dbfile = cwd / "sqlite.db"
    conffile = cwd / "config.json"
    tb = ROCrateTabulator()
    tb.crate_to_db(crates["wide"], dbfile)
    tb.infer_config()
    tb.write_config(conffile)
    tb.close()

    # load the config and move the potential tables to tables
    cf = read_config(conffile)
    cf["tables"] = cf["potential_tables"]
    cf["potential_tables"] = []
    write_config(cf, conffile)

    # this will raise an error for too many columns
    tb = ROCrateTabulator()
    tb.load_config(conffile)

    tb.crate_to_db(crates["wide"], dbfile)

    for table in cf["tables"]:
        tb.entity_table(table)


def test_all_props(crates, tmp_path):
    cwd = Path(tmp_path)
    dbfile = cwd / "sqlite.db"
    conffile = cwd / "config.json"
    tb = ROCrateTabulator()
    tb.crate_to_db(crates["languageFamily"], dbfile)
    tb.infer_config()
    tb.write_config(conffile)
    tb.close()

    # load the config and move the potential tables to tables
    cf = read_config(conffile)
    cf["tables"] = cf["potential_tables"]
    cf["potential_tables"] = []
    write_config(cf, conffile)

    tb = ROCrateTabulator()
    tb.load_config(conffile)

    tb.crate_to_db(crates["languageFamily"], dbfile)

    # build our own list of all properties (excluding @ids)

    tc = TinyCrate(crates["languageFamily"])
    props = defaultdict(set)
    for e in tc.all():
        for prop, val in e.items():
            if prop != "@id":
                if type(e.type) is list:
                    for t in e.type:
                        props[t].add(prop)
                else:
                    props[e.type].add(prop)

    for table in cf["tables"]:
        all_props = tb.entity_table(table)
        assert all_props == props[table]
