"""Automated Tier 1 metadata enrichment from a Zotero CSV.

The agent treats DOI as the paper identity, OpenAlex as the primary
paper-specific authorship source, Crossref as a fallback, and ROR as the
authority for resolving otherwise-unstructured affiliation strings. Missing
or conflicting evidence is retained as a quality flag rather than guessed.
"""

from __future__ import annotations

import csv
import hashlib
import json
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.config import settings
from app.models import (
    Author,
    Institution,
    MetadataEnrichmentRun,
    Paper,
    PaperAuthor,
    PaperAuthorshipMetadata,
)
from app.services.external.crossref_client import CrossrefClient
from app.services.external.openalex_client import OpenAlexClient, _reconstruct_abstract
from app.services.external.ror_client import RorClient
from app.services.normalization_service import (
    normalize_doi,
    normalize_institution,
    normalize_name,
)


AGENT_VERSION = "tier1_metadata_agent.v1"


@dataclass(frozen=True)
class Tier1PaperInput:
    doi: str
    title: str
    year: int | None
    venue: str | None
    abstract: str | None
    url: str | None
    authors: list[str]
    zotero_keys: list[str]
    item_types: list[str]
    attachments: list[str]
    duplicate_count: int
    quality_flags: list[str] = field(default_factory=list)


@dataclass
class AuthorshipEvidence:
    name: str
    author_position: str
    is_corresponding: bool | None
    openalex_author_id: str | None
    orcid: str | None
    affiliations: list[dict]
    raw_affiliations: list[str]
    sources: list[str]
    source_record_ids: list[str]
    quality_flags: list[str] = field(default_factory=list)


def read_tier1_csv(path: Path) -> tuple[list[Tier1PaperInput], dict]:
    """Read and DOI-deduplicate a Zotero CSV without modifying the source."""
    source = Path(path).expanduser().resolve()
    with source.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    required = {"Key", "Title", "DOI", "Author", "Publication Year"}
    missing = sorted(required - set(rows[0] if rows else []))
    if missing:
        raise ValueError(f"Tier 1 CSV is missing required columns: {missing}")

    grouped: dict[str, list[dict[str, str]]] = {}
    for index, row in enumerate(rows, start=2):
        doi = normalize_doi(row.get("DOI"))
        if not doi:
            raise ValueError(f"Tier 1 CSV row {index} has no valid DOI")
        grouped.setdefault(doi, []).append(row)

    papers: list[Tier1PaperInput] = []
    for doi, candidates in sorted(grouped.items()):
        author_lists = [_split_authors(row.get("Author")) for row in candidates]
        authors = max(author_lists, key=len, default=[])
        years = {_parse_year(row.get("Publication Year")) for row in candidates}
        years.discard(None)
        titles = {str(row.get("Title") or "").strip() for row in candidates}
        titles.discard("")
        flags: list[str] = []
        if len(author_lists) > 1 and len({tuple(value) for value in author_lists}) > 1:
            flags.append("duplicate_author_lists_differ")
        if len(years) > 1:
            flags.append("duplicate_years_differ")
        if len(titles) > 1:
            flags.append("duplicate_titles_differ")
        papers.append(
            Tier1PaperInput(
                doi=doi,
                title=max(titles, key=len, default=""),
                year=min(years) if years else None,
                venue=_longest(candidates, "Publication Title"),
                abstract=_longest(candidates, "Abstract Note"),
                url=_longest(candidates, "Url"),
                authors=authors,
                zotero_keys=sorted(
                    {
                        str(row.get("Key") or "").strip()
                        for row in candidates
                        if str(row.get("Key") or "").strip()
                    }
                ),
                item_types=sorted(
                    {
                        str(row.get("Item Type") or "").strip()
                        for row in candidates
                        if str(row.get("Item Type") or "").strip()
                    }
                ),
                attachments=sorted(
                    {
                        item.strip()
                        for row in candidates
                        for item in str(row.get("File Attachments") or "").split(";")
                        if item.strip()
                    }
                ),
                duplicate_count=len(candidates),
                quality_flags=flags,
            )
        )
    return papers, {
        "raw_rows": len(rows),
        "unique_dois": len(papers),
        "duplicate_groups": sum(1 for values in grouped.values() if len(values) > 1),
        "duplicate_rows": sum(
            len(values) for values in grouped.values() if len(values) > 1
        ),
    }


