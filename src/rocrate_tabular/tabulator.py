import csv
import json
import logging
import re
import sys
from argparse import ArgumentParser
from dataclasses import dataclass, field
from os import PathLike
from pathlib import Path

import requests
from sqlite_utils import Database
from tinycrate.tinycrate import TinyCrate, TinyCrateException, minimal_crate
from tqdm import tqdm

logger = logging.getLogger(__name__)


# TERMINOLOGY

# a 'relation' is an entity which refers to another entity by some property
# whose value is like { '@id': '#foo' }

# a 'junction' is a many-to-many relation through its own table which is
# used to capture relations in the database like:
#
# [
#   {
#       "@id": "#adocument"
#       "@type": "CreativeWork"
#       "name": "Title of Document"
#       "author": [
#           { "@id": "#jdoe" },
#           { "@id": "#jroe" }
#       ]
#   },
#   {
#       "@id": "#jdoe",
#       "@type": "Person",
#       "name": "John Doe"
#   },
#   {
#       "@id": "#jroe",
#       "@type": "Person",
#       "name": "Jane Roe"
#   }
# ]
#
# this is modeled in the database as
# Document [ id, name ]
# Document_hasPart [ Document_id, Person_id ]
# Person [ id, name ]
#
# Note that the junction table is on Type_property which means that the
# target @ids could be of different @types - for example, Datasets could have
# Datesets and Files as hasParts

PROPERTIES = {
    "row_id": str,
    "source_id": str,
    "source_name": str,
    "property_label": str,
    "target_id": str,
    "value": str,
}

MAX_NUMBERED_COLS = 10


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


@dataclass
class EntityRecord:
    """Class which represents an entity as mapped to a database row,
    plus any records which are used in junction tables"""

    table: str
    tabulator: object
    entity_id: str
    expand_props: list = field(default_factory=list)
    ignore_props: list = field(default_factory=list)
    props: set = field(default_factory=set)
    data: dict = field(default_factory=dict)
    junctions: dict = field(default_factory=dict)

    def build(self, properties):
        """Takes the properties of this entity and builds a dictionary to
        be inserted into the database, plus any junction records required"""
        self.data["entity_id"] = self.entity_id
        self.cf = self.tabulator.cf["tables"][self.table]
        self.text_prop = self.tabulator.text_prop
        self.expand_props = self.cf.get("expand_props", [])
        self.ignore_props = self.cf.get("ignore_props", [])
        for prop_row in properties:
            prop = prop_row["property_label"]
            value = prop_row["value"]
            target = prop_row["target_id"]
            self.props.add(prop)
            if prop == self.text_prop:
                try:
                    self.data[prop] = self.crate.get(target).fetch()
                except TinyCrateException as e:
                    self.data[prop] = f"load failed: {e}"
            else:
                if prop in self.expand_props and target:
                    self.add_expanded_property(prop, target)
                else:
                    if prop not in self.ignore_props:
                        self.set_property(prop, value, target)
        return self.props

    def add_expanded_property(self, prop, target):
        """Do a subquery on a target ID to make expanded properties like
        author_name author_id"""
        for ep_row in self.tabulator.fetch_properties(target):
            expanded_prop = f"{prop}_{ep_row['property_label']}"
            # Special case - if this is indexable text then we want to read t
            self.props.add(expanded_prop)
            if expanded_prop not in self.ignore_props:
                self.set_property(
                    expanded_prop,
                    ep_row["value"],
                    ep_row["target_id"],
                )

    def set_property(self, prop, value, target_id):
        """Add a property to entity_data, and add the target_id if defined"""
        if prop in self.cf["junctions"]:
            self.set_property_relational(prop, value, target_id)
        else:
            self.set_property_numbered(prop, value)
            if target_id:
                self.set_property_numbered(f"{prop}_id", target_id)

    # TODO: we should only call this if there are more than one
    def set_property_numbered(self, prop, value):
        if prop in self.data:
            # Find the first available integer to append to property_name
            i = 1
            while f"{prop}_{i}" in self.data:
                i += 1
            prop = f"{prop}_{i}"
            if i > MAX_NUMBERED_COLS:
                raise ROCrateTabulatorException(f"Too many columns for {prop}")
        self.data[prop] = value

    def set_property_relational(self, prop, value, target_id):
        """Add junctions between an entity and related entities"""
        # FIXME what happens to value here?
        if prop not in self.junctions:
            self.junctions[prop] = [target_id]
        else:
            self.junctions[prop].append(target_id)


