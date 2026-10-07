"""Auditable institution comparison from paper-specific authorship metadata."""
from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime
import hashlib
import json
from typing import Literal

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, load_only

from app.models import MetadataEnrichmentRun, Paper, PaperAuthorshipMetadata
from app.services.filter_spec import (
    PAPER_SET_ENCODING,
    paper_set_sha256,
)
from app.services.normalization_service import normalize_institution


CreditScheme = Literal[
    "lead_balanced",
    "lead_heavy",
    "equal_fractional",
    "full_counting",
]
AuthorRole = Literal["all", "first", "last", "middle", "corresponding"]
AffiliationAllocation = Literal["fractional", "full"]
FocusScope = Literal["strict", "lineage"]

UOFT_NAME = "University of Toronto"
UOFT_ROR = "https://ror.org/03dbr7087"
UOFT_OPENALEX_ID = "https://openalex.org/I185261750"


@dataclass(frozen=True)
class InstitutionMetadataFilter:
    """Metadata fields that may define the institution-comparison paper set."""

    year_from: int | None = None
    year_to: int | None = None
    search: str | None = None

    def __post_init__(self) -> None:
        if (
            self.year_from is not None
            and self.year_to is not None
            and self.year_from > self.year_to
        ):
            raise ValueError("year_from must be less than or equal to year_to")
        normalized_search = (self.search or "").strip() or None
        object.__setattr__(self, "search", normalized_search)

CREDIT_SCHEMES: dict[str, dict[str, str]] = {
    "lead_balanced": {
        "label": "First/last balanced",
        "description": (
            "First and last authors receive 0.35 each; middle authors share 0.30. "
            "One- and two-author papers receive 1.00 and 0.50 per author."
        ),
    },
    "lead_heavy": {
        "label": "First/last heavy",
        "description": (
            "First and last authors receive 0.40 each; middle authors share 0.20. "
            "One- and two-author papers receive 1.00 and 0.50 per author."
        ),
    },
    "equal_fractional": {
        "label": "Equal fractional",
        "description": "Every author receives an equal 1/n share of the paper.",
    },
    "full_counting": {
        "label": "Full counting",
        "description": "Every selected author receives one full credit.",
    },
}

AUTHOR_ROLES: dict[str, dict[str, str]] = {
    "all": {
        "label": "All authors",
        "description": "Includes every author in the ordered author list.",
    },
    "first": {
        "label": "First author only",
        "description": (
            "Includes only the first-listed author. Corresponding-author status "
            "does not affect this filter."
        ),
    },
    "corresponding": {
        "label": "Corresponding author only",
        "description": (
            "Includes only authors explicitly marked as corresponding. Author "
            "order does not affect this filter."
        ),
    },
    "last": {
        "label": "Last author only",
        "description": "Includes only the last-listed author.",
    },
    "middle": {
        "label": "Middle authors only",
        "description": "Includes authors who are neither first-listed nor last-listed.",
    },
}


