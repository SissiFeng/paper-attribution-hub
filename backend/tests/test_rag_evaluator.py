from types import SimpleNamespace


def test_rag_evaluator_flags_weak_structured_evidence():
    from app.services.rag_evaluator import evaluate_retrieval

    result = evaluate_retrieval(
        "Which papers use Bayesian optimization?",
        [],
        proposition_hints=[],
    )

    assert result.query_type == "structured"
    assert result.should_retry is True
    assert result.evidence_score < 0.55
    assert any("No source" in msg for msg in result.missing_evidence)


def test_rag_evaluator_scores_grounded_sources():
    from app.services.rag_evaluator import evaluate_retrieval

    sources = [
        SimpleNamespace(score=0.2, bm25_score=1.0, cosine_score=0.4, graph_context="cites core"),
        SimpleNamespace(score=0.18, bm25_score=0.8, cosine_score=0.3, graph_context=None),
        SimpleNamespace(score=0.16, bm25_score=0.5, cosine_score=0.2, graph_context=None),
        SimpleNamespace(score=0.15, bm25_score=0.4, cosine_score=0.2, graph_context=None),
        SimpleNamespace(score=0.14, bm25_score=0.3, cosine_score=0.1, graph_context=None),
    ]

    result = evaluate_retrieval(
        "Summarize self-driving laboratory papers",
        sources,
        proposition_hints=[],
    )

    assert result.query_type == "fact"
    assert result.should_retry is False
    assert result.evidence_score >= 0.8


def test_record_feedback_persists(session):
    from app.models import RagFeedback
    from app.services.rag_evaluator import build_feedback_report, record_feedback

    row = record_feedback(
        session,
        query="test query",
        rating=1,
        failure_type="missing_source",
        source_chunk_ids=["chunk1"],
        source_paper_ids=["paper1"],
    )

    saved = session.get(RagFeedback, row.id)
    report = build_feedback_report(session)

    assert saved is not None
    assert report["total_feedback"] == 1
    assert report["low_rating_count"] == 1
    assert report["by_failure_type"]["missing_source"] == 1
