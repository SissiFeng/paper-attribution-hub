"""
Seed paper_propositions table with structured claims for the 11 mock papers.

Covers the 4 example queries on the RetrievalPage:
  1. "Which papers use Bayesian optimization for materials discovery?"
  2. "What automation platforms are used in self-driving labs?"
  3. "Papers funded by NSERC on closed-loop synthesis"
  4. "Compare active learning approaches across SDL papers"

Usage:
    python backend/scripts/seed_propositions.py
    python backend/scripts/seed_propositions.py --db path/to/paper_attribution.db
"""
from __future__ import annotations

import argparse
import sqlite3
import uuid
from datetime import UTC, datetime
from pathlib import Path

DEFAULT_DB = Path(__file__).parent.parent / "paper_attribution.db"


def _id() -> str:
    return str(uuid.uuid4())


def _now() -> str:
    return datetime.now(UTC).isoformat()


PROPOSITIONS: list[dict] = [
    # ── P001: Autonomous closed-loop discovery of organic laser materials ──
    {
        "paper_id": "P001",
        "predicate": "uses_method",
        "object_value": "Bayesian optimization",
        "object_key": "bayesian_optimization",
        "claim_text": "Uses Bayesian optimization to autonomously discover organic laser materials.",
        "confidence": 0.97,
        "source_section": "abstract",
    },
    {
        "paper_id": "P001",
        "predicate": "uses_method",
        "object_value": "closed-loop experimentation",
        "object_key": "closed_loop",
        "claim_text": "Performs closed-loop experimentation across thousands of candidate molecules.",
        "confidence": 0.95,
        "source_section": "abstract",
    },
    {
        "paper_id": "P001",
        "predicate": "uses_method",
        "object_value": "robotic synthesis",
        "object_key": "robotic_synthesis",
        "claim_text": "Combines robotic synthesis with Bayesian optimization in a self-driving laboratory.",
        "confidence": 0.93,
        "source_section": "abstract",
    },
    {
        "paper_id": "P001",
        "predicate": "belongs_to_topic",
        "object_value": "self-driving laboratory",
        "object_key": "sdl",
        "claim_text": "Presents a self-driving laboratory platform for autonomous materials discovery.",
        "confidence": 0.98,
        "source_section": "abstract",
    },
    {
        "paper_id": "P001",
        "predicate": "funded_by",
        "object_value": "Acceleration Consortium",
        "object_key": "ac",
        "claim_text": "Research supported by the Acceleration Consortium on autonomous materials discovery.",
        "confidence": 0.85,
        "source_section": "acknowledgements",
    },

    # ── P002: Bayesian optimization for catalyst screening ──
    {
        "paper_id": "P002",
        "predicate": "uses_method",
        "object_value": "Bayesian optimization",
        "object_key": "bayesian_optimization",
        "claim_text": "Applies Bayesian optimization to accelerate catalyst screening for CO2 reduction.",
        "confidence": 0.98,
        "source_section": "abstract",
    },
    {
        "paper_id": "P002",
        "predicate": "uses_method",
        "object_value": "high-throughput experimental platform",
        "object_key": "high_throughput",
        "claim_text": "Integrates the optimizer with a high-throughput experimental platform.",
        "confidence": 0.90,
        "source_section": "abstract",
    },
    {
        "paper_id": "P002",
        "predicate": "belongs_to_topic",
        "object_value": "catalyst discovery",
        "object_key": "catalysis",
        "claim_text": "Applies data-driven Bayesian methods to catalyst discovery and screening.",
        "confidence": 0.92,
        "source_section": "abstract",
    },

    # ── P003: Graph neural networks for protein folding ──
    {
        "paper_id": "P003",
        "predicate": "uses_method",
        "object_value": "graph neural networks",
        "object_key": "gnn",
        "claim_text": "Proposes a graph neural network architecture for predicting protein 3D structures.",
        "confidence": 0.97,
        "source_section": "abstract",
    },
    {
        "paper_id": "P003",
        "predicate": "belongs_to_topic",
        "object_value": "machine learning for structural biology",
        "object_key": "ml_biology",
        "claim_text": "Applies deep learning to structural biology using AlphaFold-derived training data.",
        "confidence": 0.91,
        "source_section": "abstract",
    },

    # ── P004: Workflow orchestration for autonomous chemistry labs ──
    {
        "paper_id": "P004",
        "predicate": "uses_method",
        "object_value": "workflow orchestration",
        "object_key": "workflow_orchestration",
        "claim_text": "Describes a software framework for orchestrating multi-instrument workflows in autonomous labs.",
        "confidence": 0.96,
        "source_section": "abstract",
    },
    {
        "paper_id": "P004",
        "predicate": "uses_method",
        "object_value": "automation platform",
        "object_key": "automation_platform",
        "claim_text": "Implements an automation platform supporting closed-loop campaigns and reproducible workflows.",
        "confidence": 0.94,
        "source_section": "abstract",
    },
    {
        "paper_id": "P004",
        "predicate": "uses_method",
        "object_value": "closed-loop automation",
        "object_key": "closed_loop",
        "claim_text": "Software framework supports closed-loop experimental campaigns in chemistry labs.",
        "confidence": 0.92,
        "source_section": "abstract",
    },
    {
        "paper_id": "P004",
        "predicate": "belongs_to_topic",
        "object_value": "self-driving laboratory",
        "object_key": "sdl",
        "claim_text": "Enables autonomous chemistry laboratory operations through workflow automation.",
        "confidence": 0.95,
        "source_section": "abstract",
    },

    # ── P005: Active learning for molecular property prediction ──
    {
        "paper_id": "P005",
        "predicate": "uses_method",
        "object_value": "active learning",
        "object_key": "active_learning",
        "claim_text": "Applies active learning strategies to reduce labeling cost in molecular property prediction.",
        "confidence": 0.98,
        "source_section": "abstract",
    },
    {
        "paper_id": "P005",
        "predicate": "uses_method",
        "object_value": "machine learning for molecular properties",
        "object_key": "ml_molecular",
        "claim_text": "Benchmarks active learning approaches on QM9 and custom molecular datasets.",
        "confidence": 0.93,
        "source_section": "abstract",
    },
    {
        "paper_id": "P005",
        "predicate": "belongs_to_topic",
        "object_value": "molecular property prediction",
        "object_key": "molecular_ml",
        "claim_text": "Improves efficiency of molecular property prediction using active learning.",
        "confidence": 0.96,
        "source_section": "abstract",
    },

    # ── P006: Self-driving laboratory for thin-film photovoltaics ──
    {
        "paper_id": "P006",
        "predicate": "uses_method",
        "object_value": "closed-loop optimization",
        "object_key": "closed_loop",
        "claim_text": "Uses closed-loop optimization to maximize perovskite solar cell stability.",
        "confidence": 0.96,
        "source_section": "abstract",
    },
    {
        "paper_id": "P006",
        "predicate": "uses_method",
        "object_value": "autonomous synthesis and characterization",
        "object_key": "autonomous_synthesis",
        "claim_text": "Autonomously synthesizes and characterizes thin-film perovskite solar cells.",
        "confidence": 0.95,
        "source_section": "abstract",
    },
    {
        "paper_id": "P006",
        "predicate": "belongs_to_topic",
        "object_value": "self-driving laboratory",
        "object_key": "sdl",
        "claim_text": "Self-driving laboratory platform for photovoltaic materials discovery.",
        "confidence": 0.97,
        "source_section": "abstract",
    },

    # ── P007: Survey on transformers (non-SDL, should not match SDL queries) ──
    {
        "paper_id": "P007",
        "predicate": "uses_method",
        "object_value": "transformer architectures",
        "object_key": "transformers",
        "claim_text": "Reviews BERT, GPT, and T5 transformer architectures for NLP tasks.",
        "confidence": 0.95,
        "source_section": "abstract",
    },
    {
        "paper_id": "P007",
        "predicate": "belongs_to_topic",
        "object_value": "natural language processing",
        "object_key": "nlp",
        "claim_text": "Comprehensive survey of transformer models for natural language processing.",
        "confidence": 0.97,
        "source_section": "abstract",
    },

    # ── P008: Robotic automation in pharmaceutical compound screening ──
    {
        "paper_id": "P008",
        "predicate": "uses_method",
        "object_value": "robotic platform",
        "object_key": "robotic_platform",
        "claim_text": "Describes a robotic platform for high-throughput pharmaceutical compound screening.",
        "confidence": 0.97,
        "source_section": "abstract",
    },
    {
        "paper_id": "P008",
        "predicate": "uses_method",
        "object_value": "automation platform",
        "object_key": "automation_platform",
        "claim_text": "Uses robotic automation with on-line UV/Vis readout for compound screening.",
        "confidence": 0.93,
        "source_section": "abstract",
    },
    {
        "paper_id": "P008",
        "predicate": "uses_method",
        "object_value": "high-throughput screening",
        "object_key": "high_throughput",
        "claim_text": "Applies high-throughput robotic screening to pharmaceutical compound discovery.",
        "confidence": 0.95,
        "source_section": "abstract",
    },

    # ── P009: Closed-loop optimization of electrochemical synthesis at UofT ──
    {
        "paper_id": "P009",
        "predicate": "uses_method",
        "object_value": "Bayesian optimization",
        "object_key": "bayesian_optimization",
        "claim_text": "Integrates Bayesian optimization for autonomous electrochemical synthesis.",
        "confidence": 0.97,
        "source_section": "abstract",
    },
    {
        "paper_id": "P009",
        "predicate": "uses_method",
        "object_value": "robotic electrochemistry platform",
        "object_key": "robotic_platform",
        "claim_text": "Integrates a robotic electrochemistry platform with Bayesian optimization.",
        "confidence": 0.96,
        "source_section": "abstract",
    },
    {
        "paper_id": "P009",
        "predicate": "uses_method",
        "object_value": "closed-loop optimization",
        "object_key": "closed_loop",
        "claim_text": "Closed-loop campaign explored thousands of electrochemical synthesis conditions.",
        "confidence": 0.95,
        "source_section": "abstract",
    },
    {
        "paper_id": "P009",
        "predicate": "affiliated_with",
        "object_value": "University of Toronto",
        "object_key": "uoft",
        "claim_text": "Research conducted at the University of Toronto electrochemistry group.",
        "confidence": 0.99,
        "source_section": "abstract",
    },
    {
        "paper_id": "P009",
        "predicate": "funded_by",
        "object_value": "NSERC",
        "object_key": "nserc",
        "claim_text": "NSERC-funded closed-loop synthesis research at University of Toronto.",
        "confidence": 0.88,
        "source_section": "acknowledgements",
    },
    {
        "paper_id": "P009",
        "predicate": "funded_by",
        "object_value": "Acceleration Consortium",
        "object_key": "ac",
        "claim_text": "Acceleration Consortium affiliated research on autonomous electrochemical synthesis.",
        "confidence": 0.84,
        "source_section": "acknowledgements",
    },
    {
        "paper_id": "P009",
        "predicate": "belongs_to_topic",
        "object_value": "self-driving laboratory",
        "object_key": "sdl",
        "claim_text": "Demonstrates autonomous closed-loop electrochemical synthesis.",
        "confidence": 0.96,
        "source_section": "abstract",
    },

    # ── P010: Review of climate models (non-SDL) ──
    {
        "paper_id": "P010",
        "predicate": "belongs_to_topic",
        "object_value": "climate science",
        "object_key": "climate",
        "claim_text": "Broad review of climate modeling approaches used in IPCC reports.",
        "confidence": 0.96,
        "source_section": "abstract",
    },

    # ── P011: Surrogate models for chemical reactivity ──
    {
        "paper_id": "P011",
        "predicate": "uses_method",
        "object_value": "surrogate models",
        "object_key": "surrogate_models",
        "claim_text": "Benchmarks surrogate models for chemical reactivity prediction across organic transformations.",
        "confidence": 0.95,
        "source_section": "abstract",
    },
    {
        "paper_id": "P011",
        "predicate": "uses_method",
        "object_value": "machine learning for chemistry",
        "object_key": "ml_chemistry",
        "claim_text": "Applies machine learning surrogate models to predict chemical reactivity.",
        "confidence": 0.90,
        "source_section": "abstract",
    },
]


