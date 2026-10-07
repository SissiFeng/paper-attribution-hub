"""Export a Scopus result set and enrich it with OpenAlex metadata.

The Scopus query is the source of truth for corpus membership. OpenAlex is
used only to enrich the records returned by Scopus; it is never used to add
papers to the corpus.

Usage (from ``backend/``)::

    read -rsp "Elsevier API key: " PAS_ELSEVIER_API_KEY; echo
    export PAS_ELSEVIER_API_KEY
    python -m app.scripts.fetch_scopus_openalex_metadata

An institutional token can be supplied as ``PAS_ELSEVIER_INSTTOKEN`` and an
OpenAlex API key as ``PAS_OPENALEX_API_KEY``. Secrets are deliberately read
only from environment variables so they do not appear in shell history.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
import sys
import tempfile
import unicodedata
from collections import Counter
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterable, Iterator, TextIO

import httpx
from sqlalchemy.orm import Session

from app.db import SessionLocal, init_database
from app.services.external.openalex_client import OpenAlexClient


DEFAULT_SCOPUS_QUERY = (
    '(ALL("self-driving lab*") OR '
    'ALL("materials acceleration platform*") OR '
    'ALL("autonomous lab*")) '
    "AND PUBYEAR > 2016 AND PUBYEAR < 2028"
)
EXPECTED_SCOPUS_COUNT = 175
SCHEMA_VERSION = "scopus_openalex_metadata.v1"

_DOI_PREFIX_RE = re.compile(
    r"^(?:doi:\s*|https?://(?:dx\.)?doi\.org/)", re.IGNORECASE
)
_YEAR_RE = re.compile(r"\b(19|20)\d{2}\b")


class ApiResponseError(RuntimeError):
    """An external API returned a non-success response."""


def normalize_doi(value: Any) -> str | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    raw = _DOI_PREFIX_RE.sub("", raw).strip().rstrip(".,;)")
    return raw.lower() if raw.startswith("10.") else None


def normalize_text(value: Any) -> str:
    folded = unicodedata.normalize("NFKD", str(value or ""))
    folded = "".join(ch for ch in folded if not unicodedata.combining(ch))
    folded = re.sub(r"[^a-z0-9]+", " ", folded.lower())
    return re.sub(r"\s+", " ", folded).strip()


def parse_year(value: Any) -> int | None:
    match = _YEAR_RE.search(str(value or ""))
    return int(match.group(0)) if match else None


def reconstruct_abstract(inverted_index: Any) -> str | None:
    if not isinstance(inverted_index, dict):
        return None
    positions: dict[int, str] = {}
    for word, indexes in inverted_index.items():
        if not isinstance(indexes, list):
            continue
        for index in indexes:
            if isinstance(index, int):
                positions[index] = str(word)
    if not positions:
        return None
    return " ".join(word for _, word in sorted(positions.items()))


def _safe_json(response: httpx.Response, source: str) -> dict[str, Any]:
    if response.is_error:
        raise ApiResponseError(f"{source} returned HTTP {response.status_code}")
    try:
        payload = response.json()
    except ValueError as exc:
        raise ApiResponseError(f"{source} returned invalid JSON") from exc
    if not isinstance(payload, dict):
        raise ApiResponseError(f"{source} returned a non-object JSON payload")
    return payload


class ScopusSearchClient:
    """Small client for the Elsevier Scopus Search API."""

    endpoint = "https://api.elsevier.com/content/search/scopus"

    def __init__(
        self,
        api_key: str,
        *,
        insttoken: str | None = None,
        client: httpx.Client | None = None,
    ) -> None:
        if not api_key.strip():
            raise ValueError("Elsevier API key is required")
        headers = {
            "Accept": "application/json",
            "X-ELS-APIKey": api_key.strip(),
        }
        if insttoken and insttoken.strip():
            headers["X-ELS-Insttoken"] = insttoken.strip()
        self.client = client or httpx.Client(
            headers=headers,
            timeout=60.0,
            follow_redirects=False,
        )
        self._owns_client = client is None
        if client is not None:
            self.client.headers.update(headers)

    def close(self) -> None:
        if self._owns_client:
            self.client.close()

    def search(
        self,
        query: str,
        *,
        page_size: int = 25,
    ) -> tuple[list[dict[str, Any]], int]:
        if not 1 <= page_size <= 25:
            raise ValueError("Scopus page_size must be between 1 and 25")

        entries: list[dict[str, Any]] = []
        start = 0
        total = 0
        while start == 0 or start < total:
            response = self.client.get(
                self.endpoint,
                params={
                    "query": query,
                    "view": "STANDARD",
                    "start": start,
                    "count": page_size,
                    "sort": "-coverDate",
                    "suppressNavLinks": "true",
                },
            )
            payload = _safe_json(response, "Scopus Search API")
            search_results = payload.get("search-results") or {}
            if not isinstance(search_results, dict):
                raise ApiResponseError("Scopus response is missing search-results")
            try:
                total = int(search_results.get("opensearch:totalResults") or 0)
            except (TypeError, ValueError) as exc:
                raise ApiResponseError("Scopus returned an invalid totalResults") from exc

            page = search_results.get("entry") or []
            if not isinstance(page, list):
                raise ApiResponseError("Scopus response entry is not a list")
            page_entries = [item for item in page if isinstance(item, dict)]
            entries.extend(page_entries)
            if not page_entries:
                break
            start += len(page_entries)

        return entries, total


class ScopusOpenAlexClient(OpenAlexClient):
    """Project OpenAlex client with conservative export-only title matching."""

    def match_by_exact_title(
        self,
        session: Session,
        record: dict[str, Any],
    ) -> tuple[dict[str, Any] | None, str | None, float | None]:
        title = str(record.get("title") or "").strip()
        if not title:
            return None, None, None
        year = record.get("year")
        params: dict[str, Any] = {"search": title, "per_page": 5}
        if isinstance(year, int):
            params["filter"] = (
                f"from_publication_date:{year - 1}-01-01,"
                f"to_publication_date:{year + 1}-12-31"
            )
        payload = self._cached(session, "/works", params)
        candidates = [
            item
            for item in (payload.get("results") or [])
            if isinstance(item, dict)
            and normalize_text(item.get("display_name") or item.get("title"))
            == normalize_text(title)
        ]
        if not candidates:
            return None, None, None

        same_year = [item for item in candidates if item.get("publication_year") == year]
        if len(same_year) == 1:
            return same_year[0], "title_year", 0.98
        if len(candidates) == 1 and (
            not isinstance(year, int)
            or not isinstance(candidates[0].get("publication_year"), int)
            or abs(candidates[0]["publication_year"] - year) <= 1
        ):
            return candidates[0], "title_near_year", 0.95
        return None, None, None


def normalize_scopus_entry(entry: dict[str, Any]) -> dict[str, Any]:
    links = entry.get("link") or []
    if isinstance(links, dict):
        links = [links]
    scopus_url = next(
        (
            link.get("@href")
            for link in links
            if isinstance(link, dict) and link.get("@ref") == "scopus"
        ),
        None,
    )
    identifier = str(entry.get("dc:identifier") or "")
    scopus_id = identifier.split(":", 1)[-1] if identifier else None
    return {
        "eid": entry.get("eid"),
        "scopus_id": scopus_id,
        "doi": normalize_doi(entry.get("prism:doi")),
        "title": str(entry.get("dc:title") or "").strip(),
        "year": parse_year(entry.get("prism:coverDate")),
        "cover_date": entry.get("prism:coverDate"),
        "first_author": entry.get("dc:creator"),
        "source_title": entry.get("prism:publicationName"),
        "document_type": entry.get("subtypeDescription") or entry.get("subtype"),
        "citation_count": _integer_or_none(entry.get("citedby-count")),
        "scopus_url": scopus_url,
        "raw": entry,
    }


def _first_csv_value(row: dict[str, Any], *names: str) -> Any:
    for name in names:
        value = row.get(name)
        if value is not None and str(value).strip():
            return value
    return None


def load_scopus_csv(path: Path) -> list[dict[str, Any]]:
    """Load a Scopus web-export CSV in either English or Simplified Chinese."""
    csv.field_size_limit(sys.maxsize)
    with path.expanduser().resolve().open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    records: list[dict[str, Any]] = []
    for row in rows:
        eid = _first_csv_value(row, "EID")
        authors = _first_csv_value(row, "Authors", "作者")
        records.append(
            {
                "eid": eid,
                "scopus_id": str(eid).rsplit("-", 1)[-1] if eid else None,
                "doi": normalize_doi(_first_csv_value(row, "DOI")),
                "title": str(
                    _first_csv_value(row, "Title", "文献标题") or ""
                ).strip(),
                "year": parse_year(_first_csv_value(row, "Year", "年份")),
                "cover_date": None,
                "first_author": str(authors or "").split(";", 1)[0].strip() or None,
                "source_title": _first_csv_value(
                    row, "Source title", "来源出版物名称"
                ),
                "document_type": _first_csv_value(
                    row, "Document Type", "文献类型"
                ),
                "citation_count": _integer_or_none(
                    _first_csv_value(row, "Cited by", "施引文献")
                ),
                "scopus_url": _first_csv_value(row, "Link", "链接"),
                "raw": row,
            }
        )
    return records


def _integer_or_none(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def deduplicate_scopus_records(
    records: Iterable[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Deduplicate by DOI, then EID, then title/year/first author."""
    seen_dois: set[str] = set()
    seen_eids: set[str] = set()
    seen_fallbacks: set[tuple[str, Any, str]] = set()
    unique: list[dict[str, Any]] = []
    for record in records:
        doi = record.get("doi")
        eid = str(record.get("eid") or "").strip()
        fallback = (
            normalize_text(record.get("title")),
            record.get("year"),
            normalize_text(record.get("first_author")),
        )
        if doi:
            if doi in seen_dois:
                continue
            seen_dois.add(doi)
        elif eid:
            if eid in seen_eids:
                continue
            seen_eids.add(eid)
        elif fallback[0]:
            if fallback in seen_fallbacks:
                continue
            seen_fallbacks.add(fallback)
        else:
            continue
        unique.append(record)
    return unique


