"""Evolutionary cross-SDL transfer autosearch."""
from __future__ import annotations

from fastapi.testclient import TestClient

from app.models import Paper, PaperLabLink, TransferKnowledgeUnit
from app.services.evolutionary_transfer_service import (
    EvolutionConfig,
    export_autosearch_run,
    run_evolutionary_transfer_search,
)
from app.services.ontology_service import (
    build_proposed_claim,
    evaluate_candidate_compatibility,
    load_ontology,
)
from app.services.transfer_designer import load_target


def _tku(
    paper_id: str,
    source_domain: str,
    *,
    workflow: str,
    key_components: tuple[str, ...],
    lesson: tuple[str, str],
    task_type: str = "optimization",
    search_space: str = "mixed",
    objectives: str = "multi",
    evaluation_cost: str = "medium",
    requires_capabilities: tuple[str, ...] = (),
    required_unit_dimensions: tuple[str, ...] = (),
    ontology_mapping_complete: bool = True,
) -> TransferKnowledgeUnit:
    method_text = " ".join((workflow, *key_components)).lower()
    method_concepts: list[str] = []
    for terms, concept_id in (
        (("bayesian optimization", "expected improvement"), "method:bayesian_optimization"),
        (("active learning",), "method:active_learning"),
        (
            ("high-throughput synthesis", "autonomous catalyst screening"),
            "method:high_throughput_synthesis",
        ),
        (("flow chemistry", "continuous flow"), "method:flow_chemistry"),
        (("property prediction",), "method:property_prediction"),
        (("rheology",), "method:rheology"),
    ):
        if any(term in method_text for term in terms):
            method_concepts.append(concept_id)
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
            "required_unit_dimensions": list(required_unit_dimensions),
        },
        method_core={
            "workflow": workflow,
            "surrogate_model": "gaussian process",
            "acquisition": "expected improvement",
            "loop": "design-make-test-analyze",
            "key_components": list(key_components),
            "ontology_version": "sdl-ontology/1.1",
            "ontology_mapping_complete": ontology_mapping_complete,
            "method_concepts": method_concepts,
            "requires_capabilities": list(requires_capabilities),
        },
        assumptions=["measurements are comparable across batches"],
        lessons=[{"text": lesson[0], "polarity": lesson[1]}],
        domain_bindings=[f"{source_domain} material"],
        extractor="example",
        model=None,
    )


def _seed(session) -> None:
    rows = [
        (
            "P_BAT",
            "Battery electrolyte optimization",
            "battery",
            "closed-loop bayesian optimization",
            ("bayesian optimization", "composition search"),
            ("early stopping preserved budget", "positive"),
        ),
        (
            "P_CAT",
            "Catalyst screening loop",
            "catalysis",
            "autonomous catalyst screening",
            ("bayesian optimization", "high-throughput synthesis"),
            ("reference drift biased results", "negative"),
        ),
        (
            "P_FORM",
            "Mixture formulation search",
            "formulation",
            "mixture-aware design of experiments",
            ("formulation", "rheology", "active learning"),
            ("mixture constraints reduced invalid candidates", "positive"),
        ),
        (
            "P_MED",
            "Medicinal active learning",
            "medicinal",
            "active learning over discrete molecules",
            ("active learning", "property prediction"),
            ("uncertainty estimates needed calibration", "negative"),
        ),
    ]
    for paper_id, title, domain, workflow, components, lesson in rows:
        session.add(Paper(id=paper_id, title=title, year=2024))
        session.add(
            _tku(
                paper_id,
                domain,
                workflow=workflow,
                key_components=components,
                lesson=lesson,
            )
        )

    session.add(Paper(id="P_OWN", title="Own polymer loop", year=2025))
    session.add(PaperLabLink(paper_id="P_OWN", lab_id="sdl4"))
    session.add(
        _tku(
            "P_OWN",
            "polymer",
            workflow="polymer bayesian optimization",
            key_components=("polymer", "bayesian optimization"),
            lesson=("own lab evidence should be excluded", "positive"),
        )
    )
    session.flush()


