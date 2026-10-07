"""Versioned, exact source anchors. Offsets count Unicode code points, not bytes."""
import hashlib
import re
from typing import Literal
from fastapi import HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from app.models import Paper, PaperChunk, PaperSection


class AnchorIn(BaseModel):
    kind: Literal['section', 'chunk', 'abstract']
    source_id: str = Field(min_length=1, max_length=200)
    version: str = Field(pattern=r'^[0-9a-f]{64}$')
    start: int = Field(ge=0)
    end: int = Field(gt=0)
    quote: str = Field(min_length=1, max_length=4000)


def source_out(paper, kind, source_id, text, heading, page=None):
    return {'paper_id': paper.id, 'paper_title': paper.title, 'kind': kind, 'source_id': source_id,
            'text': text, 'heading': heading, 'page_start': page,
            'version': hashlib.sha256(text.encode()).hexdigest()}


def get_source(db, paper_id, kind, source_id):
    paper = db.get(Paper, paper_id)
    if not paper:
        raise HTTPException(404, 'Paper not found.')
    if kind == 'abstract' and source_id == paper.id and paper.abstract:
        return source_out(paper, kind, source_id, paper.abstract, 'Abstract')
    model = {'section': PaperSection, 'chunk': PaperChunk}.get(kind)
    row = db.get(model, source_id) if model else None
    if not row or row.paper_id != paper_id:
        raise HTTPException(404, 'Source not found in this paper.')
    if kind == 'section':
        return source_out(paper, kind, row.id, row.content, row.section_title or row.section_type, row.page_start)
    section = db.get(PaperSection, row.section_id) if row.section_id else None
    return source_out(paper, kind, row.id, row.chunk_text, row.section_type, section.page_start if section else None)


def make_anchor(source, start, end):
    return {k: v for k, v in source.items() if k != 'text'} | {
        'start': start, 'end': end, 'quote': source['text'][start:end]}


def check_anchor(db, paper_id, anchor):
    source = get_source(db, paper_id, anchor.kind, anchor.source_id)
    if source['version'] != anchor.version:
        raise HTTPException(409, 'Source text changed. Reopen the source and select the passage again.')
    if not anchor.quote.strip() or source['text'][anchor.start:anchor.end] != anchor.quote or anchor.end > len(source['text']):
        raise HTTPException(422, 'The quotation must match this exact source range.')
    return make_anchor(source, anchor.start, anchor.end)


# These are search hints, not extraction rules or a claim that a comparison is fair.
HINTS = {
    'Materials': 'material catalyst electrode composition 材料 催化剂',
    'Methods': 'method procedure synthesis synthesized optimization 方法 合成',
    'Conditions': 'condition electrolyte KOH loading temperature current density iR compensation 条件 电解液 电流密度',
    'Baselines': 'baseline control comparison reference benchmark 对照 基线',
    'Results': 'result performance overpotential efficiency accuracy 结果 过电位',
    'Limitations': 'limitation uncertainty future failure 局限 不确定 失败',
}


def evidence_matrix(db, papers, dimensions):
    cells = []
    for paper in papers:
        sections = list(db.scalars(select(PaperSection).where(PaperSection.paper_id == paper.id).order_by(PaperSection.order_index, PaperSection.id)))
        sources = [source_out(paper, 'section', s.id, s.content, s.section_title or s.section_type, s.page_start) for s in sections if s.content]
        if not sources:
            sources = [source_out(paper, 'chunk', c.id, c.chunk_text, c.section_type) for c in
                       db.scalars(select(PaperChunk).where(PaperChunk.paper_id == paper.id).order_by(PaperChunk.id)) if c.chunk_text]
        if paper.abstract:
            sources.append(source_out(paper, 'abstract', paper.id, paper.abstract, 'Abstract'))
        for dimension in dimensions:
            words = re.findall(r'[\w-]+', (dimension + ' ' + HINTS.get(dimension, '')).lower())
            candidates = []
            for source in sources:
                text = source['text']
                # Paragraph/sentence boundaries retain source offsets and exact scientific units.
                for match in re.finditer(r'.+?(?:[.!?](?=\s|$)|\n|$)', text, re.S):
                    passage = match.group().strip()
                    score = sum(1 for word in words if word in passage.lower())
                    score += int(any(word in source['heading'].lower() for word in words))
                    if score and passage:
                        start = match.start() + len(match.group()) - len(match.group().lstrip())
                        end = min(start + len(passage), start + 900)
                        candidates.append((score, make_anchor(source, start, end)))
            candidates.sort(key=lambda c: -c[0])
            evidence = []
            for _, anchor in candidates:
                if anchor['quote'] not in {a['quote'] for a in evidence}:
                    evidence.append(anchor)
                if len(evidence) == 2:
                    break
            cells.append({'paper_id': paper.id, 'dimension': dimension, 'interpretation': '',
                          'status': 'candidate_passages' if evidence else 'no_evidence_found', 'evidence': evidence})
    return cells
