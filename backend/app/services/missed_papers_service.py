"""Re-cut the v0.5 discovery queue by reviewer-facing angles.

v0.5 organized candidates by `status` (queued / approved / rejected).
v0.6 wants leadership-facing summaries that group them by *why* they look
interesting:

  - "Cites multiple CORE papers but isn't in our corpus"
  - "Second-degree to a new collaborator"
  - "Semantically close to CORE papers"
  - "From an AC partner institution but no AC author"

Each candidate may appear in multiple groups — that's intentional. The UI
shows each group separately so reviewers see the strongest rationale first.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import DiscoveryCandidate


GROUP_LABELS = {
    "cites_multiple_core": "Cites multiple AC core papers",
    "ac_coauthor_link": "Linked to AC member via OpenAlex authorship",
    "s2_semantic": "Semantically close to one of our CORE papers",
    "partner_institution": "From an AC partner institution",
}


@dataclass
class MissedPaperGroup:
    key: str
    label: str
    description: str
    candidate_ids: list[str]


def _classify_candidate_groups(
    candidate: DiscoveryCandidate,
) -> list[str]:
    """Return the set of group keys this candidate belongs to."""
    groups: set[str] = set()
    triggers = candidate.triggers or []

    cite_triggers = [t for t in triggers if t.get("strategy") == "cite_of_core"]
    if len(cite_triggers) >= 2:
        groups.add("cites_multiple_core")

    if any(t.get("strategy") == "ac_coauthor" for t in triggers):
        groups.add("ac_coauthor_link")

    if any(t.get("strategy") == "s2_recommend" for t in triggers):
        groups.add("s2_semantic")

    # AC partner affiliation heuristic: look at the candidate's recorded
    # affiliations against the set of partner institution names.
    affiliations = candidate.affiliations or []
    if any("toronto" in (a or "").lower() or "british columbia" in (a or "").lower()
           or "vector" in (a or "").lower()
           for a in affiliations):
        groups.add("partner_institution")

    return list(groups)


def build_missed_paper_groups(
    session: Session,
    *,
    status: str = "queued",
    limit_per_group: int = 25,
) -> list[MissedPaperGroup]:
    candidates = list(
        session.execute(
            select(DiscoveryCandidate).where(DiscoveryCandidate.status == status)
        ).scalars()
    )
    # Order candidates by confidence so each group's top-N is meaningful.
    candidates.sort(key=lambda c: -c.confidence)

    buckets: dict[str, list[str]] = defaultdict(list)
    for c in candidates:
        for key in _classify_candidate_groups(c):
            if len(buckets[key]) < limit_per_group:
                buckets[key].append(c.id)

    descriptions = {
        "cites_multiple_core": (
            "These papers cite two or more AC core papers but aren't in our "
            "corpus yet — strong signal they're built on AC work."
        ),
        "ac_coauthor_link": (
            "OpenAlex attributes these papers to an AC member's disambiguated "
            "author profile. They may have been auto-ingested via ORCID."
        ),
        "s2_semantic": (
            "Semantic Scholar's recommendation engine says these are similar "
            "to one of our CORE papers. Weakest signal — review carefully."
        ),
        "partner_institution": (
            "Authors with an AC partner institution affiliation. Often a "
            "useful seed even when no AC member is on the paper directly."
        ),
    }

    return [
        MissedPaperGroup(
            key=key,
            label=GROUP_LABELS.get(key, key),
            description=descriptions.get(key, ""),
            candidate_ids=ids,
        )
        for key, ids in buckets.items()
        if ids
    ]
