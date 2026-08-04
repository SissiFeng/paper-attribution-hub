"""Transferable Knowledge Unit (TKU) extraction."""
from __future__ import annotations

import json

import pytest

from app.models import Paper, PaperEntity, TransferKnowledgeUnit
from app.services.tku_extractor import (
    extract_tku_for_paper,
    load_example_tkus,
    run_tku_extraction,
)

_GOOD_JSON = {
    "source_domain": "Battery",  # mixed case → coerced to one lowercase word
    "problem_signature": {
        "task_type": "optimization",
        "evaluation_cost": "high",
        "search_space": "discrete",
        "objectives": "multi",
        "budget_evaluations": 100,
        "batch_size": 8,
        "noise": "low",
    },
    "method_core": {
        "workflow": "model-guided closed-loop search",
        "surrogate_model": "Gaussian process",
        "acquisition": "expected improvement",
        "loop": "propose, measure, update",
        "key_components": ["surrogate", "acquisition function"],
    },
    "assumptions": ["evaluations are expensive", "space is enumerable"],
    "lessons": [
        {"text": "Closed loop beats grid search.", "polarity": "positive"},
        {"text": "Noisy labels hurt the surrogate.", "polarity": "negative"},
    ],
    "domain_bindings": ["lithium electrolyte", "solvation energy"],
}


class _FakeClient:
    """Mimics the (call, provider, model) tuple. Returns queued responses."""

    def __init__(self, responses: list[str]):
        self._responses = list(responses)
        self.calls = 0

    def as_tuple(self):
        def call(messages):
            self.calls += 1
            return self._responses.pop(0)

        return (call, "kimi", "moonshot-v1-32k")


def _paper(session, pid="P_TKU1", provenance="ac_gold"):
    p = Paper(
        id=pid,
        title="A battery electrolyte optimization study",
        abstract="We optimize electrolyte molecules with Bayesian optimization.",
        provenance=provenance,
    )
    session.add(p)
    session.flush()
    return p


def test_canned_json_creates_row_with_right_shapes(session):
    paper = _paper(session)
    client = _FakeClient([json.dumps(_GOOD_JSON)]).as_tuple()

    tku = extract_tku_for_paper(session, paper, client=client)
    session.flush()

    assert tku is not None
    row = session.get(TransferKnowledgeUnit, "tku-P_TKU1")
    assert row.paper_id == "P_TKU1"
    assert row.extractor == "llm"
    assert row.model == "moonshot-v1-32k"
    assert row.source_domain == "battery"  # lowercased, single word
    assert row.problem_signature["task_type"] == "optimization"
    assert row.problem_signature["budget_evaluations"] == 100
    assert row.method_core["surrogate_model"] == "Gaussian process"
    assert row.method_core["key_components"] == ["surrogate", "acquisition function"]
    assert row.assumptions == ["evaluations are expensive", "space is enumerable"]
    assert {lesson["polarity"] for lesson in row.lessons} == {
        "positive",
        "negative",
    }
    assert row.domain_bindings == ["lithium electrolyte", "solvation energy"]


def test_enum_validation_and_coercion(session):
    paper = _paper(session)
    bad = json.loads(json.dumps(_GOOD_JSON))
    bad["problem_signature"]["task_type"] = "not-a-task"  # invalid → null
    bad["problem_signature"]["budget_evaluations"] = "lots"  # non-int → null
    bad["lessons"] = [{"text": "no polarity given"}]  # missing → neutral
    client = _FakeClient([json.dumps(bad)]).as_tuple()

    tku = extract_tku_for_paper(session, paper, client=client)
    session.flush()

    assert tku.problem_signature["task_type"] is None
    assert tku.problem_signature["budget_evaluations"] is None
    assert tku.lessons == [{"text": "no polarity given", "polarity": "neutral"}]


def test_fence_stripping_and_retry_path(session):
    paper = _paper(session)
    fenced = "```json\n" + json.dumps(_GOOD_JSON) + "\n```"
    # First response: garbage → triggers retry. Second: fenced valid JSON.
    fake = _FakeClient(["not json at all", fenced])
    tku = extract_tku_for_paper(session, paper, client=fake.as_tuple())
    session.flush()

    assert fake.calls == 2  # retried once
    assert tku is not None
    assert tku.source_domain == "battery"


