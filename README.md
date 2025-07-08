# RO-Crate Tabulator

Python library to turn an RO-Crate into tabular formats.

## Installation

Install [uv](https://docs.astral.sh/uv/), then

    > git clone git@github.com:Sydney-Informatics-Hub/rocrate-tabular.git
    > cd rocrate-tabular
    > uv run tabulator --help

`uv run` should create a local venv and install the dependencies

## Usage

First pass: this will scan an RO-Crate directory, build a `properties` table
in the sqlite database crate.db, and generate a config file with a list of
all available tables in the `potential_tables` section

    > uv run tabulator -c config.json ./path/to/crate crate.db

You can then edit the config file and move the tables you want to create in
the database and/or csv to the `tables` section, and re-run the tabulator

    > uv run tabulator -c config.json ./path/to/crate crate.db

To export a CSV version of any of the tables, you can define a filename / query
pair in the "export queries" section of the config file, for example:

    {
        "export_queries": {
            "repo_objects.csv": "SELECT * FROM RepositoryObject"
        },
        "tables": {
            "RepositoryObject": {
                "all_props": [ ... ],
                "ignore_props": [ ... ],
                "expand_props": [ ... ]                
            }
        }
    }

## Expanded properties

The "expand_props" field in a table's config can be used to tell the tabulator
to try to follow references from a particular property and bring the values
from linked entities into the primary table as columns. For example, here is
a fragment of an RO-Crate with a CreativeWork and a Person who is its author:

    {
        "@id": "#a_creative_work",
        "@type": "CreativeWork",
        "name": "A Creative Work",
        "description": "A creative work", 
        "author": { "@id": "#jane_smith" }
    },
    {   
        "@id": "#jane_smith",
        "@type": "Person",
        "name": "Jane Smith"
    }

If "author" is in "expand_props" on the "CreativeWork" entry in the "tables"
section of the config, the following additional columns will be created in the
CreativeWork table:

    author_@id
    author_@type
    author_name

## Ignored properties

Properties in the "ignore_props" section will not be added to the tables, and
will also be ignored when looking up expanded properties. 