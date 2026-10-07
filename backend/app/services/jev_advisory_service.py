"""Optional Jev advice beside existing PAS decisions; no automatic promotion."""
from __future__ import annotations

import importlib
import os
from pathlib import Path
import re
import sys

from sqlalchemy import select


def runtime():
    try:
        return importlib.import_module('paper_monitor.jev_tasks')
    except ModuleNotFoundError as exc:
        if exc.name != 'paper_monitor':
            raise
        directory = Path(__file__).resolve().parents[3]/'tools/author-paper-monitor'
        if not directory.is_dir():
            raise
        sys.path.insert(0, str(directory))
        return importlib.import_module('paper_monitor.jev_tasks')


def enabled():
    return os.environ.get('JEV_MODE', 'off') == 'shadow'


def advise(task, context):
    if not enabled():
        return {'task': task, 'status': 'off', 'automatic_action': False}
    try:
        return runtime().evaluate(task, context)
    except Exception as exc:
        return {'task': task, 'status': 'unavailable', 'error_type': type(exc).__name__, 'automatic_action': False}


def paper_state(paper):
    return {'title': paper.title, 'abstract': paper.abstract, 'doi': paper.doi,
            'date': str(paper.year or ''),
            'authors': [p.author.canonical_name for p in paper.authors if p.author is not None]}


def route_advice(state):
    if enabled():
        result = advise('retrieval_route', {'query': state['request'].query})
        state.setdefault('trace', []).append({'module': 'jev_route_shadow', 'baseline_mode': state['mode'], 'advice': result})


def check_answer(state):
    """Check up to three cited claim/passage pairs; retain the unmodified answer."""
    if not enabled():
        return
    sources = state.get('sources', [])
    claims = [s.strip() for s in re.split(r'(?<=[.!?。！？])\s+|\n+', state.get('answer', '')) if s.strip()]
    checks = []
    for claim in claims:
        references = list(dict.fromkeys(int(i) for i in re.findall(r'\[(\d+)\]', claim)))
        if not references:
            continue
        for index in references:
            if len(checks) >= 3:
                break
            if index < 1 or index > len(sources):
                checks.append({'status': 'invalid_citation', 'citation': index, 'automatic_action': False})
                continue
            source = sources[index-1]
            passage = source.get('text') or ''
            checks.append(advise('answer_evidence', {'claim': claim, 'quote': passage[:6000], 'source_text': passage,
                'source_id': source.get('chunk_id'), 'paper_id': source.get('paper_id'), 'source_kind': 'retrieved_chunk'}))
        if len(checks) >= 3:
            break
    state.setdefault('trace', []).append({'module': 'jev_evidence_shadow', 'checks': checks,
        'scope': 'At most three cited claim/passage pairs, not whole-answer verification.',
        'uncited_claims_checked': False, 'answer_changed': False})


def review_boundaries(session):
    from app.services.staged_screening import _screening_boundaries
    from app.models import Paper
    try:
        training, reserved = _screening_boundaries(session)
        # Persisted split assignments remain binding after opening the corpus.
        assigned = set(session.scalars(select(Paper.id).where(
            Paper.raw_metadata['sdl_stage1_split']['role'].as_string().in_(['train', 'validation', 'frozen_test']))))
        return training | reserved | assigned
    except (OSError, ValueError):
        # An absent or invalid label manifest is not permission to evaluate it.
        return None


def review_advice(items, session):
    if not enabled():
        return
    protected = review_boundaries(session)
    for item in items[:3]:
        if protected is None or item.paper_id in protected:
            item.jev_advice = {'task': 'review_priority', 'status': 'protected_record',
                'reason': 'boundaries_unavailable' if protected is None else 'reserved_evaluation', 'automatic_action': False}
            continue
        item.jev_advice = advise('review_priority', {
            'paper': {'title': item.title, 'abstract': item.abstract, 'doi': item.doi, 'authors': item.authors},
            'signals': item.reasons, 'human_resolved': item.review_status == 'COMPLETED',
            'reserved_evaluation': bool(item.stage1_role)})


def graph_advice(session, paper, rows):
    if not enabled():
        return
    from app.models import PaperChunk
    checks = []
    for row in [r for r in rows if r.entity_type in ('method', 'instrument', 'software')][:2]:
        chunk = session.get(PaperChunk, row.evidence_chunk_id) if row.evidence_chunk_id else None
        if chunk is not None and chunk.paper_id != paper.id:
            checks.append({'status': 'source_mismatch', 'object': row.normalized_name})
            continue
        source = chunk.chunk_text if chunk else (paper.abstract or paper.title or '')
        source_id = chunk.id if chunk else f'{paper.id}:metadata'
        snippet = row.usage_snippet
        if not snippet or snippet not in source:
            at = source.casefold().find(row.name.casefold())
            if at < 0:
                checks.append({'status': 'missing_evidence', 'object': row.normalized_name})
                continue
            snippet = source[max(0, at-300):at+len(row.name)+300]
        checks.append(advise('graph_relation', {'paper_id': paper.id, 'source_id': source_id,
            'source_text': source, 'quote': snippet, 'source_kind': 'chunk' if chunk else 'metadata',
            'subject': paper.title, 'relation': 'uses ' + row.entity_type, 'object': row.normalized_name}))
    paper.raw_metadata = {**(paper.raw_metadata or {}), 'jev_graph_advice': checks}


def evaluate_paper(session, paper, task):
    from app.models import PaperChunk
    if task == 'review_priority':
        protected = review_boundaries(session)
        if protected is None or paper.id in protected:
            return {'task': task, 'status': 'protected_record',
                    'reason': 'boundaries_unavailable' if protected is None else 'reserved_evaluation', 'automatic_action': False}
    chunks = session.scalars(select(PaperChunk).where(PaperChunk.paper_id == paper.id).limit(2)).all()
    signals = []
    cls = paper.classification
    if cls:
        signals.append(f'Existing classification: {cls.label}; model confidence statistic: {cls.confidence}')
    if not chunks:
        signals.append('No indexed full-text chunks available; metadata alone does not establish full-text coverage.')
    review = paper.review
    return advise(task, {'paper': paper_state(paper), 'signals': signals,
        'evidence_supplied': '\n'.join(c.chunk_text[:5000] for c in chunks),
        'human_resolved': bool((cls and cls.human_confirmed) or (review and review.review_status == 'COMPLETED')) if task == 'review_priority' else False})
