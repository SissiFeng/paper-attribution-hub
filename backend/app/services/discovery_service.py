"""Discovery service.

Goal (newidea.md §third-stage §2): given the papers + AC core papers + AC
members we already know, find papers in the wider literature that we
*should* know about but don't have yet.

Strategies:
  1. cite-of-core    ─ OpenAlex `cites:W{ac_core_id}` for each ac_core_paper
  2. ac-coauthor     ─ OpenAlex papers by AC-member OpenAlex authors
  3. s2-recommend    ─ Semantic Scholar /recommendations for our CORE papers
  4. (future) topic  ─ semantic-similarity search against external corpora

Each candidate carries a list of triggers describing *why* it was surfaced.
Multi-trigger candidates get merged on `external_id`. The auto/queue split
is the hybrid policy you confirmed:

  auto-ingest if:
    - cites ≥ N AC core papers (N = settings.discovery_auto_cite_threshold)
    - OR has an author with ORCID matching one of our AC members
    - OR was returned by S2 with citation_count ≥ K AND cites_corpus ≥ 1
  else → discovery_candidates table for human approval.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.adapters.base import PaperRecord
from app.config import settings
from app.models import (
    AcCorePaper,
    Author,
    DiscoveryCandidate,
    Paper,
)
from app.review_contract import infer_corpus_sources
from app.services.external.crossref_client import (
    CrossrefClient,
    crossref_work_to_record,
)
from app.services.external.openalex_client import (
    OpenAlexClient,
    work_to_paper_record,
)
from app.services.external.semantic_scholar_client import (
    SemanticScholarClient,
    s2_paper_to_record,
)
from app.services.external.source_reliability import merge_paper_records


# ---------------------------------------------------------------------------
# Data shapes
# ---------------------------------------------------------------------------


@dataclass
class DiscoveryTrigger:
    strategy: str  # "cite_of_core" / "ac_coauthor" / "s2_recommend"
    source: str  # "openalex" / "semantic_scholar"
    detail: str
    weight: float = 0.5


@dataclass
class CandidateEnvelope:
    external_id: str
    record: PaperRecord
    triggers: list[DiscoveryTrigger] = field(default_factory=list)
    auto_eligible: bool = False
    confidence: float = 0.0

    def merge_trigger(self, t: DiscoveryTrigger) -> None:
        if not any(
            existing.strategy == t.strategy and existing.detail == t.detail
            for existing in self.triggers
        ):
            self.triggers.append(t)


@dataclass
class DiscoveryResult:
    candidates_seen: int = 0
    auto_ingested: int = 0
    queued: int = 0
    skipped_already_in_corpus: int = 0
    by_strategy: dict[str, int] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------


def _existing_doi_set(session: Session) -> set[str]:
    return {
        d for (d,) in session.execute(select(Paper.doi)).all() if d
    }


def _ac_member_ids_with_orcid(session: Session) -> dict[str, str]:
    """orcid → author_id, for ORCID-confirmed auto-ingest."""
    out: dict[str, str] = {}
    for a in session.execute(select(Author).where(Author.is_ac_member)).scalars():
        if a.orcid:
            out[a.orcid] = a.id
    return out


def _make_envelope(
    record: PaperRecord, triggers: list[DiscoveryTrigger]
) -> CandidateEnvelope:
    """Use the paper's DOI when available as the dedup id, else the source-specific id."""
    external_id = record.doi or record.paper_id
    env = CandidateEnvelope(external_id=external_id, record=record)
    for t in triggers:
        env.merge_trigger(t)
    return env


