from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import delete, or_, select
from sqlalchemy.orm import Session

from app.db import get_session
from app.models import ChatMessage, ChatSession
from app.models.reading import ChatParticipant, Reader
from app.models.research import ProjectDiscussion, ProjectMember, ResearchProject
from app.services.research_access import require_project
from app.services.reader_auth import current_reader, public_reader
from app.services.chat_access import checked_members, require_chat
from app.services.chat_service import (
    ChatBlockedError,
    ChatNotFoundError,
    create_chat_session,
    ensure_safe_query,
    list_chat_messages,
)
from app.services.filter_spec import PaperFilter
from app.services.paper_chat import reading_scope, run_reading_turn, POLICY
from app.services.access_control import is_admin


router = APIRouter(prefix="/chat", tags=["chat"])


class ChatScopeIn(BaseModel):
    filters: PaperFilter = Field(default_factory=PaperFilter)
    paper_ids: list[str] | None = Field(default=None, max_length=100)
    page_context: str | None = Field(default=None, max_length=1000)


class ChatSessionCreate(BaseModel):
    title: str | None = Field(default=None, max_length=160)
    scope: ChatScopeIn = Field(default_factory=ChatScopeIn)
    member_ids: list[str] = Field(default_factory=list, max_length=20)


class ChatTurnIn(BaseModel):
    query: str = Field(min_length=1, max_length=2000)
    scope: ChatScopeIn | None = None

    @field_validator("query")
    @classmethod
    def normalize_query(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("query must not be blank")
        return normalized


class ChatMessageOut(BaseModel):
    reader_id: str | None = None
    id: str
    ordinal: int
    role: str
    content: str
    status: str
    answer_kind: str | None
    model: str | None
    tool_name: str | None
    sources: list[dict[str, Any]]
    audit: dict[str, Any]
    scope: dict[str, Any]
    created_at: str


class ChatSessionOut(BaseModel):
    owner_id: str | None = None
    shared: bool = False
    project_id: str | None = None
    id: str
    title: str | None
    scope: dict[str, Any]
    created_at: str
    updated_at: str
    messages: list[ChatMessageOut] = Field(default_factory=list)


class ChatTurnOut(BaseModel):
    user_message: ChatMessageOut
    assistant_message: ChatMessageOut


def _message_out(message: ChatMessage) -> ChatMessageOut:
    return ChatMessageOut(
        id=message.id,
        reader_id=message.reader_id,
        ordinal=message.ordinal,
        role=message.role,
        content=message.content,
        status=message.status,
        answer_kind=message.answer_kind,
        model=message.model,
        tool_name=message.tool_name,
        sources=message.sources or [],
        audit=message.audit or {},
        scope=message.scope or {},
        created_at=message.created_at.isoformat(),
    )


def _session_out(chat: ChatSession, messages: list[ChatMessage] | None = None) -> ChatSessionOut:
    from sqlalchemy.orm import object_session
    db = object_session(chat)
    link = db.get(ProjectDiscussion, chat.id) if db else None
    return ChatSessionOut(
        project_id=link.project_id if link else None,
        id=chat.id,
        owner_id=chat.owner_id,
        shared=chat.shared,
        title=chat.title,
        scope=chat.scope or {},
        created_at=chat.created_at.isoformat(),
        updated_at=chat.updated_at.isoformat(),
        messages=[_message_out(message) for message in (messages or [])],
    )


def _not_found(error: ChatNotFoundError) -> HTTPException:
    return HTTPException(status_code=404, detail=str(error))


@router.post("/sessions", response_model=ChatSessionOut, status_code=201)
def create_session(payload: ChatSessionCreate, session: Session = Depends(get_session),
                   user: Reader = Depends(current_reader)):
    members = checked_members(session, payload.member_ids, user)
    try:
        scope = reading_scope(payload.scope.model_dump())
    except ChatBlockedError as error:
        raise HTTPException(422, str(error)) from error
    chat = create_chat_session(
        session,
        title=payload.title,
        scope=scope,
    )
    chat.scope = scope
    chat.owner_id, chat.workspace_id, chat.shared = user.id, user.workspace_id, bool(members)
    for member in members:
        session.add(ChatParticipant(session_id=chat.id, reader_id=member.id))
    session.commit()
    return _session_out(chat)


@router.get("/sessions/{session_id}", response_model=ChatSessionOut)
def get_session_detail(session_id: str, session: Session = Depends(get_session),
                       user: Reader = Depends(current_reader)):
    try:
        chat = require_chat(session, session_id, user)
        messages = list_chat_messages(session, session_id)
    except ChatNotFoundError as error:
        raise _not_found(error) from error
    return _session_out(chat, messages)


def _run_turn(session: Session, session_id: str, payload: ChatTurnIn, user: Reader, request: Request) -> ChatTurnOut:
    chat = require_chat(session, session_id, user, lock=True)
    if chat.shared and payload.scope is not None:
        raise HTTPException(422, "A shared discussion keeps its selected paper scope.")
    try:
        user_message, assistant_message = run_reading_turn(
            session,
            session_id=session_id,
            query=payload.query,
            scope_override=payload.scope.model_dump() if payload.scope else None,
        )
    except ChatNotFoundError as error:
        raise _not_found(error) from error
    except ChatBlockedError as error:
        session.rollback()
        raise HTTPException(status_code=422, detail=str(error)) from error
    session.flush()
    session.expire_all()
    current_reader(request, session)
    require_chat(session, session_id, user)
    user_message.reader_id = user.id
    session.commit()
    return ChatTurnOut(
        user_message=_message_out(user_message),
        assistant_message=_message_out(assistant_message),
    )


@router.post("/sessions/{session_id}/messages", response_model=ChatTurnOut)
def post_message(session_id: str, payload: ChatTurnIn, request: Request, session: Session = Depends(get_session),
                 user: Reader = Depends(current_reader)):
    return _run_turn(session, session_id, payload, user, request)


def _sse(payload: dict[str, Any]) -> str:
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


@router.post("/sessions/{session_id}/messages/stream")
def stream_message(session_id: str, payload: ChatTurnIn, request: Request, session: Session = Depends(get_session),
                   user: Reader = Depends(current_reader)):
    try:
        ensure_safe_query(payload.query)
        require_chat(session, session_id, user)
    except ChatNotFoundError as error:
        raise _not_found(error) from error
    except ChatBlockedError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error

    def events():
        yield _sse({"type": "status", "status": "reasoning"})
        try:
            session.expire_all()
            current_reader(request, session)
            result = _run_turn(session, session_id, payload, user, request)
            session.expire_all()
            current_reader(request, session)
            require_chat(session, session_id, user)
        except HTTPException as error:
            yield _sse({"type": "error", "detail": error.detail})
            return
        yield _sse(
            {
                "type": "tool",
                "tool_name": result.assistant_message.tool_name,
                "status": "complete",
            }
        )
        yield _sse(
            {
                "type": "message",
                "message": result.assistant_message.model_dump(),
            }
        )
        yield _sse({"type": "done", "session_id": session_id})

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get('/sessions', response_model=list[ChatSessionOut])
def my_sessions(session: Session = Depends(get_session), user: Reader = Depends(current_reader)):
    granted = select(ChatParticipant.session_id).where(ChatParticipant.reader_id == user.id)
    project_ids = select(ResearchProject.id).where(ResearchProject.workspace_id == user.workspace_id,
        or_(ResearchProject.owner_id == user.id, ResearchProject.id.in_(select(ProjectMember.project_id).where(ProjectMember.reader_id == user.id))))
    project_chats = select(ProjectDiscussion.session_id).where(ProjectDiscussion.project_id.in_(project_ids))
    all_project_chats = select(ProjectDiscussion.session_id)
    rows = session.scalars(select(ChatSession).where(ChatSession.workspace_id == user.workspace_id,
        or_(ChatSession.id.in_(project_chats),
            (~ChatSession.id.in_(all_project_chats)) & or_(ChatSession.owner_id == user.id, ChatSession.id.in_(granted)))).order_by(ChatSession.updated_at.desc()).limit(100))
    return [_session_out(row) for row in rows if row.scope.get('access_policy') == POLICY or is_admin(session, user)]


@router.get('/members')
def members(q: str = '', session: Session = Depends(get_session), user: Reader = Depends(current_reader)):
    if len(q) > 100:
        raise HTTPException(422, 'Search is too long.')
    rows = session.scalars(select(Reader).where(Reader.workspace_id == user.workspace_id,
        Reader.active.is_(True), Reader.id != user.id,
        Reader.name.icontains(q, autoescape=True)).order_by(Reader.name).limit(50))
    return [public_reader(row) for row in rows]


@router.get('/sessions/{session_id}/members')
def discussion_members(session_id: str, session: Session = Depends(get_session), user: Reader = Depends(current_reader)):
    chat = require_chat(session, session_id, user)
    link = session.get(ProjectDiscussion, session_id)
    if link:
        project = require_project(session, link.project_id, user)
        ids = select(ProjectMember.reader_id).where(ProjectMember.project_id == project.id)
        return [public_reader(row) for row in session.scalars(select(Reader).where(or_(Reader.id == project.owner_id, Reader.id.in_(ids))))]
    ids = select(ChatParticipant.reader_id).where(ChatParticipant.session_id == session_id)
    return [public_reader(row) for row in session.scalars(select(Reader).where(or_(Reader.id == chat.owner_id, Reader.id.in_(ids))))]


class ShareIn(BaseModel):
    title: str = Field(min_length=1, max_length=160)
    member_ids: list[str] = Field(min_length=1, max_length=20)
    message_ids: list[str] = Field(default_factory=list, max_length=40)


@router.post('/sessions/{session_id}/share', response_model=ChatSessionOut, status_code=201)
def share_selected(session_id: str, payload: ShareIn, session: Session = Depends(get_session), user: Reader = Depends(current_reader)):
    original = require_chat(session, session_id, user, owner_only=True, lock=True)
    if session.get(ProjectDiscussion, session_id):
        raise HTTPException(422, 'Project discussions use project membership and cannot be copied outside the project.')
    if original.scope.get('access_policy') != POLICY:
        raise HTTPException(403, 'Archived analysis discussions cannot be shared. Start a new reading discussion.')
    members = checked_members(session, payload.member_ids, user)
    if not members:
        raise HTTPException(422, 'Choose another registered member.')
    chosen = list(session.scalars(select(ChatMessage).where(ChatMessage.session_id == session_id,
        ChatMessage.id.in_(payload.message_ids)).order_by(ChatMessage.ordinal)))
    if len(chosen) != len(set(payload.message_ids)):
        raise HTTPException(422, 'Only messages from this discussion can be shared.')
    # Create a separate discussion; never widen access to the private original.
    shared_scope = {**original.scope, 'page_context': None}
    chat = ChatSession(id=str(uuid.uuid4()), title=payload.title.strip(), scope=shared_scope,
                       owner_id=user.id, workspace_id=user.workspace_id, shared=True)
    session.add(chat)
    session.flush()
    for member in members:
        session.add(ChatParticipant(session_id=chat.id, reader_id=member.id))
    for number, message in enumerate(chosen, 1):
        session.add(ChatMessage(id=str(uuid.uuid4()), session_id=chat.id, ordinal=number,
            reader_id=message.reader_id, role=message.role, content=message.content, status=message.status,
            answer_kind=message.answer_kind, model=message.model, tool_name=message.tool_name,
            sources=message.sources, audit={'shared_copy': True}, scope=shared_scope))
    session.commit()
    return _session_out(chat, list_chat_messages(session, chat.id))


class MembersIn(BaseModel):
    member_ids: list[str] = Field(max_length=20)


@router.put('/sessions/{session_id}/members')
def replace_members(session_id: str, payload: MembersIn, session: Session = Depends(get_session), user: Reader = Depends(current_reader)):
    chat = require_chat(session, session_id, user, owner_only=True, lock=True)
    if chat.scope.get('access_policy') != POLICY:
        raise HTTPException(403, 'Archived analysis discussions cannot gain new members.')
    if session.get(ProjectDiscussion, session_id):
        raise HTTPException(422, 'Manage access through the project membership.')
    if not chat.shared:
        raise HTTPException(422, 'Create a separate shared discussion to protect private history.')
    members = checked_members(session, payload.member_ids, user)
    session.execute(delete(ChatParticipant).where(ChatParticipant.session_id == session_id))
    for member in members:
        session.add(ChatParticipant(session_id=session_id, reader_id=member.id))
    session.commit()
    return discussion_members(session_id, session, user)


@router.post('/sessions/{session_id}/comments', response_model=ChatMessageOut, status_code=201)
def comment(session_id: str, payload: ChatTurnIn, session: Session = Depends(get_session), user: Reader = Depends(current_reader)):
    from app.services.chat_service import _next_ordinal
    chat = require_chat(session, session_id, user, lock=True)
    message = ChatMessage(id=str(uuid.uuid4()), session_id=session_id, ordinal=_next_ordinal(session, session_id),
        reader_id=user.id, role='user', content=payload.query, status='complete',
        sources=[], audit={'comment_only': True}, scope=chat.scope)
    session.add(message)
    chat.updated_at = datetime.now(UTC)
    session.commit()
    return _message_out(message)
