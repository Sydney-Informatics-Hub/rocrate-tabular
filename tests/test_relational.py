from pathlib import Path
from rocrate_tabular.tabulator import ROCrateTabulator
from tinycrate.tinycrate import TinyCrate
from util import read_config, write_config


def test_wide(crates, tmp_path):
    cwd = Path(tmp_path)
    dbfile = Path(tmp_path) / "wide.db"
    conffile = cwd / "wide.json"
    tb = ROCrateTabulator()
    tb.crate_to_db(crates["wide"], dbfile)
    tb.infer_config()
    tb.write_config(conffile)
    tb.close()

    # load the config and move the potential tables to tables
    cf = read_config(conffile)
    cf["tables"]["Dataset"] = cf["potential_tables"]["Dataset"]
    cf["tables"]["File"] = cf["potential_tables"]["File"]
    write_config(cf, conffile)

    tb = ROCrateTabulator()
    tb.load_config(conffile)
    tb.crate_to_db(crates["wide"], dbfile)

    tb.entity_table("Dataset")
    tb.entity_table("File")

    rows = tb.db.query("""
        SELECT d.entity_id as dataset_id,
               d.name as dataset,
               f.entity_id as file_id,
               f.name as file
        FROM Dataset as d
        JOIN Dataset_hasPart as dh on d.entity_id = dh.entity_id
        JOIN File as f on dh.target_id = f.entity_id
        """)

    files = {}

    for row in rows:
        files[row["file_id"]] = row["file"]

    orig_crate = TinyCrate(crates["wide"])
    dataset = orig_crate.get("./")
    assert dataset
