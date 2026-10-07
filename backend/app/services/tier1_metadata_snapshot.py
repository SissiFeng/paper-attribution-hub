"""Build and publish immutable, auditable Tier 1 metadata snapshots."""

from __future__ import annotations

import copy
import csv
import hashlib
import io
import json
from collections import Counter, defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from botocore.exceptions import ClientError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    Author,
    Institution,
    MetadataEnrichmentRun,
    Paper,
    PaperAuthorshipMetadata,
)
from app.services.authorship_institution_comparison import (
    CREDIT_SCHEMES,
    InstitutionMetadataFilter,
    _author_credit,
    _eligible_affiliations,
    _empty_institution_aggregate,
    _finalize_institution,
    _is_focus_affiliation,
    build_authorship_institution_comparison,
)
from app.services.tier1_metadata_agent import read_tier1_csv


SCHEMA_VERSION = "tier1_metadata_snapshot.v2"
DEFAULT_MIN_AFFILIATION_CONFIDENCE = 0.8
DEFAULT_CREDIT_SCHEME = "lead_balanced"
DEFAULT_AFFILIATION_ALLOCATION = "fractional"


@dataclass(frozen=True)
class SnapshotArtifact:
    name: str
    content: bytes
    content_type: str
    rows: int | None = None

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.content).hexdigest()


@dataclass(frozen=True)
class Tier1MetadataSnapshot:
    enrichment_run_id: str
    input_sha256: str
    created_at: str
    artifacts: tuple[SnapshotArtifact, ...]
    manifest: dict[str, Any]