def run_tier1_metadata_agent(
    session: Session,
    csv_path: Path,
    *,
    openalex: OpenAlexClient | None = None,
    crossref: CrossrefClient | None = None,
    ror: RorClient | None = None,
    batch_size: int = 100,
    max_papers: int | None = None,
) -> dict:
    """Run the complete enrichment loop and return an auditable summary."""
    source = Path(csv_path).expanduser().resolve()
    source_bytes = source.read_bytes()
    input_sha256 = hashlib.sha256(source_bytes).hexdigest()
    papers, input_stats = read_tier1_csv(source)
    if max_papers is not None:
        if max_papers <= 0:
            raise ValueError("max_papers must be positive")
        papers = papers[:max_papers]

    run_id = (
        f"meta_{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}_{uuid.uuid4().hex[:8]}"
    )
    run = MetadataEnrichmentRun(
        id=run_id,
        agent_version=AGENT_VERSION,
        status="running",
        input_path=str(source),
        input_sha256=input_sha256,
        configuration={
            "primary_source": "openalex",
            "fallback_source": "crossref",
            "institution_authority": "ror",
            "batch_size": batch_size,
            "max_papers": max_papers,
            "openalex_api_key_configured": bool(settings.openalex_api_key),
        },
        summary={},
        errors=[],
    )
    session.add(run)
    session.commit()

    owns_openalex = openalex is None
    owns_crossref = crossref is None
    owns_ror = ror is None
    oa = openalex or OpenAlexClient()
    cr = crossref or CrossrefClient()
    ror_client = ror or RorClient()
    errors: list[dict] = []
    counters = {
        **input_stats,
        "selected_papers": len(papers),
        "openalex_matches": 0,
        "crossref_requests": 0,
        "crossref_matches": 0,
        "papers_persisted": 0,
        "papers_with_resolved_affiliations": 0,
        "authorship_rows": 0,
        "resolved_affiliation_assertions": 0,
        "unresolved_affiliation_assertions": 0,
    }
    try:
        try:
            openalex_by_doi = oa.works_by_dois(
                session,
                [paper.doi for paper in papers],
                batch_size=batch_size,
            )
        except Exception as exc:
            openalex_by_doi = {}
            errors.append(_error("openalex_batch", None, exc))
        counters["openalex_matches"] = len(openalex_by_doi)

        author_resolver = _AuthorResolver(session)
        institution_resolver = _InstitutionResolver(session)
        for index, paper_input in enumerate(papers, start=1):
            try:
                openalex_work = openalex_by_doi.get(paper_input.doi)
                authorships = _openalex_authorships(openalex_work)
                crossref_work = None
                if not authorships or any(
                    not row.affiliations and not row.raw_affiliations
                    for row in authorships
                ):
                    counters["crossref_requests"] += 1
                    crossref_work = cr.work_by_doi(session, paper_input.doi)
                    if crossref_work:
                        counters["crossref_matches"] += 1
                crossref_authors = _crossref_authorships(crossref_work)
                authorships = _merge_authorships(
                    authorships,
                    crossref_authors,
                    paper_input.authors,
                    paper_input.doi,
                )
                for authorship in authorships:
                    authorship.affiliations = _resolve_affiliations(
                        authorship,
                        session,
                        ror_client,
                    )

                with session.begin_nested():
                    result = _persist_paper(
                        session,
                        run_id=run_id,
                        input_sha256=input_sha256,
                        paper_input=paper_input,
                        authorships=authorships,
                        openalex_work=openalex_work,
                        crossref_work=crossref_work,
                        author_resolver=author_resolver,
                        institution_resolver=institution_resolver,
                    )
                counters["papers_persisted"] += 1
                counters["authorship_rows"] += result["authorship_rows"]
                counters["resolved_affiliation_assertions"] += result[
                    "resolved_affiliations"
                ]
                counters["unresolved_affiliation_assertions"] += result[
                    "unresolved_affiliations"
                ]
                if result["resolved_affiliations"]:
                    counters["papers_with_resolved_affiliations"] += 1
                if index % 25 == 0:
                    session.commit()
            except Exception as exc:
                errors.append(_error("paper", paper_input.doi, exc))
        session.commit()
        run = session.get(MetadataEnrichmentRun, run_id)
        if run is not None:
            run.status = "completed_with_errors" if errors else "succeeded"
            run.summary = counters
            run.errors = errors
            run.completed_at = datetime.now(UTC)
            session.commit()
    except Exception as exc:
        session.rollback()
        errors.append(_error("agent", None, exc))
        run = session.get(MetadataEnrichmentRun, run_id)
        if run is not None:
            run.status = "failed"
            run.summary = counters
            run.errors = errors
            run.completed_at = datetime.now(UTC)
            session.commit()
        raise
    finally:
        if owns_openalex:
            oa.close()
        if owns_crossref:
            cr.close()
        if owns_ror:
            ror_client.close()

    return {
        "run_id": run_id,
        "status": "completed_with_errors" if errors else "succeeded",
        "input_sha256": input_sha256,
        **counters,
        "errors": errors,
    }


