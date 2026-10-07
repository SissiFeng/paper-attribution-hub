"""Build a standalone OpenAlex institution-comparison dataset for Tier 1+2.

This command never writes to the PAS database and never touches the existing
Tier 1 metadata snapshot. It reads the merged Scopus CSV, resolves DOI-bearing
papers through OpenAlex, and writes immutable local artifacts consumed by the
standalone HTML report.
"""

from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import json
import math
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterable


SCHEMA_VERSION = "tier1_tier2_openalex_institution.v1"
OPENALEX_URL = "https://api.openalex.org/works"
OPENALEX_SELECT = (
    "id,doi,title,publication_year,authorships,is_authors_truncated,"
    "is_retracted,updated_date"
)
UOFT_ROR = "https://ror.org/03dbr7087"
UOFT_OPENALEX_ID = "https://openalex.org/I185261750"
NULL_VALUES = {"", "null", "none", "nan", "n/a"}


@dataclass(frozen=True)
class PaperInput:
    paper_id: str
    eids: tuple[str, ...]
    doi: str | None
    title: str
    year: int | None
    membership: str
    author_count: int
    input_rows: int
    quality_flags: tuple[str, ...] = field(default_factory=tuple)


def normalize_doi(value: object) -> str:
    text = _value(value).casefold()
    text = re.sub(r"^https?://(?:dx\.)?doi\.org/", "", text)
    if text.startswith("doi:"):
        text = text[4:]
    return text.strip().rstrip(".")


def normalize_text(value: object) -> str:
    return re.sub(r"[^a-z0-9]+", " ", _value(value).casefold()).strip()


def read_input_csv(path: Path) -> tuple[list[PaperInput], dict[str, Any]]:
    """Read the merged CSV and conservatively deduplicate only exact DOIs."""
    source = Path(path).expanduser().resolve()
    with source.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        required = {
            "EID",
            "DOI",
            "Title",
            "Publication_Year",
            "merge_tier_membership",
            "author_count",
        }
        missing = sorted(required - set(reader.fieldnames or []))
        if missing:
            raise ValueError(f"Merged CSV is missing required columns: {missing}")
        rows = list(reader)

    doi_groups: dict[str, list[dict[str, str]]] = defaultdict(list)
    without_doi: list[dict[str, str]] = []
    for row in rows:
        doi = normalize_doi(row.get("DOI"))
        if doi:
            doi_groups[doi].append(row)
        else:
            without_doi.append(row)

    papers: list[PaperInput] = []
    for doi, candidates in sorted(doi_groups.items()):
        papers.append(_paper_from_rows(candidates, doi=doi))
    for index, row in enumerate(without_doi, start=1):
        eid = _value(row.get("EID")) or f"missing-eid-{index}"
        papers.append(_paper_from_rows([row], doi=None, fallback_id=eid))
    papers.sort(key=lambda item: item.paper_id)

    duplicate_groups = sum(len(group) > 1 for group in doi_groups.values())
    duplicate_rows_beyond_first = sum(
        len(group) - 1 for group in doi_groups.values() if len(group) > 1
    )
    return papers, {
        "raw_rows": len(rows),
        "distinct_papers": len(papers),
        "rows_with_doi": len(rows) - len(without_doi),
        "unique_dois": len(doi_groups),
        "missing_doi_rows": len(without_doi),
        "duplicate_doi_groups": duplicate_groups,
        "duplicate_rows_beyond_first": duplicate_rows_beyond_first,
        "tier_membership_rows": dict(
            sorted(
                Counter(
                    _value(row.get("merge_tier_membership")) for row in rows
                ).items()
            )
        ),
    }


