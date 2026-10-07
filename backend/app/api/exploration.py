"""P2 research tools, authorized against project membership on every request."""
import time
import uuid
from datetime import UTC, datetime
from typing import Literal
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.db import get_session
from app.models import Paper
from app.models.reading import Reader
from app.models.research import ProjectPaper
from app.models.exploration import (ResearchConnection, ResearchWatch, ResearchScreening,
    ResearchAlert, ResearchAlertReceipt)
from app.services.reader_auth import current_reader
from app.services.research_access import require_project
from app.services.reading_evidence import AnchorIn, check_anchor
from app.services.research_exploration import brief, project_map, related, scan_project

router = APIRouter(prefix='/research/projects/{project_id}/exploration', tags=['research exploration'])


def clean_terms(values):
    values = list(dict.fromkeys(v.strip().casefold() for v in values if v.strip()))
    if len(values) > 12 or any(len(v) < 3 or len(v) > 100 for v in values):
        raise ValueError('Use up to 12 keywords or phrases, each 3–100 characters.')
    return values


def watch_out(row):
    if not row:
        return {'terms': [], 'criteria': '', 'enabled': False, 'since': None, 'checked_at': None, 'version': 0}
    return {k: getattr(row, k) for k in ('terms', 'criteria', 'enabled', 'since', 'checked_at', 'version')}


def screening_out(row):
    return {k: getattr(row, k) for k in ('paper_id', 'reader_id', 'decision', 'reason', 'updated_at', 'version')}


@router.get('')
def exploration(project_id: str, db: Session = Depends(get_session), user: Reader = Depends(current_reader)):
    require_project(db, project_id, user)
    alerts = list(db.scalars(select(ResearchAlert).where(ResearchAlert.project_id == project_id).order_by(ResearchAlert.created_at.desc(), ResearchAlert.paper_id).limit(201)))
    seen = set(db.scalars(select(ResearchAlertReceipt.paper_id).where(ResearchAlertReceipt.project_id == project_id, ResearchAlertReceipt.reader_id == user.id)))
    decisions = list(db.scalars(select(ResearchScreening).where(ResearchScreening.project_id == project_id).order_by(ResearchScreening.updated_at.desc()).limit(1001)))
    result = {'map': project_map(db, project_id), 'watch': watch_out(db.get(ResearchWatch, project_id)),
        'screenings': [screening_out(r) | {'paper': brief(db.get(Paper, r.paper_id))} for r in decisions[:1000]], 'screenings_truncated': len(decisions) > 1000,
        'alerts': [{'paper': brief(db.get(Paper, r.paper_id)), 'matched_terms': r.matches, 'created_at': r.created_at,
            'seen': r.paper_id in seen} for r in alerts[:200]], 'alerts_truncated': len(alerts) > 200}
    # Recheck after assembling source evidence; do not rely on a cached grant.
    db.expire_all(); require_project(db, project_id, user)
    return result


@router.get('/related')
def related_work(project_id: str, q: str = Query(default='', max_length=1200), db: Session = Depends(get_session), user: Reader = Depends(current_reader)):
    require_project(db, project_id, user)
    try:
        terms = clean_terms(q.split(','))
    except ValueError as exc:
        raise HTTPException(422, str(exc))
    return related(db, project_id, terms)


class WatchIn(BaseModel):
    terms: list[str] = Field(max_length=12)
    criteria: str = Field(default='', max_length=3000)
    enabled: bool
    version: int = Field(ge=0)

    @field_validator('terms')
    @classmethod
    def valid_terms(cls, values):
        return clean_terms(values)


@router.put('/watch')
def configure_watch(project_id: str, payload: WatchIn, db: Session = Depends(get_session), user: Reader = Depends(current_reader)):
    require_project(db, project_id, user, owner=True, lock=True)
    row = db.get(ResearchWatch, project_id, populate_existing=True)
    if payload.version != (row.version if row else 0):
        raise HTTPException(409, 'Project settings changed. Reload before saving.')
    if payload.enabled and not payload.terms:
        raise HTTPException(422, 'Add at least one phrase before enabling alerts.')
    now = datetime.now(UTC)
    if not row:
        row = ResearchWatch(project_id=project_id, since=now, version=0)
        db.add(row)
    if not row.enabled or row.terms != payload.terms:
        row.since = now; row.checked_at = None
    row.terms = payload.terms; row.criteria = payload.criteria; row.enabled = payload.enabled
    row.version += 1
    db.commit()
    return watch_out(row)


