"""Crossref: DOI authority. Only called for papers about to be posted, to
confirm the DOI resolves and take Crossref's title/venue over OpenAlex's."""
from __future__ import annotations

import urllib.error
import urllib.parse

from . import http
from .models import Paper

BASE = "https://api.crossref.org/works/"


def enrich(p: Paper) -> None:
    if not p.doi or p.doi.startswith("10.48550/"):
        return  # arXiv DOIs are DataCite, not Crossref
    try:
        msg = http.get_json(BASE + urllib.parse.quote(p.doi))["message"]
    except (urllib.error.HTTPError, urllib.error.URLError, KeyError, ValueError):
        return  # enrichment is best-effort; never blocks posting
    if msg.get("title"):
        p.title = " ".join(msg["title"][0].split())
    if msg.get("container-title"):
        p.venue = msg["container-title"][0]
    if "crossref" not in p.sources:
        p.sources.append("crossref")
