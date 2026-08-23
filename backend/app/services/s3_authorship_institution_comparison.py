"""Institution comparison computed only from an immutable S3 metadata snapshot."""

from __future__ import annotations

from collections import Counter, defaultdict
import csv
from dataclasses import dataclass
from datetime import UTC, datetime
import hashlib
import io
from itertools import combinations
import json
import os
from threading import Lock
import time
from typing import Literal

import boto3

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
MetadataCorpus = Literal["tier1", "tier1_tier2"]

UOFT_NAME = "University of Toronto"
UOFT_ROR = "https://ror.org/03dbr7087"
UOFT_OPENALEX_ID = "https://openalex.org/I185261750"
CORPUS_DEFINITIONS: dict[str, dict[str, str]] = {
    "tier1": {
        "label": "Tier 1",
        "manifest_env": "PAS_INSTITUTION_METADATA_MANIFEST_KEY",
        "manifest_prefix": "manifests/metadata/tier1/runs/",
    },
    "tier1_tier2": {
        "label": "Tier 1 + Tier 2",
        "manifest_env": "PAS_INSTITUTION_TIER1_TIER2_METADATA_MANIFEST_KEY",
        "manifest_prefix": "manifests/metadata/tier1-tier2/runs/",
    },
}
PAPER_SET_ENCODING = "paper-id-set-json.v1"
NETWORK_NODE_LIMIT = 25
NETWORK_RANKING_LIMIT = 10
AUTHOR_INSTITUTION_EXPORT_FIELDS = (
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
)

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


@dataclass(frozen=True)
class InstitutionMetadataFilter:
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
        object.__setattr__(self, "search", (self.search or "").strip() or None)


def build_author_institution_map_csv(
    papers: tuple[dict, ...],
    authorships: tuple[dict, ...],
    affiliations: tuple[dict, ...],
) -> bytes:
    """Build a standalone paper-author-affiliation export from one snapshot."""
    by_authorship: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for affiliation in affiliations:
        key = (str(affiliation["paper_id"]), str(affiliation["author_id"]))
        by_authorship[key].append(affiliation)

    rows: list[dict] = []
    for authorship in authorships:
        key = (str(authorship["paper_id"]), str(authorship["author_id"]))
        assertions: list[dict | None] = by_authorship.get(key) or [None]
        for assertion in assertions:
            value = assertion or {}
            if assertion is None:
                mapping_status = "no_affiliation_assertion"
            elif not value.get("resolved") or not value.get("institution_id"):
                mapping_status = "unresolved"
            elif float(value.get("confidence") or 0) < 0.8:
                mapping_status = "below_default_confidence_threshold"
            elif value.get("selected_for_default_comparison"):
                mapping_status = "eligible_resolved"
            else:
                mapping_status = "duplicate_resolved_assertion"
            rows.append(
                {
                    "paper_id": authorship["paper_id"],
                    "doi": authorship.get("doi"),
                    "paper_title": authorship.get("paper_title"),
                    "author_id": authorship["author_id"],
                    "author_name": authorship.get("author_name"),
                    "author_rank_one_based": authorship.get(
                        "author_rank_one_based"
                    ),
                    "author_count": authorship.get("author_count"),
                    "author_position": authorship.get("author_position"),
                    "is_first": bool(authorship.get("is_first")),
                    "is_last": bool(authorship.get("is_last")),
                    "is_corresponding": bool(authorship.get("is_corresponding")),
                    "openalex_author_id": authorship.get("openalex_author_id"),
                    "orcid": authorship.get("orcid"),
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
                    "authorship_provenance_hash": authorship.get("provenance_hash"),
                }
            )

    papers_with_authorships = {
        str(authorship["paper_id"]) for authorship in authorships
    }
    for paper in papers:
        if str(paper["paper_id"]) in papers_with_authorships:
            continue
        rows.append(
            {
                "paper_id": paper["paper_id"],
                "doi": paper.get("doi"),
                "paper_title": paper.get("title"),
                "author_count": 0,
                "is_first": False,
                "is_last": False,
                "is_corresponding": False,
                "mapping_status": "no_authorship_metadata",
                "raw_affiliations": [],
                "lineage": [],
                "resolved": False,
                "selected_for_default_comparison": False,
                "default_lead_balanced_fractional_credit": 0.0,
            }
        )

    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=AUTHOR_INSTITUTION_EXPORT_FIELDS)
    writer.writeheader()
    for row in rows:
        serialized = dict(row)
        for field in AUTHOR_INSTITUTION_EXPORT_FIELDS:
            if isinstance(serialized.get(field), (list, dict)):
                serialized[field] = json.dumps(
                    serialized[field], ensure_ascii=False, sort_keys=True
                )
        writer.writerow(
            {field: serialized.get(field) for field in AUTHOR_INSTITUTION_EXPORT_FIELDS}
        )
    return output.getvalue().encode("utf-8")


@dataclass(frozen=True)
class Tier1MetadataSnapshot:
    manifest: dict
    manifest_key: str
    manifest_sha256: str
    papers: tuple[dict, ...]
    authorships: tuple[dict, ...]
    affiliations: tuple[dict, ...]


class MetadataCountryNotFoundError(ValueError):
    """Raised when a country is absent from the filtered metadata snapshot."""


