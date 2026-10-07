"""Resolve PDF-derived affiliation candidates against official ROR records."""
from __future__ import annotations

from collections import defaultdict
import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import PaperEntity
from app.services.external.ror_client import RorClient
from app.services.normalization_service import normalize_institution


ROR_AFFILIATION_CONFIDENCE = 0.98
_GENERIC_ORGANIZATION_TOKENS = {
    "academy",
    "and",
    "center",
    "centre",
    "college",
    "for",
    "institute",
    "institution",
    "laboratory",
    "of",
    "research",
    "technology",
    "the",
    "university",
}


def _ror_display_name(organization: dict) -> str | None:
    names = organization.get("names") or []
    for name in names:
        if "ror_display" in (name.get("types") or []):
            value = str(name.get("value") or "").strip()
            if value:
                return value
    return None


def _significant_tokens(value: str) -> set[str]:
    normalized = normalize_institution(value)
    return {
        token
        for token in re.findall(r"[\w\-]+", normalized)
        if token not in _GENERIC_ORGANIZATION_TOKENS and len(token) > 1
    }


def _candidate_supports_canonical(
    candidate: str,
    canonical_name: str,
) -> bool:
    """Reject chosen ROR matches whose canonical identity is absent in text."""
    canonical_tokens = _significant_tokens(canonical_name)
    candidate_tokens = _significant_tokens(candidate)
    return bool(canonical_tokens) and canonical_tokens.issubset(candidate_tokens)


def resolve_institution_entities_with_ror(
    session: Session,
    *,
    paper_ids: list[str] | None = None,
    client: RorClient | None = None,
) -> dict:
    """Keep only ROR-chosen, text-compatible institution candidates.

    Candidate evidence remains the Zotero Tier 1 PDF-derived Markdown line.
    ROR supplies canonical organization identity only; it does not add papers
    or infer author-to-institution relationships.
    """
    statement = (
        select(PaperEntity)
        .where(PaperEntity.entity_type == "institution")
        .order_by(PaperEntity.paper_id, PaperEntity.id)
    )
    if paper_ids:
        statement = statement.where(PaperEntity.paper_id.in_(paper_ids))
    rows = list(session.execute(statement).scalars())
    owns_client = client is None
    ror = client or RorClient()
    try:
        resolutions: dict[str, tuple[str, str] | None] = {}
        for candidate in sorted(
            {row.normalized_name for row in rows},
            key=str.casefold,
        ):
            match = ror.match_affiliation(session, candidate)
            organization = (match or {}).get("organization") or {}
            canonical_name = _ror_display_name(organization)
            ror_id = str(organization.get("id") or "").strip()
            if (
                not canonical_name
                or not ror_id
                or not _candidate_supports_canonical(
                    candidate,
                    canonical_name,
                )
            ):
                resolutions[candidate] = None
                continue
            resolutions[candidate] = (canonical_name, ror_id)
    finally:
        if owns_client:
            ror.close()

    grouped: dict[tuple[str, str], list[PaperEntity]] = defaultdict(list)
    rejected = 0
    for row in rows:
        resolution = resolutions.get(row.normalized_name)
        if resolution is None:
            session.delete(row)
            rejected += 1
            continue
        canonical_name, _ror_id = resolution
        grouped[(row.paper_id, canonical_name)].append(row)

    keepers: list[tuple[PaperEntity, str, str]] = []
    duplicates = 0
    for (_paper_id, canonical_name), candidates in grouped.items():
        candidates.sort(
            key=lambda row: (
                -float(row.confidence or 0.0),
                row.id,
            )
        )
        keeper = candidates[0]
        ror_id = resolutions[keeper.normalized_name][1]  # type: ignore[index]
        keepers.append((keeper, canonical_name, ror_id))
        for duplicate in candidates[1:]:
            session.delete(duplicate)
            duplicates += 1

    session.flush()
    for keeper, canonical_name, ror_id in keepers:
        keeper.normalized_name = canonical_name
        keeper.confidence = ROR_AFFILIATION_CONFIDENCE
        keeper.extractor = f"ror_affiliation_v2:{ror_id.rsplit('/', 1)[-1]}"
    session.flush()
    return {
        "candidates": len(rows),
        "matched": len(keepers),
        "rejected": rejected,
        "duplicates_merged": duplicates,
        "papers_with_resolved_institutions": len(
            {keeper.paper_id for keeper, _name, _ror_id in keepers}
        ),
        "unique_institutions": len(
            {canonical_name for _keeper, canonical_name, _ror_id in keepers}
        ),
    }
