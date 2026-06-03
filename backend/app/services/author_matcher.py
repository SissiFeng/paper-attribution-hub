"""Match a paper author string against the AC member list (v0.7).

Tiers (best to worst, first hit wins):
  1. exact_author_match    — normalized canonical name equal
  2. alias_match           — normalized alias equal
  3. initials_match        — last name equal + first-name initial agrees
  4. fuzzy_match           — rapidfuzz token_sort_ratio above threshold

v0.7 addition: **contextual disambiguation**. Fuzzy and initials matches are
verified against the paper's other authors and affiliations. Specifically:
the candidate AC member must have evidence in *this paper* — either

  a) an ORCID match in the raw payload,
  b) another verified AC coauthor on the same paper, or
  c) the candidate's home institution appearing in the affiliations.

Without that corroboration the match is downgraded from `is_ac_member=True`
to `is_ac_member=False` (kept as `possible_match` so reviewers can still see
it), which prevents the common-surname FPs ("Wang Jian", "Li Bo", "Chen Yu")
that the old fuzzy threshold let through.
"""
from __future__ import annotations

from dataclasses import dataclass
import unicodedata

from rapidfuzz import fuzz

from app.config import settings
from app.models import Author
from app.services.normalization_service import name_initials, normalize_name


@dataclass
class AuthorMatch:
    person_id: str
    name: str
    institution: str | None
    match_type: str
    score: float
    is_ac_member: bool
    # v0.7: tells the rules engine *why* the match is or isn't trusted.
    corroborating_signals: list[str] | None = None


_MATCH_TYPE_SCORE = {
    "exact_author_match": 1.0,
    "alias_match": 0.95,
    "initials_match": 0.85,
}

# Match types that require corroboration before we trust them as AC-member.
_REQUIRES_CORROBORATION = {"initials_match", "fuzzy_match"}


def _build_alias_index(authors: list[Author]) -> dict[str, Author]:
    index: dict[str, Author] = {}
    for a in authors:
        for key in _index_keys(a.normalized_name):
            index[key] = a
        for alias in a.aliases or []:
            normalized = normalize_name(alias)
            if normalized:
                if _is_initials_alias(normalized):
                    continue
                for key in _index_keys(normalized):
                    index.setdefault(key, a)
    return index


def _index_keys(normalized_name: str) -> set[str]:
    keys = {normalized_name}
    if "-" in normalized_name:
        keys.add(normalized_name.replace("-", " "))
    return {key for key in keys if key}


def _is_initials_alias(normalized_name: str) -> bool:
    tokens = normalized_name.split()
    return len(tokens) >= 2 and any(len(token) == 1 for token in tokens)


def preferred_author_display_name(author: Author, raw_name: str | None = None) -> str:
    """Choose a stable human-facing name without changing the identity key."""
    if (
        raw_name
        and raw_name.strip() != author.canonical_name
        and normalize_name(raw_name) == author.normalized_name
    ):
        return raw_name.strip()

    candidates = [author.canonical_name, *(author.aliases or [])]
    for candidate in candidates:
        candidate = (candidate or "").strip()
        if _is_full_display_name(candidate) and _is_ascii(candidate):
            return candidate
    for candidate in candidates:
        candidate = (candidate or "").strip()
        if _is_full_display_name(candidate):
            return candidate
    return author.canonical_name


def _is_full_display_name(name: str) -> bool:
    normalized = normalize_name(name)
    tokens = normalized.split()
    if len(tokens) < 2:
        return False
    if "," in name:
        return False
    return not any(len(token) == 1 for token in tokens[:-1])


def _is_ascii(value: str) -> bool:
    folded = unicodedata.normalize("NFKD", value).encode("ascii", "ignore")
    return folded.decode("ascii") == value


def _initials_match(query: str, candidate: Author) -> bool:
    """e.g. 'a aspuru-guzik' matches 'alan aspuru-guzik' on last name + initial."""
    q_tokens = query.split()
    c_tokens = candidate.normalized_name.split()
    if not q_tokens or not c_tokens:
        return False
    if q_tokens[-1] != c_tokens[-1]:
        return False
    q_initials = name_initials(query).replace(" ", "")
    c_initials = name_initials(candidate.canonical_name).replace(" ", "")
    if not q_initials or not c_initials:
        return False
    return q_initials[0] == c_initials[0]


