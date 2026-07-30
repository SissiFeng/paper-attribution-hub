"""Identity-gated candidate fetch loop: rank -> fetch -> verify -> fall through.

The network fetch is injected (``fetch_fn``) so this orchestration is pure with
respect to I/O and testable, and the real fetch pipeline can adopt it without
this module importing it.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from app.services.document_identity import DocIdentity, verify_identity
from app.services.fetch_ranking import FetchCandidate, rank_candidates


@dataclass(frozen=True)
class FetchedDoc:
    """What a fetch attempt produced: the parsed document's own identity."""

    identity: DocIdentity


@dataclass(frozen=True)
class FetchAttempt:
    candidate: FetchCandidate
    parse_ok: bool
    verdict: str | None  # MATCH | MISMATCH | UNCERTAIN | None (fetch/parse failed)
    score: float


@dataclass(frozen=True)
class FetchOutcome:
    status: str  # ACCEPTED_MATCH | ACCEPTED_UNCERTAIN | REJECTED_ALL | NO_CANDIDATES
    accepted: FetchAttempt | None
    attempts: list[FetchAttempt] = field(default_factory=list)


FetchFn = Callable[[FetchCandidate], FetchedDoc | None]


def fetch_best_document(
    candidates: list[FetchCandidate],
    target: DocIdentity,
    *,
    fetch_fn: FetchFn,
    prefer_version: str | None = None,
    accept_uncertain: bool = True,
) -> FetchOutcome:
    ranked = rank_candidates(candidates, prefer_version=prefer_version)
    if not ranked:
        return FetchOutcome(status="NO_CANDIDATES", accepted=None)

    attempts: list[FetchAttempt] = []
    uncertain_fallback: FetchAttempt | None = None

    for rc in ranked:
        fetched = fetch_fn(rc.candidate)
        if fetched is None:
            attempts.append(FetchAttempt(rc.candidate, False, None, rc.score))
            continue

        verdict = verify_identity(target, fetched.identity).verdict
        attempt = FetchAttempt(rc.candidate, True, verdict, rc.score)
        attempts.append(attempt)

        if verdict == "MATCH":
            return FetchOutcome("ACCEPTED_MATCH", attempt, attempts)
        if verdict == "UNCERTAIN" and uncertain_fallback is None:
            uncertain_fallback = attempt
        # MISMATCH (or a later UNCERTAIN): keep trying more candidates.

    if accept_uncertain and uncertain_fallback is not None:
        return FetchOutcome("ACCEPTED_UNCERTAIN", uncertain_fallback, attempts)
    return FetchOutcome("REJECTED_ALL", None, attempts)
