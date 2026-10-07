from __future__ import annotations

import pytest
from tests.admin_client import AdminTestClient as TestClient
from sqlalchemy import select

from app.config import settings
from app.models import HumanReview, Paper
from app.services.sdl_stage1_service import (
    prepare_stage1_batches,
    stage1_assignment,
    stage1_label_map,
)


def _seed_tier1(session, count: int) -> None:
    for index in range(count):
        item_key = f"ITEM{index:03d}"
        session.add(
            Paper(
                id=f"ZOTERO:42:{item_key}",
                title=f"Tier 1 SDL candidate {index}",
                year=2010 + index % 16,
                source="zotero",
                provenance="zotero_group",
                corpus_sources=["STRICT_SDL_KEYWORD"],
                retrieval_tier="tier1",
                ac_known_publication=False,
                raw_metadata={
                    "zotero": {
                        "primary_item_key": item_key,
                        "primary_item_version": 1,
                        "collection_keys": ["ONE"],
                    }
                },
            )
        )
    session.commit()


def test_stage1_batches_are_exact_disjoint_and_deterministic(
    session,
    monkeypatch,
):
    monkeypatch.setattr(settings, "sdl_stage1_only", True)
    monkeypatch.setattr(settings, "zotero_tier1_collection", "ONE")
    _seed_tier1(session, 12)

    first = prepare_stage1_batches(
        session,
        validation_count=2,
        frozen_test_count=2,
        train_round_counts=(2, 2),
        seed="test-seed",
        expected_total=12,
    )
    session.commit()
    second = prepare_stage1_batches(
        session,
        validation_count=2,
        frozen_test_count=2,
        train_round_counts=(2, 2),
        seed="test-seed",
        expected_total=12,
        persist=False,
    )

    assert first["manifest_id"] == second["manifest_id"]
    assert first["assignments"] == second["assignments"]
    assert first["role_counts"] == {
        "train": 4,
        "validation": 2,
        "frozen_test": 2,
        "pool": 4,
    }
    assert first["train_round_counts"] == {"1": 2, "2": 2}
    ids = [row["paper_id"] for row in first["assignments"]]
    assert len(ids) == len(set(ids)) == 12
    assert all(
        stage1_assignment(paper)["manifest_id"] == first["manifest_id"]
        for paper in session.scalars(select(Paper))
    )


def test_stage1_labels_do_not_cross_split_boundaries(session, monkeypatch):
    monkeypatch.setattr(settings, "sdl_stage1_only", True)
    monkeypatch.setattr(settings, "zotero_tier1_collection", "ONE")
    _seed_tier1(session, 8)
    manifest = prepare_stage1_batches(
        session,
        validation_count=1,
        frozen_test_count=1,
        train_round_counts=(2, 2),
        expected_total=8,
    )
    session.commit()
    by_role = {
        role: [
            row
            for row in manifest["assignments"]
            if row["role"] == role
        ]
        for role in ("train", "validation", "frozen_test")
    }
    reviews = [
        (by_role["train"][0]["paper_id"], "CONFIRMED_SDL"),
        (by_role["train"][2]["paper_id"], "NOT_SDL"),
        (by_role["validation"][0]["paper_id"], "SDL_ADJACENT"),
        (by_role["frozen_test"][0]["paper_id"], "PROBABLE_SDL"),
    ]
    for index, (paper_id, judgement) in enumerate(reviews):
        session.add(
            HumanReview(
                id=f"review-{index}",
                paper_id=paper_id,
                sdl_judgement=judgement,
                review_status="COMPLETED",
                evidence_level="ABSTRACT",
                judgement_basis="STRICT_SDL",
            )
        )
    session.commit()

    train_round_1 = stage1_label_map(
        session,
        role="train",
        through_round=1,
    )
    train_round_2 = stage1_label_map(
        session,
        role="train",
        through_round=2,
    )
    validation = stage1_label_map(session, role="validation")
    frozen_test = stage1_label_map(session, role="frozen_test")

    assert len(train_round_1) == 1
    assert len(train_round_2) == 2
    assert set(train_round_2).isdisjoint(validation)
    assert set(train_round_2).isdisjoint(frozen_test)
    assert set(validation).isdisjoint(frozen_test)

    from app.services.learned_classifier import (
        build_training_set,
        build_validation_set,
    )

    assert {
        row["paper_id"]
        for row in build_training_set(session, stage1_through_round=2)
    } == set(train_round_2)
    assert {row["paper_id"] for row in build_validation_set(session)} == set(
        validation
    )


