from pathlib import Path
from rocrate_tabular.tabulator import ROCrateTabulator
from tinycrate.tinycrate import TinyCrate
import json
import sys
import csv


def read_config(cffile):
    with open(cffile, "r") as cfh:
        return json.load(cfh)


def write_config(cf, cffile):
    with open(cffile, "w") as cfh:
        json.dump(cf, cfh)


def test_export(crates, csv_headers, tmp_path):
    cwd = Path(tmp_path)
    dbfile = Path(tmp_path) / "lf.db"
    conffile = cwd / "config.json"
    tb = ROCrateTabulator()
    tb.crate_to_db(crates["languageFamily"], dbfile)
    tb.infer_config()
    tb.write_config(conffile)
    tb.close()

    # load the config and move the potential tables to tables
    cf = read_config(conffile)
    cf["tables"]["RepositoryObject"] = cf["potential_tables"]["RepositoryObject"]
    write_config(cf, conffile)

    tb = ROCrateTabulator()
    tb.load_config(conffile)
    tb.crate_to_db(crates["languageFamily"], dbfile)

    tb.entity_table("RepositoryObject")

    tb.close()

    # add the export_query to build csv
    cf = read_config(conffile)
    cf["export_queries"] = {"lf.csv": "SELECT * FROM RepositoryObject"}
    write_config(cf, conffile)

    tb2 = ROCrateTabulator()
    tb2.load_config(conffile)
    tb2.crate_to_db(crates["languageFamily"], dbfile)
    tb2.entity_table("RepositoryObject")  # shouldn't need to rebuild it
    print(f"Tables: {tb2.db.tables}", file=sys.stderr)
    csvout = cwd / "csv"
    tb2.export_csv(csvout)
    assert csvout.is_dir()
    csvfile = csvout / "lf.csv"
    assert csvfile.is_file()
    assert (csvout / "ro-crate-metadata.json").is_file()
    csv_crate = TinyCrate(csvout)
    assert csv_crate

    csv_data = {}
    with open(csvfile, "r") as cfh:
        head = True
        for row in csv.reader(cfh):
            if head:
                assert row == csv_headers
                head = False
            else:
                csv_data[row[0]] = row

    orig_crate = TinyCrate(crates["languageFamily"])
    objects = [e for e in orig_crate.all() if e.type == "RepositoryObject"]

    for ro in objects:
        assert ro["@id"] in csv_data
