"""Tests for the gold-label expansion workflow (sampler + labeling CLI helpers)."""
from __future__ import annotations

from pathlib import Path

import pytest

EVAL_HEADER = "paper_id,gold_label,gold_topics,notes"


def _add_paper(session, pid: str, label: str, confidence: float, *, doi=None, title=None):
    from app.models import Paper, PaperClassification

    paper = Paper(
        id=pid,
        title=title or f"Paper {pid}",
        doi=doi,
        year=2024,
        abstract=f"Abstract for {pid}.",
    )
    paper.classification = PaperClassification(
        id=f"cls-{pid}", paper_id=pid, label=label, confidence=confidence,
        reasons=[f"reason for {pid}"],
    )
    session.add(paper)


@pytest.fixture()
def eval_labels_file(tmp_path: Path) -> Path:
    path = tmp_path / "eval_labels.csv"
    path.write_text(f"{EVAL_HEADER}\nG001,CORE_RELEVANT,,seed row\n")
    return path


def test_sampler_excludes_already_labeled(session, eval_labels_file):
    from app.scripts.sample_for_labeling import sample_queue

    # G001 is in eval_labels; X-dupe-doi / X-dupe-title duplicate it.
    _add_paper(session, "G001", "CORE_RELEVANT", 0.9, doi="10.1/dup", title="A Gold Paper")
    _add_paper(session, "X-dupe-doi", "CORE_RELEVANT", 0.9,
               doi="https://doi.org/10.1/DUP", title="Different title")
    _add_paper(session, "X-dupe-title", "CORE_RELEVANT", 0.9, title="A Gold  PAPER!")
    _add_paper(session, "X-fresh", "ADJACENT", 0.6)
    session.flush()

    rows, _ = sample_queue(session, n=10, seed=42, eval_labels_path=eval_labels_file)
    assert [r["paper_id"] for r in rows] == ["X-fresh"]


def test_sampler_oversamples_uncertain_and_mid(session, tmp_path):
    from app.scripts.sample_for_labeling import sample_queue

    for i in range(20):
        _add_paper(session, f"CORE{i:02d}", "CORE_RELEVANT", 0.9)
    for i in range(20):
        _add_paper(session, f"UNC{i:02d}", "UNCERTAIN", 0.6)
    session.flush()

    rows, breakdown = sample_queue(
        session, n=20, seed=42, eval_labels_path=tmp_path / "missing.csv"
    )
    assert len(rows) == 20
    assert breakdown[("UNCERTAIN", "mid")][1] > breakdown[("CORE_RELEVANT", "high")][1]
    # Caps respected: sampled never exceeds available.
    for available, sampled in breakdown.values():
        assert sampled <= available


def test_sampler_deterministic_with_seed(session, tmp_path):
    from app.scripts.sample_for_labeling import sample_queue

    for i in range(30):
        _add_paper(session, f"P{i:03d}", "ADJACENT", 0.3 + (i % 3) * 0.25)
    session.flush()

    missing = tmp_path / "missing.csv"
    rows_a, _ = sample_queue(session, n=10, seed=42, eval_labels_path=missing)
    rows_b, _ = sample_queue(session, n=10, seed=42, eval_labels_path=missing)
    assert [r["paper_id"] for r in rows_a] == [r["paper_id"] for r in rows_b]


def test_confidence_bands():
    from app.scripts.sample_for_labeling import confidence_band

    assert confidence_band(0.49) == "low"
    assert confidence_band(0.5) == "mid"
    assert confidence_band(0.75) == "mid"
    assert confidence_band(0.76) == "high"


def test_queue_csv_schema(session, tmp_path):
    from app.scripts.sample_for_labeling import QUEUE_FIELDS, sample_queue, write_queue

    _add_paper(session, "P001", "UNCERTAIN", 0.6, doi="10.1/x")
    session.flush()
    rows, _ = sample_queue(session, n=5, seed=42, eval_labels_path=tmp_path / "missing.csv")
    out = tmp_path / "queue.csv"
    write_queue(out, rows)

    lines = out.read_text().splitlines()
    assert lines[0] == ",".join(QUEUE_FIELDS)
    assert QUEUE_FIELDS == [
        "paper_id", "doi", "title", "year", "predicted_label",
        "confidence", "top_reasons", "human_label", "notes",
    ]
    assert lines[1].startswith("P001,10.1/x,")


def test_append_eval_label_no_duplicates(eval_labels_file):
    from app.scripts.label_papers import append_eval_label

    assert append_eval_label(eval_labels_file, "P100", "ADJACENT") is True
    assert append_eval_label(eval_labels_file, "P100", "EXCLUDE") is False
    assert append_eval_label(eval_labels_file, "G001", "CORE_RELEVANT") is False

    lines = eval_labels_file.read_text().splitlines()
    assert lines[0] == EVAL_HEADER
    assert lines[1:] == ["G001,CORE_RELEVANT,,seed row", "P100,ADJACENT,,"]


def test_apply_label_and_undo(tmp_path, eval_labels_file):
    from app.scripts.label_papers import apply_label, load_queue, undo_label
    from app.scripts.sample_for_labeling import QUEUE_FIELDS, write_queue

    queue = tmp_path / "queue.csv"
    rows = [
        {f: "" for f in QUEUE_FIELDS} | {"paper_id": "P200", "predicted_label": "UNCERTAIN"},
        {f: "" for f in QUEUE_FIELDS} | {"paper_id": "P201", "predicted_label": "ADJACENT"},
    ]
    write_queue(queue, rows)

    appended = apply_label(rows, 0, "CORE_RELEVANT", queue, eval_labels_file)
    assert appended is True
    # Crash-safe: queue file already reflects the answer.
    assert load_queue(queue)[0]["human_label"] == "CORE_RELEVANT"
    assert "P200,CORE_RELEVANT" in eval_labels_file.read_text()

    undo_label(rows, 0, appended, queue, eval_labels_file)
    assert load_queue(queue)[0]["human_label"] == ""
    assert "P200" not in eval_labels_file.read_text()
    # The pre-existing gold row survives the undo rewrite.
    assert "G001,CORE_RELEVANT,,seed row" in eval_labels_file.read_text()


def test_eval_labels_consumable_by_eval_service(eval_labels_file):
    from app.scripts.label_papers import append_eval_label
    from app.services.eval_service import load_gold_labels

    append_eval_label(eval_labels_file, "P300", "RELATED_RELEVANT")
    gold = load_gold_labels(eval_labels_file)
    assert gold == {"G001": "CORE_RELEVANT", "P300": "RELATED_RELEVANT"}
