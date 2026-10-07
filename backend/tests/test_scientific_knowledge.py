from __future__ import annotations

import json

from tests.admin_client import AdminTestClient as TestClient
from sqlalchemy import event


def _seed_scientific_paper(session, *, paper_id: str = "P-SCIENCE"):
    from app.models import Paper, PaperChunk, PaperClassification

    paper = Paper(
        id=paper_id,
        title="Closed-loop perovskite synthesis",
        abstract="Bayesian optimization coordinates a liquid handler with BoTorch.",
        year=2025,
        full_text_available=True,
    )
    session.add(paper)
    session.add_all(
        [
            PaperChunk(
                id=f"{paper_id}-methods",
                paper_id=paper_id,
                section_type="methods",
                chunk_text=(
                    "Bayesian optimization in BoTorch selected perovskite "
                    "experiments executed by a liquid handler."
                ),
                indexed_text=None,
                char_start=0,
                char_end=102,
                token_count=13,
            ),
            PaperChunk(
                id=f"{paper_id}-references",
                paper_id=paper_id,
                section_type="references",
                chunk_text=("University of Toronto. X-ray diffraction handbook."),
                indexed_text=None,
                char_start=0,
                char_end=52,
                token_count=7,
            ),
        ]
    )
    session.add(
        PaperClassification(
            id=f"classification-{paper_id}",
            paper_id=paper_id,
            label="SECRET_CLASSIFIER_LABEL",
            confidence=0.99,
        )
    )
    session.commit()
    return paper


def test_compile_scientific_knowledge_is_evidence_linked_and_classification_neutral(
    session,
):
    from app.services.scientific_knowledge_service import (
        compile_scientific_knowledge,
    )

    paper = _seed_scientific_paper(session)
    statements: list[str] = []

    def capture_sql(_conn, _cursor, statement, _parameters, _context, _executemany):
        statements.append(statement.lower())

    event.listen(session.bind, "before_cursor_execute", capture_sql)
    try:
        first = compile_scientific_knowledge(session, paper.id)
        session.commit()
        first_generated_at = first.record.generated_at
        second = compile_scientific_knowledge(session, paper.id)
    finally:
        event.remove(session.bind, "before_cursor_execute", capture_sql)

    assert first.changed is True
    assert second.changed is False
    assert second.record.generated_at == first_generated_at
    assert set(first.record.entities) == {
        "method",
        "material",
        "instrument",
        "software",
    }
    assert {
        entity["name"]
        for entities in first.record.entities.values()
        for entity in entities
    } == {
        "bayesian optimization",
        "perovskite",
        "liquid handler",
        "BoTorch",
    }
    assert all(
        assertion["predicate"] == "reports_scientific_entity"
        for assertion in first.record.assertions
    )
    assert all(
        assertion["evidence"]["chunk_id"] == "P-SCIENCE-methods"
        for assertion in first.record.assertions
    )
    serialized = json.dumps(
        {
            "entities": first.record.entities,
            "assertions": first.record.assertions,
            "source_metadata": first.record.source_metadata,
        }
    )
    assert "SECRET_CLASSIFIER_LABEL" not in serialized
    assert "institution" not in serialized.casefold()
    assert "x-ray diffraction" not in serialized.casefold()
    assert not any(
        forbidden in statement
        for statement in statements
        for forbidden in (
            "paper_classifications",
            "human_reviews",
            "institutions",
        )
    )


def test_batch_compile_is_incremental_and_readable_through_api(session):
    from app.main import app
    from app.services.scientific_knowledge_service import (
        compile_scientific_knowledge_batch,
    )

    _seed_scientific_paper(session, paper_id="P-SCIENCE-ONE")
    _seed_scientific_paper(session, paper_id="P-SCIENCE-TWO")

    first = compile_scientific_knowledge_batch(session)
    session.commit()
    second = compile_scientific_knowledge_batch(session)

    assert first.as_dict() == {
        "selected": 2,
        "changed": 2,
        "unchanged": 0,
        "failed": 0,
        "errors": [],
    }
    assert second.as_dict() == {
        "selected": 2,
        "changed": 0,
        "unchanged": 2,
        "failed": 0,
        "errors": [],
    }

    response = TestClient(app).get("/kb/papers/P-SCIENCE-ONE/scientific-knowledge")
    assert response.status_code == 200
    payload = response.json()
    assert payload["paper_id"] == "P-SCIENCE-ONE"
    assert payload["schema_version"] == "pas-scientific-knowledge-v0.1"
    assert set(payload["entities"]) == {
        "method",
        "material",
        "instrument",
        "software",
    }
    assert payload["source_metadata"]["classification_neutral"] is True


def test_scientific_knowledge_api_returns_404_before_compilation(session):
    from app.main import app

    _seed_scientific_paper(session, paper_id="P-NOT-COMPILED")

    response = TestClient(app).get("/kb/papers/P-NOT-COMPILED/scientific-knowledge")

    assert response.status_code == 404


def test_vocabulary_change_invalidates_compiled_record(session, monkeypatch):
    from app.services import scientific_knowledge_service

    _seed_scientific_paper(session, paper_id="P-VOCABULARY")
    vocabulary = {
        "method": {"Bayesian optimization": "bayesian optimization"},
        "material": {},
        "instrument": {},
        "software": {},
    }
    monkeypatch.setattr(
        scientific_knowledge_service,
        "load_sdl_entities",
        lambda: vocabulary,
    )

    first = scientific_knowledge_service.compile_scientific_knowledge(
        session, "P-VOCABULARY"
    )
    session.commit()
    second = scientific_knowledge_service.compile_scientific_knowledge(
        session, "P-VOCABULARY"
    )
    vocabulary["material"]["perovskite"] = "perovskite"
    third = scientific_knowledge_service.compile_scientific_knowledge(
        session, "P-VOCABULARY"
    )

    assert first.changed is True
    assert second.changed is False
    assert third.changed is True
    assert [entity["name"] for entity in third.record.entities["material"]] == [
        "perovskite"
    ]
