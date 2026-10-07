"""Validate the live LLM wiki vault and optionally rebuild safe projections."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.config import settings
from app.scripts.export_llm_wiki import export_llm_wiki
from app.services.llm_wiki_lifecycle import lint_llm_wiki_vault


DEFAULT_WIKI_ROOT = settings.llm_wiki_root


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--wiki-root", type=Path, default=DEFAULT_WIKI_ROOT)
    parser.add_argument("--stale-after-days", type=int, default=30)
    parser.add_argument(
        "--fix",
        action="store_true",
        help="Rebuild deterministic projections before running the read-only lint.",
    )
    parser.add_argument("--json", action="store_true", help="Print JSON output.")
    args = parser.parse_args()

    ingest = export_llm_wiki(args.wiki_root) if args.fix else None
    report = lint_llm_wiki_vault(
        args.wiki_root,
        stale_after_days=max(args.stale_after_days, 0),
    )
    payload = report.to_dict()
    if ingest is not None:
        payload["ingest"] = ingest
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        counts = payload["issue_counts"]
        print(
            f"Wiki lint {payload['status']}: {payload['pages_scanned']} pages, "
            f"{counts['error']} errors, {counts['warning']} warnings, "
            f"{counts['review']} review items."
        )
        for issue in report.issues:
            print(f"[{issue.severity}] {issue.code}: {issue.path} — {issue.message}")
    raise SystemExit(0 if report.status == "passed" else 1)


if __name__ == "__main__":
    main()
