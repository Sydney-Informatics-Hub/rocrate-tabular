from pathlib import Path
from rocrate_tabular.tabulator import ROCrateTabulator
from util import read_config, write_config


def test_index_text(crates, tmp_path):
    cwd = Path(tmp_path)
    dbfile = cwd / "sqlite.db"
    conffile = cwd / "config.json"
    tb = ROCrateTabulator()
    tb.crate_to_db(crates["textfiles"], dbfile)
    tb.infer_config()
    tb.write_config(conffile)
    tb.close()
    cf = read_config(conffile)
    cf["tables"]["Dataset"] = cf["potential_tables"]["Dataset"]
    write_config(cf, conffile)
    tb = ROCrateTabulator()
    tb.read_config(conffile)
    tb.crate_to_db(crates["textfiles"], dbfile)
    # no indexable text
    tb.entity_table("Dataset")
    rows = list(tb.db.query("SELECT * FROM Dataset WHERE entity_id = 'doc001'"))
    assert len(rows) == 1
    te = tb.crate.get("doc001/textfile.txt")
    assert rows[0]["indexableText"] == te["name"]
    # indexable property set when building the table
    tb.entity_table("Dataset", "indexableText")
    rows = list(tb.db.query("SELECT * FROM Dataset WHERE entity_id = 'doc001'"))
    assert len(rows) == 1
    te = tb.crate.get("doc001/textfile.txt")
    assert rows[0]["indexableText"][:27] == "Lorem ipsum dolor sit amet,"
    # indexable text set on the tabulator
    tb.text_prop = "indexableText"
    tb.entity_table("Dataset")
    rows = list(tb.db.query("SELECT * FROM Dataset WHERE entity_id = 'doc001'"))
    assert len(rows) == 1
    te = tb.crate.get("doc001/textfile.txt")
    assert rows[0]["indexableText"][:27] == "Lorem ipsum dolor sit amet,"