def seed(db_path: Path) -> int:
    conn = sqlite3.connect(db_path)
    now = _now()

    # Check existing propositions
    existing = conn.execute("SELECT COUNT(*) FROM paper_propositions").fetchone()[0]
    if existing > 0:
        print(f"⚠  paper_propositions already has {existing} rows. Use --force to overwrite.")
        conn.close()
        return existing

    inserted = 0
    for p in PROPOSITIONS:
        conn.execute(
            """INSERT INTO paper_propositions
               (id, paper_id, predicate, object_value, object_key,
                source_section, claim_text, confidence, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                _id(), p["paper_id"], p["predicate"], p["object_value"],
                p.get("object_key"), p.get("source_section"),
                p["claim_text"], p["confidence"], now,
            ),
        )
        inserted += 1

    conn.commit()
    conn.close()
    print(f"✓  Inserted {inserted} propositions into {db_path}")
    return inserted


def clear(db_path: Path) -> None:
    conn = sqlite3.connect(db_path)
    n = conn.execute("DELETE FROM paper_propositions").rowcount
    conn.commit()
    conn.close()
    print(f"  Cleared {n} existing propositions.")


def main():
    parser = argparse.ArgumentParser(description="Seed paper propositions for demo")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB, help="Path to paper_attribution.db")
    parser.add_argument("--force", action="store_true", help="Clear existing and re-seed")
    args = parser.parse_args()

    if not args.db.exists():
        print(f"ERROR: database not found at {args.db}")
        return

    if args.force:
        clear(args.db)

    seed(args.db)

    # Verify
    conn = sqlite3.connect(args.db)
    rows = conn.execute(
        "SELECT predicate, COUNT(*) as n FROM paper_propositions GROUP BY predicate ORDER BY n DESC"
    ).fetchall()
    conn.close()
    print("\nProposition breakdown:")
    for predicate, n in rows:
        print(f"  {predicate:30s} {n:3d}")


if __name__ == "__main__":
    main()
