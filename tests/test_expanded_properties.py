from util import tabulator, read_config, write_config
from pathlib import Path
from tinycrate.tinycrate import TinyCrate
import sys


# FIXME this is very basic
def test_expanded_properties(crates, tmp_path):
    expand_props = ["author", "publisher"]
    tb = tabulator(tmp_path, crates["languageFamily"])
    cffile = Path(tmp_path) / "config.json"
    cf = read_config(cffile)
    cf["tables"]["Dataset"]["expand_props"] = expand_props

    write_config(cf, cffile)
    tb.load_config(cffile)
    tb.entity_table("Dataset")
    rows = list(tb.db.query("SELECT * FROM Dataset"))
    assert len(rows) == 1
    row = rows[0]

    tc = TinyCrate(crates["languageFamily"])
    te = tc.get(row["entity_id"])
    assert te
    for prop in expand_props:
        rele = tc.deref(te, prop)
        assert rele
        print(row, file=sys.stderr)
        print(rele.props, file=sys.stderr)
        for relprop in rele.props:
            if not relprop == "@id":
                eprop = f"{prop}_{relprop}"
                assert eprop in row
                assert row[eprop] == rele[relprop]
