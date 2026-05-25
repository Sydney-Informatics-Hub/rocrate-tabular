# RO-Crate Tabulator

Python library to turn an RO-Crate into tabular formats.

## Installation

Install [uv](https://docs.astral.sh/uv/), then

    > git clone git@github.com:Sydney-Informatics-Hub/rocrate-tabular.git
    > cd rocrate-tabular
    > uv run tabulator --help

`uv run` should create a local venv and install the dependencies

## Usage: command line tool

The command-line tool uses a two-pass process. The first pass
loads the RO-Crate, analyses it, and writes out two files: a
sqlite database file which contains a single table, `properties`,
which has all of the properties of all of the entities in the
crate, and a config file which has been prepopulated with the
entities found in the RO-Crate. (The `properties` table isn't
useful to end-users - it's an intermediate representation which
has all of the metadata info in the RO-Crate in a form which
is more efficient to query than JSON.)

This first pass is only necessary if you don't know anything
about the structure or entities in the RO-Crate. If you already
know what entities you're building tables for, and how they
are related to one another, you can write your own config
file and skip straight to the second pass.

The prepopulated config file from the first pass can be edited
to tell the tabulator which types of entities are to be
rendered into tables, and which properties should be ignored
or expanded in this process. On the second pass, these
new tables are added to the sqlite database file, and optionally
written out as CSV files.

### First pass - automatic discovery and config

In the following examples, the RO-Crate directory is in
`./crate`, the database file is `crate.db` and the config file is
`config.json`

The first pass is triggered if the config file specified is not
found:

    > uv run tabulator -c config.json ./crate crate.db

The new `config.json` file will look something like the following
(depending on what the tabulator finds in the RO-Crate):

    {
        "export_queries": {},
        "tables": {},
        "potential_tables": {
            "RepositoryObject": {
                "all_props": [],
                "ignore_props": [],
                "expand_props": []
            },
            "Person": {
                "all_props": [],
                "ignore_props": [],
                "expand_props": []
            },
            "CreativeWork": {
                "all_props": [],
                "ignore_props": [],
                "expand_props": []
            },
            "Dataset": {
                "all_props": [],
                "ignore_props": [],
                "expand_props": []
            },
            "RepositoryCollection": {
                "all_props": [],
                "ignore_props": [],
                "expand_props": []
            },

        [... more potential tables ...]
    }

Every entity type in the crate will have an entry in the
`potential_tables` object.

### Second pass: building entity tables and CSV

To actually build tables for the required entities, you need to
add the entities you want to the `tables` object. For example,
to build tables for `RepositoryObject` and `Person` entities,
the config file should look like the following:

    {
        "export_queries": {},
        "tables": {
            "RepositoryObject": {
                "all_props": [],
                "ignore_props": [],
                "expand_props": []
            },
            "Person": {
                "all_props": [],
                "ignore_props": [],
                "expand_props": []
            }
         },
        "potential_tables": {
       [... more potential tables ...]
         }
    }

To build the tables, run the tabulator with a config file which
has at least one entry in the `tables` section.

    > uv run tabulator -c config.json ./crate crate.db

This will add tables called `RepositoryObject` and `Person` to
the database file. Note that if you have skipped the first pass,
because you already know what tables you want, this stage will
also build the `properties` table the first time it is run.

On the build pass, the tabulator will add all of the properties
it finds in the new tables to the `all_props` objects in the
config. This is intended to help you decide which properties
you're actually interested in so that you can add the
uninmportant ones to `ignore_props`. For example:


    {
        "export_queries": {},
        "tables": {
            "RepositoryObject": {
                "all_props": [
                    "license",
                    "@type",
                    "conformsTo",
                    "inLanguage",
                    "name",
                    "ldac:communicationMode",
                    "pcdm:memberOf",
                    "description",
                    "ldac:linguisticGenre",
                    "hasPart",
                    "datePublished",
                    "ldac:indexableText",
                    "ldac:mainText",
                    "ldac:speaker"
                ],
                "ignore_props": [],
                "expand_props": [],
                "junctions": [
                    "hasPart",
                    "ldac:speaker",
                    "hasPart"
                ]
            },
            "Person": {
                "all_props": [
                    "@type",
                    "age",
                    "role",
                    "name",
                    "nationality",
                    "firstName",
                    "education",
                    "birthplace",
                    "gender",
                    "lastName",
                    "occupation",
                    "otherlanguages",
                    "mothertongue"
                ],
                "ignore_props": [],
                "expand_props": [],
                "junctions": []
            }
        }
    }

## Ignoring properties

Any properties added to the `ignore_props` list for a table's
config will be ignored and not added to the table or CSV export.

## Expanding properties

The `expand_props` field in a table's config is used to tell the
tabulator to try to follow references from a particular property
and bring the values from linked entities into the primary
table as columns. For example, here is a fragment of an
RO-Crate with a CreativeWork and a Person who is its author:

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

If "author" is in `expand_props` on the "CreativeWork" entry in
the "tables" section of the config, the following additional
columns will be created in the CreativeWork table:

    author_@id
    author_@type
    author_name

If the tabulator finds multiple linked entites (a CreativeWork
with more than one author, in the example) its behaviour changes
depending on the maximum number of relations it finds for these
entities in the entire crate.

If there are no CreativeWorks with more than 10 authors, multiple
sets of columns are added to the primary table, as in:

    author1_@id
    author1_@type
    author1_name

    author2_@id
    author2_@type
    author2_name

If more than 10 relations are found, a junction table is created
which links CreativeWorks to Authors, and will be listed in the
`junctions` section of the CreativeWorks config.

Note: this is a bit of a hack and a future version of the
tabulator should allow you to specify what behaviour you want,
or give other options like including multiple relations as a
JSON value in a single column.

## Loading main text files

A common use case for RO-Crates containing text is to build a
table which has both the metadata describing a document, and the
text of the document.  The tablulator accepts a command-line
argument, `--text`, which specifies the property pointing to
a File entity representing the text to be indexed (for *any*
entity). For example, to load files pointed to by the
`ldac:mainText` property, use:

    > uv run tabulator --text "ldac:mainText" -c config.json ./crate crate.db

In a future release, this option will be moved to the config
file.

## CSV exports

To export a CSV version of any of the tables, you can define a
filename / query pair in the "export queries" section of the
config file, for example:

    {
        "export_queries": {
            "repo_objects.csv": "SELECT * FROM RepositoryObject"
        },
        "tables": {
            "RepositoryObject": {
                "all_props": [ ... ],
                "ignore_props": [ ... ],
                "expand_props": [ .. ]
            }
        }
    }

## Using tabulator as a library

The tabulator can also be used as a library from within another
Python script or a Jupyter notebook. The interface is via an
ROCrateTabulator object, which you can configure either by
loading a config file, or by assigning a Python data structure
directly to the `.config` property.

Here is an example of building a database with two tables
and then converting one of the tables to a dataframe:

Note that the property to load as Files is configured separately
using the `.text_prop` property.


    from rocrate_tabular.tabulator import ROCrateTabulator

    import pandas as pd
    import sqlite3

    CRATE = "./crates/ice-aus/"
    DBFILE = "./ice-aus.db"

    tb = ROCrateTabulator()

    tb.config = {
        "tables": {
            "RepositoryObject": {
                "all_props": [],
                "expand_props": [ "author" ],
                "ignore_props": [ "@type", "conformsTo" ],
            },
            "Person": {
                "all_props": [],
                "ignore_props": [ "@type", "conformsTo" ],
            },
        },
    }

    tb.text_prop = "ldac:mainText"

    print("Building properties table")
    tb.crate_to_db(CRATE, DBFILE)
    print("Building RepositoryObject table")
    tb.entity_table("RepositoryObject")
    print("Building Person table")
    tb.entity_table("Person")

    # get a dataframe from the sqlite db
    # pandas needs a sqlite3 connection

    conn = sqlite3.connect(DBFILE)
    df = pd.read_sql_query("SELECT * FROM RepositoryObject", conn)

    print(df.columns)
    print(df.head())

Note that this usage of the library assumes that you are ok
with loading the whole crate and writing it out as a sqlite db
to disk somewhere. A later version of this library should support
some kind of streamed model where we don't have  to do this.