class Tier1MetadataSnapshotStore:
    """Load and hash-verify one configured institution metadata snapshot from S3."""

    def __init__(
        self,
        *,
        s3_client=None,
        bucket: str | None = None,
        manifest_key: str | None = None,
        corpus: MetadataCorpus = "tier1",
        cache_seconds: int = 300,
    ) -> None:
        if corpus not in CORPUS_DEFINITIONS:
            raise ValueError(f"Unsupported institution metadata corpus: {corpus}")
        self.corpus = corpus
        self.s3 = s3_client or boto3.client(
            "s3",
            region_name=os.getenv("PAS_AWS_REGION") or os.getenv("AWS_REGION"),
        )
        self.bucket = bucket or os.getenv("PAS_S3_ARTIFACTS_BUCKET", "")
        self.manifest_key = manifest_key or os.getenv(
            CORPUS_DEFINITIONS[corpus]["manifest_env"]
        )
        self.cache_seconds = cache_seconds
        self._cached: Tier1MetadataSnapshot | None = None
        self._cached_at = 0.0
        self._lock = Lock()

    def load(self) -> Tier1MetadataSnapshot:
        if not self.bucket:
            raise RuntimeError("PAS_S3_ARTIFACTS_BUCKET is not configured")
        now = time.monotonic()
        if self._cached is not None and now - self._cached_at < self.cache_seconds:
            return self._cached
        with self._lock:
            now = time.monotonic()
            if self._cached is not None and now - self._cached_at < self.cache_seconds:
                return self._cached
            manifest_key = self.manifest_key or self._latest_manifest_key()
            manifest_bytes = self._get(manifest_key)
            manifest = json.loads(manifest_bytes)
            self._validate_manifest(manifest)
            artifacts = {
                str(item["name"]): item
                for item in (manifest.get("storage") or {}).get("artifacts") or []
            }
            snapshot = Tier1MetadataSnapshot(
                manifest=manifest,
                manifest_key=manifest_key,
                manifest_sha256=hashlib.sha256(manifest_bytes).hexdigest(),
                papers=self._jsonl_artifact(artifacts, "papers.jsonl"),
                authorships=self._jsonl_artifact(artifacts, "authorships.jsonl"),
                affiliations=self._jsonl_artifact(artifacts, "affiliations.jsonl"),
            )
            self._cached = snapshot
            self._cached_at = time.monotonic()
            return snapshot

    def _latest_manifest_key(self) -> str:
        paginator = self.s3.get_paginator("list_objects_v2")
        candidates: list[tuple[datetime, str]] = []
        prefix = CORPUS_DEFINITIONS[self.corpus]["manifest_prefix"]
        for page in paginator.paginate(Bucket=self.bucket, Prefix=prefix):
            for item in page.get("Contents") or []:
                key = str(item.get("Key") or "")
                if key.endswith("/manifest.json"):
                    candidates.append((item["LastModified"], key))
        if not candidates:
            label = CORPUS_DEFINITIONS[self.corpus]["label"]
            raise RuntimeError(f"No {label} metadata manifest exists in S3")
        return max(candidates)[1]

    def _get(self, key: str) -> bytes:
        return self.s3.get_object(Bucket=self.bucket, Key=key)["Body"].read()

    def _jsonl_artifact(
        self,
        artifacts: dict[str, dict],
        name: str,
    ) -> tuple[dict, ...]:
        artifact = artifacts.get(name)
        if artifact is None or not artifact.get("s3_key"):
            raise RuntimeError(f"Metadata manifest is missing {name}")
        content = self._get(str(artifact["s3_key"]))
        actual_sha256 = hashlib.sha256(content).hexdigest()
        if actual_sha256 != artifact.get("sha256"):
            raise RuntimeError(f"S3 metadata hash mismatch for {name}")
        rows = tuple(
            json.loads(line)
            for line in content.decode("utf-8").splitlines()
            if line.strip()
        )
        expected_rows = artifact.get("rows")
        if expected_rows is not None and len(rows) != int(expected_rows):
            raise RuntimeError(f"S3 metadata row-count mismatch for {name}")
        return rows

    def _validate_manifest(self, manifest: dict) -> None:
        if manifest.get("schema_version") != "tier1_metadata_snapshot.v2":
            raise RuntimeError("Unsupported Tier 1 metadata snapshot schema")
        if manifest.get("kind") != "tier1_metadata_snapshot":
            raise RuntimeError("S3 object is not a Tier 1 metadata snapshot")
        if manifest.get("status") not in {"ready", "ready_with_warnings"}:
            raise RuntimeError("Tier 1 metadata snapshot is not ready")
        if (manifest.get("storage") or {}).get("separation_verified") is not True:
            raise RuntimeError("Metadata/full-text S3 separation is not verified")
        manifest_corpus = str((manifest.get("corpus") or {}).get("id") or "tier1")
        if manifest_corpus != self.corpus:
            raise RuntimeError(
                f"Metadata manifest corpus {manifest_corpus!r} does not match "
                f"requested corpus {self.corpus!r}"
            )


_default_stores: dict[str, Tier1MetadataSnapshotStore] = {}
_default_store_lock = Lock()


def get_snapshot_store(
    corpus: MetadataCorpus = "tier1",
) -> Tier1MetadataSnapshotStore:
    if corpus not in _default_stores:
        with _default_store_lock:
            if corpus not in _default_stores:
                _default_stores[corpus] = Tier1MetadataSnapshotStore(corpus=corpus)
    return _default_stores[corpus]


