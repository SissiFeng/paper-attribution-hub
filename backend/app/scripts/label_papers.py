"""Interactive CLI for hand-labeling papers from data/labeling_queue.csv.

Keys:
    1=CORE_RELEVANT 2=RELATED_RELEVANT 3=ADJACENT 4=UNCERTAIN 5=EXCLUDE
    a=accept prediction  s=skip  u=undo last  q=quit

Every answer is written back to the queue immediately and appended to
data/eval_labels.csv (no duplicates), so quitting or crashing loses nothing.

Usage:
    python -m app.scripts.label_papers [--queue data/labeling_queue.csv]
"""
from __future__ import annotations

import argparse
import csv
import textwrap
from pathlib import Path

from sqlalchemy import select

from app.config import DATA_DIR, settings
from app.db import SessionLocal, init_database
from app.models import Paper
from app.scripts.sample_for_labeling import QUEUE_FIELDS

EVAL_FIELDS = [
    "paper_id",
    "gold_label",
    "gold_topics",
    "notes",
    "label_scope",
    "annotation_source",
    "evidence_level",
]
LABEL_KEYS = {
    "1": "CORE_RELEVANT",
    "2": "RELATED_RELEVANT",
    "3": "ADJACENT",
    "4": "UNCERTAIN",
    "5": "EXCLUDE",
}
HELP_LINE = (
    "1=CORE_RELEVANT 2=RELATED_RELEVANT 3=ADJACENT 4=UNCERTAIN 5=EXCLUDE  "
    "a=accept s=skip u=undo q=quit"
)


def load_queue(path: Path) -> list[dict[str, str]]:
    with open(path, newline="") as fh:
        return [dict(row) for row in csv.DictReader(fh)]


def save_queue(path: Path, rows: list[dict[str, str]]) -> None:
    with open(path, "w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=QUEUE_FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def eval_paper_ids(path: Path) -> set[str]:
    if not path.exists():
        return set()
    with open(path, newline="") as fh:
        return {
            (row.get("paper_id") or "").strip()
            for row in csv.DictReader(fh)
            if (row.get("paper_id") or "").strip()
        }


def append_eval_label(path: Path, paper_id: str, label: str, notes: str = "") -> bool:
    """Append one gold row; returns False (no write) if the paper is already there."""
    if paper_id in eval_paper_ids(path):
        return False
    write_header = not path.exists()
    with open(path, "a", newline="") as fh:
        writer = csv.writer(fh)
        if write_header:
            writer.writerow(EVAL_FIELDS)
        writer.writerow(
            [
                paper_id,
                label,
                "",
                notes,
                "AC_REPORTING",
                "interactive_labeling",
                "UNKNOWN",
            ]
        )
    return True


def remove_eval_label(path: Path, paper_id: str) -> None:
    if not path.exists():
        return
    with open(path, newline="") as fh:
        rows = [r for r in csv.DictReader(fh) if (r.get("paper_id") or "").strip() != paper_id]
    with open(path, "w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=EVAL_FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def apply_label(
    rows: list[dict[str, str]],
    idx: int,
    label: str,
    queue_path: Path,
    eval_labels_path: Path,
) -> bool:
    """Record a label: save the queue and append to the gold set.

    Returns True if a new eval_labels row was written (False = duplicate)."""
    rows[idx]["human_label"] = label
    save_queue(queue_path, rows)
    return append_eval_label(
        eval_labels_path, rows[idx]["paper_id"], label, rows[idx].get("notes", "")
    )


def undo_label(
    rows: list[dict[str, str]],
    idx: int,
    appended: bool,
    queue_path: Path,
    eval_labels_path: Path,
) -> None:
    rows[idx]["human_label"] = ""
    save_queue(queue_path, rows)
    if appended:
        remove_eval_label(eval_labels_path, rows[idx]["paper_id"])


def print_paper(
    row: dict[str, str], abstract: str | None, position: int, total: int, labeled: int
) -> None:
    print("\n" + "=" * 72)
    print(f"[{position}/{total}, {labeled} labeled this session]")
    print(f"Title: {row['title']}")
    print(f"Year : {row['year'] or '-'}    DOI: {row['doi'] or '-'}")
    if abstract:
        print(textwrap.fill(abstract, width=88, initial_indent="  ", subsequent_indent="  "))
    else:
        print("  (no abstract in DB)")
    print(f"Predicted: {row['predicted_label']} (confidence {row['confidence']})")
    for reason in filter(None, row["top_reasons"].split("; ")):
        print(f"  - {reason}")
    print(HELP_LINE)


def main() -> None:
    parser = argparse.ArgumentParser(description="Label papers from the sampling queue.")
    parser.add_argument("--queue", type=Path, default=DATA_DIR / "labeling_queue.csv")
    parser.add_argument("--eval-labels", type=Path, default=settings.eval_labels_csv)
    args = parser.parse_args()

    init_database()
    rows = load_queue(args.queue)
    with SessionLocal() as session:
        abstracts = {
            p.id: p.abstract for p in session.execute(select(Paper)).scalars()
        }

    pending = [i for i, r in enumerate(rows) if not r["human_label"].strip()]
    print(f"{len(rows)} papers in queue, {len(pending)} unlabeled. {HELP_LINE}")

    history: list[tuple[int, bool]] = []  # (row index, appended to eval_labels)
    labeled = 0
    pos = 0
    while pos < len(pending):
        idx = pending[pos]
        row = rows[idx]
        if row["human_label"].strip():  # already handled (after an undo jump)
            pos += 1
            continue
        print_paper(row, abstracts.get(row["paper_id"]), idx + 1, len(rows), labeled)
        choice = input("> ").strip().lower()
        if choice == "q":
            break
        if choice == "s":
            pos += 1
            continue
        if choice == "u":
            if not history:
                print("Nothing to undo.")
                continue
            undo_idx, appended = history.pop()
            undo_label(rows, undo_idx, appended, args.queue, args.eval_labels)
            labeled -= 1
            pos = pending.index(undo_idx)
            print(f"Undid {rows[undo_idx]['paper_id']}.")
            continue
        if choice == "a":
            label = row["predicted_label"]
        elif choice in LABEL_KEYS:
            label = LABEL_KEYS[choice]
        else:
            print(f"Unknown key. {HELP_LINE}")
            continue
        appended = apply_label(rows, idx, label, args.queue, args.eval_labels)
        if not appended:
            print(f"(already in {args.eval_labels.name}; queue updated only)")
        history.append((idx, appended))
        labeled += 1
        pos += 1

    remaining = sum(1 for r in rows if not r["human_label"].strip())
    print(f"\nSaved. {labeled} labeled this session, {remaining} still unlabeled.")


if __name__ == "__main__":
    main()
