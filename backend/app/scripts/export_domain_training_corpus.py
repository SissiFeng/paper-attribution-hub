"""Export deterministic scientific chunks for domain model adaptation."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from app.config import REPO_ROOT
from app.db import SessionLocal, init_database
from app.services.domain_training_corpus import export_domain_training_corpus

DEFAULT_OUTPUT_DIR = REPO_ROOT / "outputs" / "domain-training-corpus"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument(
        "--paper-id",
        action="append",
        dest="paper_ids",
        help="Export only this paper ID. Repeat to select multiple papers.",
    )
    parser.add_argument("--limit", type=int)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    if args.limit is not None and args.limit < 1:
        parser.error("--limit must be positive")

    init_database()
    with SessionLocal() as session:
        result = export_domain_training_corpus(
            session,
            args.output_dir,
            paper_ids=args.paper_ids,
            limit=args.limit,
        )
    payload = {
        **result.manifest,
        "corpus_path": str(result.corpus_path),
        "manifest_path": str(result.manifest_path),
        "changed_files": result.changed_files,
    }
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(
            "Domain training corpus export complete:",
            f"papers={result.manifest['paper_count']}",
            f"records={result.manifest['record_count']}",
            f"duplicates={result.manifest['duplicate_count']}",
            f"changed_files={result.changed_files}",
            f"output={result.corpus_path}",
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
