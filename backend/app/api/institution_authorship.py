"""Institution comparison API backed by paper-specific authorship metadata."""

from __future__ import annotations

import csv
import io
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response

from app.services.s3_authorship_institution_comparison import (
    InstitutionMetadataFilter,
    MetadataCorpus,
    MetadataCountryNotFoundError,
    Tier1MetadataSnapshotStore,
    build_author_institution_map_csv,
    build_authorship_institution_comparison,
    build_metadata_country_detail,
    build_metadata_geographic_overview,
    comparison_options,
    enrichment_status,
    get_snapshot_store,
)


router = APIRouter(prefix="/institution-authorship", tags=["institution-authorship"])

CreditScheme = Literal[
    "lead_balanced",
    "lead_heavy",
    "equal_fractional",
    "full_counting",
]
AuthorRole = Literal["all", "first", "last", "middle", "corresponding"]
AffiliationAllocation = Literal["fractional", "full"]
FocusScope = Literal["strict", "lineage"]
INSTITUTION_QUERY_PARAMETERS = {
    "corpus",
    "credit_scheme",
    "author_role",
    "affiliation_allocation",
    "focus_scope",
    "min_affiliation_confidence",
    "limit",
    "year_from",
    "year_to",
    "search",
}
GEOGRAPHIC_QUERY_PARAMETERS = {
    "year_from",
    "year_to",
    "search",
    "min_affiliation_confidence",
}
COUNTRY_QUERY_PARAMETERS = GEOGRAPHIC_QUERY_PARAMETERS | {
    "credit_scheme",
    "author_role",
    "affiliation_allocation",
    "limit",
}


