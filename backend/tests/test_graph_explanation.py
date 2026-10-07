from tests.admin_client import AdminTestClient as TestClient


def test_explanation_for_direct_ac_author(fulltext_seeded_session):
    from app.main import app
    from app.services.relevance_classifier import classify_all

    classify_all(fulltext_seeded_session)
    client = TestClient(app)
    r = client.get("/papers/P001/graph-explanation")
    assert r.status_code == 200
    body = r.json()
    assert "Alan Aspuru-Guzik" in body["direct_ac_authors"]
    assert "AC author" in body["summary"]


def test_explanation_for_second_degree(fulltext_seeded_session):
    from app.main import app
    from app.services.relevance_classifier import classify_all

    classify_all(fulltext_seeded_session)
    client = TestClient(app)
    r = client.get("/papers/P011/graph-explanation")
    assert r.status_code == 200
    body = r.json()
    assert body["direct_ac_authors"] == []
    assert body["second_degree_paths"]
    assert any("Jane Doe" in p["via_author_name"] for p in body["second_degree_paths"])


def test_explanation_for_citation_only(fulltext_seeded_session):
    from app.main import app
    from app.services.relevance_classifier import classify_all

    classify_all(fulltext_seeded_session)
    client = TestClient(app)
    r = client.get("/papers/P003/graph-explanation")
    assert r.status_code == 200
    body = r.json()
    assert body["citation_signals"]
    assert any("ChemOS" in s["cited_ac_core_title"] for s in body["citation_signals"])


def test_explanation_404_on_missing(fulltext_seeded_session):
    from app.main import app

    client = TestClient(app)
    r = client.get("/papers/NOPE/graph-explanation")
    assert r.status_code == 404
