"""CLI for TDM full-text retrieval.

Usage:
    python -m tdm_fetch --csv /path/to/lack_of_pdf_0806.csv [options]

Options:
    --out DIR          output dir (default: ./tdm_downloads)
    --dry-run          only print the plan for each DOI
    --force            ignore cache
    --keyed-only       only process publishers that need API keys
    --limit N          stop after N successful downloads
    --publisher X      only process one publisher key (e.g. rsc)
    --keyless          only process publishers that need no API key
"""
from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

import pandas as pd

from adapters import plan_for, publisher_for_doi
from fetch import Fetcher

_KEYED_PUBLISHERS = {"elsevier", "acs", "wiley", "ieee", "springer"}


def load_dois(csv_path: Path) -> list[tuple[str, str]]:
    """Return (doi, key) pairs, deduped by DOI.

    Handles both a normal Zotero export (DOI + Key columns) and the
    transposed variant where the DOI column is named 'DOI' but content
    detection is still safe.
    """
    df = pd.read_csv(csv_path, dtype=str)
    doi_col = key_col = None
    for col in df.columns:
        vals = df[col].dropna().astype(str)
        if vals.str.startswith("10.").mean() > 0.9:
            doi_col = col
        elif key_col is None:
            key_col = col
    if doi_col is None:
        raise ValueError(f"No DOI-looking column found in {csv_path}")
    seen: dict[str, str] = {}
    for _, row in df.iterrows():
        doi = str(row[doi_col] or "").strip()
        if not doi or doi in seen:
            continue
        seen[doi] = str(row[key_col] or "").strip() if key_col else ""
    return list(seen.items())


def main() -> None:
    parser = argparse.ArgumentParser(description="TDM full-text retrieval CLI")
    parser.add_argument("--csv", required=True, type=Path, help="Zotero CSV export")
    parser.add_argument("--out", type=Path, default=Path("./tdm_downloads"))
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--keyed-only", action="store_true")
    parser.add_argument("--keyless", action="store_true")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--publisher", default=None)
    args = parser.parse_args()

    papers = load_dois(args.csv)
    print(f"Loaded {len(papers)} unique DOIs from {args.csv}", file=sys.stderr)

    fetcher = Fetcher(args.out)
    try:
        done = 0
        rows = []
        for doi, key in papers:
            if args.publisher:
                if publisher_for_doi(doi) != args.publisher:
                    continue
            if args.keyless and publisher_for_doi(doi) in _KEYED_PUBLISHERS:
                continue
            if args.keyed_only and publisher_for_doi(doi) not in _KEYED_PUBLISHERS:
                continue
            r = fetcher.fetch_one(doi, dry_run=args.dry_run, force=args.force)
            rows.append({**r, "key": key})
            if r["status"] in ("downloaded", "planned"):
                done += 1
            if args.limit > 0 and done >= args.limit:
                break

        manifest = args.out / "manifest.csv"
        with manifest.open("w", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=["key", "doi", "publisher", "status", "reason", "source", "file"])
            w.writeheader()
            w.writerows(rows)
        print(f"Wrote {manifest}", file=sys.stderr)

        # summary
        from collections import Counter
        by_pub = Counter(r["publisher"] for r in rows)
        by_status = Counter(r["status"] for r in rows)
        print("By publisher:", dict(by_pub), file=sys.stderr)
        print("By status:", dict(by_status), file=sys.stderr)
    finally:
        fetcher.close()


if __name__ == "__main__":
    main()
