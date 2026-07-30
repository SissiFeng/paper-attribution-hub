"""Gold-fixture checks for evidence-linked catalyst extraction."""
from __future__ import annotations

from pathlib import Path

import yaml
from sqlalchemy import select

from app.models import (
    Paper,
    PaperEntity,
    PaperEntityExtractionState,
    PaperEntityMention,
    PaperEntityRelation,
    PaperLabLink,
    PipelineRun,
    SdlLab,
)
from app.services.entity_extractor import (
    extract_entities_for_paper,
    stale_paper_ids,
)
from app.services.kb_service import entity_index, entity_page
from app.services.transfer_service import adoption_lags
from app.scripts.run_entity_extraction import (
    extraction_run_id,
    run_stale_batches,
)

GOLD_PATH = Path(__file__).parents[2] / "data" / "catalyst_entity_gold.yaml"


def _gold_cases() -> list[dict]:
    raw = yaml.safe_load(GOLD_PATH.read_text(encoding="utf-8"))
    assert raw["version"] == "catalyst-entity-gold/1.0"
    return raw["cases"]


def _relations_for_paper(paper_id: str):
    return (
        select(PaperEntityRelation)
        .join(
            PaperEntityMention,
            PaperEntityMention.id == PaperEntityRelation.subject_mention_id,
        )
        .where(PaperEntityMention.paper_id == paper_id)
    )


def test_catalyst_gold_fixture(session):
    for case in _gold_cases():
        paper_id = f"P_GOLD_{case['id']}"
        paper = Paper(id=paper_id, title="Extraction check", abstract=case["text"])
        session.add(paper)
        session.flush()

        extract_entities_for_paper(session, paper)
        mentions = list(
            session.execute(
                select(PaperEntityMention).where(
                    PaperEntityMention.paper_id == paper_id
                )
            ).scalars()
        )
        concept_ids = {mention.concept_id for mention in mentions}
        assert set(case["expected_concepts"]) <= concept_ids
        assert not (set(case["excluded_concepts"]) & concept_ids)
        relations = list(
            session.execute(_relations_for_paper(paper_id)).scalars()
        )
        for expected in case.get("expected_relations", []):
            matches = [
                relation
                for relation in relations
                if relation.predicate == expected["predicate"]
                and (
                    "object_concept_id" not in expected
                    or relation.object_concept_id == expected["object_concept_id"]
                )
                and (
                    "object_value" not in expected
                    or relation.object_value == expected["object_value"]
                )
            ]
            assert matches
            if "elements" in expected:
                assert matches[0].object_metadata["elements"] == expected["elements"]


def test_hea_mention_has_offsets_evidence_and_proposed_relations(session):
    case = _gold_cases()[0]
    paper = Paper(id="P_GOLD_HEA_DETAIL", title="Check", abstract=case["text"])
    session.add(paper)
    session.flush()

    rows = extract_entities_for_paper(session, paper)
    mention = session.execute(
        select(PaperEntityMention).where(
            PaperEntityMention.paper_id == paper.id
        )
    ).scalar_one()
    relations = list(
        session.execute(_relations_for_paper(paper.id)).scalars()
    )

    assert mention.concept_id == "material:high_entropy_alloy_catalyst"
    assert case["text"][mention.start_char : mention.end_char] == mention.surface_form
    assert mention.evidence_text == case["text"]
    assert mention.specificity == "subtype"
    assert mention.ontology_version == "sdl-ontology/1.1"
    assert {(row.entity_type, row.normalized_name) for row in rows} >= {
        ("material", "high-entropy-alloy catalyst")
    }
    assert ("material", "catalyst") not in {
        (row.entity_type, row.normalized_name) for row in rows
    }

    by_predicate = {relation.predicate: relation for relation in relations}
    assert by_predicate["catalyzes"].object_concept_id == (
        "reaction:hydrogen_evolution"
    )
    composition = by_predicate["has_composition"]
    assert composition.object_value == "IrPdPtRhRu"
    assert composition.object_metadata["elements"] == ["Ir", "Pd", "Pt", "Rh", "Ru"]
    assert {relation.status for relation in relations} == {"proposed"}
    assert {relation.ontology_version for relation in relations} == {
        "sdl-ontology/1.1"
    }


