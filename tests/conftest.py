import pytest


@pytest.fixture
def crates():
    return {
        "minimal": "./tests/crates/minimal",
        "wide": "./tests/crates/wide",
        "textfiles": "./tests/crates/textfiles",
        "utf8": "./tests/crates/utf8",
        "languageFamily": "./tests/crates/languageFamily",
        "COOEE": "./tests/crates/COOEE",
    }


@pytest.fixture
def csv_headers():
    return [
        "entity_id",
        "@type",
        "name",
        "description",
        "datePublished",
        "pcdm:memberOf",
        "pcdm:memberOf_id",
        "license",
        "license_id",
        "inLanguage",
        "inLanguage_id",
        "ldac:subjectLanguage",
        "ldac:subjectLanguage_id",
        "arcp://name,custom/terms#languageSubFamily",
        "arcp://name,custom/terms#languageSubFamily_id",
        "hasPart",
        "hasPart_id",
        "hasPart_1",
        "hasPart_id_1",
    ]
