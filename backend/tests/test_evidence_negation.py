"""v0.7 evidence extractor: negation, funding context, blacklist."""

from app.services.evidence_extractor import (
    EvidenceRecord,
    _aggregate_score,
    add_disqualifying_evidence,
    persist_evidence,
)


def test_aggregate_caps_per_evidence_type():
    records = [
        EvidenceRecord(
            evidence_type="funding_acknowledgement",
            evidence_source="acknowledgements",
            evidence_text="...",
            score=0.6,
            chunk_id=None,
        ),
        EvidenceRecord(
            evidence_type="funding_acknowledgement",
            evidence_source="acknowledgements",
            evidence_text="...",
            score=0.6,
            chunk_id=None,
        ),
    ]
    # Without cap, score would be 1.2/1.5 = 0.8. With per-type cap of 1.0 it
    # stays at 1.0/1.5 ≈ 0.667.
    score = _aggregate_score(records)
    assert 0.5 < score <= 0.7


def test_disqualifying_evidence_subtracts():
    records = [
        EvidenceRecord(
            evidence_type="funding_acknowledgement",
            evidence_source="acknowledgements",
            evidence_text="...",
            score=0.6,
            chunk_id=None,
        ),
        EvidenceRecord(
            evidence_type="disqualifying",
            evidence_source="llm_judge",
            evidence_text="no autonomous platform is described",
            score=-0.4,
            chunk_id=None,
        ),
    ]
    score = _aggregate_score(records)
    # Funding alone would give 0.6/1.5 = 0.4; subtracting 0.4 → 0.13
    assert score < 0.3


def test_add_disqualifying_evidence(session):
    from app.models import Paper

    paper = Paper(id="P_TEST", title="t")
    session.add(paper)
    session.commit()
    row = add_disqualifying_evidence(
        session,
        paper_id="P_TEST",
        source="llm_judge",
        snippet="we do not use a self-driving lab",
    )
    assert row.evidence_type == "disqualifying"
    assert row.score < 0
    assert row.extra == {
        "attribution_evidence": {
            "contract_version": "aet-evidence-meta-v0.1",
            "polarity": "negative",
            "detector_type": "disqualifying_evidence",
        }
    }


def test_reextracting_rule_evidence_preserves_disqualifying_rows(session):
    from app.models import Paper, PaperEvidence

    session.add(Paper(id="P_NEGATIVE_PERSIST", title="t"))
    session.commit()
    negative = add_disqualifying_evidence(
        session,
        paper_id="P_NEGATIVE_PERSIST",
        source="llm_judge",
        snippet="generic optimization only",
    )

    persist_evidence(session, "P_NEGATIVE_PERSIST")

    assert session.get(PaperEvidence, negative.id) is negative


def test_funding_context_required(fulltext_seeded_session):
    """When the AC vocab appears WITHOUT funding cues, the funding score
    should be halved.

    We can't easily synthesize a chunk here without writing PDFs; the
    behavior is covered by the integration test below in test_end_to_end.
    """
    from app.services.evidence_extractor import _has_funding_context
    from app.services.text_utils import TermHit

    text = "we thank acceleration consortium for hosting the workshop"
    hit = TermHit(term="acceleration consortium", start=12, end=12 + 24)
    # 'thank' is a funding cue → True (still funding-context-y).
    assert _has_funding_context(text, hit) is True

    text = "acceleration consortium hosted a panel at the conference"
    hit = TermHit(term="acceleration consortium", start=0, end=24)
    # No 'fund/support/acknowledge' cue → False.
    assert _has_funding_context(text, hit) is False
