"""Archive grounded chat answers as review-gated wiki syntheses."""
from __future__ import annotations

import hashlib
import json
import uuid
from datetime import UTC, datetime

import yaml
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import ChatMessage, PaperChunk, WikiPage


SYNTHESIS_SCHEMA_VERSION = "pas-wiki-synthesis-v0.1"
SYNTHESIS_COMPILER_VERSION = "chat-synthesis-v0.1"


class WikiSynthesisNotFoundError(LookupError):
    pass


class WikiSynthesisValidationError(ValueError):
    pass


def _now() -> datetime:
    return datetime.now(UTC)


def _canonical_hash(value: object) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _preceding_question(session: Session, message: ChatMessage) -> str:
    question = session.scalar(
        select(ChatMessage.content)
        .where(
            ChatMessage.session_id == message.session_id,
            ChatMessage.role == "user",
            ChatMessage.ordinal < message.ordinal,
        )
        .order_by(ChatMessage.ordinal.desc())
        .limit(1)
    )
    return question or "Question not recorded."


def _source_requirements(message: ChatMessage) -> list[dict]:
    requirements: list[dict] = []
    seen: set[tuple[str, str]] = set()
    for source in message.sources or []:
        paper_id = str(source.get("paper_id") or "").strip()
        chunk_id = str(source.get("chunk_id") or "").strip()
        if not paper_id or not chunk_id or (paper_id, chunk_id) in seen:
            continue
        seen.add((paper_id, chunk_id))
        requirements.append(
            {
                "paper_id": paper_id,
                "chunk_id": chunk_id,
                "section_type": source.get("section_type"),
            }
        )
    return requirements


def _missing_source_requirements(
    session: Session,
    requirements: list[dict],
) -> list[dict]:
    chunk_ids = {
        str(requirement.get("chunk_id") or "")
        for requirement in requirements
        if requirement.get("chunk_id")
    }
    available = set(
        session.execute(
            select(PaperChunk.id, PaperChunk.paper_id).where(PaperChunk.id.in_(chunk_ids))
        ).all()
    ) if chunk_ids else set()
    return [
        requirement
        for requirement in requirements
        if (
            str(requirement.get("chunk_id") or ""),
            str(requirement.get("paper_id") or ""),
        )
        not in available
    ]


def _render_markdown(page: WikiPage) -> str:
    metadata = page.source_metadata or {}
    frontmatter = {
        "type": "synthesis",
        "name": page.title,
        "review_status": metadata.get("review_status", "draft"),
        "authority": metadata.get("authority", "draft_synthesis"),
        "generated": page.generated_at.date().isoformat(),
        "source_snapshot_hash": page.source_snapshot_hash,
        "chat_message_id": metadata.get("chat_message_id"),
    }
    lines = [
        "---",
        yaml.safe_dump(frontmatter, sort_keys=False, allow_unicode=True).rstrip(),
        "---",
        "",
        f"# {page.title}",
        "",
    ]
    for section in page.sections or []:
        lines.extend([f"## {section['heading']}", "", str(section["body"]), ""])
    return "\n".join(lines).rstrip() + "\n"


def _review_section(metadata: dict) -> dict:
    lines = [
        f"Status: {metadata.get('review_status', 'draft')}",
        f"Authority: {metadata.get('authority', 'draft_synthesis')}",
    ]
    if metadata.get("reviewer"):
        lines.append(f"Reviewer: {metadata['reviewer']}")
    if metadata.get("reviewed_at"):
        lines.append(f"Reviewed at: {metadata['reviewed_at']}")
    if metadata.get("review_note"):
        lines.append(f"Review note: {metadata['review_note']}")
    return {
        "key": "review_state",
        "heading": "Review State",
        "body": "\n".join(lines),
        "chips": [{"label": metadata.get("review_status", "draft"), "kind": "label"}],
    }