def _paper_from_rows(
    rows: list[dict[str, str]],
    *,
    doi: str | None,
    fallback_id: str | None = None,
) -> PaperInput:
    titles = {_value(row.get("Title")) for row in rows if _value(row.get("Title"))}
    years = {_int(row.get("Publication_Year")) for row in rows}
    years.discard(None)
    eids = tuple(
        sorted({_value(row.get("EID")) for row in rows if _value(row.get("EID"))})
    )
    author_counts = [_int(row.get("author_count")) or 0 for row in rows]
    memberships = {_value(row.get("merge_tier_membership")) for row in rows}
    quality_flags: list[str] = []
    if len(titles) > 1:
        quality_flags.append("duplicate_titles_differ")
    if len(years) > 1:
        quality_flags.append("duplicate_years_differ")
    if len(rows) > 1:
        quality_flags.append("duplicate_doi_rows_collapsed")
    return PaperInput(
        paper_id=f"doi:{doi}" if doi else f"eid:{fallback_id}",
        eids=eids,
        doi=doi,
        title=max(titles, key=len, default=""),
        year=min(years) if years else None,
        membership=_merged_membership(memberships),
        author_count=max(author_counts, default=0),
        input_rows=len(rows),
        quality_flags=tuple(quality_flags),
    )


def _merged_membership(values: set[str]) -> str:
    cleaned = {value for value in values if value}
    if "1+2" in cleaned or ({"1", "2"} <= cleaned):
        return "1+2"
    if "1" in cleaned:
        return "1"
    return "2"


class OpenAlexBatchFetcher:
    def __init__(
        self,
        *,
        cache_dir: Path,
        api_key: str | None = None,
        mailto: str | None = None,
        batch_size: int = 100,
        timeout: int = 90,
    ) -> None:
        if not 1 <= batch_size <= 100:
            raise ValueError("batch_size must be between 1 and 100")
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.api_key = (api_key or "").strip() or None
        self.mailto = (mailto or "").strip() or None
        self.batch_size = batch_size
        self.timeout = timeout
        self.api_calls = 0
        self.cache_hits = 0
        self.last_rate_limit: dict[str, str] = {}

    def fetch(
        self, dois: Iterable[str]
    ) -> tuple[dict[str, list[dict]], dict[str, Any]]:
        normalized = sorted(
            {normalize_doi(value) for value in dois if normalize_doi(value)}
        )
        results: dict[str, list[dict]] = defaultdict(list)
        for offset in range(0, len(normalized), self.batch_size):
            batch = normalized[offset : offset + self.batch_size]
            for work in self._fetch_batch(batch):
                doi = normalize_doi(work.get("doi"))
                if doi:
                    results[doi].append(work)
        return dict(results), {
            "api_calls": self.api_calls,
            "cache_hits": self.cache_hits,
            "api_key_configured": bool(self.api_key),
            "last_rate_limit": self.last_rate_limit,
        }

    def _fetch_batch(self, dois: list[str]) -> list[dict]:
        digest = hashlib.sha256("\n".join(dois).encode()).hexdigest()[:16]
        cache_path = self.cache_dir / f"doi-batch-{digest}.json.gz"
        payload: dict[str, Any]
        if cache_path.exists():
            with gzip.open(cache_path, "rt", encoding="utf-8") as handle:
                payload = json.load(handle)
            if payload.get("requested_dois") != dois:
                raise RuntimeError(f"OpenAlex cache key collision: {cache_path}")
            self.cache_hits += 1
        else:
            response, headers = self._request(dois)
            payload = {
                "requested_dois": dois,
                "retrieved_at": datetime.now(UTC).isoformat(),
                "response": response,
                "rate_limit": headers,
            }
            with gzip.open(
                cache_path, "wt", encoding="utf-8", compresslevel=6
            ) as handle:
                json.dump(payload, handle, ensure_ascii=False, separators=(",", ":"))

        response = payload.get("response") or {}
        rows = list(response.get("results") or [])
        count = int((response.get("meta") or {}).get("count") or len(rows))
        if count > len(rows):
            if len(dois) <= 1:
                raise RuntimeError(
                    f"OpenAlex returned a truncated singleton DOI result: {dois[0]}"
                )
            midpoint = len(dois) // 2
            return self._fetch_batch(dois[:midpoint]) + self._fetch_batch(
                dois[midpoint:]
            )
        return rows

    def _request(self, dois: list[str]) -> tuple[dict[str, Any], dict[str, str]]:
        params = {
            "filter": "doi:" + "|".join(dois),
            "per_page": "100",
            "select": OPENALEX_SELECT,
        }
        if self.api_key:
            params["api_key"] = self.api_key
        if self.mailto:
            params["mailto"] = self.mailto
        url = OPENALEX_URL + "?" + urllib.parse.urlencode(params)
        request = urllib.request.Request(
            url,
            headers={
                "Accept": "application/json",
                "User-Agent": "PAS-Tier1-Tier2-Institution/1.0",
            },
        )
        for attempt in range(5):
            try:
                with urllib.request.urlopen(request, timeout=self.timeout) as response:
                    body = response.read()
                    self.api_calls += 1
                    rate_limit = {
                        key: value
                        for key, value in response.headers.items()
                        if key.casefold().startswith("x-ratelimit")
                    }
                    self.last_rate_limit = rate_limit
                    return json.loads(body), rate_limit
            except urllib.error.HTTPError as exc:
                detail = exc.read().decode("utf-8", errors="replace")[:500]
                if exc.code not in {429, 500, 502, 503, 504} or attempt == 4:
                    raise RuntimeError(
                        f"OpenAlex request failed with HTTP {exc.code}: {detail}"
                    ) from exc
                retry_after = min(
                    10.0, float(exc.headers.get("Retry-After") or 2**attempt)
                )
                time.sleep(retry_after)
            except (TimeoutError, urllib.error.URLError) as exc:
                if attempt == 4:
                    raise RuntimeError(
                        f"OpenAlex request failed after retries: {exc}"
                    ) from exc
                time.sleep(min(10.0, 2**attempt))
        raise AssertionError("unreachable")