def test_evolutionary_search_combines_cross_domain_tkus(session):
    _seed(session)
    report = run_evolutionary_transfer_search(
        session,
        EvolutionConfig(
            target_id="sdl4",
            population_size=6,
            generations=4,
            source_pool=8,
            genome_size=3,
            seed=1,
            include_knowledge_json=False,
        ),
    )

    assert report["source_count"] == 4
    assert report["accepted"] is True
    assert len(report["trace"]) == 4
    best = report["best"]
    assert best["score"] >= 8.0
    assert len(best["paper_ids"]) == 3
    assert "P_OWN" not in best["paper_ids"]
    assert best["hypothesis"].startswith("SDL 4")
    assert any("Adapt workflow" in step for step in best["transfer_plan"])
    assert "[src:" in " ".join(best["citations"])
    assert best["ontology_compatibility"]["status"] == "compatible"
    assert best["knowledge_claim"]["state"] == "proposed"
    assert best["knowledge_claim"]["executable"] is False
    assert report["candidates"][0]["id"] == best["id"]


def test_export_autosearch_run_writes_wiki_card_and_log(session, tmp_path):
    _seed(session)
    report = run_evolutionary_transfer_search(
        session,
        EvolutionConfig(
            target_id="sdl4",
            population_size=4,
            generations=2,
            include_knowledge_json=False,
        ),
    )
    path = export_autosearch_run(report, output_dir=tmp_path / "autosearch")

    text = path.read_text(encoding="utf-8")
    assert text.startswith("---")
    assert "type: autosearch-run" in text
    assert "ontology_version: sdl-ontology/1.1" in text
    assert "knowledge_state: proposed" in text
    assert "## Best candidate" in text
    assert "Ontology compatibility: compatible" in text
    assert "Knowledge state: proposed" in text
    assert "Machine-readable report" in text
    log = tmp_path / "log.md"
    assert log.exists()
    assert "Evolutionary transfer: SDL 4" in log.read_text(encoding="utf-8")