def strategy_cite_of_core(
    session: Session,
    openalex: OpenAlexClient,
    *,
    max_candidates: int,
) -> dict[str, CandidateEnvelope]:
    """For each ac_core_paper with a known OpenAlex Work id (or DOI we can
    resolve), pull "papers citing this Work" and emit candidates."""
    out: dict[str, CandidateEnvelope] = {}
    cores = list(session.execute(select(AcCorePaper)).scalars())
    if not cores:
        return out

    for core in cores:
        if not core.doi:
            continue
        # Resolve DOI → OpenAlex Work id.
        work = openalex.work_by_doi(session, core.doi)
        if not work or not work.get("id"):
            continue
        oa_work_id = work["id"].rsplit("/", 1)[-1]
        for cited_work in openalex.papers_citing(session, oa_work_id):
            if len(out) >= max_candidates:
                return out
            try:
                rec = work_to_paper_record(cited_work)
            except ValueError:
                continue
            envelope = out.get(rec.doi or rec.paper_id) or _make_envelope(
                rec, [],
            )
            envelope.merge_trigger(
                DiscoveryTrigger(
                    strategy="cite_of_core",
                    source="openalex",
                    detail=f"Cites AC core: {core.title}",
                    weight=0.7,
                )
            )
            out[envelope.external_id] = envelope
    return out


def strategy_ac_coauthor(
    session: Session,
    openalex: OpenAlexClient,
    *,
    max_candidates: int,
) -> dict[str, CandidateEnvelope]:
    """For each AC author with a known ORCID, find papers OpenAlex attributes
    to them that we don't already have in our corpus."""
    out: dict[str, CandidateEnvelope] = {}
    ac_authors = list(
        session.execute(select(Author).where(Author.is_ac_member)).scalars()
    )
    for ac in ac_authors:
        oa_authors = openalex.search_author(
            session, name=ac.canonical_name, orcid=ac.orcid
        )
        if not oa_authors:
            continue
        # `search_author` returns a list; for ORCID it's one entry.
        for oa in oa_authors[:1]:
            oa_author_id = (oa.get("id") or "").rsplit("/", 1)[-1]
            if not oa_author_id:
                continue
            for work in openalex.papers_by_author(session, oa_author_id):
                if len(out) >= max_candidates:
                    return out
                try:
                    rec = work_to_paper_record(work)
                except ValueError:
                    continue
                envelope = out.get(rec.doi or rec.paper_id) or _make_envelope(rec, [])
                envelope.merge_trigger(
                    DiscoveryTrigger(
                        strategy="ac_coauthor",
                        source="openalex",
                        detail=f"Authored by AC member: {ac.canonical_name}",
                        weight=0.85,
                    )
                )
                out[envelope.external_id] = envelope
    return out


def strategy_s2_recommend(
    session: Session,
    s2: SemanticScholarClient,
    *,
    max_candidates: int,
) -> dict[str, CandidateEnvelope]:
    """For each CORE_RELEVANT paper we already have, ask S2 for similar papers."""
    out: dict[str, CandidateEnvelope] = {}
    core_papers = list(
        session.execute(
            select(Paper).join(Paper.classification).where(
                Paper.classification.has(label="CORE_RELEVANT")
            )
        ).scalars()
    )
    for seed in core_papers:
        if not seed.doi:
            continue
        for rec_paper in s2.recommendations(session, seed.doi):
            if len(out) >= max_candidates:
                return out
            try:
                rec = s2_paper_to_record(rec_paper)
            except Exception:
                continue
            envelope = out.get(rec.doi or rec.paper_id) or _make_envelope(rec, [])
            envelope.merge_trigger(
                DiscoveryTrigger(
                    strategy="s2_recommend",
                    source="semantic_scholar",
                    detail=f"Similar to {seed.id}: {seed.title[:60]}",
                    weight=0.4,
                )
            )
            out[envelope.external_id] = envelope
    return out


