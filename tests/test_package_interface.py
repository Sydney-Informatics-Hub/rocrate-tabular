from pathlib import Path
from rocrate_tabular.tabulator import ROCrateTabulator


def test_config_interface(crates, tmp_path):
    """Test that the first-pass config can be read"""
    cwd = Path(tmp_path)
    dbfile = cwd / "sqlite.db"
    # conffile = cwd / "config.json"
    tb = ROCrateTabulator()
    tb.crate_to_db(crates["minimal"], dbfile)
    tb.infer_config()
    tb.use_tables(["Dataset"])
    # TODO: finish this (check output)
    tb.close()  # for Windows


# TODO: test that passes string to use_tables
