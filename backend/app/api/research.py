"""Project membership and private-by-default research records."""
import copy
import time
import uuid
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import delete, or_, select
from sqlalchemy.orm import Session
from app.db import get_session
from app.models import ChatMessage, ChatSession, Paper
from app.models.reading import Reader
from app.models.research import (Annotation, EvidenceComparison, ProjectDiscussion,
    ProjectMember, ProjectPaper, ResearchProject)
from app.services.reader_auth import current_reader, public_reader
from app.services.chat_access import checked_members, require_chat
from app.services.paper_chat import POLICY
from app.services.research_access import require_artifact, require_project
from app.services.reading_evidence import AnchorIn, HINTS, check_anchor, evidence_matrix

router = APIRouter(prefix='/research', tags=['research workspace'])


def new_id():
    return str(uuid.uuid4())


def paper(db, pid):
    row = db.get(Paper, pid)
    if not row:
        raise HTTPException(404, 'Paper not found.')
    return row


def paper_brief(row):
    # Deliberately excludes personal bookmarks, notes and internal attribution fields.
    return {'id': row.id, 'title': row.title, 'year': row.year, 'venue': row.venue}


def project_out(db, row, detail=False):
    result = {k: getattr(row, k) for k in ('id', 'title', 'question', 'owner_id', 'created_at')}
    if detail:
        ids = select(ProjectMember.reader_id).where(ProjectMember.project_id == row.id)
        result['members'] = [public_reader(u) for u in db.scalars(select(Reader).where(or_(Reader.id == row.owner_id, Reader.id.in_(ids))))]
        result['papers'] = [paper_brief(p) for p in db.scalars(select(Paper).join(ProjectPaper).where(ProjectPaper.project_id == row.id).order_by(Paper.title))]
        result['discussions'] = [{'id': c.id, 'title': c.title} for c in db.scalars(select(ChatSession).join(ProjectDiscussion).where(ProjectDiscussion.project_id == row.id).order_by(ChatSession.updated_at.desc()))]
    return result


class ProjectIn(BaseModel):
    title: str = Field(min_length=1, max_length=160)
    question: str = Field(default='', max_length=3000)
    member_ids: list[str] = Field(default_factory=list, max_length=20)

    @field_validator('title')
    @classmethod
    def title_not_blank(cls, value):
        if not value.strip():
            raise ValueError('Enter a title.')
        return value.strip()


@router.get('/projects')
def projects(db: Session = Depends(get_session), user: Reader = Depends(current_reader)):
    grants = select(ProjectMember.project_id).where(ProjectMember.reader_id == user.id)
    return [project_out(db, p) for p in db.scalars(select(ResearchProject).where(
        ResearchProject.workspace_id == user.workspace_id,
        or_(ResearchProject.owner_id == user.id, ResearchProject.id.in_(grants))).order_by(ResearchProject.created_at.desc()))]


@router.post('/projects', status_code=201)
def create_project(payload: ProjectIn, db: Session = Depends(get_session), user: Reader = Depends(current_reader)):
    members = checked_members(db, payload.member_ids, user)
    row = ResearchProject(id=new_id(), owner_id=user.id, workspace_id=user.workspace_id,
                          title=payload.title, question=payload.question, created_at=int(time.time()))
    db.add(row)
    db.flush()
    for member in members:
        db.add(ProjectMember(project_id=row.id, reader_id=member.id))
    db.commit()
    return project_out(db, row, True)


@router.get('/projects/{project_id}')
def project_detail(project_id: str, db: Session = Depends(get_session), user: Reader = Depends(current_reader)):
    return project_out(db, require_project(db, project_id, user), True)


class MembersIn(BaseModel):
    member_ids: list[str] = Field(max_length=20)


