"""Bridge: copy TDM-downloaded files into PAS fulltexts and run the ingest script.

The PAS ingest script matches files by paper-id in the filename stem. The TDM
manifest maps DOI → Zotero Key, so we copy each downloaded file to
`data/fulltexts/<key>.pdf` (or `.xml`/`.html`) and then invoke the existing
ingestion + embedding pipeline.

Usage:
    python ingest_to_pas.py --manifest /path/to/tdm/manifest.csv \\
        --downloads /path/to/tdm/downloads \\
        --fulltexts /path/to/paper-attribution-system/data/fulltexts

Note: this only works when the PAS DB already contains papers keyed by the
same Zotero Key. If the corpus uses a different key scheme, edit the
`paper_id` function below.
"""
from __future__ import annotations

import argparse
import csv
import shutil
import subprocess
import sys
from pathlib import Path


def paper_id(zotero_key: str) -> str:
    """Map a Zotero item key to the PAS paper id used as filename stem."""
    return zotero_key.strip()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--downloads", type=Path, required=True)
    parser.add_argument("--fulltexts", type=Path, required=True)
    parser.add_argument("--no-ingest", action="store_true",
                        help="Only copy files, don't run the ingest script")
    parser.add_argument("--skip-embed", action="store_true")
    args = parser.parse_args()

    copied = 0
    with args.manifest.open(newline="") as fh:
        for row in csv.DictReader(fh):
            if row.get("status") != "downloaded":
                continue
            fname = row.get("file") or ""
            if not fname:
                continue
            src = args.downloads / fname
            if not src.exists():
                print(f"  ! missing {src}", file=sys.stderr)
                continue
            pid = paper_id(row.get("key") or "")
            if not pid:
                print(f"  ! empty key for {row.get('doi')}", file=sys.stderr)
                continue
            dst = args.fulltexts / f"{pid}{src.suffix}"
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
            copied += 1
            print(f"  ✓ {pid}{src.suffix} <- {fname}", file=sys.stderr)

    print(f"Copied {copied} files", file=sys.stderr)
    if copied and not args.no_ingest:
        cmd = [
            sys.executable, "-m", "app.scripts.ingest_fulltexts",
            "--dir", str(args.fulltexts),
        ]
        if args.skip_embed:
            cmd.append("--skip-embed")
        subprocess.run(cmd, cwd=Path(__file__).parent.parent / "backend", check=True)


if __name__ == "__main__":
    main()
