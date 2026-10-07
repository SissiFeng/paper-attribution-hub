"""Persistent, evidence-first chat orchestration for the PAS corpus."""
from __future__ import annotations

import os
import re
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import ChatMessage, ChatSession, Paper
from app.services.filter_spec import (
    PAPER_SET_ENCODING,
    PaperFilter,
    canonical_filter_payload,
    filter_fingerprint,
    filtered_paper_ids,
    paper_set_sha256,
)
from app.services.grounded_answer_service import (
    contextualized_retrieval_query,
    generate_grounded_answer,
)
from app.services.modular_rag_service import ModularRagRequest, run_modular_rag
from app.services.nl_to_sql_service import NlSqlUnsupportedError, run_nl_sql
# Wiki planning is optional in deployments that only contain the paper corpus.
def search_llm_wiki(*args):
    from app.services.llm_wiki_lifecycle import search_llm_wiki as search
    return search(*args)


def search_reviewed_syntheses(*args):
    from app.services.llm_wiki_lifecycle import search_reviewed_syntheses as search
    return search(*args)


def wiki_retrieval_context(*args):
    from app.services.llm_wiki_lifecycle import wiki_retrieval_context as context
    return context(*args)


class ChatNotFoundError(LookupError):
    pass


class ChatBlockedError(ValueError):
    pass


_BLOCKED_TEXT = re.compile(
    r"\b(?:drop|delete|insert|update|alter|create|truncate|attach|detach|"
    r"pragma|grant|revoke|execute|exec|union\s+select)\b",
    re.I,
)

_TOOL_NAMES = {
    "count_papers": "query_corpus_stats",
    "list_papers": "list_matching_papers",
    "top_authors": "rank_authors",
    "top_institutions": "rank_institutions",
    "top_propositions": "query_structured_evidence",
    "review_queue": "query_review_queue",
}


def ensure_safe_query(query: str) -> None:
    if _BLOCKED_TEXT.search(query):
        raise ChatBlockedError(
            "Blocked: raw SQL and write-oriented database requests are not allowed."
        )


def _now() -> datetime:
    return datetime.now(UTC)


def _scope_payload(scope: dict[str, Any] | None) -> dict[str, Any]:
    raw = scope or {}
    filters = PaperFilter.model_validate(raw.get("filters") or {})
    paper_ids = raw.get("paper_ids")
    if paper_ids is not None:
        paper_ids = list(dict.fromkeys(str(value).strip() for value in paper_ids if str(value).strip()))
    page_context = raw.get("page_context")
    return {
        "filters": canonical_filter_payload(filters),
        "paper_ids": paper_ids,
        "page_context": page_context,
    }


def create_chat_session(
    session: Session,
    *,
    title: str | None,
    scope: dict[str, Any] | None,
) -> ChatSession:
    chat = ChatSession(
        id=str(uuid.uuid4()),
        title=title.strip() if title and title.strip() else None,
        scope=_scope_payload(scope),
    )
    session.add(chat)
    session.commit()
    session.refresh(chat)
    return chat


def get_chat_session(session: Session, session_id: str) -> ChatSession:
    chat = session.get(ChatSession, session_id)
    if chat is None:
        raise ChatNotFoundError(f"Chat session {session_id!r} was not found")
    return chat


def list_chat_messages(session: Session, session_id: str) -> list[ChatMessage]:
    get_chat_session(session, session_id)
    return list(
        session.execute(
            select(ChatMessage)
            .where(ChatMessage.session_id == session_id)
            .order_by(ChatMessage.ordinal, ChatMessage.created_at)
        ).scalars()
    )


def _next_ordinal(session: Session, session_id: str) -> int:
    current = session.scalar(
        select(func.max(ChatMessage.ordinal)).where(ChatMessage.session_id == session_id)
    )
    return int(current or 0) + 1


def _add_message(
    session: Session,
    *,
    chat: ChatSession,
    role: str,
    content: str,
    answer_kind: str | None = None,
    model: str | None = None,
    tool_name: str | None = None,
    sources: list[dict[str, Any]] | None = None,
    audit: dict[str, Any] | None = None,
    scope: dict[str, Any] | None = None,
) -> ChatMessage:
    message = ChatMessage(
        id=str(uuid.uuid4()),
        session_id=chat.id,
        ordinal=_next_ordinal(session, chat.id),
        role=role,
        content=content,
        answer_kind=answer_kind,
        model=model,
        tool_name=tool_name,
        sources=sources or [],
        audit=audit or {},
        scope=scope or {},
    )
    session.add(message)
    session.flush()
    return message


def _resolved_scope(
    session: Session,
    raw_scope: dict[str, Any],
) -> tuple[PaperFilter, list[str], dict[str, Any]]:
    filters = PaperFilter.model_validate(raw_scope.get("filters") or {})
    filtered_ids = filtered_paper_ids(session, filters)
    selected_ids = raw_scope.get("paper_ids")
    if selected_ids is not None:
        allowed = set(filtered_ids)
        resolved_ids = [paper_id for paper_id in selected_ids if paper_id in allowed]
    else:
        resolved_ids = filtered_ids
    resolved = {
        "filters": canonical_filter_payload(filters),
        "filter_fingerprint": filter_fingerprint(filters),
        "paper_count": len(set(resolved_ids)),
        "paper_set_sha256": paper_set_sha256(resolved_ids),
        "paper_set_encoding": PAPER_SET_ENCODING,
        "page_context": raw_scope.get("page_context"),
    }
    return filters, resolved_ids, resolved