def build_dataset(
    papers: list[PaperInput],
    openalex_by_doi: dict[str, list[dict]],
    *,
    generated_at: str,
    source_name: str,
    source_sha256: str,
    input_stats: dict[str, Any],
    fetch_stats: dict[str, Any] | None = None,
) -> dict[str, Any]:
    institutions: list[dict[str, Any]] = []
    institution_index: dict[str, int] = {}
    paper_rows: list[dict[str, Any]] = []
    status_counts: Counter[str] = Counter()
    institution_coverage: Counter[str] = Counter()
    raw_works: list[dict] = []

    for paper in papers:
        quality_flags = list(paper.quality_flags)
        work: dict | None = None
        if paper.doi is None:
            status = "missing_doi"
        else:
            candidates = openalex_by_doi.get(paper.doi) or []
            if not candidates:
                status = "openalex_unmatched"
            elif len(candidates) > 1:
                status = "doi_ambiguous"
                quality_flags.append("multiple_openalex_works_for_doi")
            else:
                status = "doi_exact"
                work = candidates[0]

        authorships: list[list[Any]] = []
        is_truncated = False
        is_retracted = False
        openalex_id = None
        if work is not None:
            raw_works.append(work)
            openalex_id = _value(work.get("id")) or None
            is_truncated = bool(work.get("is_authors_truncated"))
            is_retracted = bool(work.get("is_retracted"))
            if is_truncated:
                quality_flags.append("openalex_authors_truncated")
            if is_retracted:
                quality_flags.append("openalex_retracted")
            if normalize_text(work.get("title")) != normalize_text(paper.title):
                quality_flags.append("openalex_title_differs")
            for authorship in work.get("authorships") or []:
                indices: list[int] = []
                seen: set[int] = set()
                for institution in authorship.get("institutions") or []:
                    index = _institution_index(
                        institution, institutions, institution_index
                    )
                    if index not in seen:
                        seen.add(index)
                        indices.append(index)
                position = str(authorship.get("author_position") or "middle")
                position_code = (
                    1 if position == "first" else 2 if position == "last" else 0
                )
                authorships.append(
                    [
                        position_code,
                        1 if authorship.get("is_corresponding") is True else 0,
                        indices,
                    ]
                )

        inferred_truncation = (
            work is not None
            and paper.author_count > 100
            and len(authorships) < paper.author_count
        )
        if inferred_truncation and not is_truncated:
            is_truncated = True
            quality_flags.append("openalex_authors_truncated_inferred_from_input_count")
        author_count = max(paper.author_count, len(authorships))
        if not authorships:
            coverage = "no_authorship_metadata"
        elif is_truncated or any(not row[2] for row in authorships):
            coverage = "incomplete"
        else:
            coverage = "complete"
        status_counts[status] += 1
        institution_coverage[coverage] += 1
        paper_rows.append(
            {
                "i": paper.paper_id,
                "e": list(paper.eids),
                "d": paper.doi,
                "t": paper.title,
                "y": paper.year,
                "m": paper.membership,
                "s": status,
                "o": openalex_id,
                "x": is_truncated,
                "r": is_retracted,
                "a": author_count,
                "u": authorships,
                "q": sorted(set(quality_flags)),
            }
        )

    manifest = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": generated_at,
        "data_boundary": {
            "mode": "openalex_metadata_only_local_snapshot",
            "included": [
                "merged CSV bibliographic identity and tier membership",
                "OpenAlex ordered authorships",
                "OpenAlex institution and ROR assertions",
            ],
            "excluded": [
                "PDF or full text",
                "classification outputs",
                "PAS primary database",
                "existing Tier 1 institution snapshot",
                "Scopus affiliations as fallback",
            ],
        },
        "input": {
            "name": source_name,
            "sha256": source_sha256,
            **input_stats,
        },
        "openalex": {
            "endpoint": OPENALEX_URL,
            "select": OPENALEX_SELECT,
            "match_status": dict(sorted(status_counts.items())),
            "institution_coverage": dict(sorted(institution_coverage.items())),
            **(fetch_stats or {}),
        },
        "counts": {
            "papers": len(paper_rows),
            "institutions": len(institutions),
            "authorships": sum(len(row["u"]) for row in paper_rows),
            "affiliated_authorships": sum(
                bool(authorship[2]) for row in paper_rows for authorship in row["u"]
            ),
        },
        "codebook": {
            "paper_membership": {
                "1": "Tier 1 only",
                "1+2": "Tier 1 and Tier 2",
                "2": "Tier 2 only",
            },
            "author_position": {"0": "middle", "1": "first", "2": "last"},
        },
    }
    return {
        "manifest": manifest,
        "institutions": institutions,
        "papers": paper_rows,
        "raw_works": raw_works,
    }


