"""SDL lab registry + paper→lab mapping.

Labs are seeded from data/sdl_labs.yaml. A paper is linked to a lab when any
of its authors exact-matches the lab's member_author_names roster on folded
names (normalization_service.normalize_name — diacritics stripped, lowercased).
No fuzzy matching in v1. Papers with curated Paper.ac_members_matched names
additionally get explicit "ac_members" links at confidence 1.0.
"""
from __future__ import annotations

import re
from pathlib import Path

import yaml
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Author, Paper, PaperAuthor, PaperLabLink, SdlLab
from app.services.normalization_service import normalize_name

ROSTER_LINK_CONFIDENCE = 0.9
AC_MEMBERS_LINK_CONFIDENCE = 1.0

_TRAILING_PAREN_RE = re.compile(r"\s*\([^)]*\)\s*$")


def _split_member_names(values: list[str]) -> list[str]:
    """ac_members_matched stores raw "AC Members" strings: comma-separated
    names, sometimes suffixed with "(Deactivated)"."""
    names: list[str] = []
    for value in values:
        for part in value.split(","):
            part = _TRAILING_PAREN_RE.sub("", part).strip()
            if part:
                names.append(part)
    return names


def load_labs_from_yaml(session: Session, path: str | Path | None = None) -> dict:
    """Upsert SdlLab rows from the registry yaml. Returns summary counts."""
    from app.config import settings

    p = Path(path or settings.sdl_labs_yaml)
    raw = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    created = 0
    updated = 0
    for entry in raw.get("labs") or []:
        lab = session.get(SdlLab, entry["id"])
        if lab is None:
            lab = SdlLab(id=entry["id"])
            session.add(lab)
            created += 1
        else:
            updated += 1
        lab.name = entry["name"]
        lab.institution = entry["institution"]
        lab.pi_names = list(entry.get("pi_names") or [])
        lab.domain_focus = entry["domain_focus"]
        lab.platform_stack = entry.get("platform_stack")
        lab.automation_level = entry.get("automation_level")
        lab.member_author_names = list(entry.get("member_author_names") or [])
    session.flush()
    return {"created": created, "updated": updated}


def map_papers_to_labs(session: Session) -> dict:
    """Link papers to labs.

    Pass 1: any paper author exact-matches a lab roster on folded names →
    source="author_roster", confidence 0.9.
    Pass 2: curated Paper.ac_members_matched names matched the same way →
    source="ac_members", confidence 1.0; an existing author_roster link for
    the same (paper, lab) is upgraded in place.

    Idempotent. Returns summary counts.
    """
    labs = list(session.execute(select(SdlLab)).scalars())
    roster: dict[str, set[str]] = {}
    for lab in labs:
        for name in lab.member_author_names or []:
            folded = normalize_name(name)
            if folded:
                roster.setdefault(folded, set()).add(lab.id)

    links = {
        (link.paper_id, link.lab_id): link
        for link in session.execute(select(PaperLabLink)).scalars()
    }
    created = 0
    links_ac_members = 0
    links_upgraded = 0
    papers_linked: set[str] = set()
    if roster:
        rows = session.execute(
            select(PaperAuthor.paper_id, Author).join(
                Author, PaperAuthor.author_id == Author.id
            )
        ).all()
        for paper_id, author in rows:
            folded_names = {author.normalized_name or normalize_name(author.canonical_name)}
            folded_names.update(normalize_name(a) for a in (author.aliases or []))
            lab_ids: set[str] = set()
            for folded in folded_names:
                lab_ids |= roster.get(folded, set())
            for lab_id in lab_ids:
                if (paper_id, lab_id) in links:
                    continue
                link = PaperLabLink(
                    paper_id=paper_id,
                    lab_id=lab_id,
                    source="author_roster",
                    confidence=ROSTER_LINK_CONFIDENCE,
                )
                session.add(link)
                links[(paper_id, lab_id)] = link
                created += 1
                papers_linked.add(paper_id)

        member_rows = session.execute(
            select(Paper.id, Paper.ac_members_matched).where(
                Paper.ac_members_matched.is_not(None)
            )
        ).all()
        for paper_id, members in member_rows:
            lab_ids = set()
            for name in _split_member_names(members or []):
                lab_ids |= roster.get(normalize_name(name), set())
            for lab_id in lab_ids:
                link = links.get((paper_id, lab_id))
                if link is None:
                    link = PaperLabLink(
                        paper_id=paper_id,
                        lab_id=lab_id,
                        source="ac_members",
                        confidence=AC_MEMBERS_LINK_CONFIDENCE,
                    )
                    session.add(link)
                    links[(paper_id, lab_id)] = link
                    links_ac_members += 1
                    papers_linked.add(paper_id)
                elif link.source == "author_roster":
                    link.source = "ac_members"
                    link.confidence = AC_MEMBERS_LINK_CONFIDENCE
                    links_upgraded += 1
    session.flush()
    return {
        "labs": len(labs),
        "links_created": created,
        "links_ac_members": links_ac_members,
        "links_upgraded": links_upgraded,
        "papers_linked": len(papers_linked),
    }
