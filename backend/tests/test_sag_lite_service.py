"""SAG-lite derived event trail over existing KB tables."""
from __future__ import annotations

from app.models import (
    Paper,
    PaperChunk,
    PaperEntity,
    PaperEntityExtractionState,
    PaperLabLink,
    SdlLab,
)
from app.services.entity_extractor import (
    CATALYST_EXTRACTOR_VERSION,
    extraction_config_fingerprint,
)
from app.services.ontology_service import load_ontology
from app.services.sag_lite_service import entity_event_trail


def test_entity_event_trail_links_mentions_to_related_entities(session):
    session.add(
        SdlLab(
            id="lab-a",
            name="Lab A",
            institution="Test U",
            domain_focus="testing",
        )
    )
    session.add(
        Paper(
            id="P1",
            title="Closed-loop optimization paper",
            abstract="Fallback abstract.",
            year=2024,
        )
    )
    session.add(PaperLabLink(paper_id="P1", lab_id="lab-a"))
    session.add(
        PaperEntityExtractionState(
            paper_id="P1",
            ontology_version=load_ontology()["ontology_version"],
            extractor_version=CATALYST_EXTRACTOR_VERSION,
            config_fingerprint=extraction_config_fingerprint(),
            source_fingerprint="test:P1",
        )
    )
    session.add(
        PaperChunk(
            id="CH1",
            paper_id="P1",
            section_type="methods",
            chunk_text="Bayesian optimization selected the next formulation.",
        )
    )
    session.add_all(
        [
            PaperEntity(
                id="E1",
                paper_id="P1",
                entity_type="method",
                name="bayesian optimization",
                normalized_name="bayesian optimization",
                evidence_chunk_id="CH1",
                stage="optimization",
                usage_snippet="Bayesian optimization selected the next formulation.",
            ),
            PaperEntity(
                id="E2",
                paper_id="P1",
                entity_type="material",
                name="perovskite",
                normalized_name="perovskite",
            ),
        ]
    )
    session.flush()

    events = entity_event_trail(session, "method", "bayesian optimization")

    assert len(events) == 1
    event = events[0]
    assert event["id"] == "sag_p1-method-bayesian-optimization"
    assert event["event_type"] == "stage:optimization"
    assert event["paper_id"] == "P1"
    assert event["labs"] == ["lab-a"]
    assert event["source_chunk_id"] == "CH1"
    assert event["snippet"] == "Bayesian optimization selected the next formulation."
    assert event["related_entities"] == [
        {"entity_type": "material", "name": "perovskite"}
    ]


def test_entity_event_trail_returns_empty_for_unknown_entity(session):
    assert entity_event_trail(session, "method", "missing") == []
