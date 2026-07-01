"""Export a GNN-ready graph ML dataset from the current paper corpus.

Usage:
    python -m app.scripts.export_graph_ml_dataset --output-dir outputs/graph_ml
"""
from __future__ import annotations

import argparse
from pathlib import Path

from app.config import REPO_ROOT
from app.db import SessionLocal
from app.services.graph_ml_dataset_service import write_graph_ml_dataset

DEFAULT_OUTPUT_DIR = REPO_ROOT / "outputs" / "graph_ml"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args()

    with SessionLocal() as session:
        manifest = write_graph_ml_dataset(session, args.output_dir)

    print(
        "Wrote graph ML dataset to "
        f"{args.output_dir} "
        f"({manifest['node_count']} nodes, "
        f"{manifest['edge_count']} edges, "
        f"{manifest['label_count']} labels)"
    )


if __name__ == "__main__":
    main()