def build_authorship_institution_comparison(
    snapshot: Tier1MetadataSnapshot,
    filt: InstitutionMetadataFilter,
    *,
    credit_scheme: CreditScheme = "lead_balanced",
    author_role: AuthorRole = "all",
    affiliation_allocation: AffiliationAllocation = "fractional",
    focus_scope: FocusScope = "strict",
    min_affiliation_confidence: float = 0.8,
    limit: int | None = 30,
) -> dict:
    if credit_scheme not in CREDIT_SCHEMES:
        raise ValueError(f"Unknown credit scheme: {credit_scheme}")
    if author_role not in AUTHOR_ROLES:
        raise ValueError(f"Unknown author role: {author_role}")
    if affiliation_allocation not in {"fractional", "full"}:
        raise ValueError(f"Unknown affiliation allocation: {affiliation_allocation}")
    if focus_scope not in {"strict", "lineage"}:
        raise ValueError(f"Unknown focus scope: {focus_scope}")
    if not 0 <= min_affiliation_confidence <= 1:
        raise ValueError("min_affiliation_confidence must be between 0 and 1")
    if limit is not None and not 1 <= limit <= 200:
        raise ValueError("limit must be between 1 and 200")

    papers = [paper for paper in snapshot.papers if _paper_matches(paper, filt)]
    papers.sort(key=lambda row: str(row["paper_id"]))
    paper_by_id = {str(paper["paper_id"]): paper for paper in papers}
    authorships = [
        row for row in snapshot.authorships if str(row["paper_id"]) in paper_by_id
    ]
    affiliations_by_authorship: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for row in snapshot.affiliations:
        paper_id = str(row["paper_id"])
        if paper_id in paper_by_id:
            affiliations_by_authorship[(paper_id, str(row["author_id"]))].append(row)

    authorships_by_paper: dict[str, list[dict]] = defaultdict(list)
    for row in authorships:
        authorships_by_paper[str(row["paper_id"])].append(row)
    for rows in authorships_by_paper.values():
        rows.sort(key=lambda row: int(row["author_order_zero_based"]))

    institution_rows: dict[str, dict] = {}
    focus_credit = 0.0
    other_credit = 0.0
    focus_papers: set[str] = set()
    other_papers: set[str] = set()
    selected_author_credits = 0.0
    resolved_author_credits = 0.0
    selected_authorships = 0
    authorships_with_resolved_affiliations = 0
    unresolved_assertions = 0
    below_threshold_assertions = 0
    complete_papers: set[str] = set()
    incomplete_papers: set[str] = set()
    papers_without_authorship_metadata: set[str] = set()
    source_breakdown: Counter[str] = Counter()
    yearly: dict[int, dict[str, object]] = defaultdict(_empty_year)
    paper_author_institutions: dict[str, dict[str, set[str]]] = defaultdict(
        lambda: defaultdict(set)
    )
    network_institution_metadata: dict[str, dict] = {}

    for paper_id, paper in paper_by_id.items():
        year = paper.get("year")
        year_bucket = yearly[int(year)] if year is not None else None
        if year_bucket is not None:
            year_bucket["paper_ids"].add(paper_id)
        rows = authorships_by_paper.get(paper_id, [])
        if not rows:
            papers_without_authorship_metadata.add(paper_id)
            continue
        paper_complete = True
        for row in rows:
            author_id = str(row["author_id"])
            assertions = affiliations_by_authorship.get((paper_id, author_id), [])
            eligible, unresolved, below_threshold = _eligible_affiliations(
                assertions,
                min_affiliation_confidence=min_affiliation_confidence,
            )
            if not eligible or unresolved or below_threshold:
                paper_complete = False

            for affiliation in eligible:
                key = _institution_key(affiliation)
                is_focus = _is_focus_affiliation(affiliation, focus_scope)
                network_is_focus = _is_exact_focus_affiliation(affiliation)
                network_key = key
                paper_author_institutions[paper_id][author_id].add(network_key)
                network_institution_metadata.setdefault(
                    network_key,
                    {
                        "id": network_key,
                        "institution_id": affiliation.get("institution_id"),
                        "name": str(
                            affiliation.get("display_name")
                            or "Unknown institution"
                        ),
                        "ror": affiliation.get("ror"),
                        "openalex_id": affiliation.get("openalex_id"),
                        "country_code": affiliation.get("country_code"),
                        "is_focus": network_is_focus,
                    },
                )
                aggregate = institution_rows.setdefault(
                    key,
                    _empty_institution_aggregate(affiliation),
                )
                aggregate["paper_ids"].add(paper_id)
                aggregate["authorship_ids"].add(f"{paper_id}|{author_id}")
                if is_focus:
                    aggregate["contributes_to_focus"] = True
                    focus_papers.add(paper_id)
                    if year_bucket is not None:
                        year_bucket["focus_paper_ids"].add(paper_id)
                else:
                    other_papers.add(paper_id)
                    if year_bucket is not None:
                        year_bucket["other_paper_ids"].add(paper_id)

            if not _role_matches(author_role, row):
                continue
            credit = float((row.get("author_weights") or {}).get(credit_scheme) or 0)
            selected_authorships += 1
            selected_author_credits += credit
            unresolved_assertions += unresolved
            below_threshold_assertions += below_threshold
            if not eligible:
                continue
            authorships_with_resolved_affiliations += 1
            resolved_author_credits += credit
            allocation = (
                credit if affiliation_allocation == "full" else credit / len(eligible)
            )
            for affiliation in eligible:
                key = _institution_key(affiliation)
                aggregate = institution_rows.setdefault(
                    key,
                    _empty_institution_aggregate(affiliation),
                )
                aggregate["weighted_credit"] += allocation
                if row.get("is_first") is True:
                    aggregate["first_author_credit"] += allocation
                if row.get("is_last") is True:
                    aggregate["last_author_credit"] += allocation
                if row.get("is_corresponding") is True:
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

        (complete_papers if paper_complete else incomplete_papers).add(paper_id)

    network = _build_institution_collaboration_network(
        paper_author_institutions,
        network_institution_metadata,
        complete_papers,
    )

    institutions = [_finalize_institution(row) for row in institution_rows.values()]
    institutions.sort(
        key=lambda row: (-row["weighted_credit"], -row["paper_count"], row["name"])
    )
    resolved_total = focus_credit + other_credit
    for rank, row in enumerate(institutions, start=1):
        row["rank"] = rank
        row["share_of_resolved_credit"] = _ratio(row["weighted_credit"], resolved_total)
    focus_rank = (
        1 + sum(row["weighted_credit"] > round(focus_credit, 6) for row in institutions)
        if focus_credit
        else None
    )

    enrichment_run = snapshot.manifest.get("enrichment_run") or {}
    storage = snapshot.manifest.get("storage") or {}
    corpus = _snapshot_corpus(snapshot)
    projection = {
        "corpus": corpus["id"],
        "credit_scheme": credit_scheme,
        "author_role": author_role,
        "affiliation_allocation": affiliation_allocation,
        "focus_scope": focus_scope,
        "focus_ror": UOFT_ROR,
        "focus_openalex_id": UOFT_OPENALEX_ID,
        "paper_count_rule": "any_affiliated_author",
        "min_affiliation_confidence": min_affiliation_confidence,
        "enrichment_run_id": enrichment_run.get("id"),
        "input_sha256": enrichment_run.get("input_sha256"),
        "snapshot_id": storage.get("snapshot_id"),
    }
    filter_payload = _filter_payload(filt)
    paper_ids = list(paper_by_id)
    audit = {
        "filter": filter_payload,
        "filter_fingerprint": _sha256_json(filter_payload),
        "paper_set_sha256": _paper_set_sha256(paper_ids),
        "paper_set_encoding": PAPER_SET_ENCODING,
        "included_papers": len(paper_ids),
        "algorithm": "s3_metadata_authorship_institution_comparison.v2",
        "metric_definitions": {
            "weighted_credit": CREDIT_SCHEMES[credit_scheme]["description"],
            "paper_count": (
                "Distinct papers with at least one author affiliated with the institution. "
                "Author-role and credit-model filters do not change this count."
            ),
            "paper_institution_membership_coverage": (
                "Share of filtered papers for which every listed author has at least "
                "one eligible institution and every assertion is resolved above threshold."
            ),
            "focus_paper_share_of_corpus": (
                "Distinct papers with at least one resolved U of T affiliation "
                "divided by all filtered corpus papers in the same year."
            ),
            "institution_connection": (
                "Two institutions are connected when different authors represent "
                "them on the same paper with complete institution membership."
            ),
            "affiliation_allocation": (
                "Each author credit is divided equally among eligible affiliations."
                if affiliation_allocation == "fractional"
                else "Each eligible affiliation receives the author's full credit."
            ),
            "focus_scope": (
                "Only exact University of Toronto ROR/OpenAlex assertions count."
                if focus_scope == "strict"
                else "Exact assertions and OpenAlex descendants of U of T count."
            ),
            "role_filter": (
                f"{AUTHOR_ROLES[author_role]['description']} Original author "
                "credit is not renormalized."
            ),
        },
        "filter_semantics": {
            "allowed_metadata_filters": "year_from, year_to, and title-or-abstract search",
            "between_dimensions": "AND",
        },
        "data_boundary": {
            "mode": "metadata_only_s3_snapshot",
            "included": [
                "S3 papers.jsonl bibliographic metadata",
                "S3 authorships.jsonl author-order metadata",
                "S3 affiliations.jsonl institution assertions",
                "S3 metadata manifest and hashes",
            ],
            "excluded": [
                "primary application papers table",
                "full-text Markdown",
                "full-text chunks",
                "classification outputs",
                "human reviews",
                "RAG or extracted evidence",
            ],
        },
        "snapshot": {
            "bucket": storage.get("bucket"),
            "manifest_key": snapshot.manifest_key,
            "manifest_sha256": snapshot.manifest_sha256,
            "snapshot_id": storage.get("snapshot_id"),
            "raw_prefix": storage.get("raw_prefix"),
            "fulltext_prefix": storage.get("fulltext_prefix"),
            "separation_verified": storage.get("separation_verified"),
        },
        "projection": projection,
        "projection_fingerprint": _sha256_json(projection),
        "source_breakdown": dict(sorted(source_breakdown.items())),
        "authorship_metadata_rows": len(authorships),
        "scope_constraint": f"Immutable {corpus['label']} S3 metadata snapshot",
        "generated_at": datetime.now(UTC).isoformat(),
    }

    return {
        "available": bool(authorships),
        "scope": {
            "corpus_papers": len(papers),
            "papers_with_authorship_metadata": len(authorships_by_paper),
            "papers_with_complete_institution_membership": len(complete_papers),
            "papers_with_incomplete_institution_membership": len(incomplete_papers),
            "papers_without_authorship_metadata": len(
                papers_without_authorship_metadata
            ),
            "paper_institution_membership_coverage": _ratio(
                len(complete_papers), len(papers)
            ),
            "authorship_metadata_rows": len(authorships),
            "selected_authorships": selected_authorships,
            "authorships_with_resolved_affiliations": authorships_with_resolved_affiliations,
            "selected_author_credit": round(selected_author_credits, 6),
            "resolved_author_credit": round(resolved_author_credits, 6),
            "affiliation_credit_coverage": _ratio(
                resolved_author_credits, selected_author_credits
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
            "share_of_corpus_papers": _ratio(len(focus_papers), len(papers)),
            "share_of_resolved_credit": _ratio(focus_credit, resolved_total),
            "rank": focus_rank,
        },
        "comparison": {
            "other_institutions_weighted_credit": round(other_credit, 6),
            "other_institutions_paper_count": len(other_papers),
            "focus_to_other_credit_ratio": (
                round(focus_credit / other_credit, 6) if other_credit else None
            ),
        },
        "institutions": institutions if limit is None else institutions[:limit],
        "yearly": _finalize_yearly(yearly),
        "network": network,
        "configuration": {
            **projection,
            "credit_scheme_label": CREDIT_SCHEMES[credit_scheme]["label"],
            "credit_scheme_description": CREDIT_SCHEMES[credit_scheme]["description"],
            "author_role_label": AUTHOR_ROLES[author_role]["label"],
            "author_role_description": AUTHOR_ROLES[author_role]["description"],
        },
        "audit": audit,
    }


def build_metadata_geographic_overview(
    snapshot: Tier1MetadataSnapshot,
    filt: InstitutionMetadataFilter,
    *,
    min_affiliation_confidence: float = 0.8,
) -> dict:
    """Aggregate country coverage and collaboration from metadata only."""
    aggregates = _metadata_geographic_aggregates(
        snapshot,
        filt,
        min_affiliation_confidence=min_affiliation_confidence,
    )
    return _finalize_metadata_geographic_overview(
        snapshot,
        filt,
        aggregates,
        min_affiliation_confidence=min_affiliation_confidence,
    )


def build_metadata_country_detail(
    snapshot: Tier1MetadataSnapshot,
    filt: InstitutionMetadataFilter,
    country_code: str,
    *,
    credit_scheme: CreditScheme = "lead_balanced",
    author_role: AuthorRole = "all",
    affiliation_allocation: AffiliationAllocation = "fractional",
    min_affiliation_confidence: float = 0.8,
    limit: int = 100,
) -> dict:
    """Return one country's outline-ready summary and institution comparison."""
    normalized_country_code = _country_code(country_code)
    if normalized_country_code is None:
        raise MetadataCountryNotFoundError("Country code must be a two-letter code")
    if not 1 <= limit <= 200:
        raise ValueError("limit must be between 1 and 200")

    aggregates = _metadata_geographic_aggregates(
        snapshot,
        filt,
        min_affiliation_confidence=min_affiliation_confidence,
    )
    country_aggregate = aggregates["countries"].get(normalized_country_code)
    if country_aggregate is None:
        raise MetadataCountryNotFoundError(
            f"No metadata matches country {normalized_country_code}"
        )

    overview = _finalize_metadata_geographic_overview(
        snapshot,
        filt,
        aggregates,
        min_affiliation_confidence=min_affiliation_confidence,
    )
    country = next(
        row
        for row in overview["countries"]
        if row["country_code"] == normalized_country_code
    )
    comparison = build_authorship_institution_comparison(
        snapshot,
        filt,
        credit_scheme=credit_scheme,
        author_role=author_role,
        affiliation_allocation=affiliation_allocation,
        focus_scope="strict",
        min_affiliation_confidence=min_affiliation_confidence,
        limit=None,
    )
    institutions = [
        dict(row)
        for row in comparison["institutions"]
        if _country_code(row.get("country_code")) == normalized_country_code
    ]
    country_credit = sum(float(row["weighted_credit"]) for row in institutions)
    for rank, row in enumerate(institutions, start=1):
        row["rank"] = rank
        row["share_of_country_credit"] = _ratio(
            float(row["weighted_credit"]), country_credit
        )

    projection = {
        "country_code": normalized_country_code,
        "credit_scheme": credit_scheme,
        "author_role": author_role,
        "affiliation_allocation": affiliation_allocation,
        "paper_count_rule": "any_affiliated_author",
        "min_affiliation_confidence": min_affiliation_confidence,
        "snapshot_id": (snapshot.manifest.get("storage") or {}).get("snapshot_id"),
    }
    audit = {
        **overview["audit"],
        "algorithm": "s3_metadata_country_institution_comparison.v1",
        "metric_definitions": {
            **overview["audit"]["metric_definitions"],
            "weighted_credit": CREDIT_SCHEMES[credit_scheme]["description"],
            "share_of_country_credit": (
                "Institution weighted credit divided by all resolved weighted "
                "credit assigned to institutions carrying this country code."
            ),
        },
        "country_paper_set_sha256": _paper_set_sha256(
            list(country_aggregate["paper_ids"])
        ),
        "projection": projection,
        "projection_fingerprint": _sha256_json(projection),
    }
    return {
        "available": bool(institutions),
        "country": country,
        "institutions": institutions[:limit],
        "collaborations": [
            row
            for row in overview["collaborations"]
            if normalized_country_code in {row["source"], row["target"]}
        ],
        "scope": {
            **overview["scope"],
            "country_papers": country["paper_count"],
            "country_institutions": country["institution_count"],
            "country_authorships": country["authorship_count"],
            "country_weighted_credit": round(country_credit, 6),
        },
        "configuration": {
            **projection,
            "credit_scheme_label": CREDIT_SCHEMES[credit_scheme]["label"],
            "credit_scheme_description": CREDIT_SCHEMES[credit_scheme]["description"],
            "author_role_label": AUTHOR_ROLES[author_role]["label"],
            "author_role_description": AUTHOR_ROLES[author_role]["description"],
        },
        "audit": audit,
    }


def _metadata_geographic_aggregates(
    snapshot: Tier1MetadataSnapshot,
    filt: InstitutionMetadataFilter,
    *,
    min_affiliation_confidence: float,
) -> dict:
    if not 0 <= min_affiliation_confidence <= 1:
        raise ValueError("min_affiliation_confidence must be between 0 and 1")

    papers = [paper for paper in snapshot.papers if _paper_matches(paper, filt)]
    papers.sort(key=lambda row: str(row["paper_id"]))
    paper_by_id = {str(paper["paper_id"]): paper for paper in papers}
    authorships = [
        row for row in snapshot.authorships if str(row["paper_id"]) in paper_by_id
    ]
    authorships_by_paper: dict[str, list[dict]] = defaultdict(list)
    for row in authorships:
        authorships_by_paper[str(row["paper_id"])].append(row)

    affiliations_by_authorship: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for row in snapshot.affiliations:
        paper_id = str(row["paper_id"])
        if paper_id in paper_by_id:
            affiliations_by_authorship[(paper_id, str(row["author_id"]))].append(row)

    countries: dict[str, dict] = {}
    collaborations: dict[tuple[str, str], set[str]] = defaultdict(set)
    mapped_paper_ids: set[str] = set()
    cross_country_paper_ids: set[str] = set()
    all_institution_ids: set[str] = set()
    unresolved_assertions = 0
    below_threshold_assertions = 0
    missing_country_assertions = 0
    eligible_country_assertions = 0
    papers_without_authorship_metadata: set[str] = set()

    for paper_id, paper in paper_by_id.items():
        rows = authorships_by_paper.get(paper_id, [])
        if not rows:
            papers_without_authorship_metadata.add(paper_id)
            continue
        year = int(paper["year"]) if paper.get("year") is not None else None
        country_authors: dict[str, set[str]] = defaultdict(set)
        for authorship in rows:
            author_id = str(authorship["author_id"])
            eligible, unresolved, below_threshold = _eligible_affiliations(
                affiliations_by_authorship.get((paper_id, author_id), []),
                min_affiliation_confidence=min_affiliation_confidence,
            )
            unresolved_assertions += unresolved
            below_threshold_assertions += below_threshold
            for affiliation in eligible:
                country_code = _country_code(affiliation.get("country_code"))
                if country_code is None:
                    missing_country_assertions += 1
                    continue
                eligible_country_assertions += 1
                mapped_paper_ids.add(paper_id)
                institution_id = _institution_key(affiliation)
                all_institution_ids.add(institution_id)
                country_authors[country_code].add(author_id)
                aggregate = countries.setdefault(
                    country_code,
                    {
                        "paper_ids": set(),
                        "institution_ids": set(),
                        "authorship_ids": set(),
                        "cross_country_paper_ids": set(),
                        "yearly": defaultdict(
                            lambda: {
                                "paper_ids": set(),
                                "cross_country_paper_ids": set(),
                            }
                        ),
                    },
                )
                aggregate["paper_ids"].add(paper_id)
                aggregate["institution_ids"].add(institution_id)
                aggregate["authorship_ids"].add(f"{paper_id}|{author_id}")
                if year is not None:
                    aggregate["yearly"][year]["paper_ids"].add(paper_id)

        participating_countries: set[str] = set()
        country_codes = sorted(country_authors)
        for index, source in enumerate(country_codes):
            for target in country_codes[index + 1 :]:
                if any(
                    source_author != target_author
                    for source_author in country_authors[source]
                    for target_author in country_authors[target]
                ):
                    collaborations[(source, target)].add(paper_id)
                    participating_countries.update((source, target))
        if participating_countries:
            cross_country_paper_ids.add(paper_id)
            for country_code in participating_countries:
                aggregate = countries[country_code]
                aggregate["cross_country_paper_ids"].add(paper_id)
                if year is not None:
                    aggregate["yearly"][year]["cross_country_paper_ids"].add(paper_id)

    return {
        "papers": papers,
        "authorships": authorships,
        "countries": countries,
        "collaborations": collaborations,
        "mapped_paper_ids": mapped_paper_ids,
        "cross_country_paper_ids": cross_country_paper_ids,
        "institution_ids": all_institution_ids,
        "papers_without_authorship_metadata": papers_without_authorship_metadata,
        "unresolved_assertions": unresolved_assertions,
        "below_threshold_assertions": below_threshold_assertions,
        "missing_country_assertions": missing_country_assertions,
        "eligible_country_assertions": eligible_country_assertions,
    }


def _finalize_metadata_geographic_overview(
    snapshot: Tier1MetadataSnapshot,
    filt: InstitutionMetadataFilter,
    aggregates: dict,
    *,
    min_affiliation_confidence: float,
) -> dict:
    country_rows = [
        {
            "country_code": country_code,
            "paper_count": len(value["paper_ids"]),
            "institution_count": len(value["institution_ids"]),
            "authorship_count": len(value["authorship_ids"]),
            "cross_country_paper_count": len(value["cross_country_paper_ids"]),
            "yearly": [
                {
                    "year": year,
                    "paper_count": len(year_value["paper_ids"]),
                    "cross_country_paper_count": len(
                        year_value["cross_country_paper_ids"]
                    ),
                }
                for year, year_value in sorted(value["yearly"].items())
            ],
        }
        for country_code, value in aggregates["countries"].items()
    ]
    country_rows.sort(
        key=lambda row: (
            -row["paper_count"],
            -row["institution_count"],
            row["country_code"],
        )
    )
    collaboration_rows = [
        {
            "source": source,
            "target": target,
            "paper_count": len(paper_ids),
        }
        for (source, target), paper_ids in aggregates["collaborations"].items()
    ]
    collaboration_rows.sort(
        key=lambda row: (-row["paper_count"], row["source"], row["target"])
    )

    papers = aggregates["papers"]
    paper_ids = [str(paper["paper_id"]) for paper in papers]
    storage = snapshot.manifest.get("storage") or {}
    enrichment_run = snapshot.manifest.get("enrichment_run") or {}
    corpus = _snapshot_corpus(snapshot)
    projection = {
        "corpus": corpus["id"],
        "paper_count_rule": "any_affiliated_author",
        "collaboration_rule": "different_authors_across_two_countries",
        "min_affiliation_confidence": min_affiliation_confidence,
        "enrichment_run_id": enrichment_run.get("id"),
        "input_sha256": enrichment_run.get("input_sha256"),
        "snapshot_id": storage.get("snapshot_id"),
    }
    filter_payload = _filter_payload(filt)
    mapped_papers = len(aggregates["mapped_paper_ids"])
    scope = {
        "corpus_papers": len(papers),
        "mapped_papers": mapped_papers,
        "unmapped_papers": len(papers) - mapped_papers,
        "paper_country_coverage": _ratio(mapped_papers, len(papers)),
        "papers_without_authorship_metadata": len(
            aggregates["papers_without_authorship_metadata"]
        ),
        "authorship_metadata_rows": len(aggregates["authorships"]),
        "eligible_country_affiliation_assertions": aggregates[
            "eligible_country_assertions"
        ],
        "missing_country_affiliation_assertions": aggregates[
            "missing_country_assertions"
        ],
        "unresolved_affiliation_assertions": aggregates["unresolved_assertions"],
        "below_threshold_affiliation_assertions": aggregates[
            "below_threshold_assertions"
        ],
        "country_count": len(country_rows),
        "institution_count": len(aggregates["institution_ids"]),
        "cross_country_papers": len(aggregates["cross_country_paper_ids"]),
    }
    audit = {
        "filter": filter_payload,
        "filter_fingerprint": _sha256_json(filter_payload),
        "paper_set_sha256": _paper_set_sha256(paper_ids),
        "paper_set_encoding": PAPER_SET_ENCODING,
        "included_papers": len(paper_ids),
        "algorithm": "s3_metadata_geographic_collaboration.v1",
        "metric_definitions": {
            "paper_count": (
                "Distinct filtered papers with at least one eligible institution "
                "assertion carrying the country code."
            ),
            "cross_country_paper": (
                "A paper with eligible affiliations in two countries assigned to "
                "different authors; one author's dual affiliation alone does not count."
            ),
            "institution_count": (
                "Distinct normalized institution identifiers observed in the country."
            ),
        },
        "filter_semantics": {
            "allowed_metadata_filters": "year_from, year_to, and title-or-abstract search",
            "between_dimensions": "AND",
        },
        "data_boundary": {
            "mode": "metadata_only_s3_snapshot",
            "included": [
                "S3 papers.jsonl bibliographic metadata",
                "S3 authorships.jsonl author-order metadata",
                "S3 affiliations.jsonl institution assertions and country codes",
                "S3 metadata manifest and hashes",
            ],
            "excluded": [
                "primary application papers table",
                "full-text Markdown",
                "full-text chunks",
                "classification outputs",
                "human reviews",
                "RAG or extracted evidence",
            ],
        },
        "snapshot": {
            "bucket": storage.get("bucket"),
            "manifest_key": snapshot.manifest_key,
            "manifest_sha256": snapshot.manifest_sha256,
            "snapshot_id": storage.get("snapshot_id"),
            "raw_prefix": storage.get("raw_prefix"),
            "fulltext_prefix": storage.get("fulltext_prefix"),
            "separation_verified": storage.get("separation_verified"),
        },
        "projection": projection,
        "projection_fingerprint": _sha256_json(projection),
        "scope_constraint": f"Immutable {corpus['label']} S3 metadata snapshot",
        "generated_at": datetime.now(UTC).isoformat(),
    }
    return {
        "available": bool(country_rows),
        "scope": scope,
        "countries": country_rows,
        "collaborations": collaboration_rows,
        "configuration": projection,
        "audit": audit,
    }


def comparison_options(snapshot: Tier1MetadataSnapshot) -> dict:
    years = sorted(
        {
            int(paper["year"])
            for paper in snapshot.papers
            if paper.get("year") is not None
        }
    )
    return {
        "corpus": _snapshot_corpus(snapshot),
        "corpora": [
            {"id": corpus_id, "label": definition["label"]}
            for corpus_id, definition in CORPUS_DEFINITIONS.items()
        ],
        "focus": {"name": UOFT_NAME, "ror": UOFT_ROR, "openalex_id": UOFT_OPENALEX_ID},
        "years": years,
        "credit_schemes": [
            {"value": value, **definition}
            for value, definition in CREDIT_SCHEMES.items()
        ],
        "author_roles": [
            {"value": value, **definition} for value, definition in AUTHOR_ROLES.items()
        ],
        "affiliation_allocations": [
            {"value": "fractional", "label": "Fractional"},
            {"value": "full", "label": "Full"},
        ],
        "focus_scopes": [
            {"value": "strict", "label": "Exact U of T"},
            {"value": "lineage", "label": "U of T lineage"},
        ],
        "latest_enrichment_run": snapshot.manifest.get("enrichment_run"),
    }


def enrichment_status(snapshot: Tier1MetadataSnapshot) -> dict:
    scope = snapshot.manifest.get("scope") or {}
    storage = snapshot.manifest.get("storage") or {}
    paper_count = int(scope.get("papers") or len(snapshot.papers))
    enriched_papers = int(scope.get("papers_with_authorship_metadata") or 0)
    return {
        "corpus": _snapshot_corpus(snapshot),
        "paper_count": paper_count,
        "global_paper_count": paper_count,
        "enriched_paper_count": enriched_papers,
        "authorship_count": int(scope.get("authorships") or len(snapshot.authorships)),
        "paper_coverage": _ratio(enriched_papers, paper_count),
        "latest_enrichment_run": snapshot.manifest.get("enrichment_run"),
        "snapshot_id": storage.get("snapshot_id"),
        "manifest_key": snapshot.manifest_key,
        "separation_verified": storage.get("separation_verified") is True,
        "data_boundary": "metadata_only_s3_snapshot",
    }


def _paper_matches(paper: dict, filt: InstitutionMetadataFilter) -> bool:
    year = paper.get("year")
    if filt.year_from is not None and (year is None or int(year) < filt.year_from):
        return False
    if filt.year_to is not None and (year is None or int(year) > filt.year_to):
        return False
    if filt.search:
        haystack = (
            f"{paper.get('title') or ''}\n{paper.get('abstract') or ''}".casefold()
        )
        if filt.search.casefold() not in haystack:
            return False
    return True


def _snapshot_corpus(snapshot: Tier1MetadataSnapshot) -> dict[str, str]:
    manifest_corpus = snapshot.manifest.get("corpus") or {}
    corpus_id = str(manifest_corpus.get("id") or "tier1")
    definition = CORPUS_DEFINITIONS.get(corpus_id, CORPUS_DEFINITIONS["tier1"])
    return {
        "id": corpus_id,
        "label": str(manifest_corpus.get("label") or definition["label"]),
    }


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


def _role_matches(role: AuthorRole, row: dict) -> bool:
    if role == "all":
        return True
    if role == "first":
        return row.get("is_first") is True
    if role == "last":
        return row.get("is_last") is True
    if role == "middle":
        return row.get("is_first") is not True and row.get("is_last") is not True
    return row.get("is_corresponding") is True


def _institution_key(value: dict) -> str:
    return str(
        value.get("institution_id")
        or value.get("ror")
        or value.get("openalex_id")
        or normalize_institution(str(value.get("display_name") or ""))
    )


def _country_code(value: object) -> str | None:
    code = str(value or "").strip().upper()
    return code if len(code) == 2 and code.isalpha() else None


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
        "corresponding_author_credit": round(value["corresponding_author_credit"], 6),
        "sources": dict(sorted(value["sources"].items())),
        "contributes_to_focus": value["contributes_to_focus"],
    }


