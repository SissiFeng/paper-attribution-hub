"""Domain-aware retokenization for scholarly text (parse.md §8).

The default `tokenize()` in `embedding_service.py` is a plain word splitter.
That's fine for generic text but it ruins our matching on multi-word
terms: "self-driving lab" becomes three tokens and BM25 loses the signal,
while a single keyword hit on "lab" would also boost a totally unrelated
paper.

This module replaces tokens with three behaviors before downstream
indexing / matching:

  1. **Protected phrases** are emitted as one token.
       "self-driving lab" → "self_driving_lab"
  2. **Canonical synonyms** map surface variants onto a canonical form.
       "autonomous lab" → "self_driving_laboratory"
  3. **Negative phrases** are flagged so downstream callers can demote them.
       "closed-loop control" → mark the chunk as a likely false positive.

The vocabulary lives in `data/domain_vocabulary.yaml` so non-engineers can
edit it.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

import yaml

from app.services.embedding_service import tokenize as _basic_tokenize

_NORM_RE = re.compile(r"[^a-z0-9]+")


def _normalize_phrase(phrase: str) -> str:
    return _NORM_RE.sub("_", phrase.lower()).strip("_")


@dataclass
class DomainVocabulary:
    protected: list[str] = field(default_factory=list)
    synonyms: dict[str, str] = field(default_factory=dict)
    negatives: list[str] = field(default_factory=list)

    def normalized_protected_phrases(self) -> list[str]:
        return [p.lower() for p in self.protected]

    def normalized_synonyms(self) -> dict[str, str]:
        return {k.lower(): v.lower() for k, v in self.synonyms.items()}

    def normalized_negatives(self) -> list[str]:
        return [n.lower() for n in self.negatives]


def load_vocabulary(path: Path | None = None) -> DomainVocabulary:
    from app.config import settings

    p = Path(path or settings.domain_vocabulary_yaml)
    if not p.exists():
        return DomainVocabulary()
    raw = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    return DomainVocabulary(
        protected=list(raw.get("protected_phrases", []) or []),
        synonyms=dict(raw.get("canonical_synonyms", {}) or {}),
        negatives=list(raw.get("negative_phrases", []) or []),
    )


@lru_cache(maxsize=1)
def get_vocabulary() -> DomainVocabulary:
    return load_vocabulary()


def reset_vocabulary_cache() -> None:
    get_vocabulary.cache_clear()


# ---------------------------------------------------------------------------
# Tokenization
# ---------------------------------------------------------------------------


class DomainTokenizer:
    """Phrase-protecting tokenizer.

    Builds an alternation regex over normalized phrases and synonyms so the
    longest match wins on a single left-to-right scan. Output tokens are
    `_basic_tokenize`'s alphabet (lowercase, single-word) plus phrase
    "compound" tokens like `self_driving_lab` so they don't collide with
    real words.
    """

    def __init__(self, vocab: DomainVocabulary | None = None) -> None:
        self.vocab = vocab or get_vocabulary()
        # Build phrase → compound-token map. Synonyms map to the canonical form.
        compounds: dict[str, str] = {}
        for phrase in self.vocab.normalized_protected_phrases():
            compounds[phrase] = _normalize_phrase(phrase)
        for synonym, canonical in self.vocab.normalized_synonyms().items():
            compounds[synonym] = _normalize_phrase(canonical)
        # Longest first to avoid shadowing.
        ordered = sorted(compounds.keys(), key=lambda s: -len(s))
        self._compounds = compounds
        self._phrase_re = (
            re.compile(
                r"\b(" + "|".join(re.escape(p) for p in ordered) + r")\b",
                flags=re.IGNORECASE,
            )
            if ordered
            else None
        )
        # Negatives are tracked separately because callers may want to demote
        # rather than drop chunks that hit them.
        self._negative_set = set(self.vocab.normalized_negatives())

    def tokenize(self, text: str) -> list[str]:
        if not text:
            return []
        if self._phrase_re is None:
            return _basic_tokenize(text)

        out: list[str] = []
        cursor = 0
        for m in self._phrase_re.finditer(text.lower()):
            head = text[cursor : m.start()]
            if head:
                out.extend(_basic_tokenize(head))
            out.append(self._compounds[m.group(1).lower()])
            cursor = m.end()
        tail = text[cursor:]
        if tail:
            out.extend(_basic_tokenize(tail))
        return out

    # Convenience accessors used by other services.

    def has_negative_phrase(self, text: str) -> bool:
        if not text or not self._negative_set:
            return False
        lower = text.lower()
        return any(neg in lower for neg in self._negative_set)

    def has_protected(self, text: str, phrase: str) -> bool:
        if not text:
            return False
        return phrase.lower() in text.lower()
