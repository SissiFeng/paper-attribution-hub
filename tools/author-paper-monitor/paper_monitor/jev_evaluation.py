"""Export blind labels and per-workflow metrics; no training or auto-promotion."""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

from .jev_report import csv_safe
from .jev_tasks import SPECS, question


def metrics(entries):
    result = {'mode': 'shadow', 'promotion': 'none',
              'scope': 'Only returned records with human feedback; not an independent held-out calibration study.', 'tasks': {}}
    for task in SPECS:
        labelled = [e for e in entries if e.get('task') == task and e.get('status') == 'ok' and e.get('human_feedback')]
        values = {'labelled': len(labelled)}
        if labelled:
            probabilities = [(e['decision']['probabilities'], e['human_feedback']['label']) for e in labelled]
            if any(label not in probs for probs, label in probabilities):
                raise ValueError('Human feedback does not match the task contract')
            values['multiclass_brier'] = sum(sum((p-int(k == label))**2 for k, p in probs.items()) for probs, label in probabilities)/len(labelled)
            if question(task)['type'] == 'score':
                values['mae'] = sum(abs(e['decision']['score']-int(e['human_feedback']['label'])) for e in labelled)/len(labelled)
            else:
                values['accuracy'] = sum(e['decision']['choice'] == e['human_feedback']['label'] for e in labelled)/len(labelled)
        result['tasks'][task] = values
    return result


def export(entries, output):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    (output/'jev-decisions.json').write_text(json.dumps(entries, ensure_ascii=False, indent=2)+'\n')
    (output/'jev-metrics.json').write_text(json.dumps(metrics(entries), indent=2)+'\n')
    labels = output/'jev-workflow-labels.csv'
    if not labels.exists():
        with labels.open('w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=['decision_id', 'task', 'state', 'human_label'])
            writer.writeheader()
            for entry in entries:
                if entry.get('status') == 'ok':
                    writer.writerow({'decision_id': entry['decision_id'], 'task': entry['task'],
                                     'state': csv_safe(json.dumps(entry.get('state', {}), ensure_ascii=False)), 'human_label': ''})


def import_labels(ledger, path, reviewer):
    if not reviewer.strip() or len(reviewer) > 100:
        raise ValueError('A reviewer name of 1–100 characters is required')
    pending, seen = [], set()
    with Path(path).open(newline='') as f:
        for row in csv.DictReader(f):
            key, task, label = row['decision_id'], row['task'], row['human_label'].strip()
            if key in seen:
                raise ValueError('Duplicate decision ID in labels')
            seen.add(key)
            entry = ledger.get(key)
            if not entry or entry.get('status') != 'ok' or entry.get('task') != task or task not in SPECS:
                raise ValueError('Label does not match a successful decision')
            if not label:
                continue
            spec = question(task)
            allowed = {str(i) for i in range(len(spec['criteria']))} if spec['type'] == 'score' else set(spec['criteria'])
            if label not in allowed:
                raise ValueError('Invalid label for '+task)
            pending.append((key, label))
    # Validate the complete input before writing any feedback.
    for key, label in pending:
        ledger.feedback(key, label, reviewer.strip())
    return len(pending)


def main():
    from .jev_ledger import journal
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', required=True, type=Path)
    parser.add_argument('--labels', type=Path, help='Completed blind CSV to import before reporting')
    parser.add_argument('--reviewer', help='Required with --labels')
    args = parser.parse_args()
    if args.labels and not args.reviewer:
        parser.error('--labels requires --reviewer')
    ledger = journal()
    labelled = import_labels(ledger, args.labels, args.reviewer) if args.labels else 0
    entries = ledger.recent(50)
    export(entries, args.out)
    print(json.dumps({'records': len(entries), 'labels_imported': labelled, 'output': str(args.out)}))


if __name__ == '__main__':
    main()
