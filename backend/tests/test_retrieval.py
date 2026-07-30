from app.services.embedding_service import get_embedder
from app.services.retrieval_service import HybridIndex


def test_index_query_does_not_load_stored_embeddings(fulltext_seeded_session):
    """The request-time index refits vectors and must not deserialize old ones."""
    from sqlalchemy import event

    statements: list[str] = []
    engine = fulltext_seeded_session.get_bind()

    def capture_sql(_conn, _cursor, statement, _parameters, _context, _executemany):
        statements.append(statement)

    event.listen(engine, "before_cursor_execute", capture_sql)
    try:
        HybridIndex.from_session(
            fulltext_seeded_session,
            get_embedder(),
            max_chunks=2,
        )
    finally:
        event.remove(engine, "before_cursor_execute", capture_sql)

    chunk_select = next(
        statement
        for statement in statements
        if "FROM paper_chunks" in statement and "JOIN papers" in statement
    )
    selected_columns = chunk_select.split("FROM paper_chunks", 1)[0]
    assert "paper_chunks.embedding" not in selected_columns


def test_retrieval_finds_acknowledgement_for_ac_query(fulltext_seeded_session):
    embedder = get_embedder()
    from sqlalchemy import select

    from app.models import PaperChunk

    chunks = list(fulltext_seeded_session.execute(select(PaperChunk)).scalars())
    embedder.fit([c.chunk_text for c in chunks])
    index = HybridIndex.from_session(fulltext_seeded_session, embedder)

    results = index.search(
        "Acceleration Consortium funding postdoctoral fellowship",
        section_types=["acknowledgements"],
        top_k=5,
    )
    assert results
    top = results[0]
    assert "acceleration consortium" in top.text.lower()


def test_section_filter_restricts_results(fulltext_seeded_session):
    embedder = get_embedder()
    from sqlalchemy import select

    from app.models import PaperChunk

    chunks = list(fulltext_seeded_session.execute(select(PaperChunk)).scalars())
    embedder.fit([c.chunk_text for c in chunks])
    index = HybridIndex.from_session(fulltext_seeded_session, embedder)

    results = index.search(
        "closed-loop Bayesian optimization",
        section_types=["methods"],
        top_k=5,
    )
    assert results
    assert all(r.section_type == "methods" for r in results)


def test_paper_filter(fulltext_seeded_session):
    embedder = get_embedder()
    from sqlalchemy import select

    from app.models import PaperChunk

    chunks = list(fulltext_seeded_session.execute(select(PaperChunk)).scalars())
    embedder.fit([c.chunk_text for c in chunks])
    index = HybridIndex.from_session(fulltext_seeded_session, embedder)

    results = index.search("self-driving lab", paper_ids=["P006"], top_k=10)
    assert results
    assert all(r.paper_id == "P006" for r in results)
