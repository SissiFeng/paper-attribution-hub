"""Cross-SDL transfer engine: matching, design generation, export, API."""
from __future__ import annotations

from fastapi.testclient import TestClient

from app.models import Paper, PaperLabLink, TransferKnowledgeUnit
from app.services.transfer_designer import (
    export_transfer_md,
    generate_design,
    load_target,
    match_tkus,
)


def _tku(
    paper_id: str,
    source_domain: str,
    *,
    task_type="optimization",
    search_space="mixed",
    objectives="multi",
    evaluation_cost="medium",
    workflow="closed-loop bayesian optimization",
    surrogate="gaussian process",
    acquisition="expected improvement",
    key_components=("bayesian optimization", "active learning"),
    assumptions=("smooth objective landscape",),
    lessons=(("GP overconfident with few samples", "negative"),),
    domain_bindings=("lithium electrolyte",),
) -> TransferKnowledgeUnit:
    return TransferKnowledgeUnit(
        id=f"tku-{paper_id}",
        paper_id=paper_id,
        source_domain=source_domain,
        problem_signature={
            "task_type": task_type,
            "evaluation_cost": evaluation_cost,
            "search_space": search_space,
            "objectives": objectives,
            "budget_evaluations": None,
            "batch_size": None,
            "noise": None,
        },
        method_core={
            "workflow": workflow,
            "surrogate_model": surrogate,
            "acquisition": acquisition,
            "loop": "design-make-test-analyze",
            "key_components": list(key_components),
        },
        assumptions=list(assumptions),
        lessons=[{"text": t, "polarity": p} for t, p in lessons],
        domain_bindings=list(domain_bindings),
        extractor="example",
        model=None,
    )


def _seed(session) -> None:
    # battery optimization — strong match for an optimization/mixed/multi target
    session.add(Paper(id="P_BAT", title="Battery electrolyte optimization", year=2022))
    session.add(_tku("P_BAT", "battery"))

    # polymer prediction — different task type, weaker match
    session.add(Paper(id="P_POLY", title="Polymer property prediction", year=2021))
    session.add(
        _tku(
            "P_POLY",
            "polymer",
            task_type="prediction",
            search_space="continuous",
            workflow="supervised property prediction",
            surrogate="random forest",
            acquisition=None,
            key_components=("property prediction",),
            lessons=(("more data improved accuracy", "positive"),),
            domain_bindings=("PLGA nanoparticle",),
        )
    )

    # catalysis automation — moderate
    session.add(Paper(id="P_CAT", title="Catalysis automation loop", year=2023))
    session.add(
        _tku(
            "P_CAT",
            "catalysis",
            task_type="optimization",
            search_space="discrete",
            workflow="autonomous reaction optimization",
            key_components=("bayesian optimization", "catalyst screening"),
            lessons=(("reference electrode drift biased results", "negative"),),
            domain_bindings=("platinum catalyst",),
        )
    )

    # a TKU whose paper is linked to the target SDL itself — must be excluded
    session.add(Paper(id="P_OWN", title="Own SDL4 polymer work", year=2024))
    session.add(PaperLabLink(paper_id="P_OWN", lab_id="sdl4"))
    session.add(_tku("P_OWN", "sdl4"))
    session.flush()


# ── matching ───────────────────────────────────────────────────────────────


def test_match_scoring_and_breakdown(session):
    _seed(session)
    target = load_target("sdl4")
    matches = match_tkus(session, target)
    by_id = {m["paper"]["id"]: m for m in matches}

    # P_OWN is linked to sdl4 → excluded.
    assert "P_OWN" not in by_id

    bat = by_id["P_BAT"]
    # task_type(+3) + search_space mixed(+2) + objectives multi(+2)
    # + evaluation_cost medium(+1) + keyword overlap + cross-domain(+1)
    bd = bat["score_breakdown"]
    assert bd["task_type"] == 3
    assert bd["search_space"] == 2
    assert bd["objectives"] == 2
    assert bd["evaluation_cost"] == 1
    assert bd["cross_domain"] == 1
    assert bd["keyword_overlap"]["points"] >= 1
    assert bat["score"] >= 9


