from __future__ import annotations

import re
import html
import unicodedata
from dataclasses import dataclass, field


def normalize_doi(doi: str | None) -> str | None:
    if not doi:
        return None
    doi = doi.strip().lower()
    doi = re.sub(r"^(https?://(dx\.)?doi\.org/|doi:)", "", doi)
    return doi or None


def normalize_title(title: str | None) -> str | None:
    if not title:
        return None
    t = unicodedata.normalize("NFKD", html.unescape(title))
    t = "".join(c for c in t if not unicodedata.combining(c)).lower()
    t = re.sub(r"<[^>]+>", " ", t)          # strip <i>, <sub> etc.
    t = " ".join("".join(c if c.isalnum() else " " for c in t).split())
    return t or None


ARXIV_DOI = re.compile(r"^10\.48550/arxiv\.(.+)$")


def arxiv_id_from_doi(doi: str | None) -> str | None:
    m = ARXIV_DOI.match(doi or "")
    return m.group(1) if m else None


@dataclass
class Paper:
    title: str
    url: str | None = None
    doi: str | None = None
    arxiv_id: str | None = None
    venue: str | None = None
    date: str | None = None               # YYYY-MM-DD when known
    authors: list[str] = field(default_factory=list)
    tracked_authors: list[str] = field(default_factory=list)  # names from authors.csv
    abstract: str | None = None
    sources: list[str] = field(default_factory=list)
    summary: str | None = None             # filled by the optional LLM step
    openalex_id: str | None = None
    doi_aliases: list[str] = field(default_factory=list)
    keywords: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.doi = normalize_doi(self.doi)
        self.doi_aliases = list(dict.fromkeys(
            d for d in (normalize_doi(x) for x in [self.doi, *self.doi_aliases]) if d))
        if not self.arxiv_id:
            self.arxiv_id = arxiv_id_from_doi(self.doi)
        if self.arxiv_id:
            self.arxiv_id = re.sub(r"v\d+$", "", self.arxiv_id)

    @property
    def title_key(self) -> str | None:
        return normalize_title(self.title)

    def merge(self, other: "Paper") -> None:
        """Fold a duplicate found in the same run into this record."""
        for name in ("url", "doi", "arxiv_id", "venue", "date", "abstract", "openalex_id"):
            if not getattr(self, name) and getattr(other, name):
                setattr(self, name, getattr(other, name))
        if not self.authors:
            self.authors = other.authors
        for lst, extra in ((self.tracked_authors, other.tracked_authors),
                           (self.doi_aliases, other.doi_aliases),
                           (self.sources, other.sources),
                           (self.keywords, other.keywords)):
            lst.extend(x for x in extra if x not in lst)


def title_matches(a: Paper, b: Paper) -> bool:
    """Title fallback is deliberately conservative; strong IDs take precedence."""
    if not a.title_key or a.title_key != b.title_key:
        return False
    if a.title_key in {"editorial", "introduction", "preface", "correction", "erratum"}:
        return False
    if a.title_key.startswith(("reply to", "comment on", "response to")):
        return False
    if a.arxiv_id and b.arxiv_id and a.arxiv_id != b.arxiv_id:
        return False
    ad = {d for d in a.doi_aliases if not d.startswith("10.48550/")}
    bd = {d for d in b.doi_aliases if not d.startswith("10.48550/")}
    if ad and bd and not ad.intersection(bd):
        return False
    # A title alone is insufficient evidence that two publications are the same.
    names = {normalize_title(n) for n in a.authors if n}
    return bool(names.intersection(normalize_title(n) for n in b.authors if n))