def test_catalyst_graph_extraction_is_idempotent(session):
    case = _gold_cases()[0]
    paper = Paper(id="P_GOLD_IDEMPOTENT", title="Check", abstract=case["text"])
    session.add(paper)
    session.flush()

    extract_entities_for_paper(session, paper)
    first_counts = (
        len(
            list(
                session.execute(
                    select(PaperEntity).where(PaperEntity.paper_id == paper.id)
                ).scalars()
            )
        ),
        len(
            list(
                session.execute(
                    select(PaperEntityMention).where(
                        PaperEntityMention.paper_id == paper.id
                    )
                ).scalars()
            )
        ),
        len(
            list(
                session.execute(
                    _relations_for_paper(paper.id)
                ).scalars()
            )
        ),
    )
    extract_entities_for_paper(session, paper)
    reviewed = session.execute(
        _relations_for_paper(paper.id).where(
            PaperEntityRelation.predicate == "catalyzes",
        )
    ).scalar_one()
    reviewed.status = "reviewed"
    session.flush()
    extract_entities_for_paper(session, paper)
    second_counts = (
        session.query(PaperEntity).filter_by(paper_id=paper.id).count(),
        session.query(PaperEntityMention).filter_by(paper_id=paper.id).count(),
        len(list(session.execute(_relations_for_paper(paper.id)).scalars())),
    )
    # The compatibility roll-up also keeps the existing non-hierarchical
    # "alloy" vocabulary hit.
    assert first_counts == second_counts == (2, 1, 2)
    assert session.execute(
        select(PaperEntityRelation.status)
        .join(
            PaperEntityMention,
            PaperEntityMention.id == PaperEntityRelation.subject_mention_id,
        )
        .where(
            PaperEntityMention.paper_id == paper.id,
            PaperEntityRelation.predicate == "catalyzes",
        )
    ).scalar_one() == "reviewed"


def test_reextraction_retains_reviewed_obsolete_relation_and_evidence(session):
    original = (
        "IrPdPtRhRu high-entropy-alloy catalyst accelerates the "
        "hydrogen evolution reaction."
    )
    paper = Paper(id="P_GOLD_REVIEWED", title="Check", abstract=original)
    session.add(paper)
    session.flush()
    extract_entities_for_paper(session, paper)

    reviewed = session.execute(
        _relations_for_paper(paper.id).where(
            PaperEntityRelation.predicate == "catalyzes",
        )
    ).scalar_one()
    reviewed.status = "reviewed"
    reviewed_mention_id = reviewed.subject_mention_id
    paper.abstract = "IrPdPtRhRu high-entropy-alloy catalyst was evaluated."
    session.flush()

    extract_entities_for_paper(session, paper)

    retained = session.get(PaperEntityRelation, reviewed.id)
    assert retained is not None
    assert retained.status == "reviewed"
    retained_mention = session.get(PaperEntityMention, reviewed_mention_id)
    assert retained_mention is not None
    assert retained_mention.evidence_text == original


def test_multiple_catalysts_pair_only_with_nearest_reaction(session):
    paper = Paper(
        id="P_GOLD_NEAREST",
        title="Nearest relation check",
        abstract=(
            "A photocatalyst enables carbon dioxide reduction, while an "
            "electrocatalyst drives oxygen evolution."
        ),
    )
    session.add(paper)
    session.flush()
    extract_entities_for_paper(session, paper)

    pairs = {
        (mention.concept_id, relation.object_concept_id)
        for mention, relation in session.execute(
            select(PaperEntityMention, PaperEntityRelation)
            .join(
                PaperEntityRelation,
                PaperEntityRelation.subject_mention_id == PaperEntityMention.id,
            )
            .where(
                PaperEntityMention.paper_id == paper.id,
                PaperEntityRelation.predicate == "catalyzes",
            )
        )
    }
    assert pairs == {
        (
            "material:photocatalyst",
            "reaction:carbon_dioxide_reduction",
        ),
        ("material:electrocatalyst", "reaction:oxygen_evolution"),
    }