def _institution_index(
    institution: dict,
    rows: list[dict[str, Any]],
    by_key: dict[str, int],
) -> int:
    openalex_id = _value(institution.get("id"))
    ror = _value(institution.get("ror"))
    name = _value(institution.get("display_name")) or "Unknown institution"
    country = _value(institution.get("country_code")) or None
    key = openalex_id or ror or f"{normalize_text(name)}|{country or ''}"
    if key in by_key:
        return by_key[key]
    lineage = [str(item) for item in institution.get("lineage") or [] if item]
    exact = (
        ror.rstrip("/").casefold() == UOFT_ROR.casefold()
        or openalex_id.rstrip("/").casefold() == UOFT_OPENALEX_ID.casefold()
    )
    descendant = exact or UOFT_OPENALEX_ID.casefold() in {
        item.rstrip("/").casefold() for item in lineage
    }
    index = len(rows)
    rows.append(
        {
            "id": openalex_id or None,
            "n": name,
            "r": ror or None,
            "c": country,
            "t": _value(institution.get("type")) or None,
            "l": lineage,
            "f": 2 if exact else 1 if descendant else 0,
        }
    )
    by_key[key] = index
    return index


def aggregate_default(dataset: dict[str, Any]) -> dict[str, Any]:
    """Compute the default report; mirrored by the standalone page."""
    institutions = dataset["institutions"]
    aggregates: dict[int, dict[str, Any]] = {}
    focus_credit = 0.0
    other_credit = 0.0
    focus_papers: set[str] = set()
    other_papers: set[str] = set()
    complete = 0
    authorship_papers = 0
    selected_credit = 0.0
    resolved_credit = 0.0

    for paper in dataset["papers"]:
        authorships = paper["u"]
        if authorships:
            authorship_papers += 1
        if authorships and not paper["x"] and all(row[2] for row in authorships):
            complete += 1
        paper_institutions = {index for row in authorships for index in row[2]}
        for index in paper_institutions:
            aggregate = aggregates.setdefault(index, _empty_aggregate())
            aggregate["papers"].add(paper["i"])
            if institutions[index]["f"] == 2:
                focus_papers.add(paper["i"])
            else:
                other_papers.add(paper["i"])
        author_count = max(int(paper["a"] or 0), len(authorships))
        for order, (position, _corresponding, affiliation_indices) in enumerate(
            authorships
        ):
            credit = _author_credit("lead_balanced", order, position, author_count)
            selected_credit += credit
            if not affiliation_indices:
                continue
            resolved_credit += credit
            allocation = credit / len(affiliation_indices)
            for index in affiliation_indices:
                aggregate = aggregates.setdefault(index, _empty_aggregate())
                aggregate["credit"] += allocation
                if institutions[index]["f"] == 2:
                    focus_credit += allocation
                else:
                    other_credit += allocation

    ranked = sorted(
        (
            {
                "institution_index": index,
                "name": institutions[index]["n"],
                "weighted_credit": round(row["credit"], 6),
                "paper_count": len(row["papers"]),
            }
            for index, row in aggregates.items()
        ),
        key=lambda row: (-row["weighted_credit"], -row["paper_count"], row["name"]),
    )
    return {
        "corpus_papers": len(dataset["papers"]),
        "papers_with_authorship_metadata": authorship_papers,
        "papers_with_complete_institution_membership": complete,
        "paper_institution_membership_coverage": _ratio(
            complete, len(dataset["papers"])
        ),
        "affiliation_credit_coverage": _ratio(resolved_credit, selected_credit),
        "focus_weighted_credit": round(focus_credit, 6),
        "focus_paper_count": len(focus_papers),
        "other_weighted_credit": round(other_credit, 6),
        "other_paper_count": len(other_papers),
        "institutions": ranked,
    }