def archive_chat_synthesis(
    session: Session,
    *,
    chat_message_id: str,
    title: str | None = None,
) -> tuple[WikiPage, bool]:
    """Create one idempotent draft synthesis from a persisted assistant answer."""
    existing = session.scalar(
        select(WikiPage).where(
            WikiPage.entity_type == "synthesis",
            WikiPage.entity_id == chat_message_id,
        )
    )
    if existing is not None:
        return existing, False

    message = session.get(ChatMessage, chat_message_id)
    if message is None:
        raise WikiSynthesisNotFoundError(
            f"Chat message {chat_message_id!r} was not found"
        )
    if message.role != "assistant" or message.status != "complete":
        raise WikiSynthesisValidationError(
            "Only complete assistant messages can be archived as syntheses."
        )
    if message.answer_kind == "insufficient_evidence":
        raise WikiSynthesisValidationError(
            "An insufficient-evidence answer cannot be archived as knowledge."
        )

    question = _preceding_question(session, message)
    normalized_title = (title or question or "Archived synthesis").strip()[:240]
    requirements = _source_requirements(message)
    snapshot = {
        "chat_message_id": message.id,
        "chat_session_id": message.session_id,
        "question": question,
        "answer": message.content,
        "answer_kind": message.answer_kind,
        "model": message.model,
        "sources": message.sources or [],
        "audit": message.audit or {},
    }
    source_snapshot_hash = _canonical_hash(snapshot)
    metadata = {
        "schema_version": SYNTHESIS_SCHEMA_VERSION,
        "chat_message_id": message.id,
        "chat_session_id": message.session_id,
        "question": question,
        "answer_kind": message.answer_kind,
        "model": message.model,
        "citation_check": (message.audit or {}).get("citation_check"),
        "structured_read_only": (message.audit or {}).get("read_only") is True,
        "source_requirements": requirements,
        "source_snapshot_hash": source_snapshot_hash,
        "review_status": "draft",
        "authority": "draft_synthesis",
        "reviewer": None,
        "reviewed_at": None,
        "review_note": None,
    }
    source_lines = [
        f"[{index}] {source.get('paper_title') or source.get('paper_id')} — "
        f"paper {source.get('paper_id')}, chunk {source.get('chunk_id')}"
        for index, source in enumerate(message.sources or [], start=1)
    ] or ["No passage source was recorded; inspect the structured audit before review."]
    page = WikiPage(
        id=str(uuid.uuid4()),
        entity_type="synthesis",
        entity_id=message.id,
        title=normalized_title,
        sections=[
            {"key": "question", "heading": "Question", "body": question, "chips": []},
            {
                "key": "synthesis",
                "heading": "Synthesis",
                "body": message.content,
                "chips": [],
            },
            {
                "key": "source_requirements",
                "heading": "Required Source Evidence",
                "body": "\n".join(source_lines),
                "chips": [],
            },
            _review_section(metadata),
        ],
        content_md=None,
        model_version=SYNTHESIS_COMPILER_VERSION,
        prompt_version="archive-v0.1",
        generated_at=_now(),
        source_snapshot_hash=source_snapshot_hash,
        content_hash=None,
        source_metadata=metadata,
        compile_status="complete",
        compile_error=None,
        is_stale=False,
    )
    page.content_md = _render_markdown(page)
    page.content_hash = hashlib.sha256(page.content_md.encode("utf-8")).hexdigest()
    try:
        with session.begin_nested():
            session.add(page)
            session.flush()
    except IntegrityError:
        concurrent = session.scalar(
            select(WikiPage).where(
                WikiPage.entity_type == "synthesis",
                WikiPage.entity_id == chat_message_id,
            )
        )
        if concurrent is not None:
            return concurrent, False
        raise
    return page, True


def get_synthesis(session: Session, synthesis_id: str) -> WikiPage:
    page = session.get(WikiPage, synthesis_id)
    if page is None or page.entity_type != "synthesis":
        raise WikiSynthesisNotFoundError(
            f"Wiki synthesis {synthesis_id!r} was not found"
        )
    return page


def review_synthesis(
    session: Session,
    *,
    synthesis_id: str,
    status: str,
    reviewer: str,
    note: str | None = None,
) -> WikiPage:
    page = session.scalar(
        select(WikiPage)
        .where(WikiPage.id == synthesis_id, WikiPage.entity_type == "synthesis")
        .with_for_update()
    )
    if page is None:
        raise WikiSynthesisNotFoundError(
            f"Wiki synthesis {synthesis_id!r} was not found"
        )
    if status not in {"reviewed", "superseded"}:
        raise WikiSynthesisValidationError(
            "Review status must be 'reviewed' or 'superseded'."
        )
    normalized_reviewer = reviewer.strip()
    if not normalized_reviewer:
        raise WikiSynthesisValidationError("A reviewer is required.")

    metadata = dict(page.source_metadata or {})
    if status == "reviewed":
        grounded = (
            metadata.get("answer_kind") == "evidence_grounded"
            and metadata.get("citation_check") == "passed"
        )
        structured = (
            metadata.get("answer_kind") == "verified_structured"
            and metadata.get("structured_read_only") is True
        )
        if not (grounded or structured):
            raise WikiSynthesisValidationError(
                "Only a citation-grounded or verified structured answer can be reviewed as knowledge."
            )
        requirements = metadata.get("source_requirements") or []
        missing_requirements = _missing_source_requirements(session, requirements)
        if grounded and (not requirements or missing_requirements):
            raise WikiSynthesisValidationError(
                "The source evidence required by this synthesis is missing or no longer resolves."
            )
    reviewed_at = _now()
    review_note = note.strip() if note and note.strip() else None
    review_history = list(metadata.get("review_history") or [])
    review_history.append(
        {
            "status": status,
            "reviewer": normalized_reviewer,
            "reviewed_at": reviewed_at.isoformat(),
            "note": review_note,
        }
    )
    metadata.update(
        {
            "review_status": status,
            "authority": (
                "reviewed_synthesis" if status == "reviewed" else "superseded_synthesis"
            ),
            "reviewer": normalized_reviewer,
            "reviewed_at": reviewed_at.isoformat(),
            "review_note": review_note,
            "review_history": review_history,
        }
    )
    sections = [
        section for section in (page.sections or []) if section.get("key") != "review_state"
    ]
    sections.append(_review_section(metadata))
    page.sections = sections
    page.source_metadata = metadata
    page.generated_at = reviewed_at
    page.content_md = _render_markdown(page)
    page.content_hash = hashlib.sha256(page.content_md.encode("utf-8")).hexdigest()
    page.is_stale = False
    session.flush()
    return page
