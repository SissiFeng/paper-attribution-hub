"""End-to-end: ingest fulltexts, build embeddings, classify, verify v0.2 wins."""
from sqlalchemy import select

from app.models import PaperChunk, PaperEvidence, PaperSection


def test_p001_has_sections_and_chunks(fulltext_seeded_session):
    sections = list(
        fulltext_seeded_session.execute(
            select(PaperSection).where(PaperSection.paper_id == "P001")
        ).scalars()
    )
    assert {s.section_type for s in sections} >= {"abstract", "methods", "acknowledgements"}
    chunks = list(
        fulltext_seeded_session.execute(
            select(PaperChunk).where(PaperChunk.paper_id == "P001")
        ).scalars()
    )
    assert chunks
    assert all(c.embedding for c in chunks)


def test_p001_extracts_funding_evidence(fulltext_seeded_session):
    rows = list(
        fulltext_seeded_session.execute(
            select(PaperEvidence).where(PaperEvidence.paper_id == "P001")
        ).scalars()
    )
    types = {r.evidence_type for r in rows}
    assert "funding_acknowledgement" in types
    assert "sdl_methodology" in types
    funding_text = next(
        r.evidence_text for r in rows if r.evidence_type == "funding_acknowledgement"
    ).lower()
    assert "acceleration consortium" in funding_text


def test_p003_promoted_to_related_via_fulltext(fulltext_seeded_session):
    """P003 was EXCLUDE in v0.1 — generic GNN paper with no AC author.
    Its fulltext includes 'Acceleration Consortium' postdoctoral fellowship,
    so v0.2 must lift it at least to RELATED_RELEVANT."""
    from app.services.relevance_classifier import classify_all

    classify_all(fulltext_seeded_session)
    from app.models import Paper

    paper = fulltext_seeded_session.get(Paper, "P003")
    assert paper is not None
    assert paper.classification is not None
    assert paper.classification.label in {"RELATED_RELEVANT", "CORE_RELEVANT"}
    assert paper.classification.fulltext_evidence_score > 0


def test_p008_stays_adjacent_without_ac_mention(fulltext_seeded_session):
    """P008 has full text but no AC funding mention → no upgrade past ADJACENT."""
    from app.services.relevance_classifier import classify_all

    classify_all(fulltext_seeded_session)
    from app.models import Paper

    paper = fulltext_seeded_session.get(Paper, "P008")
    assert paper.classification.label in {"ADJACENT", "UNCERTAIN", "EXCLUDE"}
    assert paper.classification.label != "RELATED_RELEVANT"


def test_funding_evidence_reasons_cite_chunk(fulltext_seeded_session):
    from app.services.relevance_classifier import classify_all

    classify_all(fulltext_seeded_session)
    from app.models import Paper

    paper = fulltext_seeded_session.get(Paper, "P001")
    reasons = paper.classification.reasons or []
    assert any("Funding acknowledgement" in r and "chunk" in r for r in reasons)
