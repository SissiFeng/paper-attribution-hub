"""arXiv: optional, opt-in per author (arxiv_query column). Catches preprints
days before OpenAlex indexes them. arXiv has no author ids, so matches are
name-based - only use for distinctive names."""
from __future__ import annotations

import xml.etree.ElementTree as ET
import time
from typing import Iterator

from . import http
from .models import Paper

API = "https://export.arxiv.org/api/query"
NS = {"a": "http://www.w3.org/2005/Atom", "arxiv": "http://arxiv.org/schemas/atom"}


def parse_feed(xml_bytes: bytes, tracked_name: str, since: str) -> list[Paper]:
    out = []
    for e in ET.fromstring(xml_bytes).findall("a:entry", NS):
        published = (e.findtext("a:published", "", NS) or "")[:10]
        if published < since:
            continue
        abs_url = e.findtext("a:id", "", NS).strip()
        out.append(Paper(
            title=" ".join(e.findtext("a:title", "", NS).split()),
            url=abs_url,
            doi=e.findtext("arxiv:doi", None, NS),
            arxiv_id=abs_url.rsplit("/abs/", 1)[-1],
            venue="arXiv",
            date=published,
            authors=[a.findtext("a:name", "", NS) for a in e.findall("a:author", NS)],
            tracked_authors=[tracked_name],
            abstract=" ".join(e.findtext("a:summary", "", NS).split()) or None,
            sources=["arxiv"],
        ))
    return out


def recent_preprints(queries: dict[str, str], since: str) -> Iterator[Paper]:
    """queries: tracked author name -> arXiv search_query."""
    first = True
    for name, q in queries.items():
        start = 0
        while True:
            if not first:
                time.sleep(3.1)
            first = False
            xml = http.request(API, {"search_query": q, "sortBy": "submittedDate",
                                     "sortOrder": "descending", "max_results": 100, "start": start})
            entries = ET.fromstring(xml).findall("a:entry", NS)
            if any("/api/errors" in e.findtext("a:id", "", NS) for e in entries):
                raise ValueError("arXiv returned an API error feed")
            yield from parse_feed(xml, name, since)
            if len(entries) < 100 or any(e.findtext("a:published", "", NS)[:10] < since for e in entries):
                break
            start += len(entries)