def enrich_records(
    scopus_records: list[dict[str, Any]],
    openalex: ScopusOpenAlexClient,
    session: Session,
) -> list[dict[str, Any]]:
    by_doi = openalex.works_by_dois(
        session,
        [str(record["doi"]) for record in scopus_records if record.get("doi")]
    )
    enriched: list[dict[str, Any]] = []
    for record in scopus_records:
        work = by_doi.get(record.get("doi"))
        method: str | None = "doi" if work else None
        confidence: float | None = 1.0 if work else None
        if work is None:
            work, method, confidence = openalex.match_by_exact_title(session, record)
        enriched.append(
            {
                "scopus": record,
                "openalex": work,
                "match": {
                    "matched": work is not None,
                    "method": method,
                    "confidence": confidence,
                },
            }
        )
    return enriched


def _pipe(values: Iterable[Any]) -> str:
    return "|".join(str(value).strip() for value in values if str(value or "").strip())


def flatten_record(record: dict[str, Any], query: str) -> dict[str, Any]:
    scopus = record["scopus"]
    work = record.get("openalex") or {}
    authorships = work.get("authorships") or []
    authors = [
        (item.get("author") or {}).get("display_name")
        for item in authorships
        if isinstance(item, dict)
    ]
    orcids = [
        (item.get("author") or {}).get("orcid")
        for item in authorships
        if isinstance(item, dict)
    ]
    institutions: list[str] = []
    countries: list[str] = []
    author_institutions: list[str] = []
    author_countries: list[str] = []
    for item in authorships:
        if not isinstance(item, dict):
            continue
        item_institutions: list[str] = []
        item_countries: list[str] = []
        for institution in item.get("institutions") or []:
            if not isinstance(institution, dict):
                continue
            name = institution.get("display_name")
            country = institution.get("country_code")
            institutions.append(name)
            countries.append(country)
            if name:
                item_institutions.append(str(name))
            if country:
                item_countries.append(str(country))
        author_institutions.append(";".join(item_institutions))
        author_countries.append(";".join(item_countries))
    primary_location = work.get("primary_location") or {}
    primary_source = primary_location.get("source") or {}
    open_access = work.get("open_access") or {}
    topics = [
        item.get("display_name")
        for item in (work.get("topics") or [])
        if isinstance(item, dict)
    ]
    keywords = [
        item.get("display_name")
        for item in (work.get("keywords") or [])
        if isinstance(item, dict)
    ]
    return {
        "scopus_query": query,
        "scopus_eid": scopus.get("eid"),
        "scopus_id": scopus.get("scopus_id"),
        "scopus_doi": scopus.get("doi"),
        "scopus_title": scopus.get("title"),
        "scopus_year": scopus.get("year"),
        "scopus_cover_date": scopus.get("cover_date"),
        "scopus_first_author": scopus.get("first_author"),
        "scopus_source_title": scopus.get("source_title"),
        "scopus_document_type": scopus.get("document_type"),
        "scopus_citation_count": scopus.get("citation_count"),
        "scopus_url": scopus.get("scopus_url"),
        "openalex_match": record["match"]["matched"],
        "openalex_match_method": record["match"]["method"],
        "openalex_match_confidence": record["match"]["confidence"],
        "openalex_id": work.get("id"),
        "openalex_doi": normalize_doi(work.get("doi")),
        "openalex_title": work.get("display_name") or work.get("title"),
        "openalex_publication_year": work.get("publication_year"),
        "openalex_publication_date": work.get("publication_date"),
        "openalex_type": work.get("type"),
        "openalex_language": work.get("language"),
        "openalex_cited_by_count": work.get("cited_by_count"),
        "openalex_is_retracted": work.get("is_retracted"),
        "authors": _pipe(authors),
        "author_orcids": _pipe(orcids),
        "author_institutions_grouped": _pipe(author_institutions),
        "author_institution_countries_grouped": _pipe(author_countries),
        "institutions": _pipe(dict.fromkeys(filter(None, institutions))),
        "institution_countries": _pipe(dict.fromkeys(filter(None, countries))),
        "primary_source": primary_source.get("display_name"),
        "primary_source_issn_l": primary_source.get("issn_l"),
        "open_access_status": open_access.get("oa_status"),
        "is_open_access": open_access.get("is_oa"),
        "open_access_url": open_access.get("oa_url"),
        "topics": _pipe(topics),
        "keywords": _pipe(keywords),
        "abstract": reconstruct_abstract(work.get("abstract_inverted_index")),
    }


