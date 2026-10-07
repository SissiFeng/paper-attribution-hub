from __future__ import annotations

from tests.admin_client import AdminTestClient as TestClient


def _seed_chat_answer(
    session,
    *,
    message_id: str,
    answer_kind: str = "evidence_grounded",
    citation_check: str = "passed",
    read_only: bool = True,
):
    from app.models import ChatMessage, ChatSession, Paper, PaperChunk

    paper = Paper(id=f"paper-{message_id}", title="Bridge experiment evidence")
    session.add(paper)
    chunk = PaperChunk(
        id=f"chunk-{message_id}",
        paper_id=paper.id,
        section_type="results",
        chunk_text="A bridge experiment connected the two synthesis routes.",
        indexed_text="Results: A bridge experiment connected the two synthesis routes.",
        char_start=0,
        char_end=59,
        token_count=9,
    )
    session.add(chunk)
    chat = ChatSession(id=f"chat-{message_id}", title="Bridge experiments", scope={})
    session.add(chat)
    session.add(
        ChatMessage(
            id=f"question-{message_id}",
            session_id=chat.id,
            ordinal=1,
            role="user",
            content="What evidence supports a bridge experiment?",
            scope={},
        )
    )
    answer = ChatMessage(
        id=message_id,
        session_id=chat.id,
        ordinal=2,
        role="assistant",
        content="The indexed result describes a cross-route bridge experiment [1].",
        answer_kind=answer_kind,
        model="test-provider",
        tool_name="search_fulltext_evidence",
        sources=[
            {
                "paper_id": paper.id,
                "paper_title": paper.title,
                "chunk_id": chunk.id,
                "section_type": "results",
                "text": chunk.chunk_text,
                "score": 0.92,
            }
        ],
        audit={"citation_check": citation_check, "read_only": read_only},
        scope={},
    )
    session.add(answer)
    session.commit()
    return answer


def test_chat_answer_archives_as_draft_and_requires_explicit_review(session):
    from app.main import app
    from app.services.llm_wiki_lifecycle import search_reviewed_syntheses

    answer = _seed_chat_answer(session, message_id="archive-answer")
    client = TestClient(app)

    archived = client.post(
        "/wiki/syntheses",
        json={"chat_message_id": answer.id, "title": "Cross-route bridge evidence"},
    )

    assert archived.status_code == 201, archived.text
    draft = archived.json()
    assert draft["review_status"] == "draft"
    assert draft["authority"] == "draft_synthesis"
    assert draft["source_metadata"]["chat_message_id"] == answer.id
    assert draft["source_metadata"]["source_requirements"] == [
        {
            "paper_id": "paper-archive-answer",
            "chunk_id": "chunk-archive-answer",
            "section_type": "results",
        }
    ]
    review_queue = client.get("/wiki/syntheses?review_status=draft")
    assert review_queue.status_code == 200, review_queue.text
    assert [item["id"] for item in review_queue.json()] == [draft["id"]]
    assert search_reviewed_syntheses(
        session, "cross-route bridge", limit=5
    ) == []

    reviewed = client.post(
        f"/wiki/syntheses/{draft['id']}/review",
        json={"status": "reviewed", "reviewer": "Evidence curator"},
    )

    assert reviewed.status_code == 200, reviewed.text
    approved = reviewed.json()
    assert approved["review_status"] == "reviewed"
    assert approved["authority"] == "reviewed_synthesis"
    assert approved["source_metadata"]["review_history"][0]["reviewer"] == (
        "Evidence curator"
    )
    assert client.get("/wiki/syntheses?review_status=draft").json() == []
    hits = search_reviewed_syntheses(session, "cross-route bridge", limit=5)
    assert hits[0].path == f"pas://wiki/syntheses/{draft['id']}"

    repeated = client.post(
        "/wiki/syntheses",
        json={"chat_message_id": answer.id, "title": "Ignored duplicate title"},
    )
    assert repeated.status_code == 200, repeated.text
    assert repeated.json()["id"] == draft["id"]
    assert repeated.json()["review_status"] == "reviewed"


def test_partial_answer_cannot_be_promoted_to_reviewed_synthesis(session):
    from app.main import app

    answer = _seed_chat_answer(
        session,
        message_id="partial-answer",
        answer_kind="partial_evidence",
        citation_check="not_verified",
    )
    client = TestClient(app)
    archived = client.post(
        "/wiki/syntheses",
        json={"chat_message_id": answer.id},
    )
    assert archived.status_code == 201, archived.text

    response = client.post(
        f"/wiki/syntheses/{archived.json()['id']}/review",
        json={"status": "reviewed", "reviewer": "Evidence curator"},
    )

    assert response.status_code == 409, response.text
    assert "citation-grounded or verified structured" in response.json()["detail"]


def test_review_fails_closed_when_required_source_chunk_is_missing(session):
    from app.main import app
    from app.models import PaperChunk

    answer = _seed_chat_answer(session, message_id="missing-source-answer")
    client = TestClient(app)
    archived = client.post(
        "/wiki/syntheses",
        json={"chat_message_id": answer.id},
    )
    assert archived.status_code == 201, archived.text

    chunk = session.get(PaperChunk, "chunk-missing-source-answer")
    session.delete(chunk)
    session.commit()
    response = client.post(
        f"/wiki/syntheses/{archived.json()['id']}/review",
        json={"status": "reviewed", "reviewer": "Evidence curator"},
    )

    assert response.status_code == 409, response.text
    assert "source evidence" in response.json()["detail"]


def test_synthesis_mutations_follow_the_configured_api_key_policy(session, monkeypatch):
    from app.config import settings
    from app.main import app

    answer = _seed_chat_answer(session, message_id="protected-answer")
    monkeypatch.setattr(settings, "api_key", "test-key")
    client = TestClient(app)

    denied = client.post(
        "/wiki/syntheses",
        json={"chat_message_id": answer.id},
    )
    allowed = client.post(
        "/wiki/syntheses",
        headers={"X-API-Key": "test-key"},
        json={"chat_message_id": answer.id},
    )

    assert denied.status_code == 401
    assert allowed.status_code == 201, allowed.text


def test_verified_structured_synthesis_requires_a_read_only_audit(session):
    from app.main import app

    safe = _seed_chat_answer(
        session,
        message_id="safe-structured-answer",
        answer_kind="verified_structured",
        citation_check="not_applicable",
    )
    unsafe = _seed_chat_answer(
        session,
        message_id="unsafe-structured-answer",
        answer_kind="verified_structured",
        citation_check="not_applicable",
        read_only=False,
    )
    client = TestClient(app)

    safe_draft = client.post(
        "/wiki/syntheses",
        json={"chat_message_id": safe.id},
    ).json()
    unsafe_draft = client.post(
        "/wiki/syntheses",
        json={"chat_message_id": unsafe.id},
    ).json()
    safe_review = client.post(
        f"/wiki/syntheses/{safe_draft['id']}/review",
        json={"status": "reviewed", "reviewer": "Evidence curator"},
    )
    unsafe_review = client.post(
        f"/wiki/syntheses/{unsafe_draft['id']}/review",
        json={"status": "reviewed", "reviewer": "Evidence curator"},
    )

    assert safe_review.status_code == 200, safe_review.text
    assert unsafe_review.status_code == 409, unsafe_review.text