def strategy_crossref_validate(
    session: Session,
    crossref: CrossrefClient,
    candidates: dict[str, CandidateEnvelope],
) -> None:
    """For each candidate with a DOI, fetch Crossref metadata and merge it
    via source_reliability rules. Crossref always wins on title / year /
    venue when present (highest trust under v0.5)."""
    for envelope in candidates.values():
        if not envelope.record.doi:
            continue
        work = crossref.work_by_doi(session, envelope.record.doi)
        if not work:
            continue
        try:
            cr_record = crossref_work_to_record(work)
        except Exception:
            continue
        merged = merge_paper_records(envelope.record, cr_record)
        # Patch back the merged fields onto the candidate's PaperRecord.
        for field_name in ("title", "abstract", "year", "venue"):
            value = merged.get(field_name)
            if value:
                setattr(envelope.record, field_name, value)


# ---------------------------------------------------------------------------
# Auto-eligibility classifier
# ---------------------------------------------------------------------------


def _score_envelope(
    env: CandidateEnvelope,
    *,
    ac_orcid_map: dict[str, str],
) -> tuple[bool, float]:
    """Decide if this candidate should be auto-ingested (v0.7).

    Returns (auto_eligible, confidence).

    Changes vs v0.5:
      * **AND-tower** for auto: ORCID alone, or (ac_coauthor AND cite_of_core),
        or (cite_of_core with N≥threshold AND ≥1 corroborating signal). The
        old "any one trigger fires → auto" path is gone.
      * **noisy-OR** confidence (instead of max) so weak triggers add a
        small bump but cannot replace a strong one.
      * `s2_recommend` alone never auto-ingests.
      * Duplicate triggers on the same paper (same strategy + detail) only
        count once — already enforced by `merge_trigger`.
    """
    cite_triggers = [t for t in env.triggers if t.strategy == "cite_of_core"]
    coauthor_triggers = [t for t in env.triggers if t.strategy == "ac_coauthor"]
    recommend_triggers = [t for t in env.triggers if t.strategy == "s2_recommend"]

    # ORCID-confirmed: any author in the candidate's raw payload whose ORCID
    # matches an AC member.
    raw = env.record.raw or {}
    raw_work = raw.get("raw") or {}
    orcid_match = False
    for authorship in raw_work.get("authorships") or []:
        author_obj = authorship.get("author") or {}
        orcid = author_obj.get("orcid")
        if orcid and orcid.split("/")[-1] in ac_orcid_map:
            orcid_match = True
            break

    # Build per-trigger probabilities (calibrated by trigger-strength).
    p_signals: list[float] = []
    if orcid_match:
        p_signals.append(0.95)
    if coauthor_triggers and orcid_match:
        p_signals.append(0.9)
    elif coauthor_triggers:
        p_signals.append(0.7)
    if len(cite_triggers) >= settings.discovery_auto_cite_threshold:
        p_signals.append(0.8)
    elif cite_triggers:
        p_signals.append(0.45)
    if recommend_triggers:
        p_signals.append(0.25)

    # Noisy-OR fusion: P(any) = 1 - Π(1 - p_i)
    confidence = 0.0
    for p in p_signals:
        confidence = 1 - (1 - confidence) * (1 - p)
    confidence = round(confidence, 3)

    # AND-tower for auto eligibility.
    auto = False
    if orcid_match:
        auto = True
    elif coauthor_triggers and cite_triggers:
        auto = True
    elif (
        len(cite_triggers) >= settings.discovery_auto_cite_threshold
        and (coauthor_triggers or orcid_match)
    ):
        auto = True
    # s2_recommend alone, or cite_of_core alone below threshold, stays queued.

    return auto, confidence


# ---------------------------------------------------------------------------
# Persistence + auto-ingest
# ---------------------------------------------------------------------------


