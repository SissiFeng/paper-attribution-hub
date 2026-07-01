from __future__ import annotations

from fastapi.testclient import TestClient


def test_nl_to_sql_counts_core_papers(seeded_session):
    from app.services.relevance_classifier import classify_all
    from app.services.nl_to_sql_service import run_nl_sql

    classify_all(seeded_session)

    result = run_nl_sql(
        seeded_session,
        "how many core papers are in the database?",
        use_llm=False,
    )

    assert result.plan.intent == "count_papers"
    assert "COUNT" in result.sql.upper()
    assert result.rows[0]["paper_count"] >= 1
    assert "CORE_RELEVANT" in result.sql


def test_nl_to_sql_lists_top_authors_for_related_papers(seeded_session):
    from app.services.relevance_classifier import classify_all
    from app.services.nl_to_sql_service import run_nl_sql

    classify_all(seeded_session)

    result = run_nl_sql(
        seeded_session,
        "top 5 authors for related papers",
        use_llm=False,
    )

    assert result.plan.intent == "top_authors"
    assert len(result.rows) <= 5
    assert result.rows
    assert {"author_id", "author", "paper_count"}.issubset(result.rows[0])


def test_nl_to_sql_endpoint_returns_plan(seeded_session):
    from app.main import app
    from app.services.relevance_classifier import classify_all

    classify_all(seeded_session)
    client = TestClient(app)

    r = client.get(
        "/retrieval/nl-sql",
        params={"q": "count papers by label", "use_llm": "false"},
    )

    assert r.status_code == 200, r.text
    body = r.json()
    assert body["intent"] == "count_papers"
    assert body["planner"] == "heuristic"
    assert "GROUP BY" in body["sql"].upper()
    assert body["rows"]