def build_authorship_institution_comparison(
    session: Session,
    filt: InstitutionMetadataFilter,
    *,
    credit_scheme: CreditScheme = "lead_balanced",
    author_role: AuthorRole = "all",
    affiliation_allocation: AffiliationAllocation = "fractional",
    focus_scope: FocusScope = "strict",
    min_affiliation_confidence: float = 0.8,
    limit: int = 30,
) -> dict:
    """Compare U of T with other institutions under an explicit credit policy."""
    if credit_scheme not in CREDIT_SCHEMES:
        raise ValueError(f"Unknown credit scheme: {credit_scheme}")
    if author_role not in AUTHOR_ROLES:
        raise ValueError(f"Unknown author role: {author_role}")
    if affiliation_allocation not in {"fractional", "full"}:
        raise ValueError(
            f"Unknown affiliation allocation: {affiliation_allocation}"
        )
    if focus_scope not in {"strict", "lineage"}:
        raise ValueError(f"Unknown focus scope: {focus_scope}")
    if not 0 <= min_affiliation_confidence <= 1:
        raise ValueError("min_affiliation_confidence must be between 0 and 1")
    if not 1 <= limit <= 200:
        raise ValueError("limit must be between 1 and 200")

    metadata_paper_query = select(Paper).options(
        load_only(
            Paper.id,
            Paper.title,
            Paper.abstract,
            Paper.year,
            Paper.raw_metadata,
            raiseload=True,
        )
    )
    candidate_papers = list(
        session.execute(_apply_metadata_filter(metadata_paper_query, filt)).scalars()
    )
    latest_run = _latest_successful_run(session)
    if latest_run is not None:
        papers = [
            paper
            for paper in candidate_papers
            if ((paper.raw_metadata or {}).get("tier1_metadata_agent") or {}).get(
                "input_sha256"
            )
            == latest_run.input_sha256
        ]
    else:
        metadata_paper_ids = {
            value
            for value in session.execute(
                select(PaperAuthorshipMetadata.paper_id).distinct()
            ).scalars()
        }
        papers = [paper for paper in candidate_papers if paper.id in metadata_paper_ids]
    papers.sort(key=lambda row: row.id)
    paper_by_id = {paper.id: paper for paper in papers}
    authorships = _load_authorships(session, list(paper_by_id))
    by_paper: dict[str, list[PaperAuthorshipMetadata]] = defaultdict(list)
    for row in authorships:
        by_paper[row.paper_id].append(row)
    for rows in by_paper.values():
        rows.sort(key=lambda row: (row.author_order, row.author_id))

    institution_rows: dict[str, dict] = {}
    focus_credit = 0.0
    focus_papers: set[str] = set()
    other_credit = 0.0
    other_papers: set[str] = set()
    selected_author_credits = 0.0
    resolved_author_credits = 0.0
    selected_authorships = 0
    authorships_with_resolved_affiliations = 0
    unresolved_assertions = 0
    below_threshold_assertions = 0
    papers_with_complete_institution_membership: set[str] = set()
    papers_with_incomplete_institution_membership: set[str] = set()
    papers_without_authorship_metadata: set[str] = set()
    source_breakdown: Counter[str] = Counter()
    yearly: dict[int, dict[str, object]] = defaultdict(
        lambda: {
            "paper_ids": set(),
            "focus_paper_ids": set(),
            "other_paper_ids": set(),
            "focus_weighted_credit": 0.0,
            "other_weighted_credit": 0.0,
        }
    )

    for paper in papers:
        rows = by_paper.get(paper.id, [])
        year_bucket = yearly[paper.year] if paper.year is not None else None
        if year_bucket is not None:
            year_bucket["paper_ids"].add(paper.id)
        if not rows:
            papers_without_authorship_metadata.add(paper.id)
            continue
        count = len(rows)
        paper_has_complete_institution_membership = True
        for index, row in enumerate(rows):
            is_first = index == 0
            is_last = index == count - 1
            eligible, unresolved, below_threshold = _eligible_affiliations(
                row.affiliations or [],
                min_affiliation_confidence=min_affiliation_confidence,
            )
            if not eligible or unresolved or below_threshold:
                paper_has_complete_institution_membership = False

            # Paper attribution is an unweighted, all-author footprint.  A paper
            # belongs to every institution represented by any eligible author;
            # role and credit filters apply only to contribution scores below.
            for affiliation in eligible:
                institution_key = _institution_key(affiliation)
                aggregate = institution_rows.setdefault(
                    institution_key,
                    _empty_institution_aggregate(affiliation),
                )
                aggregate["paper_ids"].add(paper.id)
                aggregate["authorship_ids"].add(f"{paper.id}|{row.author_id}")
                if _is_focus_affiliation(affiliation, focus_scope):
                    aggregate["contributes_to_focus"] = True
                    focus_papers.add(paper.id)
                    if year_bucket is not None:
                        year_bucket["focus_paper_ids"].add(paper.id)
                else:
                    other_papers.add(paper.id)
                    if year_bucket is not None:
                        year_bucket["other_paper_ids"].add(paper.id)

            if not _role_matches(
                author_role,
                is_first=is_first,
                is_last=is_last,
                is_corresponding=row.is_corresponding,
            ):
                continue
            credit = _author_credit(
                credit_scheme,
                index=index,
                author_count=count,
            )
            selected_authorships += 1
            selected_author_credits += credit
            unresolved_assertions += unresolved
            below_threshold_assertions += below_threshold
            if not eligible:
                continue
            authorships_with_resolved_affiliations += 1
            resolved_author_credits += credit
            allocation = credit if affiliation_allocation == "full" else credit / len(eligible)
            for affiliation in eligible:
                institution_key = _institution_key(affiliation)
                aggregate = institution_rows.setdefault(
                    institution_key,
                    _empty_institution_aggregate(affiliation),
                )
                aggregate["weighted_credit"] += allocation
                if is_first:
                    aggregate["first_author_credit"] += allocation
                if is_last:
                    aggregate["last_author_credit"] += allocation
                if row.is_corresponding is True:
                    aggregate["corresponding_author_credit"] += allocation
                source = str(affiliation.get("source") or "unknown")
                aggregate["sources"][source] += 1
                source_breakdown[source] += 1

                if _is_focus_affiliation(affiliation, focus_scope):
                    aggregate["contributes_to_focus"] = True
                    focus_credit += allocation
                    if year_bucket is not None:
                        year_bucket["focus_weighted_credit"] += allocation
                else:
                    other_credit += allocation
                    if year_bucket is not None:
                        year_bucket["other_weighted_credit"] += allocation

        if paper_has_complete_institution_membership:
            papers_with_complete_institution_membership.add(paper.id)
        else:
            papers_with_incomplete_institution_membership.add(paper.id)

    institutions = [_finalize_institution(row) for row in institution_rows.values()]
    institutions.sort(
        key=lambda row: (-row["weighted_credit"], -row["paper_count"], row["name"])
    )
    for rank, row in enumerate(institutions, start=1):
        row["rank"] = rank
        row["share_of_resolved_credit"] = _ratio(
            row["weighted_credit"],
            focus_credit + other_credit,
        )
    focus_rank = (
        1
        + sum(
            row["weighted_credit"] > round(focus_credit, 6)
            for row in institutions
        )
        if focus_credit
        else None
    )

    projection = {
        "credit_scheme": credit_scheme,
        "author_role": author_role,
        "affiliation_allocation": affiliation_allocation,
        "focus_scope": focus_scope,
        "focus_ror": UOFT_ROR,
        "focus_openalex_id": UOFT_OPENALEX_ID,
        "paper_count_rule": "any_affiliated_author",
        "min_affiliation_confidence": min_affiliation_confidence,
        "enrichment_run_id": latest_run.id if latest_run else None,
        "input_sha256": latest_run.input_sha256 if latest_run else None,
    }
    audit = _build_metadata_audit(
        filt,
        paper_ids=list(paper_by_id),
        algorithm="paper_authorship_institution_comparison.v3",
        metric_definitions={
            "weighted_credit": CREDIT_SCHEMES[credit_scheme]["description"],
            "paper_count": (
                "Distinct papers with at least one author affiliated with the "
                "institution. Author-role and credit-model filters do not change "
                "this count."
            ),
            "paper_institution_membership_coverage": (
                "Share of filtered papers for which every listed author has at "
                "least one eligible institution and every affiliation assertion "
                "is resolved above the configured confidence threshold."
            ),
            "affiliation_allocation": (
                "Each author credit is divided equally among eligible affiliations."
                if affiliation_allocation == "fractional"
                else "Each eligible affiliation receives the author's full credit."
            ),
            "focus_scope": (
                "Only exact University of Toronto ROR/OpenAlex assertions count."
                if focus_scope == "strict"
                else "Exact assertions and OpenAlex descendants of the University of Toronto count."
            ),
            "role_filter": (
                f"{AUTHOR_ROLES[author_role]['description']} Original author "
                "credit is not renormalized."
            ),
        },
        projection=projection,
    )
    audit["source_breakdown"] = dict(sorted(source_breakdown.items()))
    audit["authorship_metadata_rows"] = len(authorships)
    audit["scope_constraint"] = (
        "Latest successful Tier 1 metadata input"
        if latest_run
        else "Papers with paper-specific authorship metadata"
    )
    return {
        "available": bool(authorships),
        "scope": {
            "corpus_papers": len(papers),
            "papers_with_authorship_metadata": len(by_paper),
            "papers_with_complete_institution_membership": len(
                papers_with_complete_institution_membership
            ),
            "papers_with_incomplete_institution_membership": len(
                papers_with_incomplete_institution_membership
            ),
            "papers_without_authorship_metadata": len(
                papers_without_authorship_metadata
            ),
            "paper_institution_membership_coverage": _ratio(
                len(papers_with_complete_institution_membership),
                len(papers),
            ),
            "authorship_metadata_rows": len(authorships),
            "selected_authorships": selected_authorships,
            "authorships_with_resolved_affiliations": authorships_with_resolved_affiliations,
            "selected_author_credit": round(selected_author_credits, 6),
            "resolved_author_credit": round(resolved_author_credits, 6),
            "affiliation_credit_coverage": _ratio(
                resolved_author_credits,
                selected_author_credits,
            ),
            "unresolved_affiliation_assertions": unresolved_assertions,
            "below_threshold_affiliation_assertions": below_threshold_assertions,
            "institution_count": len(institutions),
        },
        "focus": {
            "name": UOFT_NAME,
            "ror": UOFT_ROR,
            "openalex_id": UOFT_OPENALEX_ID,
            "weighted_credit": round(focus_credit, 6),
            "paper_count": len(focus_papers),
            "share_of_resolved_credit": _ratio(
                focus_credit,
                focus_credit + other_credit,
            ),
            "rank": focus_rank,
        },
        "comparison": {
            "other_institutions_weighted_credit": round(other_credit, 6),
            "other_institutions_paper_count": len(other_papers),
            "focus_to_other_credit_ratio": (
                round(focus_credit / other_credit, 6) if other_credit else None
            ),
        },
        "institutions": institutions[:limit],
        "yearly": _finalize_yearly(yearly),
        "configuration": {
            **projection,
            "credit_scheme_label": CREDIT_SCHEMES[credit_scheme]["label"],
            "credit_scheme_description": CREDIT_SCHEMES[credit_scheme][
                "description"
            ],
            "author_role_label": AUTHOR_ROLES[author_role]["label"],
            "author_role_description": AUTHOR_ROLES[author_role]["description"],
        },
        "audit": audit,
    }


