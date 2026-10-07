"""OpenAlex: author resolution + new-works polling (primary source)."""
from __future__ import annotations

import os
import datetime
import urllib.error
from typing import Iterator

from . import http
from .models import Paper

BASE = "https://api.openalex.org"
BATCH = 50  # author ids per OR-filter; OpenAlex allows up to 100
PAPER_TYPES = {"article", "review", "preprint", "book-chapter"}
WORK_FIELDS = ("id,doi,title,publication_date,type,primary_location,"
               "authorships,ids,is_retracted,abstract_inverted_index,keywords")


def _params(**kw) -> dict:
    p = dict(kw)
    if os.environ.get("OPENALEX_API_KEY"):
        p["api_key"] = os.environ["OPENALEX_API_KEY"]
    if os.environ.get("CONTACT_EMAIL"):
        p["mailto"] = os.environ["CONTACT_EMAIL"]
    return p


def short_id(openalex_id: str) -> str:
    return openalex_id.rsplit("/", 1)[-1]


def author_by_orcid(orcid: str) -> dict | None:
    try:
        return http.get_json(f"{BASE}/authors/orcid:{orcid}", _params())
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        raise


def search_authors(name: str, limit: int = 5) -> list[dict]:
    data = http.get_json(f"{BASE}/authors", _params(search=name, **{"per-page": limit}))
    return data.get("results", [])


def describe_author(a: dict) -> str:
    insts = a.get("last_known_institutions") or []
    inst = insts[0]["display_name"] if insts else "?"
    return (f"{short_id(a['id'])}  {a.get('display_name')}  | {inst} | "
            f"works={a.get('works_count')} | orcid={a.get('orcid') or '-'}")


def _abstract(inv: dict | None) -> str | None:
    if not inv:
        return None
    pos = sorted((i, w) for w, idxs in inv.items() for i in idxs)
    return " ".join(w for _, w in pos)


def work_to_paper(work: dict, id_to_name: dict[str, str]) -> Paper:
    loc = work.get("primary_location") or {}
    src = loc.get("source") or {}
    authors, tracked = [], []
    for a in work.get("authorships") or []:
        au = a.get("author") or {}
        authors.append(au.get("display_name") or "")
        name = id_to_name.get(short_id(au.get("id") or ""))
        if name and name not in tracked:
            tracked.append(name)
    return Paper(
        openalex_id=short_id(work["id"]) if work.get("id") else None,
        title=work.get("title") or "",
        url=work.get("doi") or loc.get("landing_page_url") or work.get("id"),
        doi=work.get("doi"),
        venue=src.get("display_name"),
        date=work.get("publication_date"),
        authors=authors,
        tracked_authors=tracked,
        abstract=_abstract(work.get("abstract_inverted_index")),
        sources=["openalex"],
        keywords=[k["display_name"] for k in (work.get("keywords") or []) if isinstance(k.get("display_name"), str)][:6],
    )


def recent_works(id_to_name: dict[str, str], since: str) -> Iterator[Paper]:
    """All works by any tracked OpenAlex author id published on/after `since`.

    Uses cursor paging and no cache, so nothing is silently truncated.
    `id_to_name` maps short OpenAlex ids (A123...) to the tracked author's name.
    """
    until = datetime.datetime.now(datetime.timezone.utc).date().isoformat()
    ids = sorted(id_to_name)
    for i in range(0, len(ids), BATCH):
        batch = "|".join(ids[i:i + BATCH])
        cursor = "*"
        seen_cursors = set()
        while cursor:
            if cursor in seen_cursors:
                raise ValueError("OpenAlex repeated a cursor; refusing an incomplete baseline")
            seen_cursors.add(cursor)
            data = http.get_json(f"{BASE}/works", _params(
                filter=f"author.id:{batch},from_publication_date:{since},to_publication_date:{until},type:article|review|preprint|book-chapter",
                sort="publication_date:desc",
                select=WORK_FIELDS,
                cursor=cursor,
                **{"per-page": 100},
            ))
            if not isinstance(data.get("results"), list) or not isinstance(data.get("meta"), dict):
                raise ValueError("OpenAlex response is missing results/meta")
            for w in data.get("results", []):
                if w.get("type") not in PAPER_TYPES or w.get("is_retracted") or not w.get("title"):
                    continue
                yield work_to_paper(w, id_to_name)
            cursor = (data.get("meta") or {}).get("next_cursor")
