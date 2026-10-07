"""Evidence-labelled connections and bounded discovery within the PAS catalogue."""
import hashlib
import re
import time
from sqlalchemy import exists, or_, select
from app.models import Paper, PaperProposition, PaperReference, PaperSection
from app.models.exploration import ResearchAlert, ResearchConnection, ResearchWatch
from app.models.reading import Reader
from app.models.research import ProjectPaper, ResearchProject
from app.services.reading_evidence import source_out, make_anchor

# These are literal phrase detectors, not a method classifier.
METHOD_PHRASES = ('Bayesian optimization', 'Gaussian process', 'density functional theory',
    'molecular dynamics', 'active learning', 'reinforcement learning', 'robotic liquid handling',
    'high-throughput screening', 'self-supervised learning', 'novel view synthesis')


def brief(p):
    return {k: getattr(p, k) for k in ('id', 'title', 'doi', 'year', 'venue')}


def term_filter(terms):
    return or_(*(or_(Paper.title.icontains(t, autoescape=True), Paper.abstract.icontains(t, autoescape=True)) for t in terms))


def matched(p, terms):
    text = (p.title + '\n' + (p.abstract or '')).casefold()
    return [term for term in terms if term.casefold() in text]


def related(db, project_id, terms):
    from app.api.catalog import published
    included = select(ProjectPaper.paper_id).where(ProjectPaper.project_id == project_id)
    if not terms:
        return {'items': [], 'truncated': False, 'basis': 'Enter keywords to search titles and abstracts in PAS.'}
    rows = list(db.scalars(select(Paper).where(published(), ~Paper.id.in_(included), term_filter(terms))
        .order_by(Paper.created_at.desc(), Paper.id).limit(501)))
    results = [{'paper': brief(p), 'matched_terms': matched(p, terms)} for p in rows[:500]]
    results.sort(key=lambda r: -len(r['matched_terms']))
    return {'items': results[:50], 'truncated': len(rows) > 50,
        'basis': 'Literal title/abstract matches in the PAS catalogue. Ranked by matched phrases among up to 500 newest matches; not semantic relevance or an exhaustive literature search.'}


def project_map(db, project_id):
    papers = list(db.scalars(select(Paper).join(ProjectPaper).where(ProjectPaper.project_id == project_id).order_by(Paper.id).limit(101)))
    truncated = len(papers) > 100
    papers = papers[:100]; ids = {p.id for p in papers}
    nodes = [{'id': p.id, 'kind': 'paper', 'label': p.title} for p in papers]
    edges = []; methods = {}
    for p in papers:
        sections = list(db.scalars(select(PaperSection).where(PaperSection.paper_id == p.id).order_by(PaperSection.order_index, PaperSection.id).limit(80)))
        sources = [source_out(p, 'abstract', p.id, p.abstract, 'Abstract')] if p.abstract else []
        sources += [source_out(p, 'section', s.id, s.content, s.section_title or s.section_type, s.page_start) for s in sections if s.content]
        extracted = db.scalars(select(PaperProposition.object_value).where(PaperProposition.paper_id == p.id,
            PaperProposition.predicate == 'uses_method').order_by(PaperProposition.id).limit(40))
        phrases = list(dict.fromkeys([*METHOD_PHRASES, *(v for v in extracted if v and 3 <= len(v) <= 100)]))
        for phrase in phrases:
            for source in sources:
                match = re.search(r'(?<!\w)' + re.escape(phrase) + r'(?!\w)', source['text'], re.I)
                if not match:
                    continue
                key = 'method:' + hashlib.sha256(phrase.casefold().encode()).hexdigest()[:16]
                methods[key] = {'id': key, 'kind': 'method', 'label': phrase.casefold()}
                start = max(0, match.start()-100); end = min(len(source['text']), match.end()+160)
                edges.append({'source': p.id, 'target': key, 'kind': 'method_mention',
                    'basis': 'Exact phrase in source; mention does not establish use or equivalence.',
                    'evidence': [make_anchor(source, start, end)]})
                break
    if ids:
        refs = db.scalars(select(PaperReference).where(PaperReference.citing_paper_id.in_(ids), PaperReference.cited_paper_id.in_(ids)).order_by(PaperReference.id))
        for ref in refs:
            edges.append({'source': ref.citing_paper_id, 'target': ref.cited_paper_id, 'kind': 'citation',
                'basis': 'Recorded reference; does not imply support or endorsement.', 'reference_id': ref.id,
                'reference_text': (ref.raw_text or '')[:1000], 'doi': ref.cited_doi, 'evidence': []})
    for row in db.scalars(select(ResearchConnection).where(ResearchConnection.project_id == project_id).order_by(ResearchConnection.created_at, ResearchConnection.id)):
        if row.source_id in ids and row.target_id in ids:
            edges.append({'id': row.id, 'owner_id': row.owner_id, 'source': row.source_id, 'target': row.target_id,
                'kind': 'hypothesis', 'relation': row.relation, 'basis': row.rationale, 'evidence': row.evidence})
    return {'nodes': nodes + list(methods.values()), 'edges': edges, 'truncated': truncated,
        'basis': 'Project papers only. References, exact method mentions and researcher hypotheses are separate; absence of an edge is not absence of a relationship.'}


def scan_project(db, project_id):
    """The project row lock serializes rule changes and duplicate-free discoveries."""
    from app.api.catalog import published
    project = db.scalar(select(ResearchProject).where(ResearchProject.id == project_id).with_for_update().execution_options(populate_existing=True))
    watch = db.get(ResearchWatch, project_id, populate_existing=True)
    owner = db.get(Reader, project.owner_id) if project else None
    if not watch or not watch.enabled or not watch.terms or not owner or not owner.active:
        return 0
    known = exists().where(ResearchAlert.project_id == project_id, ResearchAlert.paper_id == Paper.id)
    included = select(ProjectPaper.paper_id).where(ProjectPaper.project_id == project_id)
    rows = db.scalars(select(Paper).where(published(), Paper.created_at >= watch.since, term_filter(watch.terms),
        ~known, ~Paper.id.in_(included)).order_by(Paper.created_at, Paper.id).limit(1000))
    count = 0
    for p in rows:
        db.add(ResearchAlert(project_id=project_id, paper_id=p.id, matches=matched(p, watch.terms), created_at=int(time.time())))
        count += 1
    watch.checked_at = int(time.time())
    db.flush()
    return count