class ROCrateTabulator:
    def __init__(self):
        self.crate_dir = None
        self.db_file = None
        self.db = None
        self.crate = None
        self.cf = None
        self.text_prop = None
        self.schemaCrate = minimal_crate()
        self.encodedProps = {}

    def read_config(self, config_file):
        """Load config from file"""
        close_file = False
        if isinstance(config_file, (str, PathLike)):
            config_file = open(config_file, "r")
            close_file = True
        else:
            config_file.seek(0)

        self.cf = json.load(config_file)

        if close_file:
            config_file.close()
        else:
            config_file.seek(0)

    def infer_config(self):
        """Create a default config based on the properties table"""
        if self.db is None:
            raise ROCrateTabulatorException(
                "Need to run crate_to_db before infer_config"
            )
        self.cf = {"export_queries": {}, "tables": {}, "potential_tables": {}}

        for attype in self.fetch_types():
            self.cf["potential_tables"][attype] = {
                "all_props": [],
                "ignore_props": [],
                "expand_props": [],
            }

    def write_config(self, config_file):
        """Write the config file with any changes made"""
        close_file = False
        if isinstance(config_file, (str, PathLike)):
            config_file = open(config_file, "w")
            close_file = True
        else:
            config_file.seek(0)

        json.dump(self.cf, config_file, indent=4)

        if close_file:
            config_file.close()
        else:
            config_file.seek(0)

    def crate_to_db(self, crate_uri, db_file, rebuild=True):
        """Load the crate and build the properties and relations tables"""
        self.crate_dir = crate_uri
        try:
            jsonld = self._load_crate(crate_uri)
            self.crate = TinyCrate(jsonld)
        except Exception as e:
            raise ROCrateTabulatorException(f"Crate load failed: {e}")
        self.db_file = db_file
        if not rebuild:
            if not Path(db_file).is_file():
                raise ROCrateTabulatorException(f"db file {db_file} not found")
            self.db = Database(self.db_file)
            return
        self.db = Database(self.db_file, recreate=True)
        properties = self.db["property"].create(PROPERTIES)
        seq = 0
        propList = []
        for e in tqdm(self.crate.all()):
            for row in self.entity_properties(e):
                row["row_id"] = seq
                seq += 1
                propList.append(row)
        properties.insert_all(propList)
        return self.db

    def close(self):
        """Close the connection to the SQLite database - for Windows users"""
        self.db.close()

    def dump_structure(self):
        """Testing getting metadata about relations from the database"""
        # get all types

        for t in self.fetch_types():
            logger.info(f"@type: {t}")
            query = """
    SELECT p.source_id, p.property_label, count(p.target_id) as n_links
    FROM property as p
    WHERE p.source_id IN (
        SELECT p.source_id
        FROM property p
        WHERE p.property_label = '@type' AND p.value = ?
        )
    GROUP BY p.source_id, p.property_label
    ORDER BY n_links desc
    LIMIT 1
    """
            summary = self.db.query(query, [t])
            for row in summary:
                if row["n_links"] > 0:
                    logger.info(
                        row["source_id"]
                        + "."
                        + row["property_label"]
                        + ": "
                        + str(row["n_links"])
                    )

    def _load_crate(self, crate_uri):
        if crate_uri[:4] == "http":
            response = requests.get(crate_uri)
            return response.json()
        with open(
            Path(crate_uri) / "ro-crate-metadata.json", "r", encoding="utf-8"
        ) as jfh:
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

    def entity_table(self, table):
        """Build a db table for one type of entity. Returns a set() of all
        the properties found during the build"""
        self.entity_table_plan(table)
        entities = []
        allprops = set()
        for entity_id in tqdm(list(self.fetch_ids(table))):
            entity = EntityRecord(tabulator=self, table=table, entity_id=entity_id)
            props = entity.build(self.fetch_properties(entity_id))
            allprops.update(props)
            entities.append(entity.data)
            for prop, target_ids in entity.junctions.items():
                jtable = f"{table}_{prop}"
                seq = 0
                for target_id in target_ids:
                    self.db[jtable].insert(
                        {
                            "seq": seq,
                            "entity_id": entity_id,
                            "target_id": target_id,
                        },
                        pk=("entity_id", "target_id"),
                        replace=True,
                        alter=True,
                    )
                    seq += 1
        self.db[table].insert_all(entities, pk="entity_id", replace=True, alter=True)
        return allprops

    def entity_table_plan(self, table):
        """Check entity relations to see if any need to be done as a junction
        table to avoid huge numbers of expanded columns"""
        if "junctions" not in self.cf["tables"][table]:
            self.cf["tables"][table]["junctions"] = []
        for prop_counts in self.fetch_relation_counts(table):
            if prop_counts["n_links"] > MAX_NUMBERED_COLS:
                label = prop_counts["property_label"]
                print(f"{table}.{label} > {MAX_NUMBERED_COLS} relations")
                self.cf["tables"][table]["junctions"].append(label)

    # Some helper methods for wrapping SQLite statements

    def fetch_types(self):
        """return all types in the database"""
        rows = self.db.query("""
            SELECT DISTINCT(p.value)
            FROM property p
            WHERE p.property_label = '@type'
        """)
        for t in [row["value"] for row in rows]:
            yield t

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

    def fetch_properties(self, entity_id):
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

    def fetch_relation_counts(self, t):
        query = """
    SELECT p.source_id, p.property_label, count(p.target_id) as n_links
    FROM property as p
    WHERE p.source_id IN (
        SELECT p.source_id
        FROM property p
        WHERE p.property_label = '@type' AND p.value = ?
        )
    GROUP BY p.source_id, p.property_label
    ORDER BY n_links desc
    """
        return self.db.query(query, [t])

    def export_csv(self, rocrate_dir):
        """Export csvs as configured"""

        queries = self.cf["export_queries"]
        # print("Global props", self.global_props)
        # self.cf["global_props"] = list(self.global_props)

        # Ensure rocrate_dir exists if it's provided
        if rocrate_dir is not None:
            Path(rocrate_dir).mkdir(parents=True, exist_ok=True)
        files = []

        for csv_filename, query in queries.items():
            files.append({"@id": csv_filename})
            result = list(self.db.query(query))
            # Convert result into a CSV file using csv writer
            csv_path = csv_filename
            if rocrate_dir is not None:
                csv_path = Path(rocrate_dir) / csv_filename
            with open(csv_path, "w", newline="") as csvfile:
                writer = csv.DictWriter(
                    csvfile, fieldnames=result[0].keys(), quoting=csv.QUOTE_MINIMAL
                )
                writer.writeheader()
                # Check if the key is a string and replace newlines

                keys = set()

                for row in result:
                    for key, value in row.items():
                        if isinstance(value, str):
                            row[key] = value.replace("\n", "\\n").replace("\r", "\\r")
                        keys.add(key)
                    writer.writerow(row)

            # add the schema to the CSV
            schema_id = "#SCHEMA_" + csv_filename
            schema_props = {
                "name": "CSVW Table schema for: " + csv_filename,
                "columns": [],
            }
            for key in keys:
                base_prop = re.sub(r".*_", "", key)
                column_props = {
                    "name": key,
                    "label": base_prop,
                }
                uri = self.crate.resolve_term(base_prop)

                if uri:
                    column_props["propertyUrl"] = uri
                    definition = self.crate.get(uri)
                    if definition:
                        print("definition", definition["rdfs:comment"])
                        column_props["description"] = definition["rdfs:comment"]
                # TODO -- look up local definitions and add a description
                col_id = "#COLUMN_" + csv_filename + "_" + key
                self.schemaCrate.add("csvw:Column", col_id, column_props)
                schema_props["columns"].append({"@id": col_id})

            self.schemaCrate.add(
                ["File", "csvw:Table"],
                csv_filename,
                {
                    "tableSchema": {"@id": schema_id},
                    "name": "Generated export from RO-Crate: " + csv_filename,
                },
            )
            self.schemaCrate.add("csvw:Schema", schema_id, schema_props)

            print(f"Exported {csv_filename} to {csv_path}")

        root_entity = self.schemaCrate.root()
        root_entity["hasPart"] = files
        root_entity["name"] = "CSV exported from RO-Crate"
        self.schemaCrate.write_json(rocrate_dir)

    def find_csv(self):
        files = self.db.query("""
        SELECT source_id
        FROM property
        WHERE property_label = '@type' AND value = 'File' AND LOWER(source_id) LIKE '%.csv'
    """)
        for entity_id in [row["source_id"] for row in files]:
            entity_id = entity_id.replace("#", "")
            self.add_csv(self.crate_dir / entity_id, "csv_files")

    def add_csv(self, csv_path, table_name):
        with open(csv_path, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            rows = list(reader)
            if rows:
                # Insert rows into the table (the table will be created if it doesn't exist)
                self.db[table_name].insert_all(rows, pk="id", alter=True, ignore=True)
            # `pk="id"` assumes there's an 'id' column; if no primary key, you can remove it.


# Style guide: all print() output should be in the section below this -
# the library code above needs to be able to work in contexts where it has to
# write an sqlite database to stdout


def parse_args(arg_list=None):
    ap = ArgumentParser("RO-Crate to tables")
    ap.add_argument(
        "crate",
        type=str,
        help="Input RO-Crate URL or directory",
    )
    ap.add_argument(
        "output",
        default="output.db",
        type=Path,
        help="SQLite database file",
    )
    ap.add_argument(
        "--csv", default="csv", type=Path, help="Output directory for CSV files"
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
        "--concat",
        action="store_true",
        help="Find any CSV files and concatenate them into a table",
    )
    ap.add_argument(
        "--rebuild",
        action="store_true",
        help="Force rebuild of the database",
    )
    ap.add_argument(
        "--structure",
        action="store_true",
        help="Report on the database structure",
    )
    return ap.parse_args(arg_list)


def main(args):
    tb = ROCrateTabulator()

    if Path(args.output).is_file() and not args.rebuild:
        print("Loading properties table")
        tb.crate_to_db(args.crate, args.output, rebuild=False)
    else:
        print("Building properties table")
        tb.crate_to_db(args.crate, args.output)

    if args.structure:
        tb.dump_structure()
        sys.exit()

    if args.config.is_file():
        print(f"Loading config from {args.config}")
        tb.read_config(args.config)
    else:
        print(f"Config {args.config} not found - generating default")
        tb.infer_config()

    tb.text_prop = args.text
    for table in tb.cf["tables"]:
        print(f"Building entity table for {table}")
        allprops = tb.entity_table(table)
        tb.cf["tables"][table]["all_props"] = list(allprops)

    tb.write_config(args.config)
    print(f"""
Updated config file: {args.config}, edit this file to change the flattening configuration or deleted it to start over
""")

    if args.concat:
        tb.find_csv_contents()

    tb.export_csv(args.csv)


def cli():
    args = parse_args()
    main(args)


if __name__ == "__main__":
    cli()
