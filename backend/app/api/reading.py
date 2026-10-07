"""Authenticated paper reading; personal annotations never enter the shared corpus."""
import hashlib
import time

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_session
from app.models import Paper, PaperSection
from app.models.reading import Bookmark, Reader
from app.services.reader_auth import current_reader

router = APIRouter(prefix='/reading', tags=['reading space'])


def get_paper(db, paper_id):
    row = db.get(Paper, paper_id)
    if not row:
        raise HTTPException(404, 'Paper not found.')
    return row


def paper_out(db, paper, user, *, detail=False):
    saved = db.get(Bookmark, (user.id, paper.id))
    result = {'id': paper.id, 'title': paper.title, 'abstract': paper.abstract,
        'doi': paper.doi, 'year': paper.year, 'venue': paper.venue,
        'authors': [a.author.canonical_name for a in paper.authors if a.author],
        'full_text_available': paper.full_text_available,
        'saved': bool(saved), 'note': saved.note if saved else '',
        'url': 'https://doi.org/' + paper.doi if paper.doi else None}
    if detail:
        result['sections'] = [{'id': s.id, 'heading': s.section_title or s.section_type,
            'text': s.content, 'page_start': s.page_start, 'page_end': s.page_end}
            for s in db.scalars(select(PaperSection).where(PaperSection.paper_id == paper.id)
                .order_by(PaperSection.order_index))]
        raw = (paper.raw_metadata or {}).get('zotero_fulltext') or {}
        result['markdown_status'] = ('original' if raw.get('markdown_key') else
            'indexed_sections' if result['sections'] else 'unavailable')
    return result


@router.get('/papers')
def papers(q: str = Query(default='', max_length=200), saved: bool = False,
           offset: int = Query(default=0, ge=0, le=100000),
           session: Session = Depends(get_session), user: Reader = Depends(current_reader)):
    stmt = select(Paper).where(Paper.title.icontains(q, autoescape=True))
    if saved:
        stmt = stmt.join(Bookmark, Bookmark.paper_id == Paper.id).where(Bookmark.reader_id == user.id)
    rows = list(session.scalars(stmt.order_by(Paper.created_at.desc(), Paper.id).offset(offset).limit(41)))
    return {'items': [paper_out(session, p, user) for p in rows[:40]], 'has_more': len(rows) > 40}


@router.get('/papers/{paper_id}')
def paper_detail(paper_id: str, session: Session = Depends(get_session), user: Reader = Depends(current_reader)):
    return paper_out(session, get_paper(session, paper_id), user, detail=True)


class SavedIn(BaseModel):
    note: str = Field(default='', max_length=6000)


@router.put('/saved/{paper_id}')
def save(paper_id: str, payload: SavedIn, session: Session = Depends(get_session), user: Reader = Depends(current_reader)):
    get_paper(session, paper_id)
    row = session.get(Bookmark, (user.id, paper_id))
    if row is None:
        row = Bookmark(reader_id=user.id, paper_id=paper_id, saved_at=int(time.time()))
        session.add(row)
    row.note = payload.note
    session.commit()
    return {'saved': True, 'note': row.note}


@router.delete('/saved/{paper_id}')
def unsave(paper_id: str, session: Session = Depends(get_session), user: Reader = Depends(current_reader)):
    row = session.get(Bookmark, (user.id, paper_id))
    if row:
        session.delete(row)
        session.commit()
    return {'saved': False}


class CompareIn(BaseModel):
    paper_ids: list[str] = Field(min_length=2, max_length=6)


@router.post('/compare')
def compare(payload: CompareIn, session: Session = Depends(get_session), user: Reader = Depends(current_reader)):
    ids = list(dict.fromkeys(payload.paper_ids))
    if len(ids) < 2:
        raise HTTPException(422, 'Select at least two different papers.')
    return {'papers': [paper_out(session, get_paper(session, pid), user, detail=True) for pid in ids],
            'basis': 'Stored metadata and indexed source sections. Missing full text is not evidence of absence.'}


@router.get('/papers/{paper_id}/markdown')
def markdown(paper_id: str, download: bool = False, session: Session = Depends(get_session), user: Reader = Depends(current_reader)):
    paper = get_paper(session, paper_id)
    raw = (paper.raw_metadata or {}).get('zotero_fulltext') or {}
    key = raw.get('markdown_key')
    if key:
        if not isinstance(key, str) or not key.startswith('raw/zotero/') or not key.endswith('.md') or '..' in key.split('/'):
            raise HTTPException(409, 'Stored Markdown provenance needs review.')
        from app.services.s3_storage import get_file
        content = get_file(key, require_s3=True)
        if content is None:
            raise HTTPException(503, 'Markdown storage is temporarily unavailable.')
        if len(content) > 10_000_000:
            raise HTTPException(413, 'This Markdown document is too large for the reader.')
        expected = raw.get('markdown_sha256')
        if not expected or hashlib.sha256(content).hexdigest() != expected:
            raise HTTPException(409, 'Markdown integrity check failed.')
        text = content.decode('utf-8')
        source = 'original'
    else:
        parts = list(session.scalars(select(PaperSection).where(PaperSection.paper_id == paper.id)
            .order_by(PaperSection.order_index)))
        if not parts:
            raise HTTPException(404, 'Full text has not been acquired or indexed for this paper.')
        text = '# ' + paper.title + '\n\n> Reconstructed from indexed sections; not the original Markdown file.\n\n'
        text += '\n\n'.join('## ' + (p.section_title or p.section_type) + '\n\n' + p.content for p in parts)
        source = 'indexed_sections'
    if download:
        return Response(text, media_type='text/markdown', headers={'Content-Disposition': 'attachment; filename="paper.md"'})
    return {'text': text, 'source': source}


@router.get('/resolve')
def resolve(doi: str = Query(max_length=300), session: Session = Depends(get_session), user: Reader = Depends(current_reader)):
    from sqlalchemy import func
    normalized = doi.lower().strip().removeprefix('https://doi.org/').removeprefix('http://doi.org/')
    paper = session.scalar(select(Paper).where(func.lower(Paper.doi) == normalized))
    if not paper:
        raise HTTPException(404, 'Paper not found in PAS yet.')
    return {'id': paper.id}


@router.get('/papers/{paper_id}/sources/{kind}/{source_id}')
def source_location(paper_id: str, kind: str, source_id: str,
                    session: Session = Depends(get_session), user: Reader = Depends(current_reader)):
    from app.services.reading_evidence import get_source
    return get_source(session, paper_id, kind, source_id)


@router.get('/model')
def model_status(user: Reader = Depends(current_reader)):
    from app.services.grounded_answer_service import generation_status
    return generation_status()