def comparison_options(session: Session) -> dict:
    years = list(
        session.execute(
            select(Paper.year)
            .join(
                PaperAuthorshipMetadata,
                PaperAuthorshipMetadata.paper_id == Paper.id,
            )
            .where(Paper.year.is_not(None))
            .distinct()
            .order_by(Paper.year)
        ).scalars()
    )
    latest_run = session.execute(
        select(MetadataEnrichmentRun).order_by(
            MetadataEnrichmentRun.started_at.desc()
        )
    ).scalars().first()
    return {
        "focus": {
            "name": UOFT_NAME,
            "ror": UOFT_ROR,
            "openalex_id": UOFT_OPENALEX_ID,
        },
        "years": years,
        "credit_schemes": [
            {"value": value, **definition}
            for value, definition in CREDIT_SCHEMES.items()
        ],
        "author_roles": [
            {"value": value, **definition}
            for value, definition in AUTHOR_ROLES.items()
        ],
        "affiliation_allocations": [
            {"value": "fractional", "label": "Fractional"},
            {"value": "full", "label": "Full"},
        ],
        "focus_scopes": [
            {"value": "strict", "label": "Exact U of T"},
            {"value": "lineage", "label": "U of T lineage"},
        ],
        "latest_enrichment_run": _run_payload(latest_run),
    }


