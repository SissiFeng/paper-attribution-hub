"""Fine-grained method vocabulary (categories) + pipeline-stage detection."""
from __future__ import annotations

from sqlalchemy import select

from app.models import Paper, PaperEntity
from app.services.entity_extractor import (
    extract_entities_for_paper,
    load_method_stages,
    load_sdl_entities,
    load_sdl_entity_meta,
)


def _entity(rows: list[PaperEntity], entity_type: str, normalized: str) -> PaperEntity:
    return next(
        r
        for r in rows
        if r.entity_type == entity_type and r.normalized_name == normalized
    )


def test_fine_method_with_category_loads():
    vocab = load_sdl_entities()
    assert vocab["method"]["XGBoost"] == "XGBoost"
    assert vocab["method"]["MPNN"] == "message passing neural network"
    assert vocab["method"]["VAE"] == "variational autoencoder"

    meta = load_sdl_entity_meta()
    assert meta["method"]["XGBoost"]["category"] == "gradient boosting"
    assert meta["method"]["CGCNN"]["category"] == "graph neural network"
    # Coarse families carry no category.
    assert meta["method"]["machine learning"]["category"] is None
    assert meta["method"]["bayesian optimization"]["category"] is None
    # Workflow phrases point at the closed-loop workflow family.
    assert meta["method"]["human-in-the-loop"]["category"] == "closed-loop workflow"


def test_vocab_integrity_every_category_is_a_method_canonical():
    meta = load_sdl_entity_meta()
    for entity_type, entries in meta.items():
        canonicals = set(entries)
        for canonical, info in entries.items():
            category = info["category"]
            if category is not None:
                assert category in canonicals, (
                    f"{entity_type} entry {canonical!r} has category "
                    f"{category!r} which is not a canonical name"
                )


def test_stage_taxonomy_loads_in_priority_order():
    stages = load_method_stages()
    assert list(stages) == [
        "property_prediction",
        "optimization",
        "generative_design",
        "synthesis_planning",
        "characterization_analysis",
        "automation_orchestration",
        "data_extraction",
    ]
    assert "predict" in stages["property_prediction"]


def test_stage_detected_from_sentence(session):
    paper = Paper(
        id="P_STG1",
        title="A materials study",
        abstract="We use Gaussian process regression to predict bandgaps. "
        "Samples were stored at room temperature.",
    )
    session.add(paper)
    session.flush()

    rows = extract_entities_for_paper(session, paper)
    gpr = _entity(rows, "method", "gaussian process regression")
    assert gpr.stage == "property_prediction"
    assert gpr.usage_snippet == "We use Gaussian process regression to predict bandgaps."
    assert len(gpr.usage_snippet) <= 250


def test_stage_priority_first_listed_stage_wins(session):
    # "predict" (property_prediction) and "optimize" (optimization) both match;
    # property_prediction is listed first in method_stages.yaml so it wins.
    paper = Paper(
        id="P_STG2",
        title="A study",
        abstract="A random forest was trained to predict and optimize yields.",
    )
    session.add(paper)
    session.flush()

    rows = extract_entities_for_paper(session, paper)
    assert _entity(rows, "method", "random forest").stage == "property_prediction"


def test_non_method_entities_get_null_stage(session):
    paper = Paper(
        id="P_STG3",
        title="A study",
        abstract="Perovskite films were screened by X-ray diffraction.",
    )
    session.add(paper)
    session.flush()

    rows = extract_entities_for_paper(session, paper)
    for normalized, etype in (
        ("perovskite", "material"),
        ("X-ray diffraction", "instrument"),
    ):
        row = _entity(rows, etype, normalized)
        assert row.stage is None
        assert row.usage_snippet is None


def test_multi_sentence_prefers_staged_hit(session):
    # First mention has no stage keywords; second does — the staged sentence wins.
    paper = Paper(
        id="P_STG4",
        title="A study",
        abstract="Random forest is a widely used model. "
        "We trained a random forest to predict solubility.",
    )
    session.add(paper)
    session.flush()

    rows = extract_entities_for_paper(session, paper)
    rf = _entity(rows, "method", "random forest")
    assert rf.stage == "property_prediction"
    assert rf.usage_snippet == "We trained a random forest to predict solubility."


def test_staged_title_hit_beats_unstaged_abstract_hit(session):
    paper = Paper(
        id="P_STG5",
        title="Random forest screening of catalysts",
        abstract="Random forest is a popular ensemble method.",
    )
    session.add(paper)
    session.flush()

    rows = extract_entities_for_paper(session, paper)
    rf = _entity(rows, "method", "random forest")
    # Stage presence outranks confidence: title hit (0.6, staged) wins over
    # abstract hit (0.7, unstaged); the whole title is the snippet.
    assert rf.stage == "property_prediction"
    assert rf.confidence == 0.6
    assert rf.usage_snippet == "Random forest screening of catalysts"


def test_stage_columns_persisted(session):
    paper = Paper(id="P_STG6", title="Bayesian optimization of reaction conditions")
    session.add(paper)
    session.flush()
    extract_entities_for_paper(session, paper)

    stored = session.execute(
        select(PaperEntity.stage, PaperEntity.usage_snippet).where(
            PaperEntity.paper_id == "P_STG6",
            PaperEntity.normalized_name == "bayesian optimization",
        )
    ).one()
    assert stored.stage == "optimization"
    assert stored.usage_snippet == "Bayesian optimization of reaction conditions"
