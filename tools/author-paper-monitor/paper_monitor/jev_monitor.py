"""Advisory identity, publication-version and next-analysis integration."""
from __future__ import annotations

from dataclasses import asdict
from difflib import SequenceMatcher
import json
from pathlib import Path
import time

from . import jev, jev_tasks
from .models import normalize_title


def author_candidates(target, candidates):
    results = []
    for candidate in candidates[:5]:
        advice = jev_tasks.evaluate('author_identity', {'target': target, 'candidate': candidate})
        candidate['jev_advice'] = advice
        if advice['status'] == 'ok':
            results.append(candidate)
    for rank, candidate in enumerate(sorted(results, key=lambda c: -c['jev_advice']['decision']['probabilities']['supported_match']), 1):
        candidate['jev_suggested_rank'] = rank
    return candidates  # Keep original order and every candidate; the operator chooses.


def version_candidates(rows, limit=20):
    """High-recall heuristic shortlist, never an identity or merge decision."""
    pairs = []
    for n, (left_id, left) in enumerate(rows[:200]):
        names = {normalize_title(a) for a in left.authors if a}
        for right_id, right in rows[n+1:200]:
            if set(left.doi_aliases) & set(right.doi_aliases) or (left.openalex_id and left.openalex_id == right.openalex_id):
                continue
            shared = names.intersection(normalize_title(a) for a in right.authors if a)
            if not shared or not left.title_key or not right.title_key:
                continue
            similarity = SequenceMatcher(None, left.title_key, right.title_key).ratio()
            if similarity >= 0.72:
                pairs.append((similarity, left_id, left, right_id, right))
    return sorted(pairs, key=lambda p: (-p[0], p[1], p[3]))[:limit]


def run(store, directory):
    cfg = jev.config()
    if cfg['mode'] != 'shadow':
        return
    rows = store.rows("SELECT id,data FROM papers ORDER BY (status='pending') DESC,json_extract(data,'$.date') DESC,id")
    items, attempts = [], 0
    deadline = time.monotonic()+30
    # Alternate version and next-analysis candidates so one workflow cannot monopolize a run.
    pairs = version_candidates(rows)
    jobs = []
    for index, (row_id, paper) in enumerate(rows[:200]):
        jobs.append(('analysis_route', {'paper': asdict(paper)}, {'paper_id': row_id}))
        if index < len(pairs):
            _, left_id, left, right_id, right = pairs[index]
            jobs.append(('version_relation', {'left': asdict(left), 'right': asdict(right)}, {'paper_ids': [left_id, right_id]}))
    for task, context, identifiers in jobs:
        if attempts >= 8 or time.monotonic() >= deadline:
            break
        advice = jev_tasks.evaluate(task, context)
        items.append({**identifiers, 'advice': advice})
        if advice['status'] in ('needs_configuration', 'unavailable', 'daily_limit_reached', 'error'):
            break
        attempts += int(not advice.get('cached'))
    path = Path(directory)/'jev-workflows.json'
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({'mode': 'shadow', 'tasks': list(jev_tasks.SPECS), 'version_candidates': len(pairs),
        'candidate_scope': 'At most 200 recent records; heuristic shortlist, not exhaustive duplicate detection.',
        'items': items, 'automatic_actions': False}, ensure_ascii=False, indent=2)+'\n')