def enrichment_status(session: Session) -> dict:
    latest_run = session.execute(
        select(MetadataEnrichmentRun).order_by(
            MetadataEnrichmentRun.started_at.desc()
        )
    ).scalars().first()
    successful_run = _latest_successful_run(session)
    paper_rows = list(
        session.execute(select(Paper.id, Paper.raw_metadata)).all()
    )
    target_paper_ids = {
        paper_id
        for paper_id, raw_metadata in paper_rows
        if successful_run is not None
        and ((raw_metadata or {}).get("tier1_metadata_agent") or {}).get(
            "input_sha256"
        )
        == successful_run.input_sha256
    }
    enriched_ids = {
        value
        for value in session.execute(
            select(PaperAuthorshipMetadata.paper_id).distinct()
        ).scalars()
    }
    paper_count = len(target_paper_ids)
    enriched_paper_count = len(target_paper_ids & enriched_ids)
    authorship_count = session.scalar(
        select(func.count()).select_from(PaperAuthorshipMetadata)
    ) or 0
    return {
        "paper_count": paper_count,
        "global_paper_count": len(paper_rows),
        "enriched_paper_count": enriched_paper_count,
        "authorship_count": authorship_count,
        "paper_coverage": _ratio(enriched_paper_count, paper_count),
        "latest_enrichment_run": _run_payload(latest_run),
    }


