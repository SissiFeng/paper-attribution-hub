"""Evolutionary cross-SDL transfer autosearch."""
from __future__ import annotations

from tests.admin_client import AdminTestClient as TestClient

from app.models import Paper, PaperLabLink, TransferKnowledgeUnit
from app.services.evolutionary_transfer_service import (
    EvolutionConfig,
    export_autosearch_run,
    run_evolutionary_transfer_search,
)


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
            "surrogate_model": "gaussian process",
            "acquisition": "expected improvement",
            "loop": "design-make-test-analyze",
            "key_components": list(key_components),
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
    assert "## Best candidate" in text
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
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["accepted"] is True
    assert body["best"]["paper_ids"]
    assert len(body["trace"]) == 3

    r = client.post("/transfer/evolve", json={"target_id": "nope"})
    assert r.status_code == 404