def _persist_paper(
    session: Session,
    *,
    run_id: str,
    input_sha256: str,
    paper_input: Tier1PaperInput,
    authorships: list[AuthorshipEvidence],
    openalex_work: dict | None,
    crossref_work: dict | None,
    author_resolver: "_AuthorResolver",
    institution_resolver: "_InstitutionResolver",
) -> dict[str, int]:
    paper = session.execute(
        select(Paper).where(Paper.doi == paper_input.doi)
    ).scalar_one_or_none()
    if paper is None:
        if settings.sdl_stage1_only:
            raise ValueError(
                "Strict Stage 1 mode requires the Zotero group sync before CSV enrichment"
            )
        paper = Paper(
            id="DOI:" + paper_input.doi.replace("/", "_"),
            title=paper_input.title or str((openalex_work or {}).get("title") or ""),
        )
        session.add(paper)
        session.flush()

    paper.title = paper_input.title or str(
        (openalex_work or {}).get("title") or paper.title
    )
    paper.doi = paper_input.doi
    paper.year = paper_input.year or (openalex_work or {}).get("publication_year")
    paper.venue = paper_input.venue or _openalex_venue(openalex_work) or paper.venue
    paper.abstract = (
        paper_input.abstract
        or _reconstruct_abstract((openalex_work or {}).get("abstract_inverted_index"))
        or paper.abstract
    )
    if paper.source != "zotero" or paper.provenance != "zotero_group":
        paper.source = "zotero"
        paper.provenance = "zotero_csv"
    paper.retrieval_tier = paper.retrieval_tier or "tier1"
    paper.corpus_sources = paper.corpus_sources or ["STRICT_SDL_KEYWORD"]
    openalex_citation_count = (openalex_work or {}).get("cited_by_count")
    if openalex_citation_count is not None:
        paper.citation_count = openalex_citation_count
        paper.citation_count_source = "openalex"
        paper.citation_count_updated_at = datetime.now(UTC)
    raw_metadata = dict(paper.raw_metadata or {})
    raw_metadata["tier1_metadata_agent"] = {
        "agent_version": AGENT_VERSION,
        "run_id": run_id,
        "input_sha256": input_sha256,
        "zotero_keys": paper_input.zotero_keys,
        "duplicate_count": paper_input.duplicate_count,
        "attachments": paper_input.attachments,
        "quality_flags": paper_input.quality_flags,
        "openalex": openalex_work,
        "crossref": crossref_work,
    }
    paper.raw_metadata = raw_metadata

    session.execute(
        delete(PaperAuthorshipMetadata).where(
            PaperAuthorshipMetadata.paper_id == paper.id
        )
    )
    session.execute(delete(PaperAuthor).where(PaperAuthor.paper_id == paper.id))
    session.flush()

    seen_author_ids: set[str] = set()
    resolved_count = 0
    unresolved_count = 0
    for order, authorship in enumerate(authorships):
        author, identity_flags = author_resolver.resolve(
            authorship,
            paper_doi=paper_input.doi,
            order=order,
            seen_author_ids=seen_author_ids,
        )
        seen_author_ids.add(author.id)
        affiliations: list[dict] = []
        for assertion in authorship.affiliations:
            item = dict(assertion)
            if item.get("resolved"):
                institution = institution_resolver.resolve(item)
                item["institution_id"] = institution.id
                resolved_count += 1
            else:
                item["institution_id"] = None
                unresolved_count += 1
            affiliations.append(item)
        affiliation_text = (
            "; ".join(
                dict.fromkeys(
                    str(item.get("display_name") or "").strip()
                    for item in affiliations
                    if str(item.get("display_name") or "").strip()
                )
            )
            or None
        )
        session.add(
            PaperAuthor(
                paper_id=paper.id,
                author_id=author.id,
                author_order=order,
                affiliation_text=affiliation_text,
                match_confidence=1.0 if authorship.openalex_author_id else 0.9,
            )
        )
        provenance_payload = {
            "paper_id": paper.id,
            "author_id": author.id,
            "order": order,
            "position": _position(order, len(authorships)),
            "corresponding": authorship.is_corresponding,
            "affiliations": affiliations,
            "sources": sorted(set(authorship.sources)),
            "source_record_ids": sorted(set(authorship.source_record_ids)),
            "quality_flags": sorted(
                set(
                    paper_input.quality_flags
                    + authorship.quality_flags
                    + identity_flags
                )
            ),
        }
        session.add(
            PaperAuthorshipMetadata(
                paper_id=paper.id,
                author_id=author.id,
                author_order=order,
                author_position=_position(order, len(authorships)),
                is_corresponding=authorship.is_corresponding,
                openalex_author_id=authorship.openalex_author_id,
                orcid=authorship.orcid,
                affiliations=affiliations,
                sources=provenance_payload["sources"],
                source_record_ids=provenance_payload["source_record_ids"],
                quality_flags=provenance_payload["quality_flags"],
                provenance_hash=_sha256_json(provenance_payload),
            )
        )
    session.flush()
    return {
        "authorship_rows": len(authorships),
        "resolved_affiliations": resolved_count,
        "unresolved_affiliations": unresolved_count,
    }