def build_tier1_metadata_snapshot(
    session: Session,
    csv_path: Path,
    *,
    created_at: datetime | None = None,
) -> Tier1MetadataSnapshot:
    """Create a complete raw snapshot for the latest successful Tier 1 run.

    The source CSV is preserved byte-for-byte. Derived JSONL/CSV files are
    deterministic for a fixed database state, and the manifest records every
    artifact hash plus the exact weighting policy used for the default score.
    """
    source = Path(csv_path).expanduser().resolve()
    source_content = source.read_bytes()
    source_sha256 = hashlib.sha256(source_content).hexdigest()
    csv_inputs, input_stats = read_tier1_csv(source)
    latest_run = _latest_successful_run(session)
    if latest_run is None:
        raise RuntimeError("No successful Tier 1 metadata enrichment run exists")
    if latest_run.input_sha256 != source_sha256:
        raise RuntimeError(
            "The source CSV hash does not match the latest successful metadata run"
        )

    papers = [
        paper
        for paper in session.execute(select(Paper)).scalars()
        if _metadata_agent_payload(paper).get("input_sha256") == source_sha256
    ]
    papers.sort(key=lambda row: ((row.doi or ""), row.id))
    expected_dois = {row.doi for row in csv_inputs}
    actual_dois = {str(row.doi or "") for row in papers}
    if expected_dois != actual_dois:
        raise RuntimeError(
            "Tier 1 database scope does not exactly match the DOI-deduplicated source CSV"
        )

    paper_by_id = {paper.id: paper for paper in papers}
    authorships = list(
        session.execute(
            select(PaperAuthorshipMetadata).where(
                PaperAuthorshipMetadata.paper_id.in_(paper_by_id)
            )
        ).scalars()
    )
    authorships.sort(key=lambda row: (row.paper_id, row.author_order, row.author_id))
    author_ids = {row.author_id for row in authorships}
    author_by_id = {
        row.id: row
        for row in session.execute(
            select(Author).where(Author.id.in_(author_ids))
        ).scalars()
    }
    by_paper: dict[str, list[PaperAuthorshipMetadata]] = defaultdict(list)
    for row in authorships:
        by_paper[row.paper_id].append(row)

    paper_records = [_paper_record(paper) for paper in papers]
    authorship_records: list[dict[str, Any]] = []
    affiliation_records: list[dict[str, Any]] = []
    quality_rows: list[dict[str, Any]] = []
    institution_aggregates: dict[str, dict[str, Any]] = {}
    referenced_institution_ids: Counter[str] = Counter()
    resolved_assertions = 0
    unresolved_assertions = 0
    below_threshold_assertions = 0
    selected_default_assertions = 0
    authorships_with_default_affiliations = 0
    normalized_weight_failures: list[dict[str, Any]] = []

    for paper in papers:
        paper_payload = _metadata_agent_payload(paper)
        for flag in paper_payload.get("quality_flags") or []:
            quality_rows.append(
                _quality_row(
                    scope="paper",
                    paper=paper,
                    author_id=None,
                    author_order=None,
                    flag=str(flag),
                )
            )
        rows = by_paper.get(paper.id, [])
        author_count = len(rows)
        if not rows:
            quality_rows.append(
                _quality_row(
                    scope="paper",
                    paper=paper,
                    author_id=None,
                    author_order=None,
                    flag="no_authorship_metadata",
                )
            )
            continue

        for scheme in CREDIT_SCHEMES:
            if scheme == "full_counting":
                continue
            total = sum(
                _author_credit(scheme, index=index, author_count=author_count)
                for index in range(author_count)
            )
            if abs(total - 1.0) > 1e-9:
                normalized_weight_failures.append(
                    {"paper_id": paper.id, "scheme": scheme, "sum": total}
                )

        for index, row in enumerate(rows):
            author = author_by_id.get(row.author_id)
            if author is None:
                raise RuntimeError(f"Missing author master row: {row.author_id}")
            affiliations = list(row.affiliations or [])
            eligible, unresolved, below_threshold = _eligible_affiliations(
                affiliations,
                min_affiliation_confidence=DEFAULT_MIN_AFFILIATION_CONFIDENCE,
            )
            eligible_object_ids = {id(value) for value in eligible}
            unresolved_assertions += unresolved
            below_threshold_assertions += below_threshold
            if eligible:
                authorships_with_default_affiliations += 1

            weights = {
                scheme: _author_credit(
                    scheme,
                    index=index,
                    author_count=author_count,
                )
                for scheme in CREDIT_SCHEMES
            }
            authorship_records.append(
                {
                    "paper_id": paper.id,
                    "doi": paper.doi,
                    "paper_title": paper.title,
                    "author_id": row.author_id,
                    "author_name": author.canonical_name,
                    "author_order_zero_based": row.author_order,
                    "author_rank_one_based": index + 1,
                    "author_count": author_count,
                    "author_position": row.author_position,
                    "is_first": index == 0,
                    "is_last": index == author_count - 1,
                    "is_corresponding": row.is_corresponding,
                    "openalex_author_id": row.openalex_author_id,
                    "orcid": row.orcid or author.orcid,
                    "author_weights": weights,
                    "affiliation_assertion_count": len(affiliations),
                    "eligible_institution_count_default": len(eligible),
                    "sources": row.sources or [],
                    "source_record_ids": row.source_record_ids or [],
                    "quality_flags": row.quality_flags or [],
                    "provenance_hash": row.provenance_hash,
                    "enriched_at": _iso(row.enriched_at),
                }
            )
            for flag in row.quality_flags or []:
                quality_rows.append(
                    _quality_row(
                        scope="authorship",
                        paper=paper,
                        author_id=row.author_id,
                        author_order=row.author_order,
                        flag=str(flag),
                    )
                )

            for assertion_index, affiliation in enumerate(affiliations):
                selected = id(affiliation) in eligible_object_ids
                if affiliation.get("resolved") and affiliation.get("institution_id"):
                    resolved_assertions += 1
                    referenced_institution_ids[str(affiliation["institution_id"])] += 1
                default_credit = (
                    weights[DEFAULT_CREDIT_SCHEME] / len(eligible)
                    if selected and eligible
                    else 0.0
                )
                if selected:
                    selected_default_assertions += 1
                    institution_key = str(
                        affiliation.get("institution_id")
                        or affiliation.get("ror")
                        or affiliation.get("openalex_id")
                        or affiliation.get("display_name")
                        or "unknown"
                    )
                    aggregate = institution_aggregates.setdefault(
                        institution_key,
                        _empty_institution_aggregate(affiliation),
                    )
                    aggregate["weighted_credit"] += default_credit
                    aggregate["paper_ids"].add(paper.id)
                    aggregate["authorship_ids"].add(f"{paper.id}|{row.author_id}")
                    if index == 0:
                        aggregate["first_author_credit"] += default_credit
                    if index == author_count - 1:
                        aggregate["last_author_credit"] += default_credit
                    if row.is_corresponding is True:
                        aggregate["corresponding_author_credit"] += default_credit
                    aggregate["sources"][
                        str(affiliation.get("source") or "unknown")
                    ] += 1
                    if _is_focus_affiliation(affiliation, "strict"):
                        aggregate["contributes_to_focus"] = True

                affiliation_records.append(
                    {
                        "paper_id": paper.id,
                        "doi": paper.doi,
                        "paper_title": paper.title,
                        "author_id": row.author_id,
                        "author_name": author.canonical_name,
                        "author_rank_one_based": index + 1,
                        "author_count": author_count,
                        "author_position": row.author_position,
                        "is_first": index == 0,
                        "is_last": index == author_count - 1,
                        "is_corresponding": row.is_corresponding,
                        "openalex_author_id": row.openalex_author_id,
                        "orcid": row.orcid or author.orcid,
                        "affiliation_assertion_index": assertion_index,
                        **copy.deepcopy(affiliation),
                        "authorship_provenance_hash": row.provenance_hash,
                        "selected_for_default_comparison": selected,
                        "default_lead_balanced_fractional_credit": round(
                            default_credit, 12
                        ),
                        "fractional_credits_by_scheme": {
                            scheme: round(weight / len(eligible), 12)
                            if selected and eligible
                            else 0.0
                            for scheme, weight in weights.items()
                        },
                        "full_credits_by_scheme": {
                            scheme: round(weight, 12) if selected else 0.0
                            for scheme, weight in weights.items()
                        },
                    }
                )

    institution_ids = set(referenced_institution_ids)
    institution_by_id = {
        row.id: row
        for row in session.execute(
            select(Institution).where(Institution.id.in_(institution_ids))
        ).scalars()
    }
    missing_institution_ids = sorted(institution_ids - set(institution_by_id))
    institution_records = [
        _institution_record(institution_by_id[institution_id])
        for institution_id in sorted(institution_by_id)
    ]
    resolved_credit = sum(
        float(value["weighted_credit"]) for value in institution_aggregates.values()
    )
    institution_scores = [
        _finalize_institution(value) for value in institution_aggregates.values()
    ]
    institution_scores.sort(
        key=lambda row: (
            -row["weighted_credit"],
            -row["paper_count"],
            row["name"],
        )
    )
    for rank, row in enumerate(institution_scores, start=1):
        row["rank"] = rank
        row["share_of_resolved_credit"] = (
            round(row["weighted_credit"] / resolved_credit, 12)
            if resolved_credit
            else 0.0
        )

    author_institution_map = _author_institution_map_rows(
        paper_records,
        authorship_records,
        affiliation_records,
    )
    paper_institution_map = _paper_institution_map_rows(affiliation_records)

    production_report = build_authorship_institution_comparison(
        session,
        InstitutionMetadataFilter(),
        credit_scheme=DEFAULT_CREDIT_SCHEME,
        author_role="all",
        affiliation_allocation=DEFAULT_AFFILIATION_ALLOCATION,
        focus_scope="strict",
        min_affiliation_confidence=DEFAULT_MIN_AFFILIATION_CONFIDENCE,
        limit=200,
    )
    _verify_production_replay(
        production_report=production_report,
        institution_scores=institution_scores,
        authorship_count=len(authorship_records),
        resolved_credit=resolved_credit,
    )

    created = created_at or datetime.now(UTC)
    created_iso = created.isoformat()
    artifacts = (
        SnapshotArtifact(
            name=f"source/{source.name}",
            content=source_content,
            content_type="text/csv; charset=utf-8",
            rows=input_stats["raw_rows"],
        ),
        SnapshotArtifact(
            name="papers.jsonl",
            content=_jsonl(paper_records),
            content_type="application/x-ndjson",
            rows=len(paper_records),
        ),
        SnapshotArtifact(
            name="authorships.jsonl",
            content=_jsonl(authorship_records),
            content_type="application/x-ndjson",
            rows=len(authorship_records),
        ),
        SnapshotArtifact(
            name="affiliations.jsonl",
            content=_jsonl(affiliation_records),
            content_type="application/x-ndjson",
            rows=len(affiliation_records),
        ),
        SnapshotArtifact(
            name="institutions.jsonl",
            content=_jsonl(institution_records),
            content_type="application/x-ndjson",
            rows=len(institution_records),
        ),
        SnapshotArtifact(
            name="author_institution_map.csv",
            content=_author_institution_map_csv(author_institution_map),
            content_type="text/csv; charset=utf-8",
            rows=len(author_institution_map),
        ),
        SnapshotArtifact(
            name="paper_institution_map.csv",
            content=_paper_institution_map_csv(paper_institution_map),
            content_type="text/csv; charset=utf-8",
            rows=len(paper_institution_map),
        ),
        SnapshotArtifact(
            name="institution_scores_default.csv",
            content=_institution_score_csv(institution_scores),
            content_type="text/csv; charset=utf-8",
            rows=len(institution_scores),
        ),
        SnapshotArtifact(
            name="quality_flags.csv",
            content=_quality_csv(quality_rows),
            content_type="text/csv; charset=utf-8",
            rows=len(quality_rows),
        ),
        SnapshotArtifact(
            name="README.md",
            content=_readme().encode("utf-8"),
            content_type="text/markdown; charset=utf-8",
        ),
    )
    artifact_entries = [
        {
            "name": artifact.name,
            "content_type": artifact.content_type,
            "bytes": len(artifact.content),
            "sha256": artifact.sha256,
            "rows": artifact.rows,
        }
        for artifact in artifacts
    ]
    missing_authorship_papers = [
        {"paper_id": paper.id, "doi": paper.doi, "title": paper.title}
        for paper in papers
        if paper.id not in by_paper
    ]
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "kind": "tier1_metadata_snapshot",
        "status": "ready_with_warnings"
        if missing_authorship_papers or missing_institution_ids or unresolved_assertions
        else "ready",
        "created_at": created_iso,
        "source": {
            "filename": source.name,
            "sha256": source_sha256,
            **input_stats,
        },
        "enrichment_run": {
            "id": latest_run.id,
            "agent_version": latest_run.agent_version,
            "status": latest_run.status,
            "input_sha256": latest_run.input_sha256,
            "configuration": latest_run.configuration,
            "summary": latest_run.summary,
            "errors": latest_run.errors,
            "started_at": _iso(latest_run.started_at),
            "completed_at": _iso(latest_run.completed_at),
        },
        "scope": {
            "papers": len(paper_records),
            "papers_with_authorship_metadata": len(by_paper),
            "authorships": len(authorship_records),
            "affiliation_assertions": len(affiliation_records),
            "resolved_affiliation_assertions": resolved_assertions,
            "unresolved_affiliation_assertions": unresolved_assertions,
            "below_default_threshold_assertions": below_threshold_assertions,
            "selected_default_affiliation_assertions": selected_default_assertions,
            "authorships_with_default_eligible_affiliations": (
                authorships_with_default_affiliations
            ),
            "resolved_institutions_in_default_comparison": len(institution_scores),
            "author_institution_map_rows": len(author_institution_map),
            "paper_institution_map_rows": len(paper_institution_map),
        },
        "default_comparison": {
            "credit_scheme": DEFAULT_CREDIT_SCHEME,
            "author_role": "all",
            "affiliation_allocation": DEFAULT_AFFILIATION_ALLOCATION,
            "focus_scope": "strict",
            "min_affiliation_confidence": DEFAULT_MIN_AFFILIATION_CONFIDENCE,
            "focus": production_report["focus"],
            "scope": production_report["scope"],
            "production_replay_check": "passed",
        },
        "weighting_policy": {
            "paper_count_rule": (
                "A distinct paper counts once for every eligible resolved "
                "institution represented by any author. Author position, role "
                "filters, and credit weights do not change paper membership."
            ),
            "credit_schemes": CREDIT_SCHEMES,
            "lead_balanced_formula": {
                "one_author": "1.0",
                "two_authors": "0.5 each",
                "three_or_more": ("first=0.35, last=0.35, each middle=0.30/(n-2)"),
            },
            "fractional_affiliation_formula": (
                "institution_credit = author_position_weight / "
                "eligible_resolved_institution_count"
            ),
            "full_affiliation_formula": (
                "institution_credit = author_position_weight for each eligible "
                "resolved institution"
            ),
            "role_filter_behavior": (
                "Role filters select authorships and do not renormalize the "
                "original position weight"
            ),
        },
        "integrity": {
            "normalized_author_weight_sum_failures": normalized_weight_failures,
            "papers_without_authorship_metadata": missing_authorship_papers,
            "missing_institution_master_ids": [
                {
                    "institution_id": institution_id,
                    "affiliation_assertions": referenced_institution_ids[
                        institution_id
                    ],
                }
                for institution_id in missing_institution_ids
            ],
            "notes": [
                "Every authorship is preserved even when no institution resolves.",
                "Unresolved or below-threshold affiliations receive zero institution credit.",
                "Multiple eligible institutions are all counted; fractional allocation divides one author credit among them.",
            ],
        },
        "artifacts": artifact_entries,
    }
    return Tier1MetadataSnapshot(
        enrichment_run_id=latest_run.id,
        input_sha256=source_sha256,
        created_at=created_iso,
        artifacts=artifacts,
        manifest=manifest,
    )


