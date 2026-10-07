"""Export or validate the deterministic PAS evidence wiki bundle."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.config import REPO_ROOT
from app.db import SessionLocal
from app.services.evidence_wiki_bundle import (
    export_evidence_wiki_bundle,
    validate_evidence_wiki_bundle,
)

DEFAULT_OUTPUT_DIR = REPO_ROOT / "evidence-wiki-bundle"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument(
        "--paper-id",
        action="append",
        dest="paper_ids",
        help="Export only this paper ID; repeat to select multiple papers.",
    )
    parser.add_argument(
        "--validate-only",
        action="store_true",
        help="Validate an existing bundle without reading or changing the database.",
    )
    args = parser.parse_args()

    if args.validate_only:
        report = validate_evidence_wiki_bundle(args.output_dir)
        print(json.dumps(report, indent=2, sort_keys=True))
        raise SystemExit(0 if report["status"] == "passed" else 1)

    with SessionLocal() as session:
        manifest = export_evidence_wiki_bundle(
            session,
            args.output_dir,
            paper_ids=args.paper_ids,
        )
        session.commit()
    print(
        json.dumps(
            {
                "output_dir": str(args.output_dir.resolve()),
                "pages": manifest["counts"]["pages"],
                "bundle_content_hash": manifest["bundle_content_hash"],
                "validation": "passed",
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
