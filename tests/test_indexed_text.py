from util import tabulator_init


def test_no_index(crates, tmp_path):
    tb = tabulator_init(tmp_path, crates["textfiles"])
    tb.entity_table("Dataset")
    rows = list(tb.db.query("SELECT * FROM Dataset WHERE entity_id = 'doc001'"))
    assert len(rows) == 1
    te = tb.crate.get("doc001/textfile.txt")
    assert rows[0]["indexableText"] == te["name"]


def test_index_tabulator(crates, tmp_path):
    tb = tabulator_init(tmp_path, crates["textfiles"])
    tb.text_prop = "indexableText"
    tb.entity_table("Dataset")
    rows = list(tb.db.query("SELECT * FROM Dataset WHERE entity_id = 'doc001'"))
    assert len(rows) == 1
    assert rows[0]["indexableText"][:27] == "Lorem ipsum dolor sit amet,"


def test_index_build(crates, tmp_path):
    tb = tabulator_init(tmp_path, crates["textfiles"])
    tb.entity_table("Dataset", "indexableText")
    rows = list(tb.db.query("SELECT * FROM Dataset WHERE entity_id = 'doc001'"))
    assert len(rows) == 1
    assert rows[0]["indexableText"][:27] == "Lorem ipsum dolor sit amet,"