def _persist_candidate(
    session: Session,
    env: CandidateEnvelope,
    status: str,
) -> DiscoveryCandidate:
    existing = session.execute(
        select(DiscoveryCandidate).where(
            DiscoveryCandidate.external_id == env.external_id
        )
    ).scalar_one_or_none()
    triggers_payload = [
        {
            "strategy": t.strategy,
            "source": t.source,
            "detail": t.detail,
            "weight": t.weight,
        }
        for t in env.triggers
    ]
    if existing is None:
        row = DiscoveryCandidate(
            id=f"disc_{uuid.uuid4().hex[:12]}",
            external_id=env.external_id,
            doi=env.record.doi,
            title=env.record.title,
            abstract=env.record.abstract,
            year=env.record.year,
            venue=env.record.venue,
            authors=[{"name": n} for n in env.record.authors],
            affiliations=env.record.affiliations,
            source=env.triggers[0].source if env.triggers else "unknown",
            triggers=triggers_payload,
            confidence=env.confidence,
            auto_eligible=env.auto_eligible,
            status=status,
            raw_payload=env.record.raw,
        )
        session.add(row)
        return row
    # Update — merge new triggers in.
    seen = {(t["strategy"], t["detail"]) for t in (existing.triggers or [])}
    for t in triggers_payload:
        if (t["strategy"], t["detail"]) not in seen:
            existing.triggers = (existing.triggers or []) + [t]
    existing.confidence = max(existing.confidence, env.confidence)
    if env.auto_eligible:
        existing.auto_eligible = True
    if status != "queued":
        existing.status = status
    return existing


def _ingest_candidate_as_paper(
    session: Session,
    env: CandidateEnvelope,
) -> Paper:
    """Promote a discovery candidate into a real Paper row."""
    from app.services.ingestion_service import _attach_authors

    paper_id = env.record.paper_id
    existing = session.get(Paper, paper_id)
    if existing is not None:
        return existing
    # v0.7 #11: encode the discovery provenance precisely so the learned
    # classifier can use it as a prior.
    if env.confidence >= 0.85:
        provenance = "discovered_auto_high"
    elif env.confidence >= 0.7:
        provenance = "discovered_auto"
    else:
        provenance = "discovered_auto_low"

    paper = Paper(
        id=paper_id,
        title=env.record.title,
        abstract=env.record.abstract,
        doi=env.record.doi,
        year=env.record.year,
        venue=env.record.venue,
        source=env.triggers[0].source if env.triggers else "discovered",
        provenance=provenance,
        corpus_sources=infer_corpus_sources(
            provenance=provenance,
            source=env.triggers[0].source if env.triggers else "discovered",
            trigger_strategies=[trigger.strategy for trigger in env.triggers],
        ),
        keywords=env.record.keywords,
        raw_metadata=env.record.raw,
    )
    session.add(paper)
    session.flush()
    _attach_authors(session, paper, env.record.authors, env.record.affiliations)
    return paper


