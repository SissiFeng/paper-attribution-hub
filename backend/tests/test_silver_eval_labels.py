"""Silver eval-label derivation from curated AC-gold signals."""
from __future__ import annotations

import csv
from pathlib import Path

from app.config import settings
from app.models import Paper, PaperClassification
from app.scripts.build_silver_eval_labels import (
    RULE_MEMBER,
    RULE_MEMBER_ACK,
    RULE_NO_MEMBER,
    derive_silver_rows,
    run,
)
from app.services.eval_service import load_gold_labels, run_evaluation


def _seed_ac_gold(session) -> None:
    session.add_all(
        [
            # rule a: members + acknowledged
            Paper(
                id="SG_A",
                title="Closed-loop perovskite discovery",
                provenance="ac_gold",
                ac_members_matched=["Alan Aspuru-Guzik"],
                ac_acknowledged=True,
                sdl_tags=["SDL 0 - AI & Automation"],
            ),
            # rule b: members, no ack flags
            Paper(
                id="SG_B",
                title="Robotic synthesis platform",
                provenance="ac_gold",
                ac_members_matched=["Curtis Berlinguette"],
            ),
            # rule c: no members matched
            Paper(
                id="SG_C",
                title="An AC-listed paper without member match",
                provenance="ac_gold",
                ac_members_matched=None,
            ),
            # not ac_gold → never silver-labeled
            Paper(id="SG_D", title="Scopus batch paper", provenance="scopus_batch"),
        ]
    )
    session.commit()


def test_rules_a_b_c_and_no_negatives(session):
    _seed_ac_gold(session)
    rows, counts = derive_silver_rows(session, hand_labeled_ids=set())
    by_id = {r["paper_id"]: r for r in rows}

    assert by_id["SG_A"]["gold_label"] == "CORE_RELEVANT"
    assert by_id["SG_A"]["notes"] == f"silver:{RULE_MEMBER_ACK}"
    assert by_id["SG_A"]["gold_topics"] == "sdl_0_ai_automation"

    assert by_id["SG_B"]["gold_label"] == "CORE_RELEVANT"
    assert by_id["SG_B"]["notes"] == f"silver:{RULE_MEMBER}"
    assert by_id["SG_B"]["gold_topics"] == ""

    assert by_id["SG_C"]["gold_label"] == "RELATED_RELEVANT"
    assert by_id["SG_C"]["notes"] == f"silver:{RULE_NO_MEMBER}"

    assert "SG_D" not in by_id
    # d: no silver negatives, ever.
    assert all(r["gold_label"] != "EXCLUDE" for r in rows)
    assert counts[RULE_MEMBER_ACK] == 1
    assert counts[RULE_MEMBER] == 1
    assert counts[RULE_NO_MEMBER] == 1


def test_skips_papers_already_hand_labeled(session):
    _seed_ac_gold(session)
    rows, counts = derive_silver_rows(session, hand_labeled_ids={"SG_A"})
    assert "SG_A" not in {r["paper_id"] for r in rows}
    assert counts["skipped_hand_labeled"] == 1
    assert len(rows) == 2


def test_dry_run_prints_counts_and_writes_nothing(session, tmp_path):
    _seed_ac_gold(session)
    out = tmp_path / "eval_labels_silver.csv"
    counts = run(out, hand_labels=settings.eval_labels_csv, dry_run=True)
    assert not out.exists()
    assert counts[RULE_MEMBER_ACK] == 1
    assert counts[RULE_MEMBER] == 1
    assert counts[RULE_NO_MEMBER] == 1


def test_output_schema_matches_hand_curated_csv(session, tmp_path):
    _seed_ac_gold(session)
    out = tmp_path / "eval_labels_silver.csv"
    run(out, hand_labels=settings.eval_labels_csv, dry_run=False)

    hand_header = settings.eval_labels_csv.read_text().splitlines()[0]
    silver_header = out.read_text().splitlines()[0]
    assert silver_header == hand_header == "paper_id,gold_label,gold_topics,notes"
    with out.open(newline="") as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == 3
    assert all(r["notes"].startswith("silver:") for r in rows)


def test_refuses_to_overwrite_hand_curated_file(session, tmp_path):
    hand = tmp_path / "eval_labels.csv"
    hand.write_text("paper_id,gold_label,gold_topics,notes\n")
    import pytest

    with pytest.raises(SystemExit):
        run(hand, hand_labels=hand, dry_run=True)


def _write_labels(path: Path, rows: list[tuple[str, str]]) -> Path:
    lines = ["paper_id,gold_label,gold_topics,notes"]
    lines += [f"{pid},{label},," for pid, label in rows]
    path.write_text("\n".join(lines) + "\n")
    return path


def test_load_gold_labels_hand_wins_over_silver(tmp_path):
    hand = _write_labels(tmp_path / "hand.csv", [("SG_E1", "EXCLUDE")])
    silver = _write_labels(
        tmp_path / "silver.csv",
        [("SG_E1", "CORE_RELEVANT"), ("SG_E2", "CORE_RELEVANT")],
    )
    gold = load_gold_labels(hand, silver_path=silver)
    assert gold == {"SG_E1": "EXCLUDE", "SG_E2": "CORE_RELEVANT"}


def test_run_evaluation_include_silver_merge(session, tmp_path):
    """run_eval --include-silver path: hand label wins for SG_E1."""
    for pid in ("SG_E1", "SG_E2"):
        session.add(Paper(id=pid, title=f"paper {pid}"))
        session.add(
            PaperClassification(
                id=f"cls_{pid}", paper_id=pid, label="CORE_RELEVANT", confidence=0.9
            )
        )
    session.commit()

    hand = _write_labels(tmp_path / "hand.csv", [("SG_E1", "EXCLUDE")])
    silver = _write_labels(
        tmp_path / "silver.csv",
        [("SG_E1", "CORE_RELEVANT"), ("SG_E2", "CORE_RELEVANT")],
    )
    report = run_evaluation(session, hand, silver_labels_path=silver)
    assert report.n_evaluated == 2
    # SG_E1 gold=EXCLUDE (hand wins) → wrong; SG_E2 gold=CORE (silver) → right.
    assert report.accuracy == 0.5
