"""Reading-room answers use only published paper text and public catalogue fields.

No attribution filters, graph boosts, wiki, propositions, or generated SQL enter
this path. Even an admin's new reading discussion is safe to share with members.
"""
import re
from sqlalchemy import select
from app.models import Paper, PaperChunk
from app.services.chat_service import (_add_message, _conversation,
    _now, ChatBlockedError, get_chat_session)
from app.services.grounded_answer_service import contextualized_retrieval_query, generate_grounded_answer

POLICY = 'paper-reading-v1'
SAFE_FILTERS = {'year_from', 'year_to', 'search', 'has_fulltext'}


def reading_scope(scope):
    scope = dict(scope or {})
    filters = scope.get('filters') or {}
    if any(key not in SAFE_FILTERS and value is not None and value is not False and value != [] and value != '' for key, value in filters.items()):
        raise ChatBlockedError('Reading discussions support paper, year, title and full-text filters only.')
    return {'access_policy': POLICY, 'filters': {k: v for k, v in filters.items() if k in SAFE_FILTERS},
            'paper_ids': scope.get('paper_ids'), 'page_context': scope.get('page_context')}


def selected_papers(db, scope):
    stmt = select(Paper.id, Paper.title, Paper.year)
    filters = scope['filters']
    for key, condition in [('year_from', Paper.year >= (filters.get('year_from') or 0)),
                           ('year_to', Paper.year <= (filters.get('year_to') or 9999))]:
        if filters.get(key) is not None:
            stmt = stmt.where(condition)
    if filters.get('search'):
        stmt = stmt.where(Paper.title.icontains(filters['search'], autoescape=True))
    if filters.get('has_fulltext') is not None:
        stmt = stmt.where(Paper.full_text_available == filters['has_fulltext'])
    if scope.get('paper_ids') is not None:
        stmt = stmt.where(Paper.id.in_(scope['paper_ids']))
    return list(db.execute(stmt.order_by(Paper.id)))


def search_paper_text(db, query, papers):
    from app.services.embedding_service import TfidfEmbedder, domain_tokenize
    from app.services.retrieval_service import HybridIndex, IndexedChunk
    if not papers:
        return []  # Never pass [] to a retriever that treats it as unrestricted.
    ids = [p.id for p in papers]
    rows = list(db.scalars(select(PaperChunk).where(PaperChunk.paper_id.in_(ids)).order_by(PaperChunk.id)))
    if not rows:
        return abstract_sources(db, query, papers)
    # Contextual embeddings may contain internal annotations; index raw text only.
    embedder = TfidfEmbedder()
    texts = [row.chunk_text for row in rows]
    embedder.fit(texts)
    if not embedder.vocab:
        return abstract_sources(db, query, papers)
    vectors = embedder.encode(texts)
    years = {p.id: p.year for p in papers}
    index = HybridIndex([IndexedChunk(row.id, row.paper_id, row.section_type, None,
        row.chunk_text, row.chunk_text, domain_tokenize(row.chunk_text), vectors[i], years[row.paper_id])
        for i, row in enumerate(rows)], embedder, graph_scores={})
    titles = {p.id: p.title for p in papers}
    from app.services.reading_evidence import get_source, make_anchor
    sources = []
    for hit in index.search(query, paper_ids=ids, top_k=8):
        if hit.bm25_score <= 0 and hit.cosine_score <= 0:
            continue
        source = get_source(db, hit.paper_id, 'chunk', hit.chunk_id)
        sources.append({'paper_id': hit.paper_id, 'paper_title': titles[hit.paper_id],
            'chunk_id': hit.chunk_id, 'section_type': hit.section_type, 'text': hit.text[:4000],
            'anchor': make_anchor(source, 0, min(4000, len(source['text'])))})
    missing = [p for p in papers if p.id not in {s['paper_id'] for s in sources}]
    return (sources + abstract_sources(db, query, missing))[:8]


def abstract_sources(db, query, papers):
    from app.services.reading_evidence import get_source, make_anchor
    words = set(re.findall(r'\w{3,}', query.lower()))
    sources = []
    for p in papers:
        paper = db.get(Paper, p.id)
        if not paper.abstract or not any(w in paper.abstract.lower() for w in words):
            continue
        source = get_source(db, p.id, 'abstract', p.id)
        sources.append({'paper_id': p.id, 'paper_title': p.title, 'section_type': 'abstract',
            'text': paper.abstract[:4000], 'anchor': make_anchor(source, 0, min(4000, len(paper.abstract)))})
    return sources[:8]


def valid_references(answer, count):
    refs = [int(n) for n in re.findall(r'\[(\d+)\]', answer or '')]
    return bool(refs) and all(1 <= n <= count for n in refs)



def run_reading_turn(db, *, session_id, query, scope_override=None):
    from app.services.chat_service import ensure_safe_query
    ensure_safe_query(query)
    chat = get_chat_session(db, session_id)
    if chat.scope.get('access_policy') != POLICY:
        raise ChatBlockedError('This archived discussion predates reading permissions. Start a new reading discussion.')
    scope = reading_scope(scope_override if scope_override is not None else chat.scope)
    papers = selected_papers(db, scope)
    prior = _conversation(db, session_id)
    user_message = _add_message(db, chat=chat, role='user', content=query, scope=scope)
    # Exact, narrow catalogue counts; free-form requests never become database SQL.
    if re.fullmatch(r'(how many papers(?: are (?:in|there in) (?:the )?(?:current )?(?:corpus|scope))?|论文有多少篇|有多少篇论文)\??', query.strip(), re.I):
        sources = []
        answer, model, kind, tool = f'{len(papers)} papers in the selected reading scope.', 'catalogue', 'verified_structured', 'query_corpus_stats'
    else:
        sources = search_paper_text(db, contextualized_retrieval_query(query, prior), papers)
        context = '\n\n'.join(f'[{i}] {source["paper_title"]}\n{source["text"]}' for i, source in enumerate(sources, 1))
        answer, model = generate_grounded_answer(query, context, conversation=prior,
                                                page_context=scope.get('page_context')) if sources else (None, 'retrieval-only')
        generation_result = model
        rejected_citations = bool(answer and not valid_references(answer, len(sources)))
        if not answer or rejected_citations:
            answer = ('Relevant published passages:\n\n' + '\n\n'.join(
                f'[{i}] {s["paper_title"]}: {s["text"][:900]}' for i, s in enumerate(sources, 1))) if sources else 'No supporting published passages were found in this reading scope.'
            model = 'retrieval-only'
        kind = 'evidence_grounded' if model != 'retrieval-only' and valid_references(answer, len(sources)) else ('partial_evidence' if sources else 'insufficient_evidence')
        tool = 'search_fulltext_evidence'
    assistant = _add_message(db, chat=chat, role='assistant', content=answer, answer_kind=kind,
        model=model, tool_name=tool, sources=sources, scope=scope,
        audit={'access_policy': POLICY, 'read_only': True, 'llm_used': model not in ('retrieval-only', 'catalogue'), 'citation_check': 'references_only_not_entailment' if kind == 'evidence_grounded' else 'not_verified',
               'generation_result': locals().get('generation_result', model),
               'rejected_citations': locals().get('rejected_citations', False)})
    chat.scope, chat.updated_at = scope, _now()
    if not chat.title:
        chat.title = query[:80]
    return user_message, assistant