def _is_focus_affiliation(value: dict, scope: FocusScope) -> bool:
    if _is_exact_focus_affiliation(value):
        return True
    if scope == "lineage":
        lineage = {
            str(item).rstrip("/").casefold() for item in value.get("lineage") or []
        }
        return UOFT_OPENALEX_ID.casefold() in lineage
    return False


def _is_exact_focus_affiliation(value: dict) -> bool:
    ror = str(value.get("ror") or "").rstrip("/").casefold()
    openalex_id = str(value.get("openalex_id") or "").rstrip("/").casefold()
    return ror == UOFT_ROR.casefold() or openalex_id == UOFT_OPENALEX_ID.casefold()


def _empty_year() -> dict[str, object]:
    return {
        "paper_ids": set(),
        "focus_paper_ids": set(),
        "other_paper_ids": set(),
        "focus_weighted_credit": 0.0,
        "other_weighted_credit": 0.0,
    }


def _finalize_yearly(values: dict[int, dict[str, object]]) -> list[dict]:
    return [
        {
            "year": year,
            "corpus_papers": len(value["paper_ids"]),
            "focus_papers": len(value["focus_paper_ids"]),
            "focus_paper_share_of_corpus": _ratio(
                len(value["focus_paper_ids"]),
                len(value["paper_ids"]),
            ),
            "other_institution_papers": len(value["other_paper_ids"]),
            "focus_weighted_credit": round(float(value["focus_weighted_credit"]), 6),
            "other_weighted_credit": round(float(value["other_weighted_credit"]), 6),
        }
        for year, value in sorted(values.items())
    ]