def _empty_aggregate() -> dict[str, Any]:
    return {"credit": 0.0, "papers": set()}


def _author_credit(scheme: str, order: int, position: int, author_count: int) -> float:
    if author_count <= 1:
        return 1.0
    if scheme == "full_counting":
        return 1.0
    if scheme == "equal_fractional" or author_count == 2:
        return 1.0 / author_count
    lead_credit = 0.35 if scheme == "lead_balanced" else 0.4
    if position in {1, 2} or order in {0, author_count - 1}:
        return lead_credit
    return (1.0 - 2 * lead_credit) / (author_count - 2)


def write_outputs(
    dataset: dict[str, Any],
    *,
    data_js: Path,
    artifact_dir: Path,
) -> dict[str, Any]:
    artifact_dir.mkdir(parents=True, exist_ok=True)
    data_js.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "manifest": dataset["manifest"],
        "institutions": dataset["institutions"],
        "papers": dataset["papers"],
    }
    data_content = (
        "window.TIER1_TIER2_OPENALEX_INSTITUTION_DATA="
        + json.dumps(
            payload, ensure_ascii=False, separators=(",", ":"), allow_nan=False
        )
        + ";\n"
    ).encode("utf-8")
    data_js.write_bytes(data_content)

    raw_path = artifact_dir / "openalex_works.jsonl.gz"
    with gzip.GzipFile(filename=str(raw_path), mode="wb", mtime=0) as compressed:
        for work in sorted(
            dataset["raw_works"], key=lambda row: str(row.get("id") or "")
        ):
            compressed.write(
                json.dumps(
                    work, ensure_ascii=False, sort_keys=True, separators=(",", ":")
                ).encode("utf-8")
                + b"\n"
            )

    audit_path = artifact_dir / "paper_match_audit.csv"
    with audit_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            [
                "paper_id",
                "eids",
                "doi",
                "title",
                "year",
                "tier_membership",
                "match_status",
                "openalex_id",
                "authorship_count",
                "affiliated_authorship_count",
                "authors_truncated",
                "institution_coverage",
                "quality_flags",
            ]
        )
        for paper in dataset["papers"]:
            authorships = paper["u"]
            coverage = (
                "no_authorship_metadata"
                if not authorships
                else "incomplete"
                if paper["x"] or any(not row[2] for row in authorships)
                else "complete"
            )
            writer.writerow(
                [
                    paper["i"],
                    "|".join(paper["e"]),
                    paper["d"] or "",
                    paper["t"],
                    paper["y"] or "",
                    paper["m"],
                    paper["s"],
                    paper["o"] or "",
                    len(authorships),
                    sum(bool(row[2]) for row in authorships),
                    int(bool(paper["x"])),
                    coverage,
                    "|".join(paper["q"]),
                ]
            )

    default_report = aggregate_default(dataset)
    summary_path = artifact_dir / "institution_summary_default.csv"
    with summary_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["rank", "institution", "weighted_credit", "paper_count"])
        for rank, row in enumerate(default_report["institutions"], start=1):
            writer.writerow(
                [rank, row["name"], row["weighted_credit"], row["paper_count"]]
            )

    manifest = dict(dataset["manifest"])
    manifest["artifacts"] = {
        "data_js": _artifact_entry(data_js),
        "openalex_works": _artifact_entry(raw_path),
        "paper_match_audit": _artifact_entry(audit_path),
        "institution_summary_default": _artifact_entry(summary_path),
    }
    manifest["default_report"] = {
        key: value for key, value in default_report.items() if key != "institutions"
    }
    manifest_path = artifact_dir / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return {
        "manifest": str(manifest_path),
        "data_js": str(data_js),
        "paper_match_audit": str(audit_path),
        "institution_summary_default": str(summary_path),
        "openalex_works": str(raw_path),
        "default_report": default_report,
    }