class _AuthorResolver:
    def __init__(self, session: Session) -> None:
        self.session = session
        authors = list(session.execute(select(Author)).scalars())
        self.by_id = {author.id: author for author in authors}
        self.by_orcid = {author.orcid: author for author in authors if author.orcid}
        self.by_openalex: dict[str, Author] = {}
        self.by_name: dict[str, list[Author]] = {}
        for author in authors:
            self.by_name.setdefault(author.normalized_name, []).append(author)
            openalex_id = str(
                ((author.raw_metadata or {}).get("metadata_agent") or {}).get(
                    "openalex_author_id"
                )
                or ""
            )
            if openalex_id and not author.id.startswith("auth_duplicate_"):
                self.by_openalex[openalex_id] = author

    def resolve(
        self,
        evidence: AuthorshipEvidence,
        *,
        paper_doi: str,
        order: int,
        seen_author_ids: set[str],
    ) -> tuple[Author, list[str]]:
        flags: list[str] = []
        author = None
        repeated_external_identity = False
        if evidence.openalex_author_id:
            author = self.by_openalex.get(evidence.openalex_author_id)
        if author is None and evidence.orcid:
            author = self.by_orcid.get(evidence.orcid)
        normalized = normalize_name(evidence.name)
        candidates = self.by_name.get(normalized, [])
        if author is None and len(candidates) == 1:
            candidate_oa = str(
                ((candidates[0].raw_metadata or {}).get("metadata_agent") or {}).get(
                    "openalex_author_id"
                )
                or ""
            )
            if not candidate_oa or candidate_oa == evidence.openalex_author_id:
                author = candidates[0]
        if author is not None and author.id in seen_author_ids:
            author = None
            repeated_external_identity = True
            flags.append("same_name_authors_disambiguated_per_paper")
        if author is None:
            if repeated_external_identity:
                identity = (
                    f"{evidence.openalex_author_id or evidence.orcid or normalized}"
                    f"|{paper_doi}|{order}"
                )
                prefix = "auth_duplicate"
            else:
                identity = (
                    evidence.openalex_author_id
                    or evidence.orcid
                    or (
                        f"{normalized}|{paper_doi}|{order}"
                        if candidates
                        else normalized
                    )
                )
                prefix = "auth_oa" if evidence.openalex_author_id else "auth"
            stable_id = _stable_id(prefix, identity)
            author = self.by_id.get(stable_id)
            if author is None:
                author = Author(
                    id=stable_id,
                    canonical_name=evidence.name,
                    aliases=[],
                    normalized_name=normalized,
                    is_ac_member=False,
                    raw_metadata={},
                )
                self.session.add(author)
                self.session.flush()
                self.by_id[author.id] = author
                self.by_name.setdefault(normalized, []).append(author)
        if evidence.orcid and not author.orcid and not repeated_external_identity:
            existing = self.by_orcid.get(evidence.orcid)
            if existing is None or existing.id == author.id:
                author.orcid = evidence.orcid
                self.by_orcid[evidence.orcid] = author
            else:
                flags.append("orcid_identity_conflict")
        raw_metadata = dict(author.raw_metadata or {})
        raw_metadata["metadata_agent"] = {
            "openalex_author_id": evidence.openalex_author_id,
            "sources": sorted(set(evidence.sources)),
        }
        author.raw_metadata = raw_metadata
        if evidence.openalex_author_id and not repeated_external_identity:
            self.by_openalex[evidence.openalex_author_id] = author
        return author, flags


