from pathlib import Path

from sqlite_utils import Database
from tinycrate.tinycrate import TinyCrate
from util import read_config

from rocrate_tabular.tabulator import ROCrateTabulator


def test_elaborated_properties(crates, tmp_path):
    """Pedantic test of the elaborated properties table - build it and then
    go through the crate and check that everything can be found in properties"""
    cwd = Path(tmp_path)
    dbfile = cwd / "sqlite.db"
    conffile = cwd / "config.json"
    tb = ROCrateTabulator()
    tb.crate_to_db(crates["languageFamily"], dbfile)
    tb.infer_config()
    tb.write_config(conffile)
    tb.close()  # for Windows
    crate = TinyCrate(crates["languageFamily"])
    db = Database(dbfile)
    for entity in crate.all():
        for prop in entity:
            values = entity[prop]
            rows = db.query(
                """
    SELECT value, target_id FROM property
    WHERE source_id = ? AND property_label = ? 
            """,
                [entity.id, prop],
            )
            for row in rows:
                if row["target_id"]:
                    assert {"@id": row["target_id"]} in values
                else:
                    assert row["value"] in values


def test_potential_tables(crates, tmp_path):
    """Check that all the expected items are in the potential tables"""
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
