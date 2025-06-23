import sys
from collections import defaultdict
from pathlib import Path

from tinycrate.tinycrate import TinyCrate
from util import read_config, write_config

from rocrate_tabular.tabulator import ROCrateTabulator, main, parse_args


def test_smoke_cli(crates, tmp_path):
    cwd = Path(tmp_path)
    dbfile = cwd / "sqlite.db"
    conffile = cwd / "config.json"
    args = parse_args(["-c", str(conffile), crates["minimal"], str(dbfile)])
    main(args)


def test_no_stdout(crates, tmp_path, capsys):
    cwd = Path(tmp_path)
    dbfile = cwd / "sqlite.db"
    conffile = cwd / "config.json"
    args = parse_args(["-c", str(conffile), crates["minimal"], str(dbfile)])
    main(args)
    captured = capsys.readouterr()
    if captured.out != "":
        print(
            "This test is failing because you're printing to stdout.\n"
            "The library needs to run in contexts where it pipes stuff\n"
            "to stdout, so we need to keep that clean. Please use the\n"
            "logger for messages and debugging.",
            file=sys.stderr,
        )
        assert captured.out == ""


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
    tb2.read_config(conffile)


def test_potential_tables(crates, tmp_path):
    """Test that the first-pass config has a potential_table for each
    type of entity"""
    cwd = Path(tmp_path)
    dbfile = cwd / "sqlite.db"
    conffile = cwd / "config.json"
    tb = ROCrateTabulator()
    tb.crate_to_db(crates["languageFamily"], dbfile)
    tb.infer_config()
    tb.write_config(conffile)
    tb.close()  # for Windows
    cf = read_config(conffile)
    expect_tables = set()
    crate = TinyCrate(crates["languageFamily"])
    for entity in crate.all():
        expect_tables.update(entity.type)
    for table in expect_tables:
        assert table in cf["potential_tables"]


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
    tb.read_config(conffile)

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
    tb.read_config(conffile)

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