def test_stage1_review_accepts_sdl_only_and_rejects_ac(session, monkeypatch):
    monkeypatch.setattr(settings, "sdl_stage1_only", True)
    monkeypatch.setattr(
        settings,
        "sdl_stage1_derived_views_enabled",
        True,
    )
    monkeypatch.setattr(settings, "zotero_tier1_collection", "ONE")
    _seed_tier1(session, 4)
    for paper in session.execute(select(Paper)).scalars():
        paper.full_text_available = True
    manifest = prepare_stage1_batches(
        session,
        validation_count=1,
        frozen_test_count=1,
        train_round_counts=(1,),
        expected_total=4,
    )
    session.commit()
    from app.main import app
    from app.services.relevance_classifier import classify_all

    classify_all(session)
    from app.services.review_queue import refresh_queue

    refresh_queue(session)
    queue = TestClient(app).get("/reviews/queue", params={"limit": 20}).json()
    assert queue
    assert {row["stage1_manifest_id"] for row in queue} == {
        manifest["manifest_id"]
    }
    assert {row["stage1_role"] for row in queue} <= {
        "train",
        "validation",
        "frozen_test",
    }
    assert all(
        row["stage1_round"] is not None
        if row["stage1_role"] == "train"
        else row["stage1_round"] is None
        for row in queue
    )
    assert all(row["stage1_ordinal"] is not None for row in queue)
    assert all(row["label"] == "UNCERTAIN" for row in queue)
    assert all(row["confidence"] == 0.0 for row in queue)
    assert all(row["priority"] == 0.0 for row in queue)
    assert all(row["reasons"] == [] for row in queue)
    paper_id = next(
        row["paper_id"]
        for row in manifest["assignments"]
        if row["role"] == "train"
    )
    client = TestClient(app)
    response = client.post(
        f"/reviews/{paper_id}",
        json={
            "sdl_judgement": "CONFIRMED_SDL",
            "evidence_level": "ABSTRACT",
            "judgement_basis": "STRICT_SDL",
        },
    )
    assert response.status_code == 200, response.text
    assert response.json()["review_status"] == "COMPLETED"
    assert response.json()["human_label"] is None
    assert response.json()["ac_relevance_judgement"] is None

    rejected = client.post(
        f"/reviews/{paper_id}",
        json={
            "sdl_judgement": "CONFIRMED_SDL",
            "ac_relevance_judgement": "AC_RELEVANT",
            "review_status": "COMPLETED",
            "evidence_level": "ABSTRACT",
            "judgement_basis": "STRICT_SDL",
        },
    )
    assert rejected.status_code == 422
    assert "forbids AC judgements" in rejected.text


def test_stage1_frozen_test_is_sealed_until_explicit_release(
    session,
    monkeypatch,
):
    monkeypatch.setattr(settings, "sdl_stage1_only", True)
    monkeypatch.setattr(settings, "zotero_tier1_collection", "ONE")
    _seed_tier1(session, 4)
    manifest = prepare_stage1_batches(
        session,
        validation_count=1,
        frozen_test_count=1,
        train_round_counts=(1,),
        expected_total=4,
    )
    session.commit()
    from app.services.eval_service import run_stage1_evaluation
    from app.services.relevance_classifier import classify_all

    classify_all(session)
    for index, role in enumerate(("validation", "frozen_test")):
        paper_id = next(
            row["paper_id"]
            for row in manifest["assignments"]
            if row["role"] == role
        )
        session.add(
            HumanReview(
                id=f"evaluation-review-{index}",
                paper_id=paper_id,
                sdl_judgement="NOT_SDL",
                review_status="COMPLETED",
                evidence_level="ABSTRACT",
                judgement_basis="STRICT_SDL",
            )
        )
    session.commit()

    validation = run_stage1_evaluation(session, role="validation")
    assert validation.n_evaluated == 1
    assert validation.label_scope == "STRICT_SDL"
    with pytest.raises(PermissionError, match="sealed"):
        run_stage1_evaluation(session, role="frozen_test")
    frozen = run_stage1_evaluation(
        session,
        role="frozen_test",
        release_frozen_test=True,
    )
    assert frozen.n_evaluated == 1
    assert frozen.dataset_role == "frozen_holdout"
