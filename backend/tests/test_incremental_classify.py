"""v0.7 review-loop: classify_new + human_confirmed lock."""
from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from app.models import Paper, PaperClassification
from app.services.relevance_classifier import (
    CURRENT_MODEL_VERSION,
    classify_all,
    classify_new,
    papers_needing_classification,
)


def test_classify_new_no_op_when_corpus_classified(seeded_session):
    classify_all(seeded_session)
    touched, new, refreshed = classify_new(seeded_session)
    assert touched == []
    assert new == 0
    assert refreshed == 0


def test_classify_new_picks_up_brand_new_paper(seeded_session):
    classify_all(seeded_session)
    seeded_session.add(
        Paper(
            id="P_NEW",
            title="A brand new self-driving lab paper",
            abstract="We present a self-driving laboratory with Bayesian optimization.",
            year=2025,
            doi="10.test/new",
            source="csv",
            keywords=["self-driving lab"],
        )
    )
    seeded_session.commit()

    touched, new, refreshed = classify_new(seeded_session)
    assert len(touched) == 1
    assert new == 1
    assert refreshed == 0
    # And the new paper has a classification now.
    paper = seeded_session.get(Paper, "P_NEW")
    assert paper.classification is not None
    assert paper.classification.model_version.startswith("rules-v0.7")


def test_classify_new_refreshes_stale_model_version(seeded_session):
    classify_all(seeded_session)
    # Simulate an old classification with v0.1.
    paper = seeded_session.execute(select(Paper).limit(1)).scalar_one()
    paper.classification.model_version = "rules-v0.1"
    seeded_session.commit()

    needing = papers_needing_classification(seeded_session)
    assert paper in needing

    touched, new, refreshed = classify_new(seeded_session)
    assert refreshed >= 1
    seeded_session.refresh(paper.classification)
    assert paper.classification.model_version.startswith(CURRENT_MODEL_VERSION)


def test_human_confirmed_label_is_never_overwritten(seeded_session):
    classify_all(seeded_session)
    paper = seeded_session.get(Paper, "P001")
    cls = paper.classification
    # Force a (wrong) label, mark it confirmed.
    cls.label = "EXCLUDE"
    cls.human_confirmed = True
    cls.human_confirmed_at = datetime.now(UTC)
    cls.model_version = "rules-v0.1"  # force inclusion in classify_new
    seeded_session.commit()

    classify_new(seeded_session, force=True)
    seeded_session.refresh(paper.classification)
    # Locked label survives.
    assert paper.classification.label == "EXCLUDE"


def test_classify_all_sets_last_classified_at(seeded_session):
    before = datetime.now(UTC) - timedelta(seconds=1)
    classify_all(seeded_session)
    for cls in seeded_session.execute(select(PaperClassification)).scalars():
        assert cls.last_classified_at is not None
        assert cls.last_classified_at >= before