class AuthorMatcher:
    """Pre-builds an alias index over the AC member list."""

    def __init__(
        self,
        authors: list[Author],
        fuzzy_threshold: float | None = None,
    ) -> None:
        self.ac_authors = [a for a in authors if a.is_ac_member]
        self.alias_index = _build_alias_index(self.ac_authors)
        self.fuzzy_threshold = (
            fuzzy_threshold if fuzzy_threshold is not None
            else settings.fuzzy_author_threshold
        )

    # ------------------------------------------------------------------ #
    # Public API                                                         #
    # ------------------------------------------------------------------ #

    def match(
        self,
        raw_name: str,
        *,
        coauthor_names: list[str] | None = None,
        affiliations: list[str] | None = None,
        orcid: str | None = None,
    ) -> AuthorMatch | None:
        """Return a match for `raw_name`, with optional context for fuzzy
        disambiguation."""
        normalized = normalize_name(raw_name)
        if not normalized:
            return None

        author = self.alias_index.get(normalized)
        if author and author.normalized_name == normalized:
            return self._build(
                author,
                "exact_author_match",
                raw_name=raw_name,
                coauthor_names=coauthor_names,
                affiliations=affiliations,
                orcid=orcid,
            )
        if author:
            return self._build(
                author,
                "alias_match",
                raw_name=raw_name,
                coauthor_names=coauthor_names,
                affiliations=affiliations,
                orcid=orcid,
            )

        for candidate in self.ac_authors:
            if _initials_match(normalized, candidate):
                return self._build(
                    candidate,
                    "initials_match",
                    raw_name=raw_name,
                    coauthor_names=coauthor_names,
                    affiliations=affiliations,
                    orcid=orcid,
                )

        best: tuple[Author, float] | None = None
        for candidate in self.ac_authors:
            score = fuzz.token_sort_ratio(normalized, candidate.normalized_name) / 100.0
            if best is None or score > best[1]:
                best = (candidate, score)
        if best and best[1] >= self.fuzzy_threshold:
            return self._build(
                best[0],
                "fuzzy_match",
                score=best[1],
                raw_name=raw_name,
                coauthor_names=coauthor_names,
                affiliations=affiliations,
                orcid=orcid,
            )

        return None

    # ------------------------------------------------------------------ #
    # Internals                                                          #
    # ------------------------------------------------------------------ #

    def _build(
        self,
        author: Author,
        match_type: str,
        *,
        score: float | None = None,
        raw_name: str | None = None,
        coauthor_names: list[str] | None = None,
        affiliations: list[str] | None = None,
        orcid: str | None = None,
    ) -> AuthorMatch:
        raw_score = score if score is not None else _MATCH_TYPE_SCORE[match_type]

        # Contextual corroboration.
        signals: list[str] = []
        if orcid and author.orcid and orcid.split("/")[-1] == author.orcid.split("/")[-1]:
            signals.append("orcid_match")
        if author.institution and affiliations:
            home = author.institution.canonical_name.lower()
            for aff in affiliations:
                if home and home in (aff or "").lower():
                    signals.append("home_institution_in_affiliations")
                    break
        if coauthor_names:
            # Does any *other* author on the paper match a different AC member?
            other_names = [
                n
                for n in coauthor_names
                if normalize_name(n) != author.normalized_name
            ]
            for other in other_names:
                other_norm = normalize_name(other)
                if not other_norm:
                    continue
                hit = self.alias_index.get(other_norm)
                if hit is not None and hit.id != author.id:
                    signals.append(f"ac_coauthor:{hit.canonical_name}")
                    break

        is_ac_trusted = match_type not in _REQUIRES_CORROBORATION or bool(signals)

        return AuthorMatch(
            person_id=author.id,
            name=preferred_author_display_name(author, raw_name),
            institution=(
                author.institution.canonical_name if author.institution else None
            ),
            match_type=match_type if is_ac_trusted else f"{match_type}_unverified",
            score=raw_score if is_ac_trusted else raw_score * 0.6,
            is_ac_member=author.is_ac_member if is_ac_trusted else False,
            corroborating_signals=signals or None,
        )
