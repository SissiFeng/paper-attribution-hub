"""Operator-only access to eight advisory workflows and their human labels."""
from __future__ import annotations

import hmac
import os
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.db import get_session
from app.models import Paper, PaperChunk
from app.services import jev_advisory_service as service


def operator(x_jev_key: str = Header(default='')):
    expected = os.environ.get('JEV_ADMIN_KEY', '')
    if not expected:
        raise HTTPException(503, 'Jev operator access has not been configured')
    if not hmac.compare_digest(expected, x_jev_key):
        raise HTTPException(401, 'Invalid operator credential')


router = APIRouter(prefix='/jev', tags=['jev-advice'], dependencies=[Depends(operator)])


class EvaluationIn(BaseModel):
    task: str = Field(max_length=40)
    paper_id: str | None = Field(default=None, max_length=200)
    other_paper_id: str | None = Field(default=None, max_length=200)
    chunk_id: str | None = Field(default=None, max_length=200)
    context: dict[str, Any] = Field(default_factory=dict)


class FeedbackIn(BaseModel):
    label: str = Field(min_length=1, max_length=50)
    reviewer: str = Field(min_length=1, max_length=100)


@router.get('/status')
def status():
    runtime = service.runtime()
    from paper_monitor import jev
    from paper_monitor.jev_ledger import cloud_config, limit
    try:
        if os.environ.get('JEV_CONFIG_PARAMETER'):
            cloud_config()
        cfg = jev.config()
        key_status = 'configured' if cfg['api_key'] else 'needs_configuration'
    except Exception:
        key_status = 'unavailable'
    return {'mode': 'shadow' if service.enabled() else 'off', 'key_status': key_status,
            'tasks': list(runtime.SPECS), 'daily_call_limit': limit(), 'automatic_actions': False}


def paper_or_404(session, paper_id):
    paper = session.get(Paper, paper_id) if paper_id else None
    if paper is None:
        raise HTTPException(404, 'Paper not found')
    return paper


@router.post('/evaluate')
def evaluate(payload: EvaluationIn, session: Annotated[Session, Depends(get_session)]):
    runtime = service.runtime()
    if payload.task not in runtime.SPECS:
        raise HTTPException(422, 'Unknown advisory task')
    context = payload.context
    if payload.task in ('reading_priority', 'analysis_route', 'review_priority'):
        return service.evaluate_paper(session, paper_or_404(session, payload.paper_id), payload.task)
    if payload.task == 'version_relation':
        left, right = paper_or_404(session, payload.paper_id), paper_or_404(session, payload.other_paper_id)
        if left.id == right.id or (left.doi and left.doi == right.doi):
            return {'task': payload.task, 'status': 'deterministic_identity', 'automatic_action': False}
        context = {'left': service.paper_state(left), 'right': service.paper_state(right)}
    if payload.task in ('answer_evidence', 'graph_relation'):
        paper = paper_or_404(session, payload.paper_id)
        chunk = session.get(PaperChunk, payload.chunk_id) if payload.chunk_id else None
        if chunk is None or chunk.paper_id != paper.id:
            raise HTTPException(422, 'Evidence chunk does not belong to the selected paper')
        # Source text, IDs and relation subject come from the database, never the request.
        context = {**context, 'source_text': chunk.chunk_text, 'source_id': chunk.id,
                   'paper_id': paper.id, 'source_kind': 'indexed_chunk', 'subject': paper.title}
    try:
        runtime.prepare(payload.task, context)
    except (ValueError, TypeError, AttributeError) as exc:
        raise HTTPException(422, 'Invalid advisory input or source quote') from exc
    return service.advise(payload.task, context)


@router.get('/decisions')
def decisions():
    service.runtime()
    from paper_monitor.jev_ledger import journal
    return {'mode': 'shadow', 'decisions': journal().recent(30)}


@router.post('/decisions/{decision_id}/feedback')
def feedback(decision_id: str, payload: FeedbackIn):
    runtime = service.runtime()
    from paper_monitor.jev_ledger import journal
    ledger = journal()
    entry = ledger.get(decision_id)
    if not entry or entry.get('status') != 'ok' or entry.get('task') not in runtime.SPECS:
        raise HTTPException(404, 'Decision not found')
    spec = runtime.question(entry['task'])
    allowed = {str(i) for i in range(len(spec['criteria']))} if spec['type'] == 'score' else set(spec['criteria'])
    if payload.label not in allowed:
        raise HTTPException(422, 'Label is not part of this decision contract')
    ledger.feedback(decision_id, payload.label, payload.reviewer)
    return {'saved': True, 'classification_changed': False, 'training_automatically_enabled': False}