def run_discovery(
    session: Session,
    *,
    strategies: list[str] | None = None,
    max_candidates: int | None = None,
    openalex: OpenAlexClient | None = None,
    s2: SemanticScholarClient | None = None,
    crossref: CrossrefClient | None = None,
) -> DiscoveryResult:
    """Main entry point. `strategies` defaults to all; clients can be injected
    by tests (with a mocked transport) or auto-constructed."""
    strategies = strategies or ["cite_of_core", "ac_coauthor", "s2_recommend"]
    max_candidates = max_candidates or settings.discovery_max_candidates_per_strategy

    openalex = openalex or OpenAlexClient()
    s2 = s2 or SemanticScholarClient()
    crossref = crossref or CrossrefClient()

    result = DiscoveryResult()
    candidates: dict[str, CandidateEnvelope] = {}

    if "cite_of_core" in strategies:
        before = len(candidates)
        new = strategy_cite_of_core(session, openalex, max_candidates=max_candidates)
        for k, env in new.items():
            existing = candidates.get(k)
            if existing:
                for t in env.triggers:
                    existing.merge_trigger(t)
            else:
                candidates[k] = env
        result.by_strategy["cite_of_core"] = len(candidates) - before

    if "ac_coauthor" in strategies:
        before = len(candidates)
        new = strategy_ac_coauthor(session, openalex, max_candidates=max_candidates)
        for k, env in new.items():
            existing = candidates.get(k)
            if existing:
                for t in env.triggers:
                    existing.merge_trigger(t)
            else:
                candidates[k] = env
        result.by_strategy["ac_coauthor"] = len(candidates) - before

    if "s2_recommend" in strategies:
        before = len(candidates)
        new = strategy_s2_recommend(session, s2, max_candidates=max_candidates)
        for k, env in new.items():
            existing = candidates.get(k)
            if existing:
                for t in env.triggers:
                    existing.merge_trigger(t)
            else:
                candidates[k] = env
        result.by_strategy["s2_recommend"] = len(candidates) - before

    # Crossref cross-validation (best-effort, never fatal).
    if candidates:
        try:
            strategy_crossref_validate(session, crossref, candidates)
        except Exception:
            pass

    existing_dois = _existing_doi_set(session)
    ac_orcid_map = _ac_member_ids_with_orcid(session)

    for env in candidates.values():
        result.candidates_seen += 1
        if env.record.doi and env.record.doi in existing_dois:
            result.skipped_already_in_corpus += 1
            continue
        env.auto_eligible, env.confidence = _score_envelope(
            env, ac_orcid_map=ac_orcid_map
        )
        if env.auto_eligible:
            _persist_candidate(session, env, status="auto_ingested")
            _ingest_candidate_as_paper(session, env)
            result.auto_ingested += 1
        else:
            _persist_candidate(session, env, status="queued")
            result.queued += 1

    session.commit()
    return result


# ---------------------------------------------------------------------------
# Manual approval (called from the API)
# ---------------------------------------------------------------------------


def approve_candidate(
    session: Session, candidate_id: str, reviewer: str | None = None, notes: str | None = None
) -> Paper:
    from datetime import UTC, datetime

    row = session.get(DiscoveryCandidate, candidate_id)
    if row is None:
        raise ValueError(f"Discovery candidate {candidate_id} not found")
    if row.status in {"auto_ingested", "approved"} and row.resulting_paper_id:
        existing = session.get(Paper, row.resulting_paper_id)
        if existing:
            return existing

    # Rebuild a CandidateEnvelope just for ingestion convenience.
    from app.adapters.base import PaperRecord

    record = PaperRecord(
        paper_id=row.external_id.replace("/", "_") if row.external_id else f"disc_{row.id}",
        title=row.title,
        abstract=row.abstract,
        authors=[a.get("name") for a in (row.authors or []) if a.get("name")],
        affiliations=list(row.affiliations or []),
        year=row.year,
        doi=row.doi,
        venue=row.venue,
        keywords=[],
        source=row.source,
        raw=row.raw_payload,
    )
    env = CandidateEnvelope(external_id=row.external_id, record=record)
    paper = _ingest_candidate_as_paper(session, env)
    paper.provenance = "discovered_approved"
    paper.corpus_sources = infer_corpus_sources(
        provenance=paper.provenance,
        source=paper.source,
        trigger_strategies=[
            trigger.get("strategy")
            for trigger in (row.triggers or [])
            if trigger.get("strategy")
        ],
    )
    row.status = "approved"
    row.resulting_paper_id = paper.id
    row.reviewer = reviewer
    row.review_notes = notes
    row.reviewed_at = datetime.now(UTC)
    session.commit()
    return paper


def reject_candidate(
    session: Session, candidate_id: str, reviewer: str | None = None, notes: str | None = None
) -> DiscoveryCandidate:
    from datetime import UTC, datetime

    row = session.get(DiscoveryCandidate, candidate_id)
    if row is None:
        raise ValueError(f"Discovery candidate {candidate_id} not found")
    row.status = "rejected"
    row.reviewer = reviewer
    row.review_notes = notes
    row.reviewed_at = datetime.now(UTC)
    session.commit()
    return row
