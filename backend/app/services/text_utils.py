"""Shared text-analysis utilities for the candidate filter (v0.7).

Two responsibilities consolidated here so topic_classifier and evidence_extractor
stop drifting:

  * `find_term_hits` — word-boundary aware, multi-word phrase aware substring
    search that returns hit positions (not just bool).
  * `is_negated` — peek backwards N tokens around a hit; if the window contains
    a negation cue, the hit is "negative context".

These are the primitive that lets us replace "term in haystack" with something
defensible. Both are pure functions, no deps beyond stdlib.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

# ---------------------------------------------------------------------------
# Tokenization
# ---------------------------------------------------------------------------

_TOKEN_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9\-]*", flags=re.UNICODE)
_SENTENCE_RE = re.compile(r"(?<=[.!?])\s+")
_PARAGRAPH_RE = re.compile(r"\n\s*\n")

NEGATION_CUES = {
    "not",
    "no",
    "without",
    "lacks",
    "lacking",
    "unlike",
    "beyond",
    "neither",
    "nor",
    "doesn't",
    "doesnt",
    "don't",
    "dont",
    "isn't",
    "isnt",
    "aren't",
    "arent",
    "non",  # "non-autonomous"
    "absence",
    "missing",
}


def normalize_lower(text: str) -> str:
    """NFKC + lower; preserves hyphens so multi-word terms keep their shape."""
    return unicodedata.normalize("NFKC", text).lower()


def tokens(text: str) -> list[str]:
    """Word-ish tokens. Used for context windows, not for vocab features."""
    return [m.group(0).lower() for m in _TOKEN_RE.finditer(text)]


# ---------------------------------------------------------------------------
# Phrase matching with boundary control
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TermHit:
    term: str
    start: int  # char offset in the source string
    end: int
    negated: bool = False


def _phrase_regex(term: str) -> re.Pattern[str]:
    """Build a token-boundary regex from a phrase.

    Whitespace inside a phrase becomes flexible (one+ space / tab / nbsp), and
    `-` becomes `[\\s-]` so 'self-driving lab' matches both 'self-driving lab'
    and 'self driving lab' but not 'selfdriving lab'.
    """
    parts = []
    for piece in term.strip().split():
        if "-" in piece:
            sub = piece.replace("-", r"[\s\-]")
            parts.append(sub)
        else:
            parts.append(re.escape(piece))
    body = r"\s+".join(parts)
    # Use lookarounds for word boundaries that respect hyphens/letters.
    pattern = rf"(?<![A-Za-z0-9])(?:{body})(?![A-Za-z0-9])"
    return re.compile(pattern, flags=re.IGNORECASE | re.UNICODE)


_PHRASE_CACHE: dict[str, re.Pattern[str]] = {}


def get_phrase_regex(term: str) -> re.Pattern[str]:
    pat = _PHRASE_CACHE.get(term)
    if pat is None:
        pat = _phrase_regex(term)
        _PHRASE_CACHE[term] = pat
    return pat


def find_term_hits(
    haystack: str,
    term: str,
    *,
    negation_window: int = 6,
) -> list[TermHit]:
    """Return every hit of `term` in `haystack`, each annotated with negation."""
    if not haystack or not term:
        return []
    regex = get_phrase_regex(term)
    hits: list[TermHit] = []
    lower = haystack  # case handled by IGNORECASE
    for m in regex.finditer(lower):
        negated = is_negated(haystack, m.start(), window=negation_window)
        hits.append(
            TermHit(term=term, start=m.start(), end=m.end(), negated=negated)
        )
    return hits


def is_negated(text: str, hit_start: int, *, window: int = 6) -> bool:
    """Look backwards `window` tokens; if any are a NEGATION_CUE, return True.

    Also catches "not" / "no" placed right before the term within the same
    sentence. Stops at sentence boundary so a previous sentence's 'not' doesn't
    poison the current hit.
    """
    if hit_start <= 0:
        return False
    prefix = text[:hit_start]
    # truncate to start of current sentence
    last_break = max(
        prefix.rfind("."),
        prefix.rfind("!"),
        prefix.rfind("?"),
        prefix.rfind("\n"),
    )
    if last_break > 0:
        prefix = prefix[last_break + 1 :]
    prev_tokens = tokens(prefix)[-window:]
    for tok in prev_tokens:
        if tok in NEGATION_CUES:
            return True
    return False


# ---------------------------------------------------------------------------
# Topic density: count co-occurring core hits per paragraph
# ---------------------------------------------------------------------------


def split_paragraphs(text: str) -> list[str]:
    if not text:
        return []
    parts = _PARAGRAPH_RE.split(text)
    return [p.strip() for p in parts if p.strip()]


def split_sentences(text: str) -> list[str]:
    if not text:
        return []
    parts = _SENTENCE_RE.split(text.strip())
    return [p.strip() for p in parts if p.strip()]
