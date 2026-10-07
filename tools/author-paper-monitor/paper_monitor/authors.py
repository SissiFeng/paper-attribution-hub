"""authors.csv: the one list a human maintains.

Columns: name, orcid, openalex_ids, arxiv_query
  openalex_ids  '|'-separated; OpenAlex sometimes splits one person into
                several ids, list them all. Filled by `resolve` from ORCID.
  arxiv_query   optional arXiv search, e.g. au:Aspuru_Guzik_A. Only set it
                for distinctive names: arXiv has no author ids.
"""
from __future__ import annotations

import csv
from dataclasses import dataclass, field
from pathlib import Path

from . import openalex
from .models import normalize_title

COLUMNS = ["name", "orcid", "openalex_ids", "arxiv_query"]


@dataclass
class Author:
    name: str
    orcid: str = ""
    openalex_ids: list[str] = field(default_factory=list)
    arxiv_query: str = ""


def load(path: Path) -> list[Author]:
    with open(path, newline="", encoding="utf-8") as f:
        return [
            Author(
                name=r["name"].strip(),
                orcid=(r.get("orcid") or "").strip().rstrip("/").rsplit("/", 1)[-1],
                openalex_ids=[openalex.short_id(x.strip()) for x in (r.get("openalex_ids") or "").split("|") if x.strip()],
                arxiv_query=(r.get("arxiv_query") or "").strip(),
            )
            for r in csv.DictReader(f) if (r.get("name") or "").strip()
        ]


def save(path: Path, authors: list[Author]) -> None:
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNS)
        w.writeheader()
        for a in authors:
            w.writerow({"name": a.name, "orcid": a.orcid,
                        "openalex_ids": "|".join(a.openalex_ids),
                        "arxiv_query": a.arxiv_query})


def resolve(authors: list[Author]) -> list[str]:
    """Fill openalex_ids from ORCID (certain). For name-only rows, return
    candidate lines for a human to choose from - never auto-pick by name."""
    report = []
    for a in authors:
        if a.openalex_ids:
            continue
        if a.orcid:
            hit = openalex.author_by_orcid(a.orcid)
            names = [hit.get("display_name", ""), *(hit.get("display_name_alternatives") or [])] if hit else []
            expected = set((normalize_title(a.name) or "").split())
            if hit and any(expected <= set((normalize_title(n) or "").split()) for n in names):
                a.openalex_ids = [openalex.short_id(hit["id"])]
                report.append(f"OK    {a.name}: {a.openalex_ids[0]} (via ORCID)")
                continue
            if hit:
                report.append(f"MISMATCH {a.name}: ORCID {a.orcid} belongs to {hit.get('display_name')!r}; verify manually")
            else:
                report.append(f"WARN  {a.name}: ORCID {a.orcid} not found in OpenAlex")
        report.append(f"PICK  {a.name}: paste the right id(s) into openalex_ids:")
        candidates = openalex.search_authors(a.name)
        import os
        if os.environ.get('JEV_MODE') == 'shadow':
            from .jev_monitor import author_candidates
            public = [{'name': c.get('display_name'), 'orcid': c.get('orcid'),
                       'institution': ', '.join(i['display_name'] for i in c.get('last_known_institutions') or [])} for c in candidates]
            author_candidates({'name': a.name, 'orcid': a.orcid}, public)
        else:
            public = [{} for _ in candidates]
        for c, advice in zip(candidates, public, strict=True):
            suffix = ''
            if advice.get('jev_advice'):
                suggestion = advice['jev_advice']
                suffix = ' | Jev shadow: ' + str(suggestion.get('decision', {}).get('choice', suggestion['status']))
            report.append("        " + openalex.describe_author(c) + suffix)
    return report