class _InstitutionResolver:
    def __init__(self, session: Session) -> None:
        self.session = session
        institutions = list(session.execute(select(Institution)).scalars())
        self.by_name = {
            normalize_institution(row.canonical_name): row for row in institutions
        }
        self.by_external_id: dict[str, Institution] = {}
        for row in institutions:
            metadata = row.raw_metadata or {}
            for value in (metadata.get("ror"), metadata.get("openalex_id")):
                if value:
                    self.by_external_id[str(value)] = row

    def resolve(self, assertion: dict) -> Institution:
        external_ids = [
            str(assertion.get("ror") or ""),
            str(assertion.get("openalex_id") or ""),
        ]
        institution = next(
            (
                self.by_external_id[value]
                for value in external_ids
                if value in self.by_external_id
            ),
            None,
        )
        name = str(assertion.get("display_name") or "").strip()
        if institution is None:
            institution = self.by_name.get(normalize_institution(name))
        if institution is None:
            external = next((value for value in external_ids if value), name)
            institution = Institution(
                id=_stable_id("inst", external),
                canonical_name=name,
                aliases=[],
                normalized_aliases=[normalize_institution(name)],
                country=assertion.get("country_code"),
                is_partner=False,
                raw_metadata={},
            )
            self.session.add(institution)
            self.session.flush()
            self.by_name[normalize_institution(name)] = institution
        metadata = dict(institution.raw_metadata or {})
        metadata.update(
            {
                "ror": assertion.get("ror"),
                "openalex_id": assertion.get("openalex_id"),
                "lineage": assertion.get("lineage") or [],
                "metadata_sources": sorted(
                    set(
                        list(metadata.get("metadata_sources") or [])
                        + [str(assertion.get("source") or "")]
                    )
                    - {""}
                ),
            }
        )
        institution.raw_metadata = metadata
        for value in external_ids:
            if value:
                self.by_external_id[value] = institution
        return institution