def _build_institution_collaboration_network(
    paper_author_institutions: dict[str, dict[str, set[str]]],
    institution_metadata: dict[str, dict],
    complete_papers: set[str],
) -> dict:
    edge_papers: dict[tuple[str, str], set[str]] = defaultdict(set)
    node_papers: dict[str, set[str]] = defaultdict(set)

    for paper_id in sorted(complete_papers):
        authors = paper_author_institutions.get(paper_id) or {}
        author_institution_sets = [
            institutions for institutions in authors.values() if institutions
        ]
        for institution_id in set().union(*author_institution_sets):
            node_papers[institution_id].add(paper_id)
        for left, right in combinations(author_institution_sets, 2):
            for source in left:
                for target in right:
                    if source == target:
                        continue
                    edge_papers[tuple(sorted((source, target)))].add(paper_id)

    collaborators: dict[str, set[str]] = defaultdict(set)
    collaboration_papers: dict[str, set[str]] = defaultdict(set)
    connection_weight: Counter[str] = Counter()
    edges: list[dict] = []
    papers_with_connections: set[str] = set()
    for (source, target), paper_ids in edge_papers.items():
        weight = len(paper_ids)
        collaborators[source].add(target)
        collaborators[target].add(source)
        collaboration_papers[source].update(paper_ids)
        collaboration_papers[target].update(paper_ids)
        connection_weight[source] += weight
        connection_weight[target] += weight
        papers_with_connections.update(paper_ids)
        edges.append(
            {
                "source": source,
                "target": target,
                "paper_count": weight,
            }
        )
    edges.sort(key=lambda row: (-row["paper_count"], row["source"], row["target"]))

    nodes = [
        {
            **institution_metadata[institution_id],
            "paper_count": len(paper_ids),
            "collaborator_count": len(collaborators[institution_id]),
            "collaboration_paper_count": len(collaboration_papers[institution_id]),
            "connection_weight": connection_weight[institution_id],
        }
        for institution_id, paper_ids in node_papers.items()
    ]
    nodes.sort(
        key=lambda row: (
            -row["collaborator_count"],
            -row["connection_weight"],
            -row["paper_count"],
            row["name"],
        )
    )
    current_rank = 0
    previous_collaborator_count: int | None = None
    for index, node in enumerate(nodes, start=1):
        if node["collaborator_count"] != previous_collaborator_count:
            current_rank = index
            previous_collaborator_count = node["collaborator_count"]
        node["rank"] = current_rank

    focus_node = next((node for node in nodes if node["is_focus"]), None)
    focus_summary = None
    if focus_node is not None:
        institutions_with_fewer_connections = sum(
            focus_node["collaborator_count"] > node["collaborator_count"]
            for node in nodes
            if not node["is_focus"]
        )
        focus_summary = {
            **focus_node,
            "institutions_with_fewer_collaborators": (
                institutions_with_fewer_connections
            ),
            "fraction_of_institutions_with_fewer_collaborators": _ratio(
                institutions_with_fewer_connections,
                max(len(nodes) - 1, 0),
            ),
        }

    displayed_nodes = nodes[:NETWORK_NODE_LIMIT]
    if focus_node is not None and all(
        node["id"] != focus_node["id"] for node in displayed_nodes
    ):
        displayed_nodes = [*displayed_nodes[:-1], focus_node]
        displayed_nodes.sort(key=lambda row: row["rank"])
    displayed_ids = {node["id"] for node in displayed_nodes}
    displayed_edges = [
        edge
        for edge in edges
        if edge["source"] in displayed_ids and edge["target"] in displayed_ids
    ]

    ranking = nodes[:NETWORK_RANKING_LIMIT]
    if focus_node is not None and all(
        node["id"] != focus_node["id"] for node in ranking
    ):
        ranking = [*ranking, focus_node]

    return {
        "available": bool(edges),
        "scope": {
            "complete_papers": len(complete_papers),
            "papers_with_connections": len(papers_with_connections),
            "institution_count": len(nodes),
            "connection_count": len(edges),
            "displayed_node_count": len(displayed_nodes),
            "displayed_connection_count": len(displayed_edges),
            "node_limit": NETWORK_NODE_LIMIT,
        },
        "focus": focus_summary,
        "nodes": displayed_nodes,
        "edges": displayed_edges,
        "ranking": ranking,
        "method": {
            "paper_scope": "papers_with_complete_institution_membership",
            "connection_rule": "different_authors_same_paper",
            "collaborator_count_rule": "distinct_connected_institutions",
            "edge_weight_rule": "distinct_shared_papers",
            "focus_identity_rule": "exact_uoft_ror_or_openalex_id",
        },
    }


def _filter_payload(filt: InstitutionMetadataFilter) -> dict:
    return {
        key: value
        for key, value in {
            "year_from": filt.year_from,
            "year_to": filt.year_to,
            "search": filt.search,
        }.items()
        if value is not None
    }


def _paper_set_sha256(paper_ids: list[str]) -> str:
    return _sha256_json(
        {"encoding": PAPER_SET_ENCODING, "paper_ids": sorted(set(paper_ids))}
    )


def _sha256_json(value: object) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _ratio(numerator: float, denominator: float) -> float:
    return round(numerator / denominator, 6) if denominator else 0.0
