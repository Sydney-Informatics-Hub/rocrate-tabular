import sys
from collections import defaultdict
from pathlib import Path

from tinycrate.tinycrate import TinyCrate
from util import read_config, tabulator_init

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


def test_one_to_lots(crates, tmp_path):
    tabulator_init(tmp_path, crates["wide"])
    cf = read_config(tmp_path / "config.json")

    # this will raise an error for too many columns
    tb2 = ROCrateTabulator()
    tb2.read_config(tmp_path / "config.json")

    tb2.crate_to_db(crates["wide"], tmp_path / "newdb.db")

    for table in cf["tables"]:
        tb2.entity_table(table)


def test_all_props(crates, tmp_path):
    tb = tabulator_init(tmp_path, crates["languageFamily"])

    # build our own list of all properties (excluding @ids)
    cf = read_config(tmp_path / "config.json")
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


def test_table_values(crates, tmp_path):
    tb = tabulator_init(tmp_path, crates["languageFamily"])
    cf = read_config(tmp_path / "config.json")
    for table in cf["tables"]:
        tb.entity_table(table)
    tc = TinyCrate(crates["languageFamily"])
    for table in cf["tables"]:
        for row in tb.db.query(f'SELECT * FROM "{table}"'):
            eid = row["entity_id"]
            entity = tc.get(eid)
            assert entity is not None
            for prop in entity:
                if prop == "@id":
                    print("@id", row["entity_id"], entity["@id"], file=sys.stderr)
                    assert row["entity_id"] == entity["@id"]
                else:
                    print(prop, row[prop], entity[prop], file=sys.stderr)
                    assert prop in row