def _openalex_authorships(work: dict | None) -> list[AuthorshipEvidence]:
    if not work:
        return []
    record_id = str(work.get("id") or "")
    rows: list[AuthorshipEvidence] = []
    for raw in work.get("authorships") or []:
        author = raw.get("author") or {}
        name = str(
            author.get("display_name") or raw.get("raw_author_name") or ""
        ).strip()
        if not name:
            continue
        raw_affiliations = [
            str(value).strip()
            for value in raw.get("raw_affiliation_strings") or []
            if str(value).strip()
        ]
        affiliations = [
            {
                "institution_id": None,
                "display_name": str(item.get("display_name") or "").strip(),
                "ror": str(item.get("ror") or "").strip() or None,
                "openalex_id": str(item.get("id") or "").strip() or None,
                "country_code": item.get("country_code"),
                "type": item.get("type"),
                "lineage": item.get("lineage") or [],
                "raw_affiliations": raw_affiliations,
                "source": "openalex",
                "source_record_id": record_id,
                "confidence": 0.98,
                "resolved": True,
            }
            for item in raw.get("institutions") or []
            if str(item.get("display_name") or "").strip()
        ]
        rows.append(
            AuthorshipEvidence(
                name=name,
                author_position=str(raw.get("author_position") or "middle"),
                is_corresponding=raw.get("is_corresponding"),
                openalex_author_id=str(author.get("id") or "").strip() or None,
                orcid=_normalize_orcid(author.get("orcid")),
                affiliations=affiliations,
                raw_affiliations=raw_affiliations,
                sources=["openalex"],
                source_record_ids=[record_id] if record_id else [],
            )
        )
    return rows


def _crossref_authorships(work: dict | None) -> list[AuthorshipEvidence]:
    if not work:
        return []
    record_id = normalize_doi(work.get("DOI")) or ""
    rows: list[AuthorshipEvidence] = []
    authors = work.get("author") or []
    for index, raw in enumerate(authors):
        name = " ".join(
            part
            for part in (
                str(raw.get("given") or "").strip(),
                str(raw.get("family") or "").strip(),
            )
            if part
        )
        if not name:
            continue
        raw_affiliations = [
            str(item.get("name") or "").strip()
            for item in raw.get("affiliation") or []
            if str(item.get("name") or "").strip()
        ]
        rows.append(
            AuthorshipEvidence(
                name=name,
                author_position=_position(index, len(authors)),
                is_corresponding=None,
                openalex_author_id=None,
                orcid=_normalize_orcid(raw.get("ORCID")),
                affiliations=[],
                raw_affiliations=raw_affiliations,
                sources=["crossref"],
                source_record_ids=[record_id] if record_id else [],
            )
        )
    return rows


def _merge_authorships(
    primary: list[AuthorshipEvidence],
    fallback: list[AuthorshipEvidence],
    csv_authors: list[str],
    doi: str,
) -> list[AuthorshipEvidence]:
    rows = primary or fallback
    if not rows:
        rows = [
            AuthorshipEvidence(
                name=name,
                author_position=_position(index, len(csv_authors)),
                is_corresponding=None,
                openalex_author_id=None,
                orcid=None,
                affiliations=[],
                raw_affiliations=[],
                sources=["zotero_csv"],
                source_record_ids=[doi],
                quality_flags=["external_authorship_missing"],
            )
            for index, name in enumerate(csv_authors)
        ]
    if primary and fallback:
        for index, row in enumerate(rows):
            if row.affiliations or row.raw_affiliations or index >= len(fallback):
                continue
            candidate = fallback[index]
            if _same_name(row.name, candidate.name):
                row.raw_affiliations = candidate.raw_affiliations
                row.sources = sorted(set(row.sources + candidate.sources))
                row.source_record_ids = sorted(
                    set(row.source_record_ids + candidate.source_record_ids)
                )
            else:
                row.quality_flags.append("crossref_position_name_conflict")
    if csv_authors and len(csv_authors) != len(rows):
        for row in rows:
            row.quality_flags.append("zotero_external_author_count_conflict")
    elif csv_authors:
        for index, row in enumerate(rows):
            if _same_name(csv_authors[index], row.name):
                row.sources = sorted(set(row.sources + ["zotero_csv"]))
                row.source_record_ids = sorted(set(row.source_record_ids + [doi]))
            else:
                row.quality_flags.append("zotero_external_author_name_conflict")
    return rows


