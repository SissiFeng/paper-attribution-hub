"""Published paper reading views; private records and management stay protected."""
from datetime import UTC, datetime
import hashlib
import json
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.db import get_session
from app.models import Paper, PaperAuthor, PaperProposition, PaperReference
from app.schemas import PaperOut, PaperAuthorOut, ClassificationOut
from app.services.filter_spec import PaperFilter, apply_filter

router = APIRouter(prefix='/catalog', tags=['paper catalogue'])


def published():
    # Do not publish uploads or arbitrary internal records just because they
    # share the papers table. Monitor records come from publication APIs.
    return and_(
        Paper.provenance.notin_(['manual_upload', 'pdf']),
        or_(Paper.doi.like('10.%/%'), Paper.source.in_(['openalex', 'crossref', 'semantic_scholar', 'author_monitor'])),
    )


def bibliographic(paper):
    return {'id': paper.id, 'title': paper.title, 'abstract': paper.abstract,
            'doi': paper.doi, 'year': paper.year, 'venue': paper.venue,
            'authors': [p.author.canonical_name for p in paper.authors if p.author],
            'keywords': paper.keywords or [], 'full_text_available': bool(paper.full_text_available)}


def shared_paper(row):
    """Explicit shared fields, never HumanReview or arbitrary classifier payloads."""
    c = row.classification
    classification = None
    if c:
        fields = ('label', 'confidence', 'author_score', 'institution_score', 'topic_score',
                  'network_score', 'fulltext_evidence_score', 'citation_score', 'matched_people',
                  'matched_institutions', 'matched_topics', 'reasons', 'model_version', 'created_at')
        classification = ClassificationOut(**{key: getattr(c, key) for key in fields if getattr(c, key) is not None})
    return PaperOut(id=row.id, title=row.title, abstract=row.abstract, doi=row.doi,
        year=row.year, venue=row.venue, keywords=row.keywords, full_text_available=bool(row.full_text_available),
        provenance=row.provenance or 'unknown', source=row.source or 'unknown', classification=classification,
        authors=[PaperAuthorOut(name=p.author.canonical_name, order=p.author_order, affiliation=p.affiliation_text)
                 for p in row.authors if p.author])


def published_paper(session, paper_id):
    row = session.scalar(select(Paper).where(published(), Paper.id == paper_id))
    if not row:
        raise HTTPException(404, 'Paper not found in the public catalogue.')
    return row


@router.get('/paper-view', response_model=list[PaperOut])
def paper_view(search: str = Query(default='', max_length=200),
               year_from: int | None = None, year_to: int | None = None,
               labels: list[str] = Query(default=[]),
               min_confidence: float | None = Query(default=None, ge=0, le=1),
               max_confidence: float | None = Query(default=None, ge=0, le=1),
               limit: int = Query(default=50, ge=1, le=100),
               offset: int = Query(default=0, ge=0, le=100000), session: Session = Depends(get_session)):
    # Deliberately do not accept human-review or institutional analytics filters.
    from pydantic import ValidationError
    try:
        filt = PaperFilter(search=search, year_from=year_from, year_to=year_to,
            labels=[label for label in labels if label != 'all'],
            min_confidence=min_confidence, max_confidence=max_confidence)
    except ValidationError:
        raise HTTPException(422, 'Invalid paper filters.')
    query = apply_filter(select(Paper).where(published()), filt).options(
        selectinload(Paper.authors).selectinload(PaperAuthor.author), selectinload(Paper.classification))
    rows = session.scalars(query.order_by(Paper.created_at.desc(), Paper.id).offset(offset).limit(limit))
    return [shared_paper(row) for row in rows]


@router.get('/papers/{paper_id}/view', response_model=PaperOut)
def paper_detail_view(paper_id: str, session: Session = Depends(get_session)):
    return shared_paper(published_paper(session, paper_id))


@router.get('/papers/{paper_id}/wiki')
def paper_wiki(paper_id: str, session: Session = Depends(get_session)):
    # Reuse the original deterministic Wiki section builder without writing a
    # WikiPage, invoking a model, or publishing archived private chat syntheses.
    from app.services import wiki_compiler
    row = published_paper(session, paper_id)
    propositions = list(session.scalars(select(PaperProposition).where(PaperProposition.paper_id == paper_id).order_by(PaperProposition.id)))
    references = list(session.scalars(select(PaperReference).where(PaperReference.citing_paper_id == paper_id).order_by(PaperReference.order_index, PaperReference.id)))
    allowed = {'identity', 'abstract_summary', 'sdl_evidence', 'ac_evidence', 'topics',
               'classification', 'keywords', 'methods', 'materials', 'references', 'links', 'open_questions'}
    sections = [part for part in wiki_compiler._build_paper_sections(row, propositions=propositions, references=references,
        ac_cites=[ref for ref in references if ref.cited_ac_core_id]) if part['key'] in allowed]
    if all(getattr(row, key) is None for key in ('ai_decision_score', 'automation_score', 'closed_loop_score')):
        for part in sections:
            if part['key'] == 'sdl_evidence':
                part['body'] = 'SDL assessment has not been recorded for this paper.'
    content = '\n\n'.join('## '+part['heading']+'\n'+part['body'] for part in sections)
    fingerprint = hashlib.sha256(json.dumps(sections, sort_keys=True).encode()).hexdigest()
    return {'id': 'public-wiki:'+paper_id, 'entity_type': 'paper', 'entity_id': paper_id,
        'title': row.title, 'sections': sections, 'generated_at': datetime.now(UTC).isoformat(),
        'model_version': getattr(wiki_compiler, 'WIKI_COMPILER_VERSION', 'template-v0.1'), 'prompt_version': 'shared-paper-v1',
        'content_md': content, 'source_snapshot_hash': fingerprint,
        'content_hash': hashlib.sha256(content.encode()).hexdigest(),
        'source_metadata': {'projection_mode': 'shared_paper'}, 'compile_status': 'complete', 'is_stale': False}


@router.get('/papers')
def papers(q: str = Query(default='', max_length=200), offset: int = Query(default=0, ge=0, le=100000),
           session: Session = Depends(get_session)):
    rows = list(session.scalars(select(Paper).where(published(), Paper.title.icontains(q, autoescape=True))
        .options(selectinload(Paper.authors).selectinload(PaperAuthor.author))
        .order_by(Paper.created_at.desc(), Paper.id).offset(offset).limit(41)))
    return {'items': [bibliographic(p) for p in rows[:40]], 'has_more': len(rows) > 40}


@router.get('/resolve')
def resolve(doi: str = Query(max_length=300), session: Session = Depends(get_session)):
    normalized = doi.lower().strip().removeprefix('https://doi.org/').removeprefix('http://doi.org/')
    paper = session.scalar(select(Paper).where(published(), func.lower(Paper.doi) == normalized))
    if not paper:
        raise HTTPException(404, 'This publication is not available in the PAS catalogue yet.')
    return {'id': paper.id}


@router.get('/papers/{paper_id}')
def paper(paper_id: str, session: Session = Depends(get_session)):
    row = session.scalar(select(Paper).where(published(), Paper.id == paper_id))
    if not row:
        raise HTTPException(404, 'Paper not found in the public catalogue.')
    return bibliographic(row)