def test_api_evolve_endpoint(session):
    from app.main import app

    _seed(session)
    session.commit()
    client = TestClient(app)

    r = client.post(
        "/transfer/evolve",
        json={
            "target_id": "sdl4",
            "population_size": 5,
            "generations": 3,
            "genome_size": 3,
            "seed": 2,
            "include_knowledge_json": False,
            "ontology_gate": True,
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["accepted"] is True
    assert body["ontology"]["gate_enabled"] is True
    assert body["best"]["knowledge_claim"]["state"] == "proposed"
    assert body["best"]["paper_ids"]
    assert len(body["trace"]) == 3

    r = client.post("/transfer/evolve", json={"target_id": "nope"})
    assert r.status_code == 404


def test_ontology_contract_and_lifecycle_are_versioned():
    ontology = load_ontology()
    assert ontology["ontology_version"] == "sdl-ontology/1.1"
    assert "proposed" in ontology["knowledge_lifecycle"]["states"]
    assert any(
        transition["action"] == "promote" and transition["from"] == "validated"
        for transition in ontology["knowledge_lifecycle"]["transitions"]
    )


def test_ontology_compatibility_rejects_missing_capability():
    target = load_target("sdl4")
    assert target is not None
    tku = _tku(
        "P_FLOW",
        "flow",
        workflow="continuous flow synthesis",
        key_components=("flow chemistry",),
        lesson=("flow stabilized residence time", "positive"),
        requires_capabilities=("capability:continuous_flow_reactor",),
    )

    compatibility = evaluate_candidate_compatibility([tku], target)
    assert compatibility["status"] == "incompatible"
    assert compatibility["missing_capabilities"] == [
        "capability:continuous_flow_reactor"
    ]

    claim = build_proposed_claim(
        target=target,
        paper_ids=(tku.paper_id,),
        hypothesis="Test flow chemistry for polymer synthesis.",
        citations=[f"[src:{tku.paper_id}]"],
        compatibility=compatibility,
    )
    assert claim["state"] == "proposed"
    assert claim["executable"] is False
    assert "promote" not in claim["allowed_next_actions"]


def test_ontology_compatibility_keeps_unknown_references_unresolved():
    target = load_target("sdl4")
    assert target is not None
    tku = _tku(
        "P_UNKNOWN",
        "unknown",
        workflow="unmapped workflow",
        key_components=("unmapped component",),
        lesson=("requires mapping before transfer", "neutral"),
        requires_capabilities=("capability:not_in_ontology",),
    )

    compatibility = evaluate_candidate_compatibility([tku], target)
    assert compatibility["status"] == "unknown"
    assert compatibility["unknown_references"] == ["capability:not_in_ontology"]
    assert compatibility["blocking_issues"]


def test_legacy_tku_without_versioned_mapping_stays_unknown():
    target = load_target("sdl4")
    assert target is not None
    tku = _tku(
        "P_LEGACY",
        "battery",
        workflow="bayesian optimization",
        key_components=("bayesian optimization",),
        lesson=("legacy mapping is incomplete", "neutral"),
        ontology_mapping_complete=False,
    )

    compatibility = evaluate_candidate_compatibility([tku], target)
    assert compatibility["status"] == "unknown"
    assert compatibility["incomplete_mappings"] == [tku.id]


def test_ontology_compatibility_does_not_overclaim_partial_unit_inventory():
    target = load_target("sdl4")
    assert target is not None
    partial_target = {
        **target,
        "ontology_profile": {
            **target["ontology_profile"],
            "unit_dimension_inventory_complete": False,
            "supported_unit_dimensions": [],
        },
    }
    tku = _tku(
        "P_UNIT",
        "battery",
        workflow="bayesian optimization",
        key_components=("bayesian optimization",),
        lesson=("units must map before transfer", "neutral"),
        required_unit_dimensions=("unit_dimension:mass",),
    )

    compatibility = evaluate_candidate_compatibility([tku], partial_target)
    assert compatibility["status"] == "unknown"
    assert compatibility["missing_unit_dimensions"] == ["unit_dimension:mass"]
    assert "cannot confirm" in " ".join(compatibility["blocking_issues"])


def test_ontology_gate_blocks_incompatible_best_candidate(session):
    session.add(Paper(id="P_FLOW", title="Flow chemistry transfer", year=2025))
    session.add(
        _tku(
            "P_FLOW",
            "flow",
            workflow="continuous flow synthesis",
            key_components=("flow chemistry", "bayesian optimization"),
            lesson=("flow stabilized residence time", "positive"),
            requires_capabilities=("capability:continuous_flow_reactor",),
        )
    )
    session.flush()

    report = run_evolutionary_transfer_search(
        session,
        EvolutionConfig(
            target_id="sdl4",
            source_domain="flow",
            population_size=1,
            generations=1,
            source_pool=1,
            genome_size=1,
            include_knowledge_json=False,
            ontology_gate=True,
        ),
    )
    assert report["accepted"] is False
    assert report["best"]["ontology_compatibility"]["status"] == "incompatible"
    assert "Ontology gate blocked acceptance" in " ".join(report["recommendations"])

    ungated = run_evolutionary_transfer_search(
        session,
        EvolutionConfig(
            target_id="sdl4",
            source_domain="flow",
            population_size=1,
            generations=1,
            source_pool=1,
            genome_size=1,
            include_knowledge_json=False,
            ontology_gate=False,
        ),
    )
    assert ungated["accepted"] is True
    assert ungated["best"]["knowledge_claim"]["executable"] is False


def test_api_exposes_ontology_summary():
    from app.main import app

    client = TestClient(app)
    response = client.get("/transfer/ontology")
    assert response.status_code == 200
    assert response.json()["ontology_version"] == "sdl-ontology/1.1"
    targets = client.get("/transfer/targets")
    assert targets.status_code == 200
    sdl4 = next(target for target in targets.json() if target["id"] == "sdl4")
    assert sdl4["ontology_profile"]["capability_inventory_complete"] is True
    assert sdl4["ontology_gate_ready"] is True
    sdl1 = next(target for target in targets.json() if target["id"] == "sdl1")
    assert sdl1["ontology_gate_ready"] is False

    unavailable = client.post(
        "/transfer/evolve",
        json={"target_id": "sdl1", "ontology_gate": True},
    )
    assert unavailable.status_code == 422