@router.put('/projects/{project_id}/members')
def project_members(project_id: str, payload: MembersIn, db: Session = Depends(get_session), user: Reader = Depends(current_reader)):
    row = require_project(db, project_id, user, owner=True, lock=True)
    members = checked_members(db, payload.member_ids, user)
    db.execute(delete(ProjectMember).where(ProjectMember.project_id == project_id))
    for member in members:
        db.add(ProjectMember(project_id=project_id, reader_id=member.id))
    db.commit()
    return project_out(db, row, True)


@router.put('/projects/{project_id}/papers/{paper_id}')
def add_paper(project_id: str, paper_id: str, db: Session = Depends(get_session), user: Reader = Depends(current_reader)):
    require_project(db, project_id, user, lock=True)
    paper(db, paper_id)
    if not db.get(ProjectPaper, (project_id, paper_id)):
        db.add(ProjectPaper(project_id=project_id, paper_id=paper_id))
    db.commit()
    return {'added': True}


@router.delete('/projects/{project_id}/papers/{paper_id}')
def remove_paper(project_id: str, paper_id: str, db: Session = Depends(get_session), user: Reader = Depends(current_reader)):
    require_project(db, project_id, user, owner=True, lock=True)
    db.execute(delete(ProjectPaper).where(ProjectPaper.project_id == project_id, ProjectPaper.paper_id == paper_id))
    db.commit()
    return {'removed': True}


def scope_artifacts(stmt, model, db, user, project_id):
    if project_id:
        require_project(db, project_id, user)
        return stmt.where(model.project_id == project_id)
    return stmt.where(model.project_id.is_(None), model.owner_id == user.id)


def check_destination(db, project_id, user, paper_ids):
    if project_id:
        require_project(db, project_id, user, lock=True)
        present = set(db.scalars(select(ProjectPaper.paper_id).where(ProjectPaper.project_id == project_id)))
        if not set(paper_ids).issubset(present):
            raise HTTPException(422, 'Add the selected papers to this project first.')


def annotation_out(row):
    return {k: getattr(row, k) for k in ('id', 'owner_id', 'project_id', 'paper_id', 'anchor', 'body', 'created_at')}


class AnnotationIn(BaseModel):
    paper_id: str = Field(max_length=200)
    project_id: str | None = None
    anchor: AnchorIn
    body: str = Field(default='', max_length=6000)


@router.get('/annotations')
def annotations(paper_id: str | None = None, project_id: str | None = None,
                db: Session = Depends(get_session), user: Reader = Depends(current_reader)):
    stmt = scope_artifacts(select(Annotation), Annotation, db, user, project_id)
    if paper_id:
        stmt = stmt.where(Annotation.paper_id == paper_id)
    return [annotation_out(a) for a in db.scalars(stmt.order_by(Annotation.created_at.desc(), Annotation.id))]


@router.post('/annotations', status_code=201)
def annotate(payload: AnnotationIn, db: Session = Depends(get_session), user: Reader = Depends(current_reader)):
    check_destination(db, payload.project_id, user, [payload.paper_id])
    anchor = check_anchor(db, payload.paper_id, payload.anchor)
    row = Annotation(id=new_id(), owner_id=user.id, project_id=payload.project_id, paper_id=payload.paper_id,
                     anchor=anchor, body=payload.body, created_at=int(time.time()))
    db.add(row)
    db.commit()
    return annotation_out(row)


class NoteIn(BaseModel):
    body: str = Field(max_length=6000)


@router.put('/annotations/{annotation_id}')
def edit_annotation(annotation_id: str, payload: NoteIn, db: Session = Depends(get_session), user: Reader = Depends(current_reader)):
    row = require_artifact(db, Annotation, annotation_id, user, edit=True)
    row.body = payload.body
    db.commit()
    return annotation_out(row)


@router.delete('/annotations/{annotation_id}')
def delete_annotation(annotation_id: str, db: Session = Depends(get_session), user: Reader = Depends(current_reader)):
    db.delete(require_artifact(db, Annotation, annotation_id, user, edit=True))
    db.commit()
    return {'deleted': True}