def _seed_catalyst_transfer(session) -> None:
    session.add_all(
        [
            SdlLab(
                id="cat-lab-a",
                name="Catalyst Lab A",
                institution="Test U",
                domain_focus="catalysis",
            ),
            SdlLab(
                id="cat-lab-b",
                name="Catalyst Lab B",
                institution="Test U",
                domain_focus="catalysis",
            ),
        ]
    )
    papers = [
        Paper(
            id="P_CAT_A",
            title="First system",
            abstract=(
                "IrPdPtRhRu high-entropy-alloy catalyst accelerates the "
                "hydrogen evolution reaction."
            ),
            year=2020,
        ),
        Paper(
            id="P_CAT_B",
            title="Second system",
            abstract=(
                "A photocatalyst was evaluated for the hydrogen evolution reaction."
            ),
            year=2022,
        ),
    ]
    session.add_all(papers)
    session.add_all(
        [
            PaperLabLink(paper_id="P_CAT_A", lab_id="cat-lab-a"),
            PaperLabLink(paper_id="P_CAT_B", lab_id="cat-lab-b"),
        ]
    )
    session.flush()
    for paper in papers:
        extract_entities_for_paper(session, paper)


def test_kb_catalyst_parent_rollup_and_facets(session):
    _seed_catalyst_transfer(session)

    entries = entity_index(session, entity_type="material")
    catalyst = next(entry for entry in entries if entry["name"] == "catalyst")
    assert catalyst["direct_paper_count"] == 0
    assert catalyst["rolled_up_paper_count"] == 2
    assert catalyst["rolled_up_lab_count"] == 2
    assert {child["name"] for child in catalyst["children"]} >= {
        "high-entropy-alloy catalyst",
        "photocatalyst",
    }

    page = entity_page(session, "material", "catalyst")
    assert page is not None
    assert page["direct_paper_count"] == 0
    assert page["rolled_up_paper_count"] == 2
    assert {paper["id"] for paper in page["papers"]} == {"P_CAT_A", "P_CAT_B"}
    assert {evidence["text"] for evidence in page["evidence"]} == {
        (
            "IrPdPtRhRu high-entropy-alloy catalyst accelerates the "
            "hydrogen evolution reaction."
        ),
        "A photocatalyst was evaluated for the hydrogen evolution reaction.",
    }
    assert page["reactions"] == [
        {
            "name": "hydrogen evolution reaction",
            "concept_id": "reaction:hydrogen_evolution",
            "paper_count": 2,
            "knowledge_state": "proposed",
        }
    ]
    assert page["compositions"][0]["name"] == "IrPdPtRhRu"


def test_transfer_catalyst_granularity(session):
    _seed_catalyst_transfer(session)

    exact = adoption_lags(
        session,
        entity_type="material",
        min_labs=1,
        granularity="entity",
    )
    assert {"high-entropy-alloy catalyst", "photocatalyst"} <= {
        entry["entity"] for entry in exact
    }

    parent = adoption_lags(
        session,
        entity_type="material",
        min_labs=2,
        granularity="parent",
    )
    catalyst = next(entry for entry in parent if entry["entity"] == "catalyst")
    assert catalyst["origin_lab"] == "cat-lab-a"
    assert catalyst["adoptions"] == [
        {"lab": "cat-lab-b", "first_year": 2022, "lag_years": 2}
    ]
    assert catalyst["knowledge_state"] == "observed"

    reactions = adoption_lags(session, min_labs=2, granularity="reaction")
    assert reactions == [
        {
            "entity": "hydrogen evolution reaction",
            "entity_type": "reaction",
            "origin_lab": "cat-lab-a",
            "origin_year": 2020,
            "adoptions": [
                {"lab": "cat-lab-b", "first_year": 2022, "lag_years": 2}
            ],
            "knowledge_state": "proposed",
        }
    ]

    rejected = session.execute(
        _relations_for_paper("P_CAT_B").where(
            PaperEntityRelation.predicate == "catalyzes",
        )
    ).scalar_one()
    rejected.status = "rejected"
    session.flush()
    assert adoption_lags(session, min_labs=2, granularity="reaction") == []


def test_kb_and_transfer_hide_relations_from_old_ontology_versions(session):
    _seed_catalyst_transfer(session)

    old_mention = session.execute(
        select(PaperEntityMention).where(
            PaperEntityMention.paper_id == "P_CAT_B",
            PaperEntityMention.concept_id == "material:photocatalyst",
        )
    ).scalar_one()
    old_mention.ontology_version = "sdl-ontology/obsolete"
    session.flush()

    page = entity_page(session, "material", "catalyst")
    assert page is not None
    assert page["reactions"][0]["paper_count"] == 1
    assert {evidence["paper_id"] for evidence in page["evidence"]} == {
        "P_CAT_A"
    }
    assert adoption_lags(session, min_labs=2, granularity="reaction") == []


