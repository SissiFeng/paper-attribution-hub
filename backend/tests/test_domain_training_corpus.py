from __future__ import annotations

import json

import pytest
from sqlalchemy import event


def test_domain_training_corpus_is_deterministic_and_classification_neutral(
    session,
    tmp_path,
):
    from app.models import Paper, PaperChunk, PaperClassification
    from app.services.domain_training_corpus import export_domain_training_corpus
    from app.services.scientific_knowledge_service import compile_scientific_knowledge

    text = "Bayesian optimization in BoTorch selected perovskite experiments."
    session.add(
        Paper(
            id="P-CORPUS",
            title="Closed-loop materials discovery",
            abstract="A reproducible scientific abstract.",
            year=2025,
            full_text_available=True,
        )
    )
    session.add_all(
        [
            PaperChunk(
                id="P-CORPUS-methods",
                paper_id="P-CORPUS",
                section_type="methods",
                chunk_text=text,
                char_start=0,
                char_end=len(text),
                token_count=7,
            ),
            PaperChunk(
                id="P-CORPUS-duplicate",
                paper_id="P-CORPUS",
                section_type="results",
                chunk_text=text,
                char_start=0,
                char_end=len(text),
                token_count=7,
            ),
            PaperChunk(
                id="P-CORPUS-references",
                paper_id="P-CORPUS",
                section_type="references",
                chunk_text="University of Toronto institutional bibliography.",
                char_start=0,
                char_end=49,
                token_count=6,
            ),
        ]
    )
    session.add(
        PaperClassification(
            id="classification-P-CORPUS",
            paper_id="P-CORPUS",
            label="SECRET_CLASSIFIER_LABEL",
            confidence=0.99,
        )
    )
    session.commit()
    compile_scientific_knowledge(session, "P-CORPUS")
    session.commit()

    statements: list[str] = []

    def capture_sql(_conn, _cursor, statement, _parameters, _context, _executemany):
        statements.append(statement.lower())

    event.listen(session.bind, "before_cursor_execute", capture_sql)
    try:
        first = export_domain_training_corpus(session, tmp_path)
        first_corpus = first.corpus_path.read_bytes()
        first_manifest = first.manifest_path.read_bytes()
        second = export_domain_training_corpus(session, tmp_path)
    finally:
        event.remove(session.bind, "before_cursor_execute", capture_sql)

    assert first.changed_files == 2
    assert second.changed_files == 0
    assert second.corpus_path.read_bytes() == first_corpus
    assert second.manifest_path.read_bytes() == first_manifest
    assert first.manifest == {
        "schema_version": "pas-domain-training-corpus-v0.1",
        "classification_neutral": True,
        "paper_count": 1,
        "record_count": 1,
        "duplicate_count": 1,
        "sections": {"methods": 1},
        "corpus_sha256": first.manifest["corpus_sha256"],
    }

    rows = [json.loads(line) for line in first.corpus_path.read_text().splitlines()]
    assert rows == [
        {
            "schema_version": "pas-domain-training-text-v0.1",
            "record_id": rows[0]["record_id"],
            "paper_id": "P-CORPUS",
            "title": "Closed-loop materials discovery",
            "year": 2025,
            "chunk_id": "P-CORPUS-methods",
            "section_type": "methods",
            "text": text,
            "content_sha256": rows[0]["content_sha256"],
            "knowledge_record_hash": rows[0]["knowledge_record_hash"],
        }
    ]
    serialized = first_corpus.decode() + first_manifest.decode()
    assert "SECRET_CLASSIFIER_LABEL" not in serialized
    assert "institutional bibliography" not in serialized
    assert not any(
        forbidden in statement
        for statement in statements
        for forbidden in (
            "paper_classifications",
            "human_reviews",
            "institutions",
        )
    )


def test_domain_training_corpus_rejects_stale_knowledge_records(session, tmp_path):
    from app.models import Paper, PaperChunk
    from app.services.domain_training_corpus import (
        StaleScientificKnowledgeError,
        export_domain_training_corpus,
    )
    from app.services.scientific_knowledge_service import compile_scientific_knowledge

    session.add(
        Paper(
            id="P-STALE",
            title="Perovskite synthesis",
            full_text_available=True,
        )
    )
    chunk = PaperChunk(
        id="P-STALE-methods",
        paper_id="P-STALE",
        section_type="methods",
        chunk_text="A liquid handler prepared perovskite samples.",
        char_start=0,
        char_end=47,
        token_count=7,
    )
    session.add(chunk)
    session.commit()
    compile_scientific_knowledge(session, "P-STALE")
    session.commit()
    chunk.chunk_text = "The source text changed after knowledge compilation."
    session.commit()

    with pytest.raises(StaleScientificKnowledgeError, match="P-STALE"):
        export_domain_training_corpus(session, tmp_path)

    assert not (tmp_path / "domain_corpus.jsonl").exists()
