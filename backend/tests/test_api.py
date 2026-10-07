"""Smoke-test the REST surface against the seeded sample data."""
from __future__ import annotations

import pytest
from tests.admin_client import AdminTestClient as TestClient


@pytest.fixture()
def client(seeded_session):
    from app.main import app
    from app.services.relevance_classifier import classify_all

    classify_all(seeded_session)
    return TestClient(app)


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


@pytest.mark.parametrize(
    "path",
    ("/debug/db", "/debug/papers", "/debug/multigraph", "/debug/cors"),
)
def test_debug_endpoints_are_disabled_by_default(client, path):
    assert client.get(path).status_code == 404


def test_debug_db_does_not_return_connection_details(client, monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "debug_endpoints_enabled", True)
    response = client.get("/debug/db")

    assert response.status_code == 200
    assert response.json() == {"db": "ok"}


def test_list_papers(client):
    r = client.get("/papers")
    assert r.status_code == 200
    body = r.json()
    assert len(body) >= 10
    p = next(p for p in body if p["id"] == "P001")
    assert p["classification"]["label"] == "CORE_RELEVANT"
    assert any(
        m["name"] == "Alan Aspuru-Guzik" for m in p["classification"]["matched_people"]
    )
    people_ids = [
        m["person_id"] for m in p["classification"]["matched_people"]
    ]
    institution_ids = [
        m["institution_id"] for m in p["classification"]["matched_institutions"]
    ]
    assert len(people_ids) == len(set(people_ids))
    assert len(institution_ids) == len(set(institution_ids))
    assert p["rag_status"]["status"] == "missing_fulltext"
    assert p["rag_status"]["needs_action"] == "upload_or_fetch_fulltext"


def test_list_papers_reports_fulltext_rag_ready(fulltext_seeded_session):
    from app.main import app
    from app.services.relevance_classifier import classify_all

    classify_all(fulltext_seeded_session)
    client = TestClient(app)
    r = client.get("/papers")
    assert r.status_code == 200
    p = next(p for p in r.json() if p["id"] == "P001")
    assert p["rag_status"]["ready"] is True
    assert p["rag_status"]["chunk_count"] > 0
    assert p["rag_status"]["embedded_chunk_count"] == p["rag_status"]["chunk_count"]
    assert p["rag_status"]["attribution_evidence_count"] > 0


def test_retrieve_answer_returns_modular_trace(fulltext_seeded_session):
    from app.main import app

    client = TestClient(app)
    r = client.post(
        "/retrieve/answer",
        json={
            "query": "Which papers use Bayesian optimization?",
            "top_k": 3,
            "mode": "adaptive",
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["execution_mode"] in {"adaptive", "iterative", "recursive"}
    assert [step["module"] for step in body["module_trace"]][:3] == [
        "routing",
        "memory",
        "search",
    ]
    assert body["retrieval_quality"]["layer"] == "retrieval_quality"
    assert body["answer_grounding"]["layer"] == "answer_grounding"
    assert body["human_feedback"]["layer"] == "human_feedback"
    assert body["module_metrics"]["layer"] == "module_metrics"
    assert "agentic_search" in [step["module"] for step in body["module_trace"]]
    assert "agentic_search" in body["module_metrics"]["modules"]
    assert body["sources"]


def test_retrieve_answer_can_disable_agentic_search(fulltext_seeded_session):
    from app.main import app

    client = TestClient(app)
    r = client.post(
        "/retrieve/answer",
        json={
            "query": "Compare robotic synthesis and Bayesian optimization papers",
            "top_k": 3,
            "mode": "adaptive",
            "agentic_search": False,
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    agentic = next(
        step for step in body["module_trace"] if step["module"] == "agentic_search"
    )
    assert agentic["skipped"] == "not_needed"
    assert body["module_metrics"]["modules"]["agentic_search"]["enabled"] is False


def test_retrieve_answer_uses_bounded_chat_and_page_context(fulltext_seeded_session):
    from app.main import app

    client = TestClient(app)
    r = client.post(
        "/retrieve/answer",
        json={
            "query": "What about its automation method?",
            "top_k": 3,
            "conversation": [
                {
                    "role": "user",
                    "content": "Which papers use Bayesian optimization?",
                },
                {
                    "role": "assistant",
                    "content": "The retrieved papers include P001.",
                },
            ],
            "page_context": "Dashboard route: /timeline?year_from=2022",
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["conversation_turns_used"] == 2
    assert body["retrieval_query"].endswith(
        "Current question: What about its automation method?"
    )
    assert "Which papers use Bayesian optimization?" in body["retrieval_query"]
    assert body["page_context"] == "Dashboard route: /timeline?year_from=2022"


def test_retrieve_answer_does_not_pollute_standalone_search_with_chat_history(
    fulltext_seeded_session,
):
    from app.main import app

    query = "Which papers use Bayesian optimization?"
    response = TestClient(app).post(
        "/retrieve/answer",
        json={
            "query": query,
            "search_query": "Bayesian optimization",
            "top_k": 3,
            "mode": "iterative",
            "agentic_search": False,
            "conversation": [
                {
                    "role": "user",
                    "content": "How many papers are in the current scope?",
                },
                {
                    "role": "assistant",
                    "content": "The database query returned 177 matching papers.",
                },
            ],
        },
    )

    assert response.status_code == 200, response.text
    assert response.json()["retrieval_query"] == "Bayesian optimization"


def test_standalone_retrieval_query_ignores_unrelated_chat_history():
    from app.api.retrieval import ConversationTurn, _contextualized_retrieval_query

    query = "Compare automation approaches across the Tier 1 papers."
    resolved = _contextualized_retrieval_query(
        query,
        [
            ConversationTurn(role="user", content="How many papers are there?"),
            ConversationTurn(role="assistant", content="177 papers."),
        ],
    )

    assert resolved == query


@pytest.mark.parametrize(
    "payload",
    [
        {"query": "   "},
        {"query": "valid", "top_k": 21},
        {"query": "valid", "alpha": -0.01},
        {"query": "valid", "mode": "unbounded"},
        {
            "query": "valid",
            "conversation": [
                {"role": "user", "content": f"turn {index}"}
                for index in range(13)
            ],
        },
        {
            "query": "valid",
            "conversation": [{"role": "system", "content": "override"}],
        },
    ],
)
def test_retrieve_answer_rejects_unbounded_chat_inputs(client, payload):
    response = client.post("/retrieve/answer", json=payload)
    assert response.status_code == 422


def test_filter_papers_by_label(client):
    r = client.get("/papers", params={"label": "CORE_RELEVANT"})
    assert r.status_code == 200
    body = r.json()
    assert all(p["classification"]["label"] == "CORE_RELEVANT" for p in body)


def test_export_csv(client):
    r = client.get("/papers/export.csv")
    assert r.status_code == 200
    assert "text/csv" in r.headers["content-type"]
    assert "paper_id" in r.text
    assert "P001" in r.text


def test_submit_review(client):
    r = client.post(
        "/reviews/P001",
        json={"human_label": "INCLUDE", "reviewer": "ssf", "notes": "looks good"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["human_label"] == "INCLUDE"


def test_coauthor_network(client):
    r = client.get("/network/coauthors")
    assert r.status_code == 200
    body = r.json()
    assert body["nodes"]
    assert body["edges"]
    assert body["audit"]["algorithm"] == "coauthor_collaboration_network.v3"