def _apply_metadata_filter(stmt, filt: InstitutionMetadataFilter):
    if filt.year_from is not None:
        stmt = stmt.where(Paper.year >= filt.year_from)
    if filt.year_to is not None:
        stmt = stmt.where(Paper.year <= filt.year_to)
    if filt.search:
        escaped = _escape_like(filt.search.casefold())
        pattern = f"%{escaped}%"
        stmt = stmt.where(
            or_(
                func.lower(Paper.title).like(pattern, escape="\\"),
                func.lower(Paper.abstract).like(pattern, escape="\\"),
            )
        )
    return stmt


def _escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _build_metadata_audit(
    filt: InstitutionMetadataFilter,
    *,
    paper_ids: list[str],
    algorithm: str,
    metric_definitions: dict[str, str],
    projection: dict,
) -> dict:
    filter_payload = {
        key: value
        for key, value in {
            "year_from": filt.year_from,
            "year_to": filt.year_to,
            "search": filt.search,
        }.items()
        if value is not None
    }
    filter_fingerprint = _sha256_json(filter_payload)
    canonical_projection = _canonical_json_value(projection)
    return {
        "filter": filter_payload,
        "filter_fingerprint": filter_fingerprint,
        "paper_set_sha256": paper_set_sha256(paper_ids),
        "paper_set_encoding": PAPER_SET_ENCODING,
        "included_papers": len(set(paper_ids)),
        "algorithm": algorithm,
        "metric_definitions": metric_definitions,
        "filter_semantics": {
            "allowed_metadata_filters": "year_from, year_to, and title-or-abstract search",
            "between_dimensions": "AND",
        },
        "data_boundary": {
            "mode": "metadata_only",
            "included": [
                "paper bibliographic metadata",
                "paper-specific authorship metadata",
                "resolved affiliation metadata",
                "metadata enrichment provenance",
            ],
            "excluded": [
                "full-text Markdown",
                "full-text chunks",
                "classification outputs",
                "human reviews",
                "RAG or extracted evidence",
            ],
        },
        "projection": canonical_projection,
        "projection_fingerprint": _sha256_json(canonical_projection),
        "generated_at": datetime.now(UTC).isoformat(),
    }


def _sha256_json(value: object) -> str:
    encoded = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _canonical_json_value(value):
    if isinstance(value, dict):
        return {
            key: _canonical_json_value(value[key])
            for key in sorted(value)
        }
    if isinstance(value, (list, tuple, set)):
        normalized = [_canonical_json_value(item) for item in value]
        return sorted(normalized, key=lambda item: json.dumps(item, sort_keys=True))
    return value


def _load_authorships(
    session: Session,
    paper_ids: list[str],
) -> list[PaperAuthorshipMetadata]:
    if not paper_ids:
        return []
    return list(
        session.execute(
            select(PaperAuthorshipMetadata).where(
                PaperAuthorshipMetadata.paper_id.in_(paper_ids)
            )
        ).scalars()
    )


def _author_credit(
    scheme: CreditScheme,
    *,
    index: int,
    author_count: int,
) -> float:
    if author_count <= 1:
        return 1.0
    if scheme == "full_counting":
        return 1.0
    if scheme == "equal_fractional" or author_count == 2:
        return 1.0 / author_count
    lead_credit = 0.35 if scheme == "lead_balanced" else 0.4
    if index in {0, author_count - 1}:
        return lead_credit
    middle_pool = 1.0 - (2 * lead_credit)
    return middle_pool / (author_count - 2)


def _role_matches(
    role: AuthorRole,
    *,
    is_first: bool,
    is_last: bool,
    is_corresponding: bool | None,
) -> bool:
    if role == "all":
        return True
    if role == "first":
        return is_first
    if role == "last":
        return is_last
    if role == "middle":
        return not is_first and not is_last
    return is_corresponding is True