def _metadata_filter_query(
    request: Request,
    *,
    allowed_parameters: set[str],
    year_from: int | None,
    year_to: int | None,
    search: str | None,
) -> InstitutionMetadataFilter:
    unsupported = sorted(set(request.query_params) - allowed_parameters)
    if unsupported:
        raise HTTPException(
            status_code=422,
            detail=(
                "Unsupported institution metadata filter(s): " + ", ".join(unsupported)
            ),
        )
    try:
        return InstitutionMetadataFilter(
            year_from=year_from,
            year_to=year_to,
            search=search,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


def institution_metadata_filter_query(
    request: Request,
    year_from: Annotated[int | None, Query()] = None,
    year_to: Annotated[int | None, Query()] = None,
    search: Annotated[str | None, Query()] = None,
) -> InstitutionMetadataFilter:
    return _metadata_filter_query(
        request,
        allowed_parameters=INSTITUTION_QUERY_PARAMETERS,
        year_from=year_from,
        year_to=year_to,
        search=search,
    )


def geographic_metadata_filter_query(
    request: Request,
    year_from: Annotated[int | None, Query()] = None,
    year_to: Annotated[int | None, Query()] = None,
    search: Annotated[str | None, Query()] = None,
) -> InstitutionMetadataFilter:
    return _metadata_filter_query(
        request,
        allowed_parameters=GEOGRAPHIC_QUERY_PARAMETERS,
        year_from=year_from,
        year_to=year_to,
        search=search,
    )


def country_metadata_filter_query(
    request: Request,
    year_from: Annotated[int | None, Query()] = None,
    year_to: Annotated[int | None, Query()] = None,
    search: Annotated[str | None, Query()] = None,
) -> InstitutionMetadataFilter:
    return _metadata_filter_query(
        request,
        allowed_parameters=COUNTRY_QUERY_PARAMETERS,
        year_from=year_from,
        year_to=year_to,
        search=search,
    )


@router.get("/geographic")
def geographic(
    min_affiliation_confidence: Annotated[float, Query(ge=0.0, le=1.0)] = 0.8,
    filt: InstitutionMetadataFilter = Depends(geographic_metadata_filter_query),
    store: Tier1MetadataSnapshotStore = Depends(get_snapshot_store),
) -> dict:
    """Return a metadata-only country overview and collaboration graph."""
    return build_metadata_geographic_overview(
        store.load(),
        filt,
        min_affiliation_confidence=min_affiliation_confidence,
    )


@router.get("/geographic/countries/{country_code}")
def geographic_country(
    country_code: str,
    credit_scheme: Annotated[CreditScheme, Query()] = "lead_balanced",
    author_role: Annotated[AuthorRole, Query()] = "all",
    affiliation_allocation: Annotated[AffiliationAllocation, Query()] = "fractional",
    min_affiliation_confidence: Annotated[float, Query(ge=0.0, le=1.0)] = 0.8,
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
    filt: InstitutionMetadataFilter = Depends(country_metadata_filter_query),
    store: Tier1MetadataSnapshotStore = Depends(get_snapshot_store),
) -> dict:
    """Return one country's institution comparison from the same snapshot."""
    try:
        return build_metadata_country_detail(
            store.load(),
            filt,
            country_code,
            credit_scheme=credit_scheme,
            author_role=author_role,
            affiliation_allocation=affiliation_allocation,
            min_affiliation_confidence=min_affiliation_confidence,
            limit=limit,
        )
    except MetadataCountryNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/report")
def report(
    credit_scheme: Annotated[CreditScheme, Query()] = "lead_balanced",
    author_role: Annotated[AuthorRole, Query()] = "all",
    affiliation_allocation: Annotated[AffiliationAllocation, Query()] = "fractional",
    focus_scope: Annotated[FocusScope, Query()] = "strict",
    min_affiliation_confidence: Annotated[float, Query(ge=0.0, le=1.0)] = 0.8,
    limit: Annotated[int, Query(ge=1, le=200)] = 30,
    filt: InstitutionMetadataFilter = Depends(institution_metadata_filter_query),
    store: Tier1MetadataSnapshotStore = Depends(get_snapshot_store),
) -> dict:
    """Return a replayable U of T versus other-institutions comparison."""
    return build_authorship_institution_comparison(
        store.load(),
        filt,
        credit_scheme=credit_scheme,
        author_role=author_role,
        affiliation_allocation=affiliation_allocation,
        focus_scope=focus_scope,
        min_affiliation_confidence=min_affiliation_confidence,
        limit=limit,
    )


@router.get("/options")
def options(
    store: Tier1MetadataSnapshotStore = Depends(get_snapshot_store),
) -> dict:
    return comparison_options(store.load())


@router.get("/status")
def status(
    store: Tier1MetadataSnapshotStore = Depends(get_snapshot_store),
) -> dict:
    return enrichment_status(store.load())


@router.get("/author-institution-map.csv")
def export_author_institution_map(
    store: Tier1MetadataSnapshotStore = Depends(get_snapshot_store),
) -> Response:
    """Download all Tier 1 papers with ordered authors and affiliations."""
    if store.corpus != "tier1":
        raise HTTPException(
            status_code=422,
            detail="The author-institution metadata export is available for Tier 1 only",
        )
    snapshot = store.load()
    content = build_author_institution_map_csv(
        snapshot.papers,
        snapshot.authorships,
        snapshot.affiliations,
    )
    paper_count = len(snapshot.papers)
    return Response(
        content=b"\xef\xbb\xbf" + content,
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": (
                "attachment; filename="
                f"tier1-{paper_count}-paper-author-institution-metadata.csv"
            ),
            "X-Metadata-Manifest-SHA256": snapshot.manifest_sha256,
            "X-Paper-Count": str(paper_count),
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.get("/export.csv")
def export_csv(
    credit_scheme: Annotated[CreditScheme, Query()] = "lead_balanced",
    author_role: Annotated[AuthorRole, Query()] = "all",
    affiliation_allocation: Annotated[AffiliationAllocation, Query()] = "fractional",
    focus_scope: Annotated[FocusScope, Query()] = "strict",
    min_affiliation_confidence: Annotated[float, Query(ge=0.0, le=1.0)] = 0.8,
    limit: Annotated[int, Query(ge=1, le=200)] = 200,
    filt: InstitutionMetadataFilter = Depends(institution_metadata_filter_query),
    store: Tier1MetadataSnapshotStore = Depends(get_snapshot_store),
) -> Response:
    payload = build_authorship_institution_comparison(
        store.load(),
        filt,
        credit_scheme=credit_scheme,
        author_role=author_role,
        affiliation_allocation=affiliation_allocation,
        focus_scope=focus_scope,
        min_affiliation_confidence=min_affiliation_confidence,
        limit=limit,
    )
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(
        [
            "rank",
            "institution",
            "institution_id",
            "ror",
            "openalex_id",
            "country_code",
            "weighted_credit",
            "share_of_resolved_credit",
            "paper_count",
            "paper_count_rule",
            "authorship_count",
            "first_author_credit",
            "last_author_credit",
            "corresponding_author_credit",
            "contributes_to_focus",
            "credit_scheme",
            "author_role",
            "affiliation_allocation",
            "focus_scope",
            "corpus",
            "min_affiliation_confidence",
            "filter_fingerprint",
            "paper_set_sha256",
        ]
    )
    configuration = payload["configuration"]
    audit = payload["audit"]
    for row in payload["institutions"]:
        writer.writerow(
            [
                row["rank"],
                row["name"],
                row["id"],
                row["ror"],
                row["openalex_id"],
                row["country_code"],
                row["weighted_credit"],
                row["share_of_resolved_credit"],
                row["paper_count"],
                configuration["paper_count_rule"],
                row["authorship_count"],
                row["first_author_credit"],
                row["last_author_credit"],
                row["corresponding_author_credit"],
                row["contributes_to_focus"],
                configuration["credit_scheme"],
                configuration["author_role"],
                configuration["affiliation_allocation"],
                configuration["focus_scope"],
                configuration["corpus"],
                configuration["min_affiliation_confidence"],
                audit["filter_fingerprint"],
                audit["paper_set_sha256"],
            ]
        )
    corpus: MetadataCorpus = configuration["corpus"]
    filename_corpus = corpus.replace("_", "-")
    return Response(
        content="\ufeff" + buffer.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": (
                f"attachment; filename={filename_corpus}-institution-authorship-comparison.csv"
            )
        },
    )