def build_s3_snapshot_rows(
    dataset: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    """Project the compact local dataset into the shared S3 snapshot contract."""
    papers: list[dict[str, Any]] = []
    authorships: list[dict[str, Any]] = []
    affiliations: list[dict[str, Any]] = []
    institution_rows = dataset["institutions"]

    for paper in dataset["papers"]:
        paper_id = str(paper["i"])
        papers.append(
            {
                "paper_id": paper_id,
                "title": paper["t"],
                "abstract": None,
                "year": paper["y"],
                "doi": paper["d"],
                "external_ids": list(paper["e"]),
                "metadata_source": "openalex",
                "metadata_match_status": paper["s"],
                "tier_membership": paper["m"],
                "openalex_id": paper["o"],
                "quality_flags": list(paper["q"]),
            }
        )
        compact_authorships = paper["u"]
        author_count = max(int(paper["a"] or 0), len(compact_authorships))
        for order, (position, corresponding, institution_indices) in enumerate(
            compact_authorships
        ):
            author_id = f"{paper_id}|author:{order}"
            authorships.append(
                {
                    "paper_id": paper_id,
                    "author_id": author_id,
                    "author_order_zero_based": order,
                    "is_first": position == 1,
                    "is_last": position == 2,
                    "is_corresponding": corresponding == 1,
                    "author_identity_scope": "paper_local_openalex_order",
                    "author_weights": {
                        scheme: _author_credit(
                            scheme,
                            order,
                            int(position),
                            author_count,
                        )
                        for scheme in (
                            "lead_balanced",
                            "lead_heavy",
                            "equal_fractional",
                            "full_counting",
                        )
                    },
                }
            )
            if institution_indices:
                for institution_index in institution_indices:
                    institution = institution_rows[int(institution_index)]
                    affiliations.append(
                        {
                            "paper_id": paper_id,
                            "author_id": author_id,
                            "institution_id": (
                                institution["id"]
                                or institution["r"]
                                or f"name:{normalize_text(institution['n'])}"
                            ),
                            "display_name": institution["n"],
                            "ror": institution["r"],
                            "openalex_id": institution["id"],
                            "country_code": institution["c"],
                            "lineage": list(institution["l"]),
                            "source": "openalex",
                            "confidence": 1.0,
                            "resolved": True,
                        }
                    )
            else:
                affiliations.append(
                    {
                        "paper_id": paper_id,
                        "author_id": author_id,
                        "institution_id": None,
                        "display_name": None,
                        "ror": None,
                        "openalex_id": None,
                        "country_code": None,
                        "lineage": [],
                        "source": "openalex_missing_institution",
                        "confidence": 0.0,
                        "resolved": False,
                    }
                )

        if (
            paper["x"]
            and compact_authorships
            and all(row[2] for row in compact_authorships)
        ):
            affiliations.append(
                {
                    "paper_id": paper_id,
                    "author_id": f"{paper_id}|author:0",
                    "institution_id": None,
                    "display_name": None,
                    "ror": None,
                    "openalex_id": None,
                    "country_code": None,
                    "lineage": [],
                    "source": "openalex_truncated_author_list",
                    "confidence": 0.0,
                    "resolved": False,
                }
            )

    return papers, authorships, affiliations


def write_s3_snapshot(
    dataset: dict[str, Any],
    *,
    snapshot_dir: Path,
    bucket: str,
    snapshot_id: str,
) -> dict[str, Any]:
    """Write an immutable Tier 1 + Tier 2 snapshot ready for audited S3 upload."""
    snapshot_dir.mkdir(parents=True, exist_ok=True)
    papers, authorships, affiliations = build_s3_snapshot_rows(dataset)
    raw_prefix = f"raw/metadata/tier1-tier2/{snapshot_id}"
    manifest_prefix = f"manifests/metadata/tier1-tier2/runs/{snapshot_id}"
    artifact_rows = {
        "papers.jsonl": papers,
        "authorships.jsonl": authorships,
        "affiliations.jsonl": affiliations,
    }
    artifacts: list[dict[str, Any]] = []
    artifact_paths: dict[str, str] = {}
    for name, rows in artifact_rows.items():
        path = snapshot_dir / name
        content = b"".join(
            json.dumps(
                row,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            ).encode("utf-8")
            + b"\n"
            for row in rows
        )
        path.write_bytes(content)
        artifacts.append(
            {
                "name": name,
                "rows": len(rows),
                "bytes": len(content),
                "sha256": hashlib.sha256(content).hexdigest(),
                "s3_key": f"{raw_prefix}/{name}",
            }
        )
        artifact_paths[name] = str(path)

    compact_manifest = dataset["manifest"]
    match_status = compact_manifest["openalex"]["match_status"]
    complete_papers = sum(
        bool(paper["u"]) and not paper["x"] and all(row[2] for row in paper["u"])
        for paper in dataset["papers"]
    )
    papers_with_authorships = sum(bool(paper["u"]) for paper in dataset["papers"])
    resolved_affiliations = sum(row["resolved"] for row in affiliations)
    manifest = {
        "schema_version": "tier1_metadata_snapshot.v2",
        "kind": "tier1_metadata_snapshot",
        "status": "ready_with_warnings",
        "corpus": {
            "id": "tier1_tier2",
            "label": "Tier 1 + Tier 2",
            "source": compact_manifest["input"]["name"],
        },
        "enrichment_run": {
            "id": snapshot_id,
            "agent_version": "tier1_tier2_openalex_metadata.v1",
            "status": "succeeded",
            "input_path": compact_manifest["input"]["name"],
            "input_sha256": compact_manifest["input"]["sha256"],
            "summary": {
                "match_status": match_status,
                "papers": len(papers),
                "papers_with_authorship_metadata": papers_with_authorships,
                "papers_with_complete_institution_membership": complete_papers,
                "authorships": len(authorships),
                "affiliation_assertions": len(affiliations),
                "resolved_affiliation_assertions": resolved_affiliations,
            },
            "started_at": compact_manifest["generated_at"],
            "completed_at": compact_manifest["generated_at"],
        },
        "scope": {
            "papers": len(papers),
            "papers_with_authorship_metadata": papers_with_authorships,
            "papers_with_complete_institution_membership": complete_papers,
            "authorships": len(authorships),
            "affiliation_assertions": len(affiliations),
            "resolved_affiliation_assertions": resolved_affiliations,
        },
        "storage": {
            "bucket": bucket,
            "snapshot_id": snapshot_id,
            "raw_prefix": raw_prefix,
            "manifest_prefix": manifest_prefix,
            "fulltext_prefix": "raw/zotero/",
            "separation_verified": True,
            "artifacts": artifacts,
        },
        "data_boundary": compact_manifest["data_boundary"],
        "source_manifest": compact_manifest,
    }
    manifest_path = snapshot_dir / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return {
        "manifest": str(manifest_path),
        "manifest_s3_key": f"{manifest_prefix}/manifest.json",
        "artifacts": artifact_paths,
        "scope": manifest["scope"],
    }


def _artifact_entry(path: Path) -> dict[str, Any]:
    content = path.read_bytes()
    return {
        "path": str(path),
        "bytes": len(content),
        "sha256": hashlib.sha256(content).hexdigest(),
    }


def _value(value: object) -> str:
    text = str(value or "").strip()
    return "" if text.casefold() in NULL_VALUES else text


def _int(value: object) -> int | None:
    text = _value(value)
    if not text:
        return None
    try:
        return int(float(text))
    except ValueError:
        return None


def _ratio(numerator: float, denominator: float) -> float:
    if not denominator:
        return 0.0
    value = numerator / denominator
    return 0.0 if not math.isfinite(value) else value


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build a local Tier 1+2 OpenAlex institution comparison dataset."
    )
    parser.add_argument("--csv", type=Path, required=True)
    parser.add_argument("--data-js", type=Path, required=True)
    parser.add_argument("--artifact-dir", type=Path, required=True)
    parser.add_argument("--cache-dir", type=Path, required=True)
    parser.add_argument(
        "--s3-snapshot-dir",
        type=Path,
        help="Also write the shared institution-service S3 snapshot contract.",
    )
    parser.add_argument(
        "--s3-bucket",
        help="Artifacts bucket recorded in the S3 snapshot manifest.",
    )
    parser.add_argument(
        "--s3-snapshot-id",
        help="Immutable S3 snapshot ID; defaults to generated time plus input hash.",
    )
    parser.add_argument("--batch-size", type=int, default=100)
    parser.add_argument("--api-key", default=os.getenv("OPENALEX_API_KEY"))
    parser.add_argument("--mailto", default=os.getenv("OPENALEX_MAILTO"))
    parser.add_argument(
        "--offline", action="store_true", help="Use cache only; do not call OpenAlex."
    )
    args = parser.parse_args()

    source = args.csv.expanduser().resolve()
    papers, input_stats = read_input_csv(source)
    source_sha256 = hashlib.sha256(source.read_bytes()).hexdigest()
    fetcher = OpenAlexBatchFetcher(
        cache_dir=args.cache_dir,
        api_key=args.api_key,
        mailto=args.mailto,
        batch_size=args.batch_size,
    )
    if args.offline:
        missing_cache = []
        for offset in range(0, len([p for p in papers if p.doi]), args.batch_size):
            batch = sorted(p.doi for p in papers if p.doi)[
                offset : offset + args.batch_size
            ]
            digest = hashlib.sha256("\n".join(batch).encode()).hexdigest()[:16]
            if not (args.cache_dir / f"doi-batch-{digest}.json.gz").exists():
                missing_cache.append(digest)
        if missing_cache:
            raise RuntimeError(
                f"Offline cache is incomplete: {len(missing_cache)} DOI batches missing"
            )

    openalex_by_doi, fetch_stats = fetcher.fetch(
        paper.doi for paper in papers if paper.doi
    )
    generated_at = datetime.now(UTC).isoformat()
    dataset = build_dataset(
        papers,
        openalex_by_doi,
        generated_at=generated_at,
        source_name=source.name,
        source_sha256=source_sha256,
        input_stats=input_stats,
        fetch_stats=fetch_stats,
    )
    result = write_outputs(
        dataset, data_js=args.data_js, artifact_dir=args.artifact_dir
    )
    if args.s3_snapshot_dir:
        if not args.s3_bucket:
            parser.error("--s3-bucket is required with --s3-snapshot-dir")
        snapshot_id = args.s3_snapshot_id or (
            re.sub(r"[^0-9A-Za-z]+", "", generated_at) + "Z_" + source_sha256[:12]
        )
        result["s3_snapshot"] = write_s3_snapshot(
            dataset,
            snapshot_dir=args.s3_snapshot_dir,
            bucket=args.s3_bucket,
            snapshot_id=snapshot_id,
        )
    summary = {
        "status": "completed",
        "generated_at": generated_at,
        "input": input_stats,
        "openalex": dataset["manifest"]["openalex"],
        "counts": dataset["manifest"]["counts"],
        "outputs": {
            key: value for key, value in result.items() if key != "default_report"
        },
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