def _eligible_affiliations(
    values: list[dict],
    *,
    min_affiliation_confidence: float,
) -> tuple[list[dict], int, int]:
    eligible: dict[str, dict] = {}
    unresolved = 0
    below_threshold = 0
    for value in values:
        if not value.get("resolved") or not value.get("institution_id"):
            unresolved += 1
            continue
        if float(value.get("confidence") or 0) < min_affiliation_confidence:
            below_threshold += 1
            continue
        key = _institution_key(value)
        current = eligible.get(key)
        if current is None or float(value.get("confidence") or 0) > float(
            current.get("confidence") or 0
        ):
            eligible[key] = value
    return list(eligible.values()), unresolved, below_threshold


def _institution_key(value: dict) -> str:
    return str(
        value.get("institution_id")
        or value.get("ror")
        or value.get("openalex_id")
        or normalize_institution(str(value.get("display_name") or ""))
    )


def _empty_institution_aggregate(value: dict) -> dict:
    return {
        "id": value.get("institution_id"),
        "name": str(value.get("display_name") or "Unknown institution"),
        "ror": value.get("ror"),
        "openalex_id": value.get("openalex_id"),
        "country_code": value.get("country_code"),
        "weighted_credit": 0.0,
        "first_author_credit": 0.0,
        "last_author_credit": 0.0,
        "corresponding_author_credit": 0.0,
        "paper_ids": set(),
        "authorship_ids": set(),
        "sources": Counter(),
        "contributes_to_focus": False,
    }


def _finalize_institution(value: dict) -> dict:
    return {
        "id": value["id"],
        "name": value["name"],
        "ror": value["ror"],
        "openalex_id": value["openalex_id"],
        "country_code": value["country_code"],
        "weighted_credit": round(value["weighted_credit"], 6),
        "paper_count": len(value["paper_ids"]),
        "authorship_count": len(value["authorship_ids"]),
        "first_author_credit": round(value["first_author_credit"], 6),
        "last_author_credit": round(value["last_author_credit"], 6),
        "corresponding_author_credit": round(
            value["corresponding_author_credit"], 6
        ),
        "sources": dict(sorted(value["sources"].items())),
        "contributes_to_focus": value["contributes_to_focus"],
    }


def _is_focus_affiliation(value: dict, scope: FocusScope) -> bool:
    ror = str(value.get("ror") or "").rstrip("/").casefold()
    openalex_id = str(value.get("openalex_id") or "").rstrip("/").casefold()
    if ror == UOFT_ROR.casefold() or openalex_id == UOFT_OPENALEX_ID.casefold():
        return True
    if scope == "lineage":
        lineage = {
            str(item).rstrip("/").casefold() for item in value.get("lineage") or []
        }
        return UOFT_OPENALEX_ID.casefold() in lineage
    return False


def _finalize_yearly(values: dict[int, dict[str, object]]) -> list[dict]:
    rows = []
    for year, value in sorted(values.items()):
        rows.append(
            {
                "year": year,
                "corpus_papers": len(value["paper_ids"]),
                "focus_papers": len(value["focus_paper_ids"]),
                "other_institution_papers": len(value["other_paper_ids"]),
                "focus_weighted_credit": round(
                    float(value["focus_weighted_credit"]), 6
                ),
                "other_weighted_credit": round(
                    float(value["other_weighted_credit"]), 6
                ),
            }
        )
    return rows


def _run_payload(run: MetadataEnrichmentRun | None) -> dict | None:
    if run is None:
        return None
    return {
        "id": run.id,
        "agent_version": run.agent_version,
        "status": run.status,
        "input_sha256": run.input_sha256,
        "summary": run.summary,
        "started_at": run.started_at.isoformat(),
        "completed_at": run.completed_at.isoformat() if run.completed_at else None,
    }


def _latest_successful_run(session: Session) -> MetadataEnrichmentRun | None:
    return session.execute(
        select(MetadataEnrichmentRun)
        .where(MetadataEnrichmentRun.status == "succeeded")
        .order_by(MetadataEnrichmentRun.completed_at.desc())
    ).scalars().first()


def _ratio(numerator: float, denominator: float) -> float:
    return round(numerator / denominator, 6) if denominator else 0.0