def _conversation(session: Session, session_id: str) -> list[Any]:
    messages = list_chat_messages(session, session_id)[-12:]
    return [
        {"role": message.role, "content": message.content}
        for message in messages
        if message.role in {"user", "assistant"}
    ]


def _has_valid_citations(answer: str, source_count: int) -> bool:
    if source_count <= 0:
        return False
    citations = [int(value) for value in re.findall(r"\[(\d+)\]", answer)]
    return bool(citations) and all(1 <= value <= source_count for value in citations)


def _enrich_sources(session: Session, sources: list[dict[str, Any]]) -> list[dict[str, Any]]:
    paper_ids = list({source["paper_id"] for source in sources if source.get("paper_id")})
    titles = dict(
        session.execute(select(Paper.id, Paper.title).where(Paper.id.in_(paper_ids))).all()
    ) if paper_ids else {}
    return [
        {
            **source,
            "paper_title": titles.get(source.get("paper_id")),
        }
        for source in sources
    ]


def run_chat_turn(
    session: Session,
    *,
    session_id: str,
    query: str,
    scope_override: dict[str, Any] | None = None,
) -> tuple[ChatMessage, ChatMessage]:
    normalized_query = query.strip()
    ensure_safe_query(normalized_query)
    chat = get_chat_session(session, session_id)
    active_scope = _scope_payload(scope_override) if scope_override is not None else chat.scope
    filters, paper_ids, resolved_scope = _resolved_scope(session, active_scope)
    prior_turns = _conversation(session, session_id)

    user_message = _add_message(
        session,
        chat=chat,
        role="user",
        content=normalized_query,
        scope=resolved_scope,
    )

    try:
        sql_result = run_nl_sql(
            session,
            normalized_query,
            base_filter=filters,
            paper_ids=paper_ids,
        )
    except NlSqlUnsupportedError:
        sql_result = None

    if sql_result is not None:
        audit = {
            **sql_result.audit,
            "sql": sql_result.sql,
            "parameters": sql_result.parameters,
            "rows": sql_result.rows,
        }
        assistant_message = _add_message(
            session,
            chat=chat,
            role="assistant",
            content=sql_result.summary,
            answer_kind="verified_structured",
            model="deterministic-text-to-sql",
            tool_name=_TOOL_NAMES[sql_result.plan.intent],
            audit=audit,
            scope=resolved_scope,
        )
    else:
        retrieval_query = contextualized_retrieval_query(normalized_query, prior_turns)
        wiki_hits = [
            *search_reviewed_syntheses(session, normalized_query),
            *search_llm_wiki(normalized_query),
        ] if os.environ.get("PAS_CHAT_WIKI_PLANNING", "1") == "1" else []
        wiki_hits = sorted(
            {hit.path: hit for hit in wiki_hits}.values(),
            key=lambda hit: (-hit.score, hit.path),
        )[:4]
        wiki_context = wiki_retrieval_context(wiki_hits) if wiki_hits else ""
        if wiki_context:
            retrieval_query = f"{retrieval_query}\n\n{wiki_context}"
        result = run_modular_rag(
            session,
            ModularRagRequest(
                query=retrieval_query,
                paper_ids=paper_ids,
                mode="adaptive",
                top_k=8,
                max_chunks=None,
                agentic_search=True,
            ),
            answer_fn=lambda _request_query, context: generate_grounded_answer(
                normalized_query,
                context,
                conversation=prior_turns,
                page_context=active_scope.get("page_context"),
            ),
        )
        sources = _enrich_sources(session, result.sources)
        if not sources:
            answer_kind = "insufficient_evidence"
        elif result.model == "retrieval-only":
            answer_kind = "partial_evidence"
        elif _has_valid_citations(result.answer, len(sources)):
            answer_kind = "evidence_grounded"
        else:
            answer_kind = "partial_evidence"
        assessment = result.assessment
        audit = {
            "read_only": True,
            "llm_used": result.model not in {"retrieval-only", "provider-error"},
            "query_type": assessment.query_type if assessment else "fact",
            "missing_evidence": assessment.missing_evidence if assessment else [],
            "execution_mode": result.mode,
            "chunks_retrieved": result.chunks_retrieved,
            "module_trace": result.module_trace,
            "citation_check": "passed" if answer_kind == "evidence_grounded" else "not_verified",
            "answer_grounding": getattr(assessment, "answer_grounding", {}) if assessment else {},
            "requires_judge": bool(
                assessment and getattr(assessment, "answer_grounding", {}).get("requires_judge")
            ),
            "wiki_retrieval": {
                "used_for_planning": bool(wiki_hits),
                "answer_authority": False,
                "hits": [hit.audit_dict() for hit in wiki_hits],
            },
        }
        assistant_message = _add_message(
            session,
            chat=chat,
            role="assistant",
            content=result.answer,
            answer_kind=answer_kind,
            model=result.model,
            tool_name="search_fulltext_evidence",
            sources=sources,
            audit=audit,
            scope=resolved_scope,
        )

    if chat.title is None:
        chat.title = normalized_query[:80]
    chat.scope = active_scope
    chat.updated_at = _now()
    session.commit()
    session.refresh(user_message)
    session.refresh(assistant_message)
    return user_message, assistant_message
