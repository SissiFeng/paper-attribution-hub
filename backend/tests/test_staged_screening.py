from __future__ import annotations

from tests.admin_client import AdminTestClient as TestClient
from sqlalchemy import select

from app.main import app
from app.models import HumanReview, Paper, PaperClassification
from app.services.relevance_classifier import classify_all
from app.services.review_queue import list_queue, refresh_queue
from app.services.staged_screening import (
    apply_paper_screening,
    apply_staged_screening,
    decide_screening_route,
)


def _classification(seeded_session, paper_id: str) -> PaperClassification:
    paper = seeded_session.get(Paper, paper_id)
    assert paper is not None
    assert paper.classification is not None
    return paper.classification


def test_staged_screening_routes_only_positive_and_uncertain_subset(
    seeded_session,
):
    classify_all(seeded_session)
    positive = _classification(seeded_session, "P001")
    uncertain = _classification(seeded_session, "P002")
    screened_out = _classification(seeded_session, "P003")

    positive.label = "CORE_RELEVANT"
    positive.confidence = 0.91
    uncertain.label = "EXCLUDE"
    uncertain.confidence = 0.62
    screened_out.label = "EXCLUDE"
    screened_out.confidence = 0.94
    seeded_session.commit()

    summary = apply_staged_screening(seeded_session)

    assert positive.screening_stage == "HUMAN_REVIEW"
    assert positive.screening_route == "POSITIVE_REVIEW"
    assert positive.needs_review is True
    assert uncertain.screening_stage == "HUMAN_REVIEW"
    assert uncertain.screening_route == "UNCERTAIN_REVIEW"
    assert uncertain.needs_review is True
    assert screened_out.screening_stage == "BROAD_SCORED"
    assert screened_out.screening_route == "SCREENED_OUT"
    assert screened_out.needs_review is False
    assert summary.route_counts["POSITIVE_REVIEW"] >= 1
    assert summary.route_counts["UNCERTAIN_REVIEW"] >= 1
    assert summary.route_counts["SCREENED_OUT"] >= 1


def test_explicit_training_feedback_becomes_seed_not_review_work(
    seeded_session,
):
    seeded_session.add(
        Paper(
            id="P_SEED",
            title="Curated training seed",
            abstract="A self-driving laboratory closes the experiment loop.",
            source="manual",
            provenance="manual",
        )
    )
    seeded_session.commit()
    classify_all(seeded_session)
    cls = _classification(seeded_session, "P_SEED")
    cls.label = "CORE_RELEVANT"
    cls.confidence = 0.55
    seeded_session.add(
        HumanReview(
            id="review-seed-P_SEED",
            paper_id="P_SEED",
            human_label="CORE_RELEVANT",
        )
    )
    seeded_session.commit()

    apply_staged_screening(seeded_session)

    assert cls.screening_stage == "SEED_REFERENCE"
    assert cls.screening_route == "SEED"
    assert cls.needs_review is False


def test_needs_fulltext_route_survives_queue_refresh(seeded_session):
    classify_all(seeded_session)
    cls = _classification(seeded_session, "P002")
    seeded_session.add(
        HumanReview(
            id="review-fulltext-P002",
            paper_id="P002",
            sdl_judgement="INSUFFICIENT_EVIDENCE",
            ac_relevance_judgement="AC_RELEVANT",
            review_status="NEEDS_FULLTEXT",
            evidence_level="ABSTRACT",
            judgement_basis="DUAL_REVIEW",
        )
    )
    seeded_session.commit()

    refresh_queue(seeded_session)
    seeded_session.refresh(cls)

    assert cls.screening_stage == "HUMAN_REVIEW"
    assert cls.screening_route == "FULLTEXT_REVIEW"
    assert cls.needs_review is True
    assert any(item.paper_id == "P002" for item in list_queue(seeded_session))


def test_completed_dimensional_review_is_resolved_not_seeded(
    seeded_session,
):
    classify_all(seeded_session)
    cls = _classification(seeded_session, "P002")
    seeded_session.add(
        HumanReview(
            id="review-resolved-P002",
            paper_id="P002",
            sdl_judgement="NOT_SDL",
            ac_relevance_judgement="AC_RELEVANT",
            review_status="COMPLETED",
            evidence_level="FULLTEXT",
            judgement_basis="DUAL_REVIEW",
        )
    )
    seeded_session.commit()

    apply_staged_screening(seeded_session)

    assert cls.screening_stage == "HUMAN_RESOLVED"
    assert cls.screening_route == "RESOLVED"
    assert cls.needs_review is False


def test_queue_never_contains_screened_out_routes(seeded_session):
    classify_all(seeded_session)
    for cls in seeded_session.execute(select(PaperClassification)).scalars():
        cls.label = "EXCLUDE"
        cls.confidence = 0.95
    seeded_session.commit()

    assert refresh_queue(seeded_session) == 0
    assert list_queue(seeded_session) == []


def test_paper_api_exposes_persisted_screening_state(seeded_session):
    classify_all(seeded_session)
    apply_staged_screening(seeded_session)

    response = TestClient(app).get("/papers")

    assert response.status_code == 200
    classification = response.json()[0]["classification"]
    assert classification["screening_stage"]
    assert classification["screening_route"]
    assert classification["screening_reason"]


def test_single_paper_routing_fails_closed_when_label_boundary_is_missing(
    seeded_session,
    tmp_path,
    monkeypatch,
):
    from app.config import settings

    classify_all(seeded_session)
    paper = seeded_session.get(Paper, "P002")
    paper.review = HumanReview(
        id="review-boundary-P002",
        paper_id="P002",
        human_label="CORE_RELEVANT",
    )
    seeded_session.commit()
    monkeypatch.setattr(
        settings,
        "validation_labels_csv",
        tmp_path / "missing-validation.csv",
    )

    decision = apply_paper_screening(seeded_session, paper)

    assert decision is not None
    assert decision.route == "RESOLVED"
    assert paper.classification.screening_route != "SEED"


def test_alias_unknown_and_nonfinite_classifier_outputs_fail_safe(
    seeded_session,
):
    classify_all(seeded_session)
    include_alias = _classification(seeded_session, "P001")
    unknown = _classification(seeded_session, "P002")
    nonfinite = _classification(seeded_session, "P003")
    include_alias.label = "INCLUDE"
    include_alias.confidence = 0.9
    unknown.label = "MYSTERY"
    unknown.confidence = 0.99
    seeded_session.commit()

    apply_staged_screening(seeded_session)

    assert include_alias.screening_route == "POSITIVE_REVIEW"
    assert unknown.screening_route == "UNCERTAIN_REVIEW"
    nonfinite.label = "EXCLUDE"
    nonfinite.confidence = float("nan")
    decision = decide_screening_route(
        nonfinite.paper,
        nonfinite,
        training_ids=set(),
        reserved_ids=set(),
    )
    assert decision.route == "UNCERTAIN_REVIEW"
