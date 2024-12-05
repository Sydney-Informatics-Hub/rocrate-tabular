from rocrate_tabular.tinycrate import TinyCrate, TinyCrateException
from argparse import ArgumentParser
from pathlib import Path
from sqlite_utils import Database
import csv
import json
import requests

PROPERTIES = {
    "row_id": str,
    "source_id": str,
    "source_name": str,
    "property_label": str,
    "target_id": str,
    "value": str,
}

MAX_NUMBERED_COLS = 999  # sqllite limit


def get_as_list(v):
    """Ensures that a value is a list"""
    if v is None:
        return []
    if type(v) is list:
        return v
    return [v]


def get_as_id(v):
    """If v is an ID, return it or else return None"""
    if type(v) is dict:
        mid = v.get("@id", None)
        if mid is not None:
            return mid
    return None


class ROCrateTabulatorException(Exception):
    pass


class ROCrateTabulator:
    def __init__(self):
        self.crate_dir = None
        self.db_file = None
        self.db = None
        self.crate = None
        self.cf = None

    def load_config(self, config_file):
        """Load config from file"""
        with open(config_file, "r") as jfh:
            self.cf = json.load(jfh)

    def infer_config(self):
        """Create a default config based on the properties table"""
        if self.db is None:
            raise ROCrateTabulatorException(
                "Need to run crate_to_db before infer_config"
            )
        self.cf = {"export_queries": {}, "tables": {}, "potential_tables": {}}
        query = """
            SELECT DISTINCT(p.value)
            FROM property p
            WHERE p.property_label = '@type'
        """
        types = self.db.query(query)

        for attype in [row["value"] for row in types]:
            self.cf["potential_tables"][attype] = {
                "all_props": [],
                "ignore_props": [],
                "expand_props": [],
            }

    def write_config(self, config_file):
        """Write the config file with any changes made"""
        with open(config_file, "w") as f:
            json.dump(self.cf, f, indent=4)

    def crate_to_db(self, crate_uri, db_file):
        """Load the crate and build the properties table"""
        self.crate_dir = crate_uri
        try:
            jsonld = self._load_crate(crate_uri)
            self.crate = TinyCrate(jsonld=jsonld, directory=crate_uri)
        except Exception as e:
            raise ROCrateTabulatorException(f"Crate load failed: {e}")
        self.db_file = db_file
        self.db = Database(self.db_file, recreate=True)
        properties = self.db["property"].create(PROPERTIES)
        seq = 0
        propList = []
        for e in self.crate.all():
            for row in self.entity_properties(e):
                row["row_id"] = seq
                seq += 1
                propList.append(row)
        properties.insert_all(propList)
        return self.db

    def _load_crate(self, crate_uri):
        if crate_uri[:4] == "http":
            response = requests.get(crate_uri)
            return response.json()
        with open(Path(crate_uri) / "ro-crate-metadata.json", "r") as jfh:
            return json.load(jfh)

    def entity_properties(self, e):
        """Returns a generator which yields all of this entity's rows"""
        eid = e["@id"]
        if eid is None:
            return
        ename = e["name"]
        for key, value in e.props.items():
            if key != "@id":
                for v in get_as_list(value):
                    maybe_id = get_as_id(v)
                    if maybe_id is not None:
                        yield self.relation_row(eid, ename, key, maybe_id)
                    else:
                        yield self.property_row(eid, ename, key, v)

    def relation_row(self, eid, ename, prop, tid):
        """Return a row representing a relation between two entities"""
        target_name = ""
        target = self.crate.get(tid)
        if target:
            target_name = target["name"]
        return {
            "source_id": eid,
            "source_name": ename,
            "property_label": prop,
            "target_id": tid,
            "value": target_name,
        }

    def property_row(self, eid, ename, prop, value):
        """Return a row representing a property"""
        return {
            "source_id": eid,
            "source_name": ename,
            "property_label": prop,
            "value": value,
        }

    def entity_table(self, table, text):
        """Build a db table for one type of entity"""
        self.text_prop = text

        for entity_id in self.fetch_ids(table):
            properties = list(self.fetch_entity(entity_id))
            self.flatten_one_entity(table, entity_id, properties)

    # Some helper methods for wrapping SQLite statements

    def fetch_ids(self, entity_type):
        """return a generator which yields all ids of this type"""
        rows = self.db.query(
            """
            SELECT p.source_id
            FROM property p
            WHERE p.property_label = '@type' AND p.value = ?
        """,
            [entity_type],
        )
        for entity_id in [row["source_id"] for row in rows]:
            yield entity_id

    def fetch_entity(self, entity_id):
        """return a generator which yields all properties for an entity"""
        properties = self.db.query(
            """
            SELECT property_label, value, target_id
            FROM property
            WHERE source_id = ?
            """,
            [entity_id],
        )
        for prop in properties:
            yield prop

    def flatten_one_entity(self, table, entity_id, properties):
        """Add a single entity's properties to its table"""
        # FIXME - analyse properties and find multiples
        # Create a dictionary to hold the properties for this entity
        entity_data = {"entity_id": entity_id}
        config = self.cf["tables"][table]
        expand_props = config.get("expand_props")
        ignore_props = config.get("ignore_props")
        # Loop through properties and add them to entity_data
        props = set()
        for prop in properties:
            name = prop["property_label"]
            value = prop["value"]
            target = prop["target_id"]
            props.add(name)

            if self.text_prop and name == self.text_prop:
                try:
                    print(f"looking for target: {target}")
                    entity_data[name] = self.crate.get(target).fetch()
                except TinyCrateException as e:
                    entity_data[name] = f"load failed: {e}"

            else:
                if name in expand_props and target:
                    props.update(
                        self.add_expanded_property(
                            entity_data, ignore_props, name, target
                        )
                    )
                else:
                    # If it's a normal property, just add it to the entity_data dictionary
                    if name not in ignore_props:
                        self.set_property(entity_data, name, value, target)
        self.db[table].insert(entity_data, pk="entity_id", replace=True, alter=True)
        props.update(config["all_props"])
        config["all_props"] = list(props)

    def add_expanded_property(self, entity_data, ignore_props, name, target):
        """Do a subquery on a target ID to make expanded properties like
        author_name author_id"""
        props = set()
        for expanded_prop in self.fetch_entity(target):
            expanded_property_name = f"{name}_{expanded_prop['property_label']}"
            # Special case - if this is indexable text then we want to read t
            props.add(expanded_property_name)
            if expanded_property_name not in ignore_props:
                self.set_property(
                    entity_data,
                    expanded_property_name,
                    expanded_prop["value"],
                    expanded_prop["target_id"],
                )
        return props

    # Both of the following mutate entity_data. I'm not very happy about it

    def set_property(self, entity_data, name, value, target_id):
        """Add a property to entity_data, and add the target_id if defined"""
        self.set_property_name(entity_data, name, value)
        if target_id:
            self.set_property_name(entity_data, f"{name}_id", target_id)

    def set_property_name(self, entity_data, name, value):
        """FIXME - strategy by property goes here"""
        if name in entity_data:
            # Find the first available integer to append to property_name
            i = 1
            while f"{name}_{i}" in entity_data:
                i += 1
            name = f"{name}_{i}"
            if i > MAX_NUMBERED_COLS:
                raise ROCrateTabulatorException(f"Too many columns for {name}")
        entity_data[name] = value

    def export_csv(self):
        """Export csvs as configured"""
        queries = self.cf["export_queries"]
        for csv_file, query in queries.items():
            result = list(self.db.query(query))
            # Convert result into a CSV file using csv writer
            with open(csv_file, "w", newline="") as csvfile:
                writer = csv.DictWriter(
                    csvfile, fieldnames=result[0].keys(), quoting=csv.QUOTE_MINIMAL
                )
                writer.writeheader()
                for row in result:
                    for key, value in row.items():
                        if isinstance(value, str):
                            row[key] = value.replace("\n", "\\n").replace("\r", "\\r")
                    writer.writerow(row)

        # print(f"Exported data to {csv_file}")

    def find_csv(self):
        files = self.db.query("""
        SELECT source_id
        FROM property
        WHERE property_label = '@type' AND value = 'File' AND LOWER(source_id) LIKE '%.csv'
    """)
        for entity in files:
            entity_id = entity["source_id"]
            print("Adding csv for {entity_id}")
            csvtext = self.crate.get(entity_id).fetch()
            reader = csv.DictReader(csvtext.splitlines())
            rows = list(reader)
            print(rows)
            if rows:
                # Insert rows into the table (the table will be created if it doesn't exist)
                self.db["csv_files"].insert_all(rows, pk="id", alter=True, ignore=True)
            # `pk="id"` assumes there's an 'id' column; if no primary key, you can remove it.


