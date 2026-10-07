"""Fresh-install and legacy-upgrade coverage for the Alembic chain."""

from __future__ import annotations

import json

from alembic import command
from alembic.config import Config
from pgvector.sqlalchemy import Vector
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.dialects import postgresql, sqlite

from app.config import BACKEND_ROOT, settings
from app.country_normalization import country_keys_v1
from app.models.chunk import PaperChunk


def _config(monkeypatch, database_url: str) -> Config:
    monkeypatch.setattr(settings, "database_url", database_url)
    config = Config(str(BACKEND_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_ROOT / "alembic"))
    return config


def test_chunk_embedding_uses_dialect_specific_storage():
    embedding_type = PaperChunk.__table__.c.embedding.type

    assert isinstance(
        embedding_type.dialect_impl(sqlite.dialect()), type(embedding_type)
    )
    assert isinstance(embedding_type.dialect_impl(postgresql.dialect()), Vector)


def test_fresh_sqlite_migrations_round_trip(tmp_path, monkeypatch):
    database_url = f"sqlite:///{tmp_path / 'fresh.db'}"
    config = _config(monkeypatch, database_url)

    command.upgrade(config, "head")
    engine = create_engine(database_url)
    assert {
        "papers",
        "wiki_pages",
        "paper_entities",
        "transfer_knowledge_units",
        "attribution_skill_invocations",
        "training_feedback_events",
        "model_training_runs",
        "model_training_state",
        "paper_authorship_metadata",
        "metadata_enrichment_runs",
        "chat_sessions",
        "chat_messages",
        "scientific_knowledge_records",
        "pas_readers", "pas_reader_sessions", "pas_bookmarks", "chat_participants",
    } <= set(inspect(engine).get_table_names())
    invocation_columns = {
        column["name"]
        for column in inspect(engine).get_columns(
            "attribution_skill_invocations"
        )
    }
    assert {
        "final_confidence",
        "failure_category",
        "retrieval_api_calls",
        "fulltext_retrieval_status",
        "extraction_seconds",
        "model_calls",
        "input_tokens",
        "output_tokens",
        "estimated_cost_usd",
        "graph_queries",
        "human_review_seconds",
        "retries",
        "resolution_path",
    } <= invocation_columns
    paper_columns = {
        column["name"] for column in inspect(engine).get_columns("papers")
    }
    wiki_columns = {
        column["name"] for column in inspect(engine).get_columns("wiki_pages")
    }
    assert {
        "source_snapshot_hash",
        "content_hash",
        "source_metadata",
        "compile_status",
        "compile_error",
    } <= wiki_columns
    assert "corpus_sources" in paper_columns
    review_columns = {
        column["name"]
        for column in inspect(engine).get_columns("human_reviews")
    }
    assert {
        "sdl_judgement",
        "ac_relevance_judgement",
        "ai_for_science_judgement",
        "review_status",
        "evidence_level",
        "judgement_basis",
    } <= review_columns
    classification_columns = {
        column["name"]
        for column in inspect(engine).get_columns("paper_classifications")
    }
    assert {
        "screening_stage",
        "screening_route",
        "screening_reason",
        "review_assignee",
        "review_assigned_at",
        "review_assigned_by",
    } <= classification_columns
    assert {
        "citation_count",
        "citation_count_source",
        "citation_count_updated_at",
    } <= paper_columns
    training_run_columns = {
        column["name"]
        for column in inspect(engine).get_columns("model_training_runs")
    }
    assert {
        "model_artifact",
        "label_boundary_hashes",
        "lease_generation",
        "promotion_gate_config",
        "runtime_versions",
        "cache_sync_status",
        "heartbeat_at",
    } <= training_run_columns
    feedback_columns = {
        column["name"]
        for column in inspect(engine).get_columns("training_feedback_events")
    }
    assert {"retired_at", "retirement_reason"} <= feedback_columns
    institution_columns = {
        column["name"]
        for column in inspect(engine).get_columns("institutions")
    }
    assert "country_keys" in institution_columns
    with engine.connect() as connection:
        assert (
            connection.scalar(text("SELECT version_num FROM alembic_version")) == "0026"
        )
    command.check(config)


def test_country_key_migration_backfills_unicode_tokens(tmp_path, monkeypatch):
    database_url = f"sqlite:///{tmp_path / 'existing-0016.db'}"
    config = _config(monkeypatch, database_url)
    command.upgrade(config, "0016")
    engine = create_engine(database_url)
    country = "TÜRKİYE; United\u00a0States"

    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO institutions (id, canonical_name, country, "
                "is_partner) VALUES "
                "('unicode-country', 'Unicode Country Lab', :country, 0)"
            ),
            {"country": country},
        )

    command.upgrade(config, "head")
    with engine.connect() as connection:
        stored = connection.scalar(
            text(
                "SELECT country_keys FROM institutions "
                "WHERE id = 'unicode-country'"
            )
        )
    assert json.loads(stored) == country_keys_v1(country)

    command.downgrade(config, "base")
    command.upgrade(config, "head")
    command.check(config)


