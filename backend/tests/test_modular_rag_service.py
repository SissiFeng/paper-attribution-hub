import pytest

from app.services.modular_rag_service import (
    ModularRagRequest,
    build_langgraph_app,
    run_modular_rag,
)


def _no_llm_answer(query: str, context: str):
    return None, "retrieval-only"


def test_modular_rag_runs_core_modules(fulltext_seeded_session):
    result = run_modular_rag(
        fulltext_seeded_session,
        ModularRagRequest(
            query="Which papers use Bayesian optimization?",
            top_k=5,
            mode="adaptive",
        ),
        answer_fn=_no_llm_answer,
    )

    modules = [step["module"] for step in result.module_trace]
    assert modules[:3] == ["routing", "memory", "search"]
    assert "agentic_search" in modules
    assert "fusion" in modules
    assert "predict" in modules
    assert modules[-1] == "demonstrate"
    assert result.mode == "adaptive"
    assert result.sources
    assert result.assessment is not None
    assert result.assessment.retrieval_quality["layer"] == "retrieval_quality"
    assert result.assessment.answer_grounding["layer"] == "answer_grounding"
    assert result.assessment.module_metrics["layer"] == "module_metrics"
    assert result.model == "retrieval-only"


def test_agentic_search_expands_exploratory_queries(fulltext_seeded_session):
    result = run_modular_rag(
        fulltext_seeded_session,
        ModularRagRequest(
            query="Compare papers using robotic synthesis versus Bayesian optimization",
            top_k=5,
            mode="adaptive",
        ),
        answer_fn=_no_llm_answer,
    )

    agentic = next(
        step for step in result.module_trace if step["module"] == "agentic_search"
    )
    assert agentic["generated_queries"] > 0
    assert agentic["expanded_candidates"] > 0
    assert result.assessment is not None
    metrics = result.assessment.module_metrics["modules"]["agentic_search"]
    assert metrics["enabled"] is True
    assert metrics["generated_queries"] == agentic["generated_queries"]


def test_agentic_search_can_be_disabled(fulltext_seeded_session):
    result = run_modular_rag(
        fulltext_seeded_session,
        ModularRagRequest(
            query="Compare papers using robotic synthesis versus Bayesian optimization",
            top_k=5,
            mode="adaptive",
            agentic_search=False,
        ),
        answer_fn=_no_llm_answer,
    )

    agentic = next(
        step for step in result.module_trace if step["module"] == "agentic_search"
    )
    assert agentic["skipped"] == "not_needed"
    assert result.assessment is not None
    metrics = result.assessment.module_metrics["modules"]["agentic_search"]
    assert metrics["enabled"] is False


def test_modular_rag_routes_comparison_to_recursive(fulltext_seeded_session):
    result = run_modular_rag(
        fulltext_seeded_session,
        ModularRagRequest(
            query="Compare papers using robotic synthesis versus Bayesian optimization",
            top_k=5,
            mode="adaptive",
        ),
        answer_fn=_no_llm_answer,
    )

    routing = next(step for step in result.module_trace if step["module"] == "routing")
    search = next(step for step in result.module_trace if step["module"] == "search")
    assert routing["query_type"] == "comparison"
    assert result.mode == "recursive"
    assert search["queries"] > 1


def test_modular_rag_accepts_forced_iterative_mode(fulltext_seeded_session):
    result = run_modular_rag(
        fulltext_seeded_session,
        ModularRagRequest(
            query="Summarize self-driving laboratory papers",
            top_k=3,
            mode="iterative",
        ),
        answer_fn=_no_llm_answer,
    )

    assert result.mode == "iterative"
    assert len(result.sources) <= 3


def test_langgraph_adapter_requires_bound_nodes():
    with pytest.raises(ValueError, match="must be provided"):
        build_langgraph_app()