# Style guide: all print() output should be in the section below this -
# the library code above needs to be able to work in contexts where it has to
# write an sqlite database to stdout


def cli():
    ap = ArgumentParser("RO-Crate to tables")
    ap.add_argument(
        "crate",
        type=str,
        help="RO-Crate URL or directory",
    )
    ap.add_argument(
        "output",
        default="output.db",
        type=Path,
        help="SQLite database file",
    )
    ap.add_argument(
        "-c", "--config", default="config.json", type=Path, help="Configuration file"
    )
    ap.add_argument(
        "-t",
        "--text",
        default=None,
        type=str,
        help="Entities of this type will be loaded as text into the database",
    )
    ap.add_argument(
        "--csv",
        action="store_true",
        help="Find any CSV files and concatenate them into a table",
    )
    args = ap.parse_args()

    tb = ROCrateTabulator()

    print("Building properties table")
    tb.crate_to_db(args.crate, args.output)

    if args.config.is_file():
        print(f"Loading config from {args.config}")
        tb.load_config(args.config)
    else:
        print(f"Config {args.config} not found - generating default")
        tb.infer_config()

    for table in tb.cf["tables"]:
        print(f"Building entity table for {table}")
        tb.entity_table(table, args.text)  # should args.text be config?

    tb.write_config(args.config)
    print(f"""
Updated config file: {args.config}, edit this file to change the flattening configuration or deleted it to start over
""")

    if args.csv:
        tb.find_csv()

    tb.export_csv()


if __name__ == "__main__":
    cli()