def test_kb_and_transfer_hide_stale_compatibility_projections(session):
    _seed_catalyst_transfer(session)
    stale_state = session.get(PaperEntityExtractionState, "P_CAT_B")
    assert stale_state is not None
    stale_state.ontology_version = "sdl-ontology/obsolete"
    session.flush()

    entries = entity_index(session, entity_type="material")
    catalyst = next(entry for entry in entries if entry["name"] == "catalyst")
    assert catalyst["rolled_up_paper_count"] == 1
    page = entity_page(session, "material", "catalyst")
    assert page is not None
    assert {paper["id"] for paper in page["papers"]} == {"P_CAT_A"}
    assert (
        adoption_lags(
            session,
            entity_type="material",
            min_labs=2,
            granularity="parent",
        )
        == []
    )


def test_compatibility_projection_hides_source_and_config_staleness(session):
    _seed_catalyst_transfer(session)
    paper = session.get(Paper, "P_CAT_B")
    paper.abstract = "A changed photocatalyst abstract."
    session.flush()

    page = entity_page(session, "material", "catalyst")
    assert page is not None
    assert {row["id"] for row in page["papers"]} == {"P_CAT_A"}

    extract_entities_for_paper(session, paper)
    state = session.get(PaperEntityExtractionState, paper.id)
    state.config_fingerprint = "obsolete-config"
    session.flush()
    page = entity_page(session, "material", "catalyst")
    assert page is not None
    assert {row["id"] for row in page["papers"]} == {"P_CAT_A"}


def test_deploy_backfill_skips_when_sqlite_lease_is_held(session):
    from app.db import SessionLocal
    from app.scripts import run_entity_extraction as extraction_script

    if extraction_script.fcntl is None:
        return
    with SessionLocal() as lease_session:
        lock_path = extraction_script._sqlite_lock_path(lease_session)
    with lock_path.open("a+") as lock_file:
        extraction_script.fcntl.flock(
            lock_file.fileno(),
            extraction_script.fcntl.LOCK_EX,
        )
        try:
            summary = run_stale_batches(batch_size=1)
        finally:
            extraction_script.fcntl.flock(
                lock_file.fileno(),
                extraction_script.fcntl.LOCK_UN,
            )

    assert summary["skipped"] is True
    assert summary["reason"] == "lease_unavailable"


def test_transfer_granularity_endpoint(session):
    from fastapi.testclient import TestClient

    from app.main import app

    _seed_catalyst_transfer(session)
    session.commit()
    client = TestClient(app)

    parent = client.get(
        "/analytics/transfer/adoption",
        params={
            "entity_type": "material",
            "min_labs": 2,
            "granularity": "parent",
        },
    )
    assert parent.status_code == 200
    assert parent.json()[0]["entity"] == "catalyst"

    reaction = client.get(
        "/analytics/transfer/adoption",
        params={"min_labs": 2, "granularity": "reaction"},
    )
    assert reaction.status_code == 200
    assert reaction.json()[0]["knowledge_state"] == "proposed"
    assert client.get(
        "/analytics/transfer/adoption",
        params={"granularity": "unknown"},
    ).status_code == 422


def test_versioned_deploy_backfill_runs_once_and_records_completion(session):
    paper = Paper(
        id="P_STALE_BACKFILL",
        title="Backfill check",
        abstract="A photocatalyst enables hydrogen evolution.",
    )
    session.add(paper)
    session.commit()
    assert stale_paper_ids(session) == [paper.id]

    first = run_stale_batches(batch_size=1)
    session.expire_all()

    assert first["skipped"] is False
    assert first["papers_processed"] == 1
    marker = session.get(PipelineRun, extraction_run_id())
    assert marker is not None
    assert marker.status == "success"
    assert marker.steps[0]["total_stale"] == 1
    assert marker.steps[0]["papers_processed"] == 1
    assert marker.steps[0]["ontology_version"] == "sdl-ontology/1.1"
    state = session.get(PaperEntityExtractionState, paper.id)
    assert state is not None
    first_fingerprint = state.source_fingerprint

    second = run_stale_batches(batch_size=1)
    assert second["skipped"] is True

    paper.abstract = "An electrocatalyst enables oxygen evolution."
    session.commit()
    assert stale_paper_ids(session) == [paper.id]
    third = run_stale_batches(batch_size=1)
    session.expire_all()

    assert third["papers_processed"] == 1
    assert session.get(
        PaperEntityExtractionState,
        paper.id,
    ).source_fingerprint != first_fingerprint
