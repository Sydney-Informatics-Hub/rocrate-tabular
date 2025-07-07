from util import tabulator, read_config, write_config
from pathlib import Path
import sys


def test_expanded_properties(crates, tmp_path):
    tb = tabulator(tmp_path, crates["languageFamily"])
    cffile = Path(tmp_path) / "config.json"
    cf = read_config(cffile)
    cf["tables"]["RepositoryObject"]["expand_props"] = ["author", "publisher"]

    write_config(cf, cffile)
    tb.load_config(cffile)
    tb.entity_table("RepositoryObject")
    rows = list(tb.db.query("SELECT * FROM RepositoryObject"))
    assert len(rows) > 1
    for row in rows:
        print(row, file=sys.stderr)