def _resolve_affiliations(
    authorship: AuthorshipEvidence,
    session: Session,
    ror: RorClient,
) -> list[dict]:
    assertions = list(authorship.affiliations)
    if assertions:
        return _deduplicate_affiliations(assertions)
    for raw in authorship.raw_affiliations:
        match = ror.match_affiliation(session, raw)
        organization = (match or {}).get("organization") or {}
        display_name = _ror_display_name(organization)
        ror_id = str(organization.get("id") or "").strip() or None
        locations = organization.get("locations") or []
        country = (
            (locations[0].get("geonames_details") or {}).get("country_code")
            if locations
            else None
        )
        if display_name and ror_id:
            assertions.append(
                {
                    "institution_id": None,
                    "display_name": display_name,
                    "ror": ror_id,
                    "openalex_id": None,
                    "country_code": country,
                    "type": None,
                    "lineage": [],
                    "raw_affiliations": [raw],
                    "source": "crossref_ror",
                    "source_record_id": authorship.source_record_ids[-1]
                    if authorship.source_record_ids
                    else None,
                    "confidence": 0.95,
                    "resolved": True,
                }
            )
        else:
            assertions.append(
                {
                    "institution_id": None,
                    "display_name": raw,
                    "ror": None,
                    "openalex_id": None,
                    "country_code": None,
                    "type": None,
                    "lineage": [],
                    "raw_affiliations": [raw],
                    "source": "crossref",
                    "source_record_id": authorship.source_record_ids[-1]
                    if authorship.source_record_ids
                    else None,
                    "confidence": 0.5,
                    "resolved": False,
                }
            )
    if not assertions:
        authorship.quality_flags.append("no_affiliation_evidence")
    return _deduplicate_affiliations(assertions)


def _deduplicate_affiliations(values: list[dict]) -> list[dict]:
    by_identity: dict[str, dict] = {}
    for value in values:
        identity = str(
            value.get("ror")
            or value.get("openalex_id")
            or normalize_institution(str(value.get("display_name") or ""))
        )
        existing = by_identity.get(identity)
        if existing is None or float(value.get("confidence") or 0) > float(
            existing.get("confidence") or 0
        ):
            by_identity[identity] = value
    return list(by_identity.values())


def _ror_display_name(organization: dict) -> str | None:
    for name in organization.get("names") or []:
        if "ror_display" in (name.get("types") or []):
            value = str(name.get("value") or "").strip()
            if value:
                return value
    return None


def _openalex_venue(work: dict | None) -> str | None:
    source = ((work or {}).get("primary_location") or {}).get("source") or {}
    return str(source.get("display_name") or "").strip() or None


def _split_authors(value: object) -> list[str]:
    return [item.strip() for item in str(value or "").split(";") if item.strip()]


def _parse_year(value: object) -> int | None:
    text = str(value or "").strip()
    return int(text) if text.isdigit() else None


def _longest(rows: list[dict[str, str]], key: str) -> str | None:
    values = [str(row.get(key) or "").strip() for row in rows]
    value = max(values, key=len, default="")
    return value or None


def _position(order: int, count: int) -> str:
    if order == 0:
        return "first"
    if order == count - 1:
        return "last"
    return "middle"


def _same_name(left: str, right: str) -> bool:
    left_tokens = sorted(normalize_name(left).split())
    right_tokens = sorted(normalize_name(right).split())
    return bool(left_tokens) and left_tokens == right_tokens


def _normalize_orcid(value: object) -> str | None:
    text = str(value or "").strip().removeprefix("https://orcid.org/")
    return text or None


def _stable_id(prefix: str, value: str) -> str:
    return f"{prefix}_{uuid.uuid5(uuid.NAMESPACE_URL, value.casefold()).hex[:12]}"


def _sha256_json(value: object) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _error(stage: str, doi: str | None, exc: Exception) -> dict[str, str | None]:
    return {
        "stage": stage,
        "doi": doi,
        "error_type": type(exc).__name__,
        "message": str(exc)[:500],
    }
