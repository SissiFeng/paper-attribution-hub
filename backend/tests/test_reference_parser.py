from app.services.reference_parser import parse_references


def test_parses_numbered_references_with_doi():
    text = """1. Häse, F.; Roch, L. ChemOS. Science Robotics 2019. doi: 10.1126/scirobotics.aax9876
2. MacLeod, B.; Berlinguette, C. SDL for thin films. Science Advances 2020. doi: 10.1126/sciadv.aaz4244"""
    refs = parse_references(text)
    assert len(refs) == 2
    assert refs[0].doi == "10.1126/scirobotics.aax9876"
    assert refs[0].year == 2019
    assert refs[1].doi == "10.1126/sciadv.aaz4244"


def test_handles_bracketed_index():
    text = """[1] Smith, J. Foo. Nature 2024. doi: 10.1038/test.xyz
[2] Doe, B. Bar."""
    refs = parse_references(text)
    assert len(refs) == 2
    assert refs[0].doi == "10.1038/test.xyz"
    assert refs[1].doi is None


def test_doi_normalized_to_lowercase():
    text = "1. Foo. Bar. doi: 10.1126/SCIROBOTICS.AAX9876"
    refs = parse_references(text)
    assert refs[0].doi == "10.1126/scirobotics.aax9876"