def upload_tier1_metadata_snapshot(
    snapshot: Tier1MetadataSnapshot,
    *,
    s3_client,
    bucket: str,
    raw_prefix: str = "raw/metadata/tier1",
    manifest_prefix: str = "manifests/metadata/tier1",
) -> dict[str, Any]:
    """Upload and download-verify all data objects, publishing the manifest last."""
    if not bucket.strip():
        raise ValueError("S3 bucket is required")
    run_segment = (
        f"input_sha256={snapshot.input_sha256}/run_id={snapshot.enrichment_run_id}"
    )
    snapshot_id = _snapshot_id(snapshot)
    snapshot_segment = f"snapshot_id={snapshot_id}"
    raw_root = f"{raw_prefix.strip('/')}/{run_segment}/{snapshot_segment}"
    manifest_root = (
        f"{manifest_prefix.strip('/')}/runs/{run_segment}/{snapshot_segment}"
    )
    uploaded: list[dict[str, Any]] = []
    for artifact in snapshot.artifacts:
        key = f"{raw_root}/{artifact.name}"
        _put_verified(
            s3_client,
            bucket=bucket,
            key=key,
            content=artifact.content,
            content_type=artifact.content_type,
            metadata={
                "sha256": artifact.sha256,
                "schema-version": SCHEMA_VERSION,
                "enrichment-run-id": snapshot.enrichment_run_id,
            },
        )
        uploaded.append(
            {
                "name": artifact.name,
                "s3_key": key,
                "s3_uri": f"s3://{bucket}/{key}",
                "bytes": len(artifact.content),
                "sha256": artifact.sha256,
                "rows": artifact.rows,
                "verified": True,
            }
        )

    manifest = copy.deepcopy(snapshot.manifest)
    manifest["storage"] = {
        "bucket": bucket,
        "snapshot_id": snapshot_id,
        "raw_prefix": raw_root,
        "fulltext_prefix": "raw/zotero/",
        "separation_verified": raw_root.startswith("raw/metadata/")
        and not raw_root.startswith("raw/zotero/"),
        "artifacts": uploaded,
    }
    manifest_content = json.dumps(
        manifest,
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
        default=_json_default,
    ).encode("utf-8")
    manifest_key = f"{manifest_root}/manifest.json"
    manifest_sha256 = hashlib.sha256(manifest_content).hexdigest()
    _put_verified(
        s3_client,
        bucket=bucket,
        key=manifest_key,
        content=manifest_content,
        content_type="application/json",
        metadata={
            "sha256": manifest_sha256,
            "schema-version": SCHEMA_VERSION,
            "enrichment-run-id": snapshot.enrichment_run_id,
        },
    )
    return {
        "status": "uploaded_and_verified",
        "bucket": bucket,
        "snapshot_id": snapshot_id,
        "raw_prefix": raw_root,
        "manifest_key": manifest_key,
        "manifest_uri": f"s3://{bucket}/{manifest_key}",
        "manifest_sha256": manifest_sha256,
        "artifacts": uploaded,
    }


