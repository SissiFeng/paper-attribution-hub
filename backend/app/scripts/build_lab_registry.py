"""Build data/sdl_labs.yaml (the SDL lab registry) from the AC member CSV.

One lab is generated per PI row (role == "PI"). Non-PI rows (Staff / Member /
Affiliate) are skipped: the CSV carries no lab affiliation for them, so there
is nothing to attach them to. The CSV's orcid column is dropped — nothing
downstream consumes it.

Lab ids are slugified PI surnames ("aspuru-guzik-lab"); when two PIs share a
folded surname, each colliding id gets the given-name initial appended
("li-b-lab"), which keeps ids deterministic regardless of row order.

Usage:
    python -m app.scripts.build_lab_registry [--members-csv PATH]
        [--output PATH] [--dry-run]
"""
from __future__ import annotations

import argparse
import csv
import sys
from collections import Counter
from pathlib import Path

import yaml

from app.services.normalization_service import normalize_name

HEADER = """\
# SDL lab registry — GENERATED FILE, do not edit by hand.
#
# Source: data/ac_members.csv (one lab per PI row; non-PI rows skipped).
# Regenerate with:
#   python -m app.scripts.build_lab_registry
#
# Fields per lab (consumed by lab_service.load_labs_from_yaml):
#   id                  stable slug (PI surname), used as primary key
#   name                display name ("<PI name> Group")
#   institution         host institution
#   pi_names            principal investigators
#   domain_focus        short free-text domain descriptor (empty: unknown)
#   member_author_names author roster matched against paper authors
#                       (exact match on folded names — diacritics stripped,
#                       lowercased; see normalization_service.normalize_name)
"""


def _slug(name: str, *, with_initial: bool) -> str:
    tokens = normalize_name(name).split()
    surname = tokens[-1]
    if with_initial and len(tokens) > 1:
        return f"{surname}-{tokens[0][0]}-lab"
    return f"{surname}-lab"


def build_labs(members_csv: str | Path) -> list[dict]:
    """Return lab registry entries (one per PI row) from the member CSV."""
    with open(members_csv, encoding="utf-8", newline="") as fh:
        pis = [row for row in csv.DictReader(fh) if row["role"] == "PI"]

    surname_counts = Counter(normalize_name(r["name"]).split()[-1] for r in pis)
    labs: list[dict] = []
    seen: set[str] = set()
    for row in pis:
        name = " ".join(row["name"].split())
        surname = normalize_name(name).split()[-1]
        slug = _slug(name, with_initial=surname_counts[surname] > 1)
        if slug in seen:
            raise ValueError(f"lab id collision: {slug} ({name})")
        seen.add(slug)
        aliases = [a.strip() for a in (row.get("aliases") or "").split(";") if a.strip()]
        labs.append(
            {
                "id": slug,
                "name": f"{name} Group",
                "institution": row["institution"],
                "pi_names": [name],
                "domain_focus": "",
                "member_author_names": [name, *aliases],
            }
        )
    return labs


def write_registry(labs: list[dict], output: str | Path) -> None:
    body = yaml.safe_dump({"labs": labs}, sort_keys=False, allow_unicode=True)
    Path(output).write_text(HEADER + "\n" + body, encoding="utf-8")


def main() -> int:
    from app.config import settings

    parser = argparse.ArgumentParser(
        description="Build the SDL lab registry yaml from the AC member CSV."
    )
    parser.add_argument("--members-csv", type=Path, default=settings.people_csv)
    parser.add_argument("--output", type=Path, default=settings.sdl_labs_yaml)
    parser.add_argument(
        "--dry-run", action="store_true", help="Print summary without writing."
    )
    args = parser.parse_args()

    labs = build_labs(args.members_csv)
    if args.dry_run:
        print(f"Would write {len(labs)} labs to {args.output}.")
    else:
        write_registry(labs, args.output)
        print(f"Wrote {len(labs)} labs to {args.output}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