class CopyIn(BaseModel):
    project_id: str


@router.post('/annotations/{annotation_id}/copy', status_code=201)
def copy_annotation(annotation_id: str, payload: CopyIn, db: Session = Depends(get_session), user: Reader = Depends(current_reader)):
    row = require_artifact(db, Annotation, annotation_id, user, edit=True)
    check_destination(db, payload.project_id, user, [row.paper_id])
    copied = Annotation(id=new_id(), owner_id=user.id, project_id=payload.project_id,
                        paper_id=row.paper_id, anchor=copy.deepcopy(row.anchor), body=row.body, created_at=int(time.time()))
    db.add(copied)
    db.commit()
    return annotation_out(copied)


class CompareIn(BaseModel):
    title: str = Field(default='Evidence comparison', min_length=1, max_length=160)
    paper_ids: list[str] = Field(min_length=2, max_length=6)
    dimensions: list[str] = Field(default_factory=lambda: list(HINTS), min_length=1, max_length=8)
    project_id: str | None = None

    @field_validator('dimensions')
    @classmethod
    def clean_dimensions(cls, values):
        if any(not v.strip() or len(v) > 80 for v in values):
            raise ValueError('Each comparison dimension needs 1–80 characters.')
        return list(dict.fromkeys(v.strip() for v in values))


def comparison_out(db, row):
    return {k: getattr(row, k) for k in ('id', 'owner_id', 'project_id', 'title', 'paper_ids', 'dimensions', 'cells', 'created_at')} | {
        'papers': [paper_brief(paper(db, pid)) for pid in row.paper_ids],
        'basis': 'Candidate source passages, not verified extracted values. Missing evidence is not absence. Compare units and experimental conditions before interpreting results.'}


@router.post('/comparisons', status_code=201)
def create_comparison(payload: CompareIn, db: Session = Depends(get_session), user: Reader = Depends(current_reader)):
    ids = list(dict.fromkeys(payload.paper_ids))
    if len(ids) < 2:
        raise HTTPException(422, 'Select at least two different papers.')
    check_destination(db, payload.project_id, user, ids)
    papers = [paper(db, pid) for pid in ids]
    row = EvidenceComparison(id=new_id(), owner_id=user.id, project_id=payload.project_id, title=payload.title,
        paper_ids=ids, dimensions=payload.dimensions, cells=evidence_matrix(db, papers, payload.dimensions), created_at=int(time.time()))
    db.add(row)
    db.commit()
    return comparison_out(db, row)


@router.get('/comparisons')
def comparisons(project_id: str | None = None, db: Session = Depends(get_session), user: Reader = Depends(current_reader)):
    stmt = scope_artifacts(select(EvidenceComparison), EvidenceComparison, db, user, project_id)
    return [{k: getattr(row, k) for k in ('id', 'title', 'owner_id', 'project_id', 'paper_ids')} for row in db.scalars(stmt.order_by(EvidenceComparison.created_at.desc()))]


@router.get('/comparisons/{comparison_id}')
def get_comparison(comparison_id: str, db: Session = Depends(get_session), user: Reader = Depends(current_reader)):
    return comparison_out(db, require_artifact(db, EvidenceComparison, comparison_id, user))


class CellIn(BaseModel):
    paper_id: str
    dimension: str
    interpretation: str = Field(max_length=2000)
    evidence: list[AnchorIn] = Field(min_length=1, max_length=3)


@router.put('/comparisons/{comparison_id}/cells')
def edit_cell(comparison_id: str, payload: CellIn, db: Session = Depends(get_session), user: Reader = Depends(current_reader)):
    row = require_artifact(db, EvidenceComparison, comparison_id, user, edit=True)
    if payload.paper_id not in row.paper_ids or payload.dimension not in row.dimensions:
        raise HTTPException(422, 'Select a cell in this comparison.')
    evidence = [check_anchor(db, payload.paper_id, a) for a in payload.evidence]
    row.cells = [({'paper_id': payload.paper_id, 'dimension': payload.dimension, 'interpretation': payload.interpretation,
                  'status': 'reader_interpretation', 'evidence': evidence} if c['paper_id'] == payload.paper_id and c['dimension'] == payload.dimension else c) for c in row.cells]
    db.commit()
    return comparison_out(db, row)