def _snapshot_id(snapshot: Tier1MetadataSnapshot) -> str:
    created = datetime.fromisoformat(snapshot.created_at.replace("Z", "+00:00"))
    timestamp = created.astimezone(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    digest = hashlib.sha256(
        json.dumps(
            snapshot.manifest,
            ensure_ascii=False,
            sort_keys=True,
            default=_json_default,
        ).encode("utf-8")
    ).hexdigest()[:12]
    return f"{timestamp}_{digest}"


def _put_verified(
    s3_client,
    *,
    bucket: str,
    key: str,
    content: bytes,
    content_type: str,
    metadata: dict[str, str],
) -> None:
    expected_sha256 = hashlib.sha256(content).hexdigest()
    try:
        existing = s3_client.head_object(Bucket=bucket, Key=key)
    except ClientError as exc:
        code = str((exc.response.get("Error") or {}).get("Code") or "")
        if code not in {"404", "NoSuchKey", "NotFound"}:
            raise
    else:
        existing_sha256 = str((existing.get("Metadata") or {}).get("sha256") or "")
        if (
            int(existing.get("ContentLength") or -1) != len(content)
            or existing_sha256 != expected_sha256
        ):
            raise RuntimeError(
                f"Refusing to overwrite a different existing S3 object: s3://{bucket}/{key}"
            )
        downloaded = s3_client.get_object(Bucket=bucket, Key=key)["Body"].read()
        if hashlib.sha256(downloaded).hexdigest() != expected_sha256:
            raise RuntimeError(f"S3 download verification failed for {key}")
        return

    s3_client.put_object(
        Bucket=bucket,
        Key=key,
        Body=content,
        ContentType=content_type,
        ServerSideEncryption="AES256",
        Metadata=metadata,
    )
    head = s3_client.head_object(Bucket=bucket, Key=key)
    if int(head.get("ContentLength") or -1) != len(content):
        raise RuntimeError(f"S3 size verification failed for {key}")
    if str((head.get("Metadata") or {}).get("sha256") or "") != expected_sha256:
        raise RuntimeError(f"S3 hash metadata verification failed for {key}")
    downloaded = s3_client.get_object(Bucket=bucket, Key=key)["Body"].read()
    if hashlib.sha256(downloaded).hexdigest() != expected_sha256:
        raise RuntimeError(f"S3 download verification failed for {key}")


def _latest_successful_run(session: Session) -> MetadataEnrichmentRun | None:
    return (
        session.execute(
            select(MetadataEnrichmentRun)
            .where(MetadataEnrichmentRun.status == "succeeded")
            .order_by(MetadataEnrichmentRun.completed_at.desc())
        )
        .scalars()
        .first()
    )


def _metadata_agent_payload(paper: Paper) -> dict[str, Any]:
    return dict((paper.raw_metadata or {}).get("tier1_metadata_agent") or {})


def _paper_record(paper: Paper) -> dict[str, Any]:
    metadata = _metadata_agent_payload(paper)
    return {
        "paper_id": paper.id,
        "doi": paper.doi,
        "title": paper.title,
        "abstract": paper.abstract,
        "year": paper.year,
        "venue": paper.venue,
        "source": paper.source,
        "provenance": paper.provenance,
        "retrieval_tier": paper.retrieval_tier,
        "corpus_sources": paper.corpus_sources or [],
        "full_text_available": bool(paper.full_text_available),
        "citation_count": paper.citation_count,
        "citation_count_source": paper.citation_count_source,
        "citation_count_updated_at": _iso(paper.citation_count_updated_at),
        "created_at": _iso(paper.created_at),
        "updated_at": _iso(paper.updated_at),
        "tier1_metadata_agent": copy.deepcopy(metadata),
    }


def _institution_record(row: Institution) -> dict[str, Any]:
    return {
        "institution_id": row.id,
        "canonical_name": row.canonical_name,
        "aliases": row.aliases or [],
        "normalized_aliases": row.normalized_aliases or [],
        "country": row.country,
        "country_keys": row.country_keys or [],
        "city": row.city,
        "is_partner": bool(row.is_partner),
        "raw_metadata": copy.deepcopy(row.raw_metadata or {}),
    }


def _quality_row(
    *,
    scope: str,
    paper: Paper,
    author_id: str | None,
    author_order: int | None,
    flag: str,
) -> dict[str, Any]:
    return {
        "scope": scope,
        "paper_id": paper.id,
        "doi": paper.doi,
        "author_id": author_id,
        "author_order_zero_based": author_order,
        "quality_flag": flag,
    }


def _verify_production_replay(
    *,
    production_report: dict[str, Any],
    institution_scores: list[dict[str, Any]],
    authorship_count: int,
    resolved_credit: float,
) -> None:
    scope = production_report["scope"]
    if scope["selected_authorships"] != authorship_count:
        raise RuntimeError("Snapshot authorship count does not replay production")
    if scope["institution_count"] != len(institution_scores):
        raise RuntimeError("Snapshot institution count does not replay production")
    if abs(float(scope["resolved_author_credit"]) - resolved_credit) > 1e-6:
        raise RuntimeError("Snapshot resolved credit does not replay production")
    for expected, actual in zip(
        production_report["institutions"], institution_scores, strict=False
    ):
        for key in ("id", "name", "weighted_credit", "paper_count"):
            if expected[key] != actual[key]:
                raise RuntimeError(
                    f"Snapshot institution ranking does not replay production: {key}"
                )


def _jsonl(rows: list[dict[str, Any]]) -> bytes:
    return (
        "".join(
            json.dumps(
                row,
                ensure_ascii=False,
                sort_keys=True,
                default=_json_default,
            )
            + "\n"
            for row in rows
        )
    ).encode("utf-8")


def _author_institution_map_rows(
    papers: Sequence[dict[str, Any]],
    authorships: Sequence[dict[str, Any]],
    affiliations: Sequence[dict[str, Any]],
) -> list[dict[str, Any]]:
    by_authorship: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for affiliation in affiliations:
        by_authorship[
            (str(affiliation["paper_id"]), str(affiliation["author_id"]))
        ].append(affiliation)

    rows: list[dict[str, Any]] = []
    for authorship in authorships:
        key = (str(authorship["paper_id"]), str(authorship["author_id"]))
        assertions = by_authorship.get(key) or [None]
        for assertion in assertions:
            if assertion is None:
                mapping_status = "no_affiliation_assertion"
            elif not assertion.get("resolved") or not assertion.get("institution_id"):
                mapping_status = "unresolved"
            elif (
                float(assertion.get("confidence") or 0)
                < DEFAULT_MIN_AFFILIATION_CONFIDENCE
            ):
                mapping_status = "below_default_confidence_threshold"
            elif assertion.get("selected_for_default_comparison"):
                mapping_status = "eligible_resolved"
            else:
                mapping_status = "duplicate_resolved_assertion"

            value = assertion or {}
            rows.append(
                {
                    "paper_id": authorship["paper_id"],
                    "doi": authorship["doi"],
                    "paper_title": authorship["paper_title"],
                    "author_id": authorship["author_id"],
                    "author_name": authorship["author_name"],
                    "author_rank_one_based": authorship["author_rank_one_based"],
                    "author_count": authorship["author_count"],
                    "author_position": authorship["author_position"],
                    "is_first": authorship["is_first"],
                    "is_last": authorship["is_last"],
                    "is_corresponding": authorship["is_corresponding"],
                    "openalex_author_id": authorship["openalex_author_id"],
                    "orcid": authorship["orcid"],
                    "mapping_status": mapping_status,
                    "affiliation_assertion_index": value.get(
                        "affiliation_assertion_index"
                    ),
                    "institution_id": value.get("institution_id"),
                    "institution_name": value.get("display_name"),
                    "ror": value.get("ror"),
                    "openalex_institution_id": value.get("openalex_id"),
                    "country_code": value.get("country_code"),
                    "institution_type": value.get("type"),
                    "raw_affiliations": value.get("raw_affiliations") or [],
                    "lineage": value.get("lineage") or [],
                    "source": value.get("source"),
                    "source_record_id": value.get("source_record_id"),
                    "confidence": value.get("confidence"),
                    "resolved": bool(value.get("resolved")),
                    "selected_for_default_comparison": bool(
                        value.get("selected_for_default_comparison")
                    ),
                    "default_lead_balanced_fractional_credit": value.get(
                        "default_lead_balanced_fractional_credit", 0.0
                    ),
                    "authorship_provenance_hash": authorship["provenance_hash"],
                }
            )

    paper_ids_with_authorships = {
        str(authorship["paper_id"]) for authorship in authorships
    }
    for paper in papers:
        if str(paper["paper_id"]) in paper_ids_with_authorships:
            continue
        rows.append(
            {
                "paper_id": paper["paper_id"],
                "doi": paper.get("doi"),
                "paper_title": paper.get("title"),
                "author_id": None,
                "author_name": None,
                "author_rank_one_based": None,
                "author_count": 0,
                "author_position": None,
                "is_first": False,
                "is_last": False,
                "is_corresponding": False,
                "openalex_author_id": None,
                "orcid": None,
                "mapping_status": "no_authorship_metadata",
                "affiliation_assertion_index": None,
                "institution_id": None,
                "institution_name": None,
                "ror": None,
                "openalex_institution_id": None,
                "country_code": None,
                "institution_type": None,
                "raw_affiliations": [],
                "lineage": [],
                "source": None,
                "source_record_id": None,
                "confidence": None,
                "resolved": False,
                "selected_for_default_comparison": False,
                "default_lead_balanced_fractional_credit": 0.0,
                "authorship_provenance_hash": None,
            }
        )
    return rows


def build_author_institution_map_csv(
    papers: Sequence[dict[str, Any]],
    authorships: Sequence[dict[str, Any]],
    affiliations: Sequence[dict[str, Any]],
) -> bytes:
    """Build the complete paper-author-affiliation export for a snapshot."""
    return _author_institution_map_csv(
        _author_institution_map_rows(papers, authorships, affiliations)
    )


def _paper_institution_map_rows(
    affiliations: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str], dict[str, Any]] = {}
    for affiliation in affiliations:
        if not affiliation.get("selected_for_default_comparison"):
            continue
        institution_id = str(affiliation.get("institution_id") or "")
        if not institution_id:
            continue
        key = (str(affiliation["paper_id"]), institution_id)
        aggregate = grouped.setdefault(
            key,
            {
                "paper_id": affiliation["paper_id"],
                "doi": affiliation["doi"],
                "paper_title": affiliation["paper_title"],
                "institution_id": institution_id,
                "institution_name": affiliation.get("display_name"),
                "ror": affiliation.get("ror"),
                "openalex_institution_id": affiliation.get("openalex_id"),
                "country_code": affiliation.get("country_code"),
                "institution_type": affiliation.get("type"),
                "paper_count": 1,
                "paper_count_rule": "any_affiliated_author",
                "author_ids": set(),
                "author_names": set(),
                "author_ranks_one_based": set(),
                "contains_first_author": False,
                "contains_last_author": False,
                "contains_corresponding_author": False,
                "sources": set(),
            },
        )
        aggregate["author_ids"].add(str(affiliation["author_id"]))
        aggregate["author_names"].add(str(affiliation["author_name"]))
        aggregate["author_ranks_one_based"].add(
            int(affiliation["author_rank_one_based"])
        )
        aggregate["contains_first_author"] |= bool(affiliation["is_first"])
        aggregate["contains_last_author"] |= bool(affiliation["is_last"])
        aggregate["contains_corresponding_author"] |= bool(
            affiliation["is_corresponding"]
        )
        if affiliation.get("source"):
            aggregate["sources"].add(str(affiliation["source"]))

    rows: list[dict[str, Any]] = []
    for aggregate in grouped.values():
        author_ids = sorted(aggregate.pop("author_ids"))
        author_names = sorted(aggregate.pop("author_names"))
        ranks = sorted(aggregate.pop("author_ranks_one_based"))
        sources = sorted(aggregate.pop("sources"))
        rows.append(
            {
                **aggregate,
                "affiliated_author_count": len(author_ids),
                "author_ids": author_ids,
                "author_names": author_names,
                "author_ranks_one_based": ranks,
                "sources": sources,
            }
        )
    rows.sort(
        key=lambda row: (
            str(row["institution_name"] or ""),
            str(row["doi"] or ""),
            str(row["paper_id"]),
        )
    )
    return rows