@contextmanager
def _atomic_text_file(
    path: Path,
    *,
    encoding: str,
    newline: str,
) -> Iterator[TextIO]:
    if path.is_symlink():
        raise ValueError(f"Refusing to overwrite symlink: {path}")
    descriptor, temporary_name = tempfile.mkstemp(
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
    )
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding=encoding, newline=newline) as handle:
            yield handle
        if path.is_symlink():
            raise ValueError(f"Refusing to overwrite symlink: {path}")
        os.replace(temporary_path, path)
    finally:
        temporary_path.unlink(missing_ok=True)


def _write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    with _atomic_text_file(path, encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def _csv_safe(value: Any) -> Any:
    if isinstance(value, str) and value.lstrip().startswith(("=", "+", "-", "@")):
        return "'" + value
    return value


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        raise ValueError(f"Cannot write empty CSV: {path}")
    with _atomic_text_file(path, encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(
            {key: _csv_safe(value) for key, value in row.items()} for row in rows
        )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_export(
    output_dir: Path,
    *,
    query: str,
    expected_count: int,
    scopus_total: int,
    raw_entry_count: int,
    enriched: list[dict[str, Any]],
    scopus_source: str = "scopus_api",
    scopus_input_sha256: str | None = None,
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = output_dir / "manifest.json"
    if manifest_path.is_symlink():
        raise ValueError(f"Refusing to overwrite symlink: {manifest_path}")
    manifest_path.unlink(missing_ok=True)
    scopus_path = output_dir / "scopus_results.jsonl"
    openalex_path = output_dir / "openalex_metadata.jsonl"
    merged_path = output_dir / "merged_metadata.csv"
    audit_path = output_dir / "match_audit.csv"

    _write_jsonl(scopus_path, (item["scopus"] for item in enriched))
    _write_jsonl(
        openalex_path,
        (
            {
                "scopus_eid": item["scopus"].get("eid"),
                "scopus_doi": item["scopus"].get("doi"),
                "match": item["match"],
                "openalex": item.get("openalex"),
            }
            for item in enriched
        ),
    )
    flat_rows = [flatten_record(item, query) for item in enriched]
    _write_csv(merged_path, flat_rows)
    audit_rows = [
        {
            "scopus_eid": item["scopus"].get("eid"),
            "scopus_doi": item["scopus"].get("doi"),
            "scopus_title": item["scopus"].get("title"),
            "scopus_year": item["scopus"].get("year"),
            "matched": item["match"]["matched"],
            "match_method": item["match"]["method"],
            "match_confidence": item["match"]["confidence"],
            "openalex_id": (item.get("openalex") or {}).get("id"),
            "openalex_doi": normalize_doi((item.get("openalex") or {}).get("doi")),
            "openalex_title": (item.get("openalex") or {}).get("display_name"),
            "openalex_year": (item.get("openalex") or {}).get("publication_year"),
        }
        for item in enriched
    ]
    _write_csv(audit_path, audit_rows)

    methods = Counter(
        item["match"]["method"] or "unmatched" for item in enriched
    )
    artifact_paths = [scopus_path, openalex_path, merged_path, audit_path]
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "created_at": datetime.now(UTC).isoformat(),
        "scopus_query": query,
        "scopus_source": scopus_source,
        "scopus_input_sha256": scopus_input_sha256,
        "expected_scopus_count": expected_count,
        "scopus_total_reported": scopus_total,
        "scopus_raw_entries_received": raw_entry_count,
        "scopus_unique_records": len(enriched),
        "scopus_count_matches_expected": scopus_total == expected_count,
        "openalex_matched_records": sum(
            1 for item in enriched if item["match"]["matched"]
        ),
        "openalex_unmatched_records": methods["unmatched"],
        "match_methods": dict(sorted(methods.items())),
        "artifacts": {
            path.name: {"sha256": _sha256(path), "bytes": path.stat().st_size}
            for path in artifact_paths
        },
    }
    with _atomic_text_file(manifest_path, encoding="utf-8", newline="\n") as handle:
        handle.write(
            json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        )
    return manifest


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Fetch a Scopus corpus and enrich it with OpenAlex metadata."
    )
    parser.add_argument("--query", default=DEFAULT_SCOPUS_QUERY)
    parser.add_argument("--expected-count", type=int, default=EXPECTED_SCOPUS_COUNT)
    parser.add_argument(
        "--scopus-csv",
        type=Path,
        help="Use an existing Scopus web-export CSV instead of the Search API.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=_repo_root() / "reports" / "scopus-175-openalex-metadata",
    )
    args = parser.parse_args()

    elsevier_key = os.environ.get("PAS_ELSEVIER_API_KEY", "").strip()
    if not args.scopus_csv and not elsevier_key:
        parser.error("PAS_ELSEVIER_API_KEY is required")

    scopus = (
        None
        if args.scopus_csv
        else ScopusSearchClient(
            elsevier_key,
            insttoken=os.environ.get("PAS_ELSEVIER_INSTTOKEN"),
        )
    )
    init_database()
    openalex = ScopusOpenAlexClient()
    try:
        if args.scopus_csv:
            csv_path = args.scopus_csv.expanduser().resolve()
            normalized = load_scopus_csv(csv_path)
            reported_total = len(normalized)
            raw_entry_count = len(normalized)
            scopus_source = "scopus_ui_csv"
            input_sha256 = _sha256(csv_path)
        else:
            assert scopus is not None
            raw_entries, reported_total = scopus.search(args.query)
            normalized = [normalize_scopus_entry(entry) for entry in raw_entries]
            raw_entry_count = len(raw_entries)
            scopus_source = "scopus_api"
            input_sha256 = None
        unique_records = deduplicate_scopus_records(normalized)
        with SessionLocal() as session:
            enriched = enrich_records(unique_records, openalex, session)
        manifest = write_export(
            args.output_dir.resolve(),
            query=args.query,
            expected_count=args.expected_count,
            scopus_total=reported_total,
            raw_entry_count=raw_entry_count,
            enriched=enriched,
            scopus_source=scopus_source,
            scopus_input_sha256=input_sha256,
        )
    except (httpx.HTTPError, ApiResponseError, ValueError) as exc:
        print(f"Export failed: {exc}", file=sys.stderr)
        return 1
    finally:
        if scopus is not None:
            scopus.close()
        openalex.close()

    print(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True))
    if reported_total != args.expected_count:
        print(
            f"Warning: Scopus currently reports {reported_total} results, "
            f"not the expected {args.expected_count}.",
            file=sys.stderr,
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
