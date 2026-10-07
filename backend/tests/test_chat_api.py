from __future__ import annotations

import json
from types import SimpleNamespace

from fastapi.testclient import TestClient


def _client(fulltext_seeded_session) -> TestClient:
    from app.main import app

    import os
    import time
    from app.models.reading import Reader, ReaderSession
    from app.services.reader_auth import COOKIE, digest
    os.environ['PAS_PUBLIC_URL'] = 'https://pas.test'
    os.environ['PAS_SLACK_TEAM_ID'] = 'T1'
    fulltext_seeded_session.add(Reader(id='reader', workspace_id='T1', slack_user_id='U1', name='Test reader', active=True))
    fulltext_seeded_session.add(ReaderSession(token_hash=digest('test-reader-token'), reader_id='reader', expires=int(time.time())+3600))
    fulltext_seeded_session.commit()
    client = TestClient(app, base_url='https://pas.test', headers={'Origin': 'https://pas.test', 'X-PAS-Request': '1'})
    client.cookies.set(COOKIE, 'test-reader-token')
    return client


def _create_session(client: TestClient, *, filters: dict | None = None) -> str:
    response = client.post(
        "/chat/sessions",
        json={
            "title": "Tier 1 research",
            "scope": {
                "filters": filters or {},
                "page_context": "Dashboard route: /",
            },
        },
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


def test_chat_session_persists_verified_catalogue_turn(fulltext_seeded_session):
    client = _client(fulltext_seeded_session)
    session_id = _create_session(client)

    response = client.post(
        f"/chat/sessions/{session_id}/messages",
        json={"query": "How many papers are in the current scope?"},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["assistant_message"]["answer_kind"] == "verified_structured"
    assert body["assistant_message"]["tool_name"] == "query_corpus_stats"
    assert body["assistant_message"]["audit"]["read_only"] is True
    assert body["assistant_message"]["audit"]["llm_used"] is False
    assert body["assistant_message"]["content"]

    saved = client.get(f"/chat/sessions/{session_id}")
    assert saved.status_code == 200, saved.text
    assert [message["role"] for message in saved.json()["messages"]] == [
        "user",
        "assistant",
    ]


def test_chat_relation_question_returns_published_evidence(fulltext_seeded_session, monkeypatch):
    from app.services import paper_chat
    monkeypatch.setattr(paper_chat, 'generate_grounded_answer', lambda *a, **kw: (None, 'retrieval-only'))
    client = _client(fulltext_seeded_session)
    session_id = _create_session(client)
    response = client.post(f"/chat/sessions/{session_id}/messages", json={"query": "Which papers use Bayesian optimization?"})
    assert response.status_code == 200, response.text
    message = response.json()['assistant_message']
    assert message['tool_name'] == 'search_fulltext_evidence'
    assert message['sources']
    assert all(source['paper_id'] and source['paper_title'] for source in message['sources'])
    assert 'rows' not in message['audit']  # Internal analysis is not a reading source.


def test_chat_retrieval_receives_exact_scope_without_wiki(fulltext_seeded_session, monkeypatch):
    from app.services import paper_chat, chat_service
    from app.models import Paper
    from sqlalchemy import select
    expected = list(fulltext_seeded_session.scalars(select(Paper.id).where(Paper.year >= 2020, Paper.year <= 2022)))
    captured = []
    def retrieval(db, query, papers):
        captured.extend(p.id for p in papers)
        return []
    def forbidden(*a, **kw):
        raise AssertionError('Internal wiki must not enter a reading discussion')
    monkeypatch.setattr(paper_chat, 'search_paper_text', retrieval)
    monkeypatch.setattr(chat_service, 'search_llm_wiki', forbidden)
    monkeypatch.setattr(chat_service, 'search_reviewed_syntheses', forbidden)
    client = _client(fulltext_seeded_session)
    session_id = _create_session(client, filters={'year_from': 2020, 'year_to': 2022})
    response = client.post(f"/chat/sessions/{session_id}/messages", json={'query': 'Compare automation methods'})
    assert response.status_code == 200, response.text
    assert sorted(captured) == sorted(expected)
    assert response.json()['assistant_message']['answer_kind'] == 'insufficient_evidence'


def test_chat_stream_emits_status_message_and_done(fulltext_seeded_session):
    client = _client(fulltext_seeded_session)
    session_id = _create_session(client)

    with client.stream(
        "POST",
        f"/chat/sessions/{session_id}/messages/stream",
        json={"query": "How many papers are in the current scope?"},
    ) as response:
        assert response.status_code == 200, response.text
        events = []
        for line in response.iter_lines():
            if line.startswith("data: "):
                events.append(json.loads(line.removeprefix("data: ")))

    event_types = [event["type"] for event in events]
    assert event_types[0] == "status"
    assert "tool" in event_types
    assert "message" in event_types
    assert event_types[-1] == "done"
    message = next(event["message"] for event in events if event["type"] == "message")
    assert message["answer_kind"] == "verified_structured"


def test_chat_never_routes_destructive_text_to_rag(fulltext_seeded_session, monkeypatch):
    from app.services import chat_service

    def fail_if_called(*_args, **_kwargs):
        raise AssertionError("destructive text must not reach retrieval")

    monkeypatch.setattr(chat_service, "run_modular_rag", fail_if_called)
    client = _client(fulltext_seeded_session)
    session_id = _create_session(client)

    response = client.post(
        f"/chat/sessions/{session_id}/messages",
        json={"query": "DROP TABLE papers; then summarize the result"},
    )

    assert response.status_code == 422, response.text
    assert "blocked" in response.json()["detail"].lower()