def _csv_bytes(rows: list[dict[str, Any]], fields: list[str]) -> bytes:
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=fields)
    writer.writeheader()
    for row in rows:
        value = dict(row)
        for field in fields:
            if isinstance(value.get(field), (list, dict)):
                value[field] = json.dumps(
                    value[field], ensure_ascii=False, sort_keys=True
                )
        writer.writerow({field: value.get(field) for field in fields})
    return output.getvalue().encode("utf-8")


def _author_institution_map_csv(rows: list[dict[str, Any]]) -> bytes:
    return _csv_bytes(
        rows,
        [
            "paper_id",
            "doi",
            "paper_title",
            "author_id",
            "author_name",
            "author_rank_one_based",
            "author_count",
            "author_position",
            "is_first",
            "is_last",
            "is_corresponding",
            "openalex_author_id",
            "orcid",
            "mapping_status",
            "affiliation_assertion_index",
            "institution_id",
            "institution_name",
            "ror",
            "openalex_institution_id",
            "country_code",
            "institution_type",
            "raw_affiliations",
            "lineage",
            "source",
            "source_record_id",
            "confidence",
            "resolved",
            "selected_for_default_comparison",
            "default_lead_balanced_fractional_credit",
            "authorship_provenance_hash",
        ],
    )


def _paper_institution_map_csv(rows: list[dict[str, Any]]) -> bytes:
    return _csv_bytes(
        rows,
        [
            "paper_id",
            "doi",
            "paper_title",
            "institution_id",
            "institution_name",
            "ror",
            "openalex_institution_id",
            "country_code",
            "institution_type",
            "paper_count",
            "paper_count_rule",
            "affiliated_author_count",
            "author_ids",
            "author_names",
            "author_ranks_one_based",
            "contains_first_author",
            "contains_last_author",
            "contains_corresponding_author",
            "sources",
        ],
    )


