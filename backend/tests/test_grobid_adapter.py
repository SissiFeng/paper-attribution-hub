"""Tests for the GROBID adapter. Runs entirely against a TEI XML fixture so
CI doesn't need a GROBID container."""
from pathlib import Path

import pytest

from app.services.grobid_adapter import parse_tei_xml

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "sample.tei.xml"


@pytest.fixture(scope="module")
def doc():
    return parse_tei_xml(FIXTURE.read_text(encoding="utf-8"))


def test_title_and_source(doc):
    assert "Autonomous closed-loop" in doc.title
    assert doc.source == "grobid"


def test_authors_with_orcid_and_affiliations(doc):
    names = [a.name for a in doc.authors]
    assert "Alan Aspuru-Guzik" in names
    aspuru = next(a for a in doc.authors if a.name == "Alan Aspuru-Guzik")
    assert aspuru.orcid == "0000-0003-1024-3325"
    assert "University of Toronto" in aspuru.affiliations


def test_section_types_canonical(doc):
    types = [s.section_type for s in doc.sections]
    assert "abstract" in types
    assert "introduction" in types
    assert "methods" in types
    assert "results" in types
    assert "discussion" in types
    assert "acknowledgements" in types
    assert "figure_caption" in types


def test_acknowledgement_contains_ac(doc):
    ack = next(s for s in doc.sections if s.section_type == "acknowledgements")
    assert "acceleration consortium" in ack.text.lower()


def test_methods_text_mentions_bayesian(doc):
    methods = next(s for s in doc.sections if s.section_type == "methods")
    assert "bayesian optimization" in methods.text.lower()


def test_references_structured_with_dois(doc):
    assert len(doc.references) == 3
    dois = {r.doi for r in doc.references}
    assert "10.1126/scirobotics.aax9876" in dois
    assert "10.1126/sciadv.aaz4244" in dois
    assert "10.1038/s41586-021-04157-z" in dois
    chemos = next(r for r in doc.references if "ChemOS" in (r.title or ""))
    assert chemos.year == 2019
    assert any("Aspuru-Guzik" in a for a in chemos.authors)


def test_figure_caption_extracted(doc):
    cap = next(s for s in doc.sections if s.section_type == "figure_caption")
    assert "autonomous closed-loop" in cap.text.lower()


def test_is_grobid_available_returns_false_when_url_empty():
    from app.services.grobid_adapter import is_grobid_available

    assert is_grobid_available("") is False
