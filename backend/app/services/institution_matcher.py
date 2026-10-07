"""Match an affiliation string against the institution alias table."""
from __future__ import annotations

import re

from dataclasses import dataclass

from rapidfuzz import fuzz

from app.config import settings
from app.models import Institution
from app.services.normalization_service import normalize_institution


@dataclass
class InstitutionMatch:
    institution_id: str
    canonical_name: str
    is_partner: bool
    match_type: str
    score: float
    matched_text: str | None


# Module-level cache for substring match regex patterns.
_SUBSTRING_RE_CACHE: dict[str, "re.Pattern[str]"] = {}


class InstitutionMatcher:
    def __init__(
        self, institutions: list[Institution], fuzzy_threshold: float | None = None
    ) -> None:
        self.institutions = institutions
        self.alias_index: dict[str, Institution] = {}
        for inst in institutions:
            self.alias_index[normalize_institution(inst.canonical_name)] = inst
            for alias in inst.normalized_aliases or []:
                self.alias_index.setdefault(alias, inst)
        self.fuzzy_threshold = fuzzy_threshold or settings.fuzzy_institution_threshold

    def match(self, raw_text: str) -> InstitutionMatch | None:
        normalized = normalize_institution(raw_text)
        if not normalized:
            return None

        # Exact / alias match on the whole string.
        inst = self.alias_index.get(normalized)
        if inst is not None:
            return self._build(inst, "exact_match", 1.0, raw_text)

        # Substring containment with word-boundary enforcement.
        # A match only fires when the alias text is bounded by non-alphanumeric
        # characters in the query, preventing false matches such as
        # "eth" matching inside "methodology" or "cas" inside "case study".
        for key, inst in self.alias_index.items():
            if not key or len(key) < 4:
                continue
            pat = _SUBSTRING_RE_CACHE.get(key)
            if pat is None:
                escaped = re.escape(key)
                pat = re.compile(rf"(?<!\w){escaped}(?!\w)", flags=re.IGNORECASE | re.UNICODE)
                _SUBSTRING_RE_CACHE[key] = pat
            if pat.search(normalized):
                return self._build(inst, "substring_match", 0.9, raw_text)

        best: tuple[Institution, float] | None = None
        for inst in self.institutions:
            score = (
                max(
                    fuzz.token_set_ratio(normalized, normalize_institution(inst.canonical_name)),
                    *[
                        fuzz.token_set_ratio(normalized, alias)
                        for alias in (inst.normalized_aliases or [])
                    ],
                )
                / 100.0
            )
            if best is None or score > best[1]:
                best = (inst, score)
        if best and best[1] >= self.fuzzy_threshold:
            return self._build(best[0], "fuzzy_match", best[1], raw_text)

        return None

    @staticmethod
    def _build(
        inst: Institution, match_type: str, score: float, matched_text: str
    ) -> InstitutionMatch:
        return InstitutionMatch(
            institution_id=inst.id,
            canonical_name=inst.canonical_name,
            is_partner=inst.is_partner,
            match_type=match_type,
            score=score,
            matched_text=matched_text,
        )