def _institution_score_csv(rows: list[dict[str, Any]]) -> bytes:
    fields = [
        "rank",
        "id",
        "name",
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
        "sources",
    ]
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=fields)
    writer.writeheader()
    for row in rows:
        value = dict(row)
        value["paper_count_rule"] = "any_affiliated_author"
        value["sources"] = json.dumps(
            value.get("sources") or {}, ensure_ascii=False, sort_keys=True
        )
        writer.writerow({field: value.get(field) for field in fields})
    return output.getvalue().encode("utf-8")


def _quality_csv(rows: list[dict[str, Any]]) -> bytes:
    fields = [
        "scope",
        "paper_id",
        "doi",
        "author_id",
        "author_order_zero_based",
        "quality_flag",
    ]
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=fields)
    writer.writeheader()
    writer.writerows(rows)
    return output.getvalue().encode("utf-8")


def _readme() -> str:
    return """# Tier 1 Metadata Snapshot

This immutable snapshot keeps bibliographic metadata separate from the Zotero
full-text Markdown stored under `raw/zotero/`.

## Files

- `source/*.csv`: the exact 885-row input export.
- `papers.jsonl`: one record per DOI-deduplicated paper, including the raw
  OpenAlex and Crossref payloads retained by the enrichment agent.
- `authorships.jsonl`: one record per paper-author relationship, with author
  order, source provenance, quality flags, and weights for every supported
  credit scheme.
- `affiliations.jsonl`: one record per author-affiliation assertion, including
  unresolved assertions and the exact credit used by the default comparison.
- `institutions.jsonl`: referenced institution master records available in the
  database at snapshot time.
- `author_institution_map.csv`: a flat audit table for every paper-author and
  affiliation assertion. Authors with no affiliation assertion remain present
  with `mapping_status=no_affiliation_assertion`; papers with no author metadata
  remain present with `mapping_status=no_authorship_metadata`.
- `paper_institution_map.csv`: one row per distinct paper-institution
  membership. A paper appears once for every eligible institution represented
  by any author, independent of author-position weights.
- `institution_scores_default.csv`: the complete default institution ranking.
- `quality_flags.csv`: paper- and authorship-level review flags.

## Default comparison formula

All authors are selected. For papers with three or more authors, the first and
last authors receive 0.35 each and all middle authors share 0.30. A solo author
receives 1.0; two authors receive 0.5 each.

If an author has `k` distinct resolved affiliations with confidence at least
0.8, each institution receives `author_position_weight / k`. Therefore every
eligible institution is counted without multiplying the paper's total credit
when fractional affiliation allocation is selected. Unresolved or
below-threshold affiliations remain in the raw export but receive zero
institution credit.

Paper membership is separate from weighted credit: if any author has an
eligible affiliation with an institution, the paper counts once for that
institution. Author position and credit settings affect contribution scores,
not this distinct-paper count.

The manifest records counts, hashes, quality warnings, exact formulas, and a
replay check against the production comparison implementation.
"""


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def _json_default(value: Any) -> str:
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)
