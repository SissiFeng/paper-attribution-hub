from sqlalchemy import select

from app.models import PaperProposition


def _props_for(session, paper_id: str):
    return list(
        session.execute(
            select(PaperProposition).where(PaperProposition.paper_id == paper_id)
        ).scalars()
    )


def _setup(session):
    from app.services.relevance_classifier import classify_all

    classify_all(session)


def test_funded_by_proposition_for_p001(fulltext_seeded_session):
    _setup(fulltext_seeded_session)
    props = _props_for(fulltext_seeded_session, "P001")
    funded_by = [p for p in props if p.predicate == "funded_by"]
    objects = {p.object_value for p in funded_by}
    assert "Acceleration Consortium" in objects
    assert "Vector Institute" in objects
    ac_prop = next(p for p in funded_by if p.object_value == "Acceleration Consortium")
    assert ac_prop.confidence >= 0.9
    assert ac_prop.source_chunk_id is not None


def test_uses_method_proposition_for_p001(fulltext_seeded_session):
    _setup(fulltext_seeded_session)
    props = _props_for(fulltext_seeded_session, "P001")
    methods = [p.object_value for p in props if p.predicate == "uses_method"]
    assert any("Bayesian optimization" in m for m in methods) or any(
        "closed-loop" in m.lower() for m in methods
    )


def test_cites_ac_core_proposition_for_p003(fulltext_seeded_session):
    _setup(fulltext_seeded_session)
    props = _props_for(fulltext_seeded_session, "P003")
    cites = [p for p in props if p.predicate == "cites"]
    titles = {p.object_value for p in cites}
    assert any("ChemOS" in t for t in titles)


def test_affiliated_with_proposition_for_p001(fulltext_seeded_session):
    _setup(fulltext_seeded_session)
    props = _props_for(fulltext_seeded_session, "P001")
    affil = [
        p.object_value for p in props if p.predicate == "affiliated_with"
    ]
    assert "University of Toronto" in affil


def test_negative_phrase_demotes_method_confidence(seeded_session):
    """Inject a fake evidence row with 'closed-loop control' (negative phrase)
    and confirm the method proposition is demoted."""
    import uuid

    from app.models import PaperEvidence
    from app.services.proposition_extractor import extract_propositions_for_paper

    seeded_session.add(
        PaperEvidence(
            id=f"ev_{uuid.uuid4().hex[:8]}",
            paper_id="P010",  # Climate paper — no real evidence
            evidence_type="sdl_methodology",
            evidence_source="methods",
            evidence_text=(
                "We applied closed-loop control to manage feedback in the "
                "ocean modeling subsystem; Bayesian optimization was used "
                "for hyperparameter selection."
            ),
            score=0.5,
        )
    )
    seeded_session.flush()

    records = extract_propositions_for_paper(seeded_session, "P010")
    bayes = [r for r in records if r.object_value == "Bayesian optimization"]
    assert bayes
    assert bayes[0].confidence < 0.6  # original would be 0.85; negative cuts it to ~0.34
    assert (bayes[0].extra or {}).get("negative_phrase_detected") is True
