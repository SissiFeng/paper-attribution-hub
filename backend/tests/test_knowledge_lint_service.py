from __future__ import annotations

from app.models import Paper, PaperClassification
from app.services.knowledge_lint_service import build_knowledge_lint_report


def test_lint_flags_high_label_without_ac_evidence(session):
    paper = Paper(
        id="p_lint_1",
        title="Generic autonomous materials lab",
        abstract="A self-driving lab paper without AC attribution.",
        doi="10.1234/lint-1",
        provenance="scopus_batch",
        ai_decision_score=1.0,
        automation_score=1.0,
        closed_loop_score=1.0,
    )
    paper.classification = PaperClassification(
        id="cls_lint_1",
        paper_id="p_lint_1",
        label="CORE_RELEVANT",
        confidence=0.91,
        topic_score=0.9,
        architecture_signal=1.0,
    )
    session.add(paper)
    session.commit()

    report = build_knowledge_lint_report(session)

    bucket = next(b for b in report.buckets if b.bucket == "core_ac_missing_evidence")
    assert bucket.count == 1
    assert report.website_blockers == 1
    assert bucket.entries[0].paper_id == "p_lint_1"


def test_lint_allows_core_label_with_ac_evidence(session):
    paper = Paper(
        id="p_lint_2",
        title="AC funded closed-loop materials platform",
        abstract="An AC-attributed self-driving lab paper.",
        doi="10.1234/lint-2",
        provenance="ac_gold",
        ac_known_publication=True,
        ac_programs="Acceleration Consortium",
    )
    paper.classification = PaperClassification(
        id="cls_lint_2",
        paper_id="p_lint_2",
        label="CORE_RELEVANT",
        confidence=0.95,
        funding_signal=1.0,
    )
    session.add(paper)
    session.commit()

    report = build_knowledge_lint_report(session)

    bucket = next(b for b in report.buckets if b.bucket == "core_ac_missing_evidence")
    assert bucket.count == 0
