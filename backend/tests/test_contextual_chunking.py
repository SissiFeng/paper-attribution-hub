from sqlalchemy import select

from app.models import PaperChunk
from app.services.chunking_service import contextual_prefix, with_context


def test_contextual_prefix_formats_title_year_section():
    p = contextual_prefix(
        title="Autonomous lab paper",
        year=2024,
        section_type="methods",
        section_title=None,
    )
    assert p.startswith("Context: ")
    assert "Autonomous lab paper" in p
    assert "2024" in p
    assert "methods" in p


def test_contextual_prefix_includes_section_title_when_distinct():
    p = contextual_prefix(
        title="X",
        year=2024,
        section_type="methods",
        section_title="Closed-loop workflow",
    )
    assert "Closed-loop workflow" in p


def test_contextual_prefix_omits_year_when_missing():
    p = contextual_prefix(title="X", year=None, section_type="abstract", section_title=None)
    assert "(202" not in p
    assert "abstract" in p


def test_with_context_concatenates():
    out = with_context("Hello.", "Context: From X (2024), methods.")
    assert "Context: From X" in out
    assert "Hello." in out
    assert out.index("Context") < out.index("Hello")


def test_ingestion_populates_indexed_text(fulltext_seeded_session):
    rows = list(fulltext_seeded_session.execute(select(PaperChunk)).scalars())
    assert rows
    for chunk in rows:
        assert chunk.indexed_text is not None
        # indexed_text should be at least as long as the raw chunk_text.
        assert len(chunk.indexed_text) >= len(chunk.chunk_text)
        # And carry the contextual signal.
        assert chunk.indexed_text.lower().startswith("context:")


def test_metadata_carries_prefix(fulltext_seeded_session):
    chunk = (
        fulltext_seeded_session.execute(
            select(PaperChunk).where(PaperChunk.section_type == "methods")
        )
        .scalars()
        .first()
    )
    assert chunk is not None
    meta = chunk.chunk_metadata or {}
    assert "contextual_prefix" in meta
    assert "From" in meta["contextual_prefix"]
    assert meta["chunk_kind"] == "child"
    assert meta["parent_id"]
    assert meta["parent_text"]
    assert meta["split_strategy"] in {
        "semantic_adaptive",
        "sliding_fallback",
        "unsplit",
    }


def test_indexed_text_carries_parent_context(fulltext_seeded_session):
    chunk = (
        fulltext_seeded_session.execute(
            select(PaperChunk).where(PaperChunk.section_type == "methods")
        )
        .scalars()
        .first()
    )
    assert chunk is not None
    assert chunk.indexed_text is not None
    meta = chunk.chunk_metadata or {}
    if meta.get("parent_text") != chunk.chunk_text:
        assert "Parent context:" in chunk.indexed_text
        assert "Child chunk:" in chunk.indexed_text
