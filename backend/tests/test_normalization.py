from app.services.normalization_service import (
    name_initials,
    normalize_doi,
    normalize_institution,
    normalize_name,
)


def test_normalize_name_handles_diacritics_and_punctuation():
    assert normalize_name("Alán Aspuru-Guzik") == "alan aspuru-guzik"


def test_normalize_name_handles_last_first():
    assert normalize_name("Aspuru-Guzik, Alan") == "alan aspuru-guzik"


def test_normalize_name_handles_initials():
    assert normalize_name("A. Aspuru-Guzik") == "a aspuru-guzik"


def test_name_initials():
    assert name_initials("Alan Aspuru-Guzik") == "a a"


def test_normalize_doi_strips_prefix():
    assert normalize_doi("https://doi.org/10.1038/foo") == "10.1038/foo"
    assert normalize_doi("10.1038/FOO") == "10.1038/foo"
    assert normalize_doi(None) is None


def test_normalize_institution_expands_abbreviations():
    assert normalize_institution("UofT") == "university of toronto"
    assert normalize_institution("Univ. Toronto") == "university toronto"