@router.post('/check')
def check_updates(project_id: str, db: Session = Depends(get_session), user: Reader = Depends(current_reader)):
    require_project(db, project_id, user, lock=True)
    count = scan_project(db, project_id)
    db.commit()
    return {'new_alerts': count}


@router.post('/alerts/{paper_id}/seen')
def mark_seen(project_id: str, paper_id: str, db: Session = Depends(get_session), user: Reader = Depends(current_reader)):
    require_project(db, project_id, user, lock=True)
    if not db.get(ResearchAlert, (project_id, paper_id)):
        raise HTTPException(404, 'Project alert not found.')
    if not db.get(ResearchAlertReceipt, (project_id, paper_id, user.id)):
        db.add(ResearchAlertReceipt(project_id=project_id, paper_id=paper_id, reader_id=user.id, seen_at=int(time.time())))
    db.commit()
    return {'seen': True}


class ScreeningIn(BaseModel):
    decision: Literal['include', 'exclude', 'undecided']
    reason: str = Field(max_length=3000)
    version: int = Field(ge=0)


@router.put('/screening/{paper_id}')
def screen(project_id: str, paper_id: str, payload: ScreeningIn, db: Session = Depends(get_session), user: Reader = Depends(current_reader)):
    from app.api.catalog import published
    require_project(db, project_id, user, lock=True)
    if not db.get(ProjectPaper, (project_id, paper_id)) and not db.scalar(select(Paper.id).where(Paper.id == paper_id, published())):
        raise HTTPException(404, 'Paper not available for screening.')
    if payload.decision != 'undecided' and not payload.reason.strip():
        raise HTTPException(422, 'Record a reason for inclusion or exclusion.')
    row = db.get(ResearchScreening, (project_id, paper_id, user.id), populate_existing=True)
    if payload.version != (row.version if row else 0):
        raise HTTPException(409, 'Your screening decision changed. Reload before saving.')
    if not row:
        row = ResearchScreening(project_id=project_id, paper_id=paper_id, reader_id=user.id, version=0)
        db.add(row)
    row.decision = payload.decision; row.reason = payload.reason.strip(); row.version += 1; row.updated_at = int(time.time())
    db.commit()
    return screening_out(row)


class ConnectionEvidence(AnchorIn):
    paper_id: str = Field(max_length=200)


class ConnectionIn(BaseModel):
    source_id: str = Field(max_length=200)
    target_id: str = Field(max_length=200)
    relation: Literal['complements', 'contrasts', 'method_transfer']
    rationale: str = Field(min_length=1, max_length=3000)
    evidence: list[ConnectionEvidence] = Field(default_factory=list, max_length=2)


@router.post('/connections', status_code=201)
def connect(project_id: str, payload: ConnectionIn, db: Session = Depends(get_session), user: Reader = Depends(current_reader)):
    require_project(db, project_id, user, lock=True)
    if payload.source_id == payload.target_id or not payload.rationale.strip():
        raise HTTPException(422, 'Choose two different papers and explain the hypothesis.')
    ids = {payload.source_id, payload.target_id}
    if any(not db.get(ProjectPaper, (project_id, pid)) for pid in ids):
        raise HTTPException(422, 'Both papers must belong to this project.')
    if any(a.paper_id not in ids for a in payload.evidence):
        raise HTTPException(422, 'Evidence must come from the connected papers.')
    anchors = [check_anchor(db, a.paper_id, a) for a in payload.evidence]
    row = ResearchConnection(id=str(uuid.uuid4()), project_id=project_id, owner_id=user.id,
        source_id=payload.source_id, target_id=payload.target_id, relation=payload.relation,
        rationale=payload.rationale.strip(), evidence=anchors, created_at=int(time.time()))
    db.add(row); db.commit()
    return {'id': row.id, 'kind': 'hypothesis'}


@router.delete('/connections/{connection_id}')
def remove_connection(project_id: str, connection_id: str, db: Session = Depends(get_session), user: Reader = Depends(current_reader)):
    require_project(db, project_id, user, lock=True)
    row = db.get(ResearchConnection, connection_id)
    if not row or row.project_id != project_id:
        raise HTTPException(404, 'Connection not found.')
    if row.owner_id != user.id:
        raise HTTPException(403, 'Only the creator can remove this hypothesis.')
    db.delete(row); db.commit()
    return {'removed': True}
