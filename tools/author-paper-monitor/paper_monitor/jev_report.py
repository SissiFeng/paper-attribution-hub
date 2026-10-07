"""Portable shadow reports and blind human labels; no automatic promotion."""
from __future__ import annotations

import csv
import datetime
import json
import math
from pathlib import Path

from . import jev
from .slack_app import paper_key


def report(store):
    cfg = jev.config()
    exists = store.db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='jev_decisions'").fetchone()
    items = []
    for rank, (row_id, paper) in enumerate(store.rows("SELECT id,data FROM papers ORDER BY json_extract(data,'$.date') DESC,id"), 1):
        key = jev.fingerprint(jev.request_for(paper, cfg))
        row = store.db.execute('SELECT status,result FROM jev_decisions WHERE paper_id=? AND input_hash=?', (row_id, key)).fetchone() if exists else None
        items.append({'paper_id': row_id, 'paper_key': paper_key(paper), 'input_hash': key,
                      'title': paper.title, 'abstract': (paper.abstract or '')[:12000], 'url': paper.url,
                      'authors': paper.authors, 'venue': paper.venue, 'tracked_authors': paper.tracked_authors,
                      'sources': paper.sources, 'doi': paper.doi, 'openalex_id': paper.openalex_id,
                      'date': paper.date, 'baseline_rank': rank, 'status': row[0] if row else 'not_evaluated',
                      'decision': json.loads(row[1]) if row else None, 'suggested_rank': None})
    scored = sorted((item for item in items if item['status'] == 'ok'),
                    key=lambda x: (-x['decision']['priority_score'], x['baseline_rank']))
    for rank, item in enumerate(scored, 1):
        item['suggested_rank'] = rank
    return {'mode': cfg['mode'], 'question_version': jev.VERSION, 'model': cfg['model'], 'focus': cfg['focus'],
            'generated_at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
            'collection_status': json.loads(store.meta('jev_shadow_status') or '{}'),
            'papers': len(items), 'scored': len(scored), 'unscored': len(items)-len(scored),
            'warning': 'Suggestions only. Formal delivery order, paper inclusion and full-text acquisition are unchanged. '
                       'Probabilities are not validated on this corpus; unscored papers are not irrelevant.', 'items': items}


def csv_safe(value):
    value = str(value or '')
    return "'" + value if value.lstrip().startswith(('=', '+', '-', '@')) else value


def export(store, directory):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    data = report(store)
    (directory/'jev-shadow.json').write_text(json.dumps(data, ensure_ascii=False, indent=2)+'\n')
    # Never replace labels that a human has already started filling in.
    label_path = directory/'jev-labels.csv'
    if not label_path.exists():
        with label_path.open('w', newline='') as handle:
            fields = ['paper_id', 'input_hash', 'title', 'abstract', 'priority', 'next_step']
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()
            for item in data['items']:
                writer.writerow({key: csv_safe(item.get(key, '')) for key in fields})
    return data


def ndcg(values, k=10):
    def dcg(xs):
        return sum((2**v-1)/math.log2(i+2) for i, v in enumerate(xs[:k]))
    ideal = dcg(sorted(values, reverse=True))
    return dcg(values)/ideal if ideal else None


def evaluate(data, labels):
    items = {str(item['paper_id']): item for item in data['items']}
    priority, steps, seen, labelled = [], [], set(), 0
    for label in labels:
        if not label.get('priority', '').strip() and not label.get('next_step', '').strip():
            continue
        pid = label['paper_id']
        if pid in seen or pid not in items:
            raise ValueError('Duplicate or unknown labelled paper ID: ' + pid)
        seen.add(pid)
        item = items[pid]
        if label['input_hash'] != item['input_hash']:
            raise ValueError('Labels refer to an older input, focus or model: ' + pid)
        p, step = label.get('priority', '').strip(), label.get('next_step', '').strip()
        if p and p not in {'0', '1', '2', '3', '4'}:
            raise ValueError('Human priority must be an integer from 0 to 4')
        if step and step not in jev.NEXT_STEPS:
            raise ValueError('Unknown human next_step')
        labelled += 1
        if item['status'] != 'ok':
            continue
        if p:
            priority.append((item, int(p)))
        if step:
            steps.append((item, step))
    result = {'labelled_papers': labelled, 'scored_papers': data['scored'],
              'priority_labels_with_prediction': len(priority), 'next_step_labels_with_prediction': len(steps),
              'ranking_scope': 'Only labelled papers with successful predictions; unlabelled papers are excluded, not assumed irrelevant.',
              'promotion': 'shadow_only', 'calibration_claim': 'Not established by this report; use held-out representative labels.'}
    if priority:
        baseline = sorted(priority, key=lambda x: x[0]['baseline_rank'])
        suggested = sorted(priority, key=lambda x: x[0]['suggested_rank'])
        result.update(priority_mae=sum(abs(i['decision']['priority_score']-y) for i, y in priority)/len(priority),
                      baseline_ndcg_at_10=ndcg([y for _, y in baseline]),
                      suggested_ndcg_at_10=ndcg([y for _, y in suggested]))
        relevant = sum(y >= 3 for _, y in priority)
        result['relevant_recall_at_10'] = sum(y >= 3 for _, y in suggested[:10])/relevant if relevant else None
    if steps:
        brier = sum(sum((p-(key == target))**2 for key, p in i['decision']['next_step_probabilities'].items()) for i, target in steps)/len(steps)
        correct = sum(i['decision']['next_step'] == target for i, target in steps)
        needed = [(i, y) for i, y in steps if y == 'fulltext_needed']
        result.update(next_step_accuracy=correct/len(steps), next_step_multiclass_brier=brier,
                      missed_fulltext_rate=sum(i['decision']['next_step'] == 'metadata_sufficient' for i, _ in needed)/len(needed) if needed else None,
                      manual_review_rate=sum(i['decision']['next_step'] == 'manual_review' for i, _ in steps)/len(steps))
    successful = [i['decision'] for i in data['items'] if i['status'] == 'ok']
    if successful:
        costs = [r['estimated_input_cost_usd'] for r in successful if r.get('estimated_input_cost_usd') is not None]
        result['estimated_successful_input_cost_usd'] = sum(costs) if costs else None
        result['cost_coverage'] = f'{len(costs)} successful requests; failed requests and configuration smoke checks excluded; not an invoice'
        latency = sorted(r['latency_ms'] for r in successful)
        result['latency_p50_ms'] = latency[(len(latency)-1)//2]
        result['latency_p95_ms'] = latency[math.ceil(len(latency)*0.95)-1]
    return result


def main():
    import argparse
    import contextlib
    import fcntl
    from .store import Store
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--db', required=True, type=Path)
    parser.add_argument('--out', required=True, type=Path)
    parser.add_argument('--labels', type=Path)
    args = parser.parse_args()
    if not args.db.is_file():
        parser.error('The state database does not exist')
    with Path(str(args.db)+'.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with contextlib.closing(Store(args.db)) as store:
            data = export(store, args.out)
    if args.labels:
        with args.labels.open(newline='') as handle:
            metrics = evaluate(data, csv.DictReader(handle))
        (args.out/'jev-evaluation.json').write_text(json.dumps(metrics, indent=2)+'\n')
        print(json.dumps(metrics))
    else:
        print(json.dumps({'papers': data['papers'], 'scored': data['scored'], 'out': str(args.out)}))


if __name__ == '__main__':
    main()