@router.delete('/comparisons/{comparison_id}')
def delete_comparison(comparison_id: str, db: Session = Depends(get_session), user: Reader = Depends(current_reader)):
    db.delete(require_artifact(db, EvidenceComparison, comparison_id, user, edit=True))
    db.commit()
    return {'deleted': True}


@router.post('/comparisons/{comparison_id}/copy', status_code=201)
def copy_comparison(comparison_id: str, payload: CopyIn, db: Session = Depends(get_session), user: Reader = Depends(current_reader)):
    row = require_artifact(db, EvidenceComparison, comparison_id, user, edit=True)
    check_destination(db, payload.project_id, user, row.paper_ids)
    copied = EvidenceComparison(id=new_id(), owner_id=user.id, project_id=payload.project_id, title=row.title,
        paper_ids=copy.deepcopy(row.paper_ids), dimensions=copy.deepcopy(row.dimensions), cells=copy.deepcopy(row.cells), created_at=int(time.time()))
    db.add(copied)
    db.commit()
    return comparison_out(db, copied)


class DiscussionIn(BaseModel):
    title: str = Field(default='Project discussion', min_length=1, max_length=160)
    paper_ids: list[str] = Field(min_length=1, max_length=100)
    source_session_id: str | None = None
    message_ids: list[str] = Field(default_factory=list, max_length=40)


@router.post('/projects/{project_id}/discussions', status_code=201)
def project_discussion(project_id: str, payload: DiscussionIn, db: Session = Depends(get_session), user: Reader = Depends(current_reader)):
    check_destination(db, project_id, user, payload.paper_ids)
    chosen = []
    if payload.source_session_id:
        source = require_chat(db, payload.source_session_id, user, owner_only=True, lock=True)
        if source.scope.get('access_policy') != POLICY or db.get(ProjectDiscussion, source.id):
            raise HTTPException(403, 'Only a reading discussion outside a project can be copied here.')
        if set(payload.paper_ids) != set(source.scope.get('paper_ids') or []):
            raise HTTPException(422, 'A copied discussion must retain its original paper scope.')
        chosen = list(db.scalars(select(ChatMessage).where(ChatMessage.session_id == source.id,
            ChatMessage.id.in_(payload.message_ids)).order_by(ChatMessage.ordinal)))
        if len(chosen) != len(set(payload.message_ids)):
            raise HTTPException(422, 'Choose messages from the source discussion.')
    elif payload.message_ids:
        raise HTTPException(422, 'Choose a source discussion for message copies.')
    scope = {'access_policy': POLICY, 'paper_ids': list(dict.fromkeys(payload.paper_ids)), 'filters': {}, 'page_context': None}
    # Project membership is the only grant. Older deployments reject unowned chats,
    # so rolling back cannot resurrect access for a removed discussion creator.
    chat = ChatSession(id=new_id(), title=payload.title, owner_id=None, workspace_id=user.workspace_id, shared=True, scope=scope)
    db.add(chat)
    db.flush()
    db.add(ProjectDiscussion(session_id=chat.id, project_id=project_id))
    for number, message in enumerate(chosen, 1):
        db.add(ChatMessage(id=new_id(), session_id=chat.id, ordinal=number, reader_id=message.reader_id,
            role=message.role, content=message.content, status=message.status, answer_kind=message.answer_kind,
            model=message.model, tool_name=message.tool_name, sources=copy.deepcopy(message.sources),
            audit={'shared_copy': True}, scope=scope))
    db.commit()
    return {'id': chat.id, 'project_id': project_id}
