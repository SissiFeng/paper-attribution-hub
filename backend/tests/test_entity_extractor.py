"""Typed entity extraction (cross-SDL foundation)."""
from __future__ import annotations

from app.models import Paper, PaperChunk, PaperEntity
from app.services.entity_extractor import (
    extract_entities_for_paper,
    load_sdl_entities,
    run_entity_extraction,
)


def _entity(rows: list[PaperEntity], entity_type: str, normalized: str) -> PaperEntity:
    return next(
        r
        for r in rows
        if r.entity_type == entity_type and r.normalized_name == normalized
    )


def test_vocab_loads_all_types_and_maps_aliases():
    vocab = load_sdl_entities()
    assert set(vocab) == {"method", "material", "instrument", "software"}
    assert vocab["method"]["self-driving lab"] == "self-driving laboratory"
    assert vocab["material"]["MOF"] == "metal-organic framework"
    assert vocab["instrument"]["XRD"] == "X-ray diffraction"
    assert vocab["software"]["sklearn"] == "scikit-learn"
    # No matchable term shorter than 3 chars.
    for terms in vocab.values():
        assert all(len(t) >= 3 for t in terms)


def test_extract_from_title_and_abstract(session):
    paper = Paper(
        id="P_ENT1",
        title="Self-driving lab for perovskite discovery",
        abstract="We use Bayesian optimization and an Opentrons liquid handler.",
    )
    session.add(paper)
    session.flush()

    rows = extract_entities_for_paper(session, paper)
    by_key = {(r.entity_type, r.normalized_name) for r in rows}
    assert ("method", "self-driving laboratory") in by_key
    assert ("material", "perovskite") in by_key
    assert ("method", "bayesian optimization") in by_key
    assert ("instrument", "Opentrons") in by_key
    assert ("instrument", "liquid handler") in by_key

    # Title-only hit → 0.6; abstract hit → 0.7.
    assert _entity(rows, "material", "perovskite").confidence == 0.6
    assert _entity(rows, "method", "bayesian optimization").confidence == 0.7
    # Surface form preserved as matched.
    assert _entity(rows, "method", "self-driving laboratory").name == "Self-driving lab"
    # No chunk evidence here.
    assert all(r.evidence_chunk_id is None for r in rows)
    assert all(r.extractor == "vocabulary" for r in rows)


def test_chunk_hits_get_evidence_link_and_higher_confidence(session):
    paper = Paper(id="P_ENT2", title="A study", abstract="We use flow chemistry.")
    chunk = PaperChunk(
        id="chk_ent2",
        paper_id="P_ENT2",
        section_type="methods",
        chunk_text="Synthesis was carried out via flow chemistry on a Chemspeed.",
    )
    session.add_all([paper, chunk])
    session.flush()

    rows = extract_entities_for_paper(session, paper)
    flow = _entity(rows, "method", "flow chemistry")
    # Abstract (0.7) and chunk (0.9) both hit — max wins, with evidence link.
    assert flow.confidence == 0.9
    assert flow.evidence_chunk_id == "chk_ent2"
    assert flow.section == "methods"
    assert _entity(rows, "instrument", "Chemspeed").confidence == 0.9


def test_word_boundaries_block_substring_matches(session):
    paper = Paper(
        id="P_ENT3",
        title="Polymerization kinetics",
        abstract="Hemoflow chemistry is not discussed; we study polymerization.",
    )
    session.add(paper)
    session.flush()

    rows = extract_entities_for_paper(session, paper)
    keys = {(r.entity_type, r.normalized_name) for r in rows}
    # "polymer" inside "polymerization" must not match.
    assert ("material", "polymer") not in keys
    # "flow chemistry" inside "Hemoflow chemistry" must not match.
    assert ("method", "flow chemistry") not in keys


def test_extraction_is_idempotent(session):
    paper = Paper(id="P_ENT4", title="Bayesian optimization of catalysts")
    session.add(paper)
    session.flush()

    first = extract_entities_for_paper(session, paper)
    second = extract_entities_for_paper(session, paper)
    assert len(first) == len(second) > 0
    from sqlalchemy import select

    stored = list(
        session.execute(
            select(PaperEntity).where(PaperEntity.paper_id == "P_ENT4")
        ).scalars()
    )
    assert len(stored) == len(second)


def test_run_entity_extraction_summary(session):
    session.add(Paper(id="P_ENT5", title="Active learning with RDKit"))
    session.add(Paper(id="P_ENT6", title="A paper about nothing in particular"))
    session.flush()

    summary = run_entity_extraction(session, paper_ids=["P_ENT5", "P_ENT6"])
    assert summary["papers_processed"] == 2
    assert summary["entities"] == summary["by_type"].get("method", 0) + summary[
        "by_type"
    ].get("software", 0)
    assert summary["by_type"]["method"] >= 1
    assert summary["by_type"]["software"] >= 1