def test_second_failure_returns_none(session):
    paper = _paper(session)
    fake = _FakeClient(["garbage", "still garbage"])
    tku = extract_tku_for_paper(session, paper, client=fake.as_tuple())
    assert tku is None
    assert fake.calls == 2


def test_idempotent_skip_and_force(session):
    _paper(session)
    client_tuple = _FakeClient([json.dumps(_GOOD_JSON)]).as_tuple()
    r1 = run_tku_extraction(session, provenance="ac_gold", client=client_tuple)
    assert r1["extracted"] == 1
    assert r1["skipped_existing"] == 0

    # Second run with no force → skipped.
    client2 = _FakeClient([json.dumps(_GOOD_JSON)]).as_tuple()
    r2 = run_tku_extraction(session, provenance="ac_gold", client=client2)
    assert r2["extracted"] == 0
    assert r2["skipped_existing"] == 1

    # With force → re-extracts.
    client3 = _FakeClient([json.dumps(_GOOD_JSON)]).as_tuple()
    r3 = run_tku_extraction(session, provenance="ac_gold", client=client3, force=True)
    assert r3["extracted"] == 1
    assert r3["skipped_existing"] == 0


def test_provenance_filter(session):
    _paper(session, pid="P_GOLD", provenance="ac_gold")
    _paper(session, pid="P_CSV", provenance="csv")
    session.flush()

    client = _FakeClient([json.dumps(_GOOD_JSON)]).as_tuple()
    summary = run_tku_extraction(session, provenance="ac_gold", client=client)
    assert summary["targeted"] == 1
    assert session.get(TransferKnowledgeUnit, "tku-P_GOLD") is not None
    assert session.get(TransferKnowledgeUnit, "tku-P_CSV") is None


def test_method_entity_hints_feed_user_message(session):
    """Smoke: extraction works even when the paper has method entities."""
    paper = _paper(session)
    session.add(
        PaperEntity(
            id="ent_x",
            paper_id=paper.id,
            entity_type="method",
            name="Bayesian optimization",
            normalized_name="bayesian optimization",
            stage="optimization",
            usage_snippet="We optimize electrolyte molecules with Bayesian optimization.",
        )
    )
    session.flush()
    client = _FakeClient([json.dumps(_GOOD_JSON)]).as_tuple()
    tku = extract_tku_for_paper(session, paper, client=client)
    assert tku is not None


def test_example_loader(session, tmp_path):
    """Loads 8 example TKUs against real paper ids, idempotently."""
    from app.config import settings

    raw = (settings.example_tkus_yaml).read_text(encoding="utf-8")
    import yaml

    entries = yaml.safe_load(raw)["tkus"]
    assert len(entries) == 8

    # Seed the referenced papers so the loader can attach to them.
    for entry in entries:
        session.add(
            Paper(
                id=entry["paper_id"],
                title="seed",
                abstract="seed abstract",
                provenance="ac_gold",
            )
        )
    session.flush()

    summary = load_example_tkus(session)
    assert summary["loaded"] == 8
    assert summary["skipped_missing"] == 0
    rows = session.query(TransferKnowledgeUnit).all()
    assert len(rows) == 8
    assert all(r.extractor == "example" for r in rows)
    assert all(r.model is None for r in rows)
    # Polarity-diverse lessons present somewhere.
    polarities = {
        lesson["polarity"]
        for row in rows
        for lesson in row.lessons
    }
    assert {"positive", "negative", "neutral"} <= polarities

    # Idempotent: second load does not duplicate.
    summary2 = load_example_tkus(session)
    assert summary2["loaded"] == 8
    assert session.query(TransferKnowledgeUnit).count() == 8


def test_no_provider_raises_clear_runtime_error(session, monkeypatch):
    from app.config import settings
    from app.services import tku_extractor

    monkeypatch.setattr(settings, "llm_provider", "auto")
    monkeypatch.setattr(settings, "kimi_api_key", "")
    monkeypatch.setattr(settings, "anthropic_api_key", "")

    with pytest.raises(RuntimeError, match="PAS_KIMI_API_KEY"):
        tku_extractor._resolve_client()