def test_staged_screening_migration_backfills_existing_classifications(
    tmp_path,
    monkeypatch,
):
    database_url = f"sqlite:///{tmp_path / 'existing-0012.db'}"
    config = _config(monkeypatch, database_url)
    command.upgrade(config, "0012")
    engine = create_engine(database_url)
    now = "2026-07-31 00:00:00+00:00"

    with engine.begin() as connection:
        for paper_id in ("P-POSITIVE", "P-SCREENED", "P-FULLTEXT"):
            connection.execute(
                text(
                    """
                    INSERT INTO papers (
                        id, title, source, provenance, full_text_available,
                        created_at, updated_at
                    ) VALUES (
                        :id, :title, 'test', 'test', 0, :created_at, :updated_at
                    )
                    """
                ),
                {
                    "id": paper_id,
                    "title": paper_id,
                    "created_at": now,
                    "updated_at": now,
                },
            )
        rows = [
            ("P-POSITIVE", "CORE_RELEVANT", 0.92),
            ("P-SCREENED", "EXCLUDE", 0.95),
            ("P-FULLTEXT", "UNCERTAIN", 0.50),
        ]
        for paper_id, label, confidence in rows:
            connection.execute(
                text(
                    """
                    INSERT INTO paper_classifications (
                        id, paper_id, label, confidence, author_score,
                        institution_score, topic_score, network_score,
                        fulltext_evidence_score, citation_score, model_version,
                        created_at, needs_review, review_priority,
                        human_confirmed
                    ) VALUES (
                        :id, :paper_id, :label, :confidence, 0, 0, 0, 0, 0, 0,
                        'test', :created_at, 0, 0, 0
                    )
                    """
                ),
                {
                    "id": f"cls-{paper_id}",
                    "paper_id": paper_id,
                    "label": label,
                    "confidence": confidence,
                    "created_at": now,
                },
            )
        connection.execute(
            text(
                """
                INSERT INTO human_reviews (
                    id, paper_id, human_label, review_status, evidence_level,
                    judgement_basis, created_at
                ) VALUES (
                    'review-fulltext', 'P-FULLTEXT', NULL, 'NEEDS_FULLTEXT',
                    'ABSTRACT', 'DUAL_REVIEW', :created_at
                )
                """
            ),
            {"created_at": now},
        )

    command.upgrade(config, "head")

    with engine.connect() as connection:
        routes = dict(
            connection.execute(
                text(
                    "SELECT paper_id, screening_route "
                    "FROM paper_classifications"
                )
            ).all()
        )
    assert routes == {
        "P-POSITIVE": "POSITIVE_REVIEW",
        "P-SCREENED": "SCREENED_OUT",
        "P-FULLTEXT": "FULLTEXT_REVIEW",
    }


def test_tku_alignment_upgrades_existing_0009_database(tmp_path, monkeypatch):
    database_url = f"sqlite:///{tmp_path / 'existing-0009.db'}"
    config = _config(monkeypatch, database_url)
    command.upgrade(config, "0009")

    now = "2026-07-28 00:00:00+00:00"
    engine = create_engine(database_url)
    with engine.begin() as connection:
        connection.execute(
            text(
                """
                INSERT INTO papers (
                    id, title, source, provenance, full_text_available,
                    created_at, updated_at
                ) VALUES (
                    :id, :title, :source, :provenance, :full_text_available,
                    :created_at, :updated_at
                )
                """
            ),
            {
                "id": "P-MIGRATION",
                "title": "Migration fixture",
                "source": "test",
                "provenance": "test",
                "full_text_available": False,
                "created_at": now,
                "updated_at": now,
            },
        )
        connection.execute(
            text(
                """
                INSERT INTO transfer_knowledge_units (
                    id, paper_id, source_domain, problem_signature,
                    method_core, assumptions, lessons, domain_bindings,
                    extractor, model, created_at
                ) VALUES (
                    :id, :paper_id, :source_domain, :problem_signature,
                    :method_core, :assumptions, :lessons, :domain_bindings,
                    :extractor, :model, NULL
                )
                """
            ),
            {
                "id": "tku-P-MIGRATION",
                "paper_id": "P-MIGRATION",
                "source_domain": "test",
                "problem_signature": "{}",
                "method_core": "{}",
                "assumptions": "[]",
                "lessons": "[]",
                "domain_bindings": "[]",
                "extractor": "test",
                "model": None,
            },
        )

    command.upgrade(config, "head")

    with engine.connect() as connection:
        created_at = connection.scalar(
            text(
                "SELECT created_at FROM transfer_knowledge_units "
                "WHERE id = 'tku-P-MIGRATION'"
            )
        )
    assert created_at is not None
    indexes = {
        index["name"]: index
        for index in inspect(engine).get_indexes("transfer_knowledge_units")
    }
    assert indexes["ix_transfer_knowledge_units_paper_id"]["unique"] == 1


def test_scoped_cloud_reading_schema_is_adopted_by_full_migrations(tmp_path, monkeypatch):
    from app.db import Base
    from app.services.reading_schema import ensure_reading_schema
    database_url = f"sqlite:///{tmp_path / 'adoption.db'}"
    config = _config(monkeypatch, database_url)
    engine = create_engine(database_url)
    command.upgrade(config, '0018')
    ensure_reading_schema(engine, Base.metadata)
    ensure_reading_schema(engine, Base.metadata)
    from app.services.access_schema import ensure_access_schema
    ensure_access_schema(engine, Base.metadata)
    ensure_access_schema(engine, Base.metadata)
    from app.services.research_schema import ensure_research_schema
    ensure_research_schema(engine, Base.metadata)
    ensure_research_schema(engine, Base.metadata)
    from app.services.exploration_schema import ensure_exploration_schema
    ensure_exploration_schema(engine, Base.metadata)
    ensure_exploration_schema(engine, Base.metadata)
    command.upgrade(config, 'head')
    with engine.connect() as connection:
        assert connection.execute(text('SELECT version_num FROM alembic_version')).scalar_one() == '0026'