def test_cross_domain_bonus_and_sorting(session):
    _seed(session)
    target = load_target("sdl4")
    matches = match_tkus(session, target)
    scores = [m["score"] for m in matches]
    assert scores == sorted(scores, reverse=True)
    # battery (full signature align) beats polymer-prediction (task mismatch)
    by_id = {m["paper"]["id"]: m for m in matches}
    assert by_id["P_BAT"]["score"] > by_id["P_POLY"]["score"]


def test_source_domain_filter(session):
    _seed(session)
    target = load_target("sdl4")
    matches = match_tkus(session, target, source_domain="battery")
    assert [m["paper"]["id"] for m in matches] == ["P_BAT"]


# ── template document ────────────────────────────────────────────────────────


def test_template_document_tags_and_risks(session):
    _seed(session)
    design = generate_design(session, "sdl4", llm_client=_FailClient())
    md = design["markdown"]
    assert design["mode"] == "template"

    # Citations only for matched papers; never for the excluded P_OWN.
    assert "[src:P_BAT]" in md
    assert "[src:P_OWN]" not in md

    # Negative lessons surface under Risks, before positives.
    assert "## Risks & lessons from source domains" in md
    risks_idx = md.index("## Risks & lessons from source domains")
    assert "GP overconfident with few samples" in md
    assert "reference electrode drift biased results" in md
    # negative section header precedes positive one
    neg = md.index("**Risks (negative results):**", risks_idx)
    pos = md.index("**What worked (positive lessons):**", risks_idx)
    assert neg < pos

    # Domain bindings flagged for re-binding.
    assert "needs re-binding to target domain" in md
    # Matched sources table present.
    assert "## Matched sources" in md


# ── LLM mode ─────────────────────────────────────────────────────────────────


class _FailClient:
    def __call__(self, messages):
        raise RuntimeError("no llm")


class _EchoClient:
    """Returns the skeleton verbatim (keeps every tag) → llm mode."""

    def __call__(self, messages):
        user = next(m["content"] for m in messages if m["role"] == "user")
        skeleton = user.split("SKELETON:\n", 1)[1].rsplit("\n\nRewrite", 1)[0]
        return skeleton


class _InventClient:
    """Adds a bogus [src:] tag → must fail validation → fall back to template."""

    def __call__(self, messages):
        return "# Proposal\n\nMade up claim [src:NOT_A_PAPER]."


def test_llm_mode_keeps_tags(session):
    _seed(session)
    design = generate_design(session, "sdl4", llm_client=_EchoClient())
    assert design["mode"] == "llm"
    assert "[src:P_BAT]" in design["markdown"]


def test_llm_invented_tag_falls_back_to_template(session):
    _seed(session)
    design = generate_design(session, "sdl4", llm_client=_InventClient())
    assert design["mode"] == "template"
    assert "[src:NOT_A_PAPER]" not in design["markdown"]


# ── export ───────────────────────────────────────────────────────────────────


def test_export_writes_file_and_log(session, tmp_path):
    _seed(session)
    out = export_transfer_md(
        session, "sdl4", llm_client=_FailClient(), output_dir=tmp_path / "transfers"
    )
    assert out.exists()
    text = out.read_text(encoding="utf-8")
    assert text.startswith("---")
    assert "type: transfer-design" in text
    assert "[src:P_BAT]" in text

    log = (tmp_path / "log.md")
    assert log.exists()
    assert "Transfer design: SDL 4" in log.read_text(encoding="utf-8")


# ── API ──────────────────────────────────────────────────────────────────────


def test_api_endpoints(session):
    from app.main import app

    _seed(session)
    session.commit()
    client = TestClient(app)

    r = client.get("/transfer/targets")
    assert r.status_code == 200
    ids = [t["id"] for t in r.json()]
    assert "sdl4" in ids and len(ids) == 8

    r = client.get("/transfer/tkus", params={"source_domain": "battery"})
    assert r.status_code == 200
    assert [t["paper_id"] for t in r.json()] == ["P_BAT"]

    r = client.post(
        "/transfer/design", json={"target_id": "sdl4", "use_llm": False, "top_k": 6}
    )
    assert r.status_code == 200
    body = r.json()
    assert body["mode"] == "template"
    assert any(m["paper_id"] == "P_BAT" for m in body["matches"])
    assert "[src:P_BAT]" in body["markdown"]

    r = client.post("/transfer/design", json={"target_id": "nope"})
    assert r.status_code == 404
