"""Apply the updated ac_members.csv to existing Author records in the DB.

The production DB was seeded via ingest_scopus_batch, which creates Author
rows from paper metadata but only marks is_ac_member=True for the ~23 names
that appeared in the AC Publications gold set. The CSV now has 82 members.

This script:
  1. Reads data/ac_members.csv (82 members with aliases)
  2. Fuzzy-matches each member against all existing Author records
  3. Marks matched Authors is_ac_member=True and updates aliases/institution
  4. Creates new Author rows for any member with no existing record
  5. Re-stamps Paper.ac_members_matched for papers those authors wrote
  6. Calls classify_all() to re-label papers with the updated signal

Usage:
    python -m app.scripts.apply_ac_members [--dry-run] [--skip-classify]
"""
from __future__ import annotations

import argparse
import csv
import sys
from collections import defaultdict

from sqlalchemy import select

from app.config import settings
from app.db import SessionLocal
from app.models import Author, Institution, Paper, PaperAuthor
from app.services.normalization_service import normalize_name

DATA_DIR = settings.people_csv.parent


def _load_csv_members() -> list[dict]:
    """Read ac_members.csv and return list of member dicts."""
    members = []
    with open(settings.people_csv, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if not row.get("is_ac_member", "").lower().startswith("t"):
                continue
            aliases_raw = row.get("aliases", "") or ""
            aliases = [a.strip() for a in aliases_raw.split(";") if a.strip()]
            members.append({
                "person_id": row["person_id"].strip(),
                "name": row["name"].strip(),
                "aliases": aliases,
                "institution": (row.get("institution") or "").strip() or None,
                "orcid": (row.get("orcid") or "").strip() or None,
                "role": (row.get("role") or "").strip() or None,
            })
    return members


def _build_norm_map(members: list[dict]) -> dict[str, dict]:
    """norm(name/alias) → member dict."""
    m: dict[str, dict] = {}
    for mb in members:
        m[normalize_name(mb["name"])] = mb
        for alias in mb["aliases"]:
            n = normalize_name(alias)
            if n and n not in m:
                m[n] = mb
    return m


def run(dry_run: bool = False, skip_classify: bool = False) -> None:
    members = _load_csv_members()
    norm_map = _build_norm_map(members)
    print(f"Loaded {len(members)} AC members from CSV ({len(norm_map)} name variants)")

    with SessionLocal() as session:
        # ── Step 1: match existing Author records ────────────────────────
        all_authors = list(session.execute(select(Author)).scalars())
        institutions_by_name: dict[str, Institution] = {
            inst.canonical_name: inst
            for inst in session.execute(select(Institution)).scalars()
        }

        matched_author_ids: set[str] = set()   # DB author IDs we marked
        csv_id_to_author: dict[str, Author] = {}  # CSV person_id → DB Author

        for author in all_authors:
            n = normalize_name(author.canonical_name)
            member = norm_map.get(n)
            if member is None:
                # Try aliases stored on the author
                for alias in (author.aliases or []):
                    member = norm_map.get(normalize_name(alias))
                    if member:
                        break
            if member is None:
                continue

            # Match found — update the Author record
            matched_author_ids.add(author.id)
            csv_id_to_author[member["person_id"]] = author
            if not dry_run:
                author.is_ac_member = True
                # Merge aliases from CSV
                existing_aliases = set(author.aliases or [])
                for alias in member["aliases"]:
                    if alias.lower() != author.canonical_name.lower():
                        existing_aliases.add(alias)
                author.aliases = sorted(existing_aliases)
                if member["orcid"] and not author.orcid:
                    author.orcid = member["orcid"]
                if member["institution"] and not author.institution_id:
                    inst = institutions_by_name.get(member["institution"])
                    if inst:
                        author.institution_id = inst.id
            print(f"  {'[DRY] ' if dry_run else ''}Matched: {author.canonical_name} (id={author.id[:20]})")

        # ── Step 2: create Author records for unmatched CSV members ──────
        new_count = 0
        for mb in members:
            if mb["person_id"] in csv_id_to_author:
                continue  # already matched via name
            # Check if any existing author uses this CSV person_id
            existing = session.execute(
                select(Author).where(Author.id == mb["person_id"])
            ).scalar_one_or_none()
            if existing:
                csv_id_to_author[mb["person_id"]] = existing
                matched_author_ids.add(existing.id)
                if not dry_run:
                    existing.is_ac_member = True
                print(f"  {'[DRY] ' if dry_run else ''}ID match: {existing.canonical_name}")
                continue

            # No existing record — create one
            inst = institutions_by_name.get(mb["institution"] or "")
            new_author = Author(
                id=mb["person_id"],
                canonical_name=mb["name"],
                aliases=mb["aliases"],
                normalized_name=normalize_name(mb["name"]),
                orcid=mb["orcid"],
                institution_id=inst.id if inst else None,
                role=mb["role"],
                is_ac_member=True,
            )
            csv_id_to_author[mb["person_id"]] = new_author
            if not dry_run:
                session.add(new_author)
            new_count += 1
            print(f"  {'[DRY] ' if dry_run else ''}Created: {mb['name']}")

        if not dry_run:
            session.flush()

        print(f"\nMatched {len(matched_author_ids)} existing authors, created {new_count} new")

        # ── Step 3: update Paper.ac_members_matched ──────────────────────
        # For every paper authored by a newly-identified AC member, ensure
        # their name appears in Paper.ac_members_matched.
        if not dry_run:
            paper_updates: dict[str, set[str]] = defaultdict(set)
            for author_id in matched_author_ids | {a.id for a in csv_id_to_author.values()}:
                pa_rows = session.execute(
                    select(PaperAuthor.paper_id)
                    .where(PaperAuthor.author_id == author_id)
                ).scalars().all()
                # Get canonical name for this author
                author = session.get(Author, author_id)
                if not author:
                    continue
                for paper_id in pa_rows:
                    paper_updates[paper_id].add(author.canonical_name)

            updated_papers = 0
            for paper_id, new_members in paper_updates.items():
                paper = session.get(Paper, paper_id)
                if not paper:
                    continue
                existing = set(paper.ac_members_matched or [])
                merged = existing | new_members
                if merged != existing:
                    paper.ac_members_matched = sorted(merged)
                    updated_papers += 1

            session.commit()
            print(f"Updated ac_members_matched on {updated_papers} papers")

        # ── Step 4: reclassify ───────────────────────────────────────────
        if not dry_run and not skip_classify:
            print("\nRunning classify_all() …")
            from app.services.relevance_classifier import classify_all
            with SessionLocal() as cls_session:
                classify_all(cls_session)
            print("Classification complete.")
        elif skip_classify:
            print("\nSkipped classify (--skip-classify). Run POST /admin/reclassify when ready.")

    print("\nDone.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true",
                        help="Print matches without writing to DB")
    parser.add_argument("--skip-classify", action="store_true",
                        help="Skip classify_all() at the end (run it separately)")
    args = parser.parse_args()
    run(dry_run=args.dry_run, skip_classify=args.skip_classify)
    sys.exit(0)
