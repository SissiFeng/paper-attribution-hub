"""Measure domain-term fragmentation without changing a model tokenizer."""

from __future__ import annotations

import math
from typing import Protocol, Sequence

from app.services.domain_tokenizer import DomainTokenizer, DomainVocabulary

TOKENIZER_AUDIT_SCHEMA = "pas-tokenizer-fragmentation-audit-v0.1"


class TokenizerAdapter(Protocol):
    name: str
    model_tokenizer: bool

    def encode(self, text: str) -> Sequence[object]: ...


class WhitespaceTokenizerAdapter:
    name = "whitespace"
    model_tokenizer = False

    def encode(self, text: str) -> list[str]:
        return text.split()


class DomainRetrievalTokenizerAdapter:
    """Adapter for PAS retrieval tokenization, not model vocabulary analysis."""

    name = "pas-domain-retrieval-tokenizer"
    model_tokenizer = False

    def __init__(self, vocabulary: DomainVocabulary | None = None) -> None:
        self._tokenizer = DomainTokenizer(vocabulary)

    def encode(self, text: str) -> list[str]:
        return self._tokenizer.tokenize(text)


class HuggingFaceTokenizerAdapter:
    """Lazy adapter for a real model tokenizer."""

    model_tokenizer = True

    def __init__(
        self,
        model_name_or_path: str,
        *,
        local_files_only: bool = True,
    ) -> None:
        try:
            from transformers import AutoTokenizer
        except ImportError as exc:  # pragma: no cover - optional dependency
            raise RuntimeError(
                "Install transformers to audit a Hugging Face tokenizer"
            ) from exc
        self._tokenizer = AutoTokenizer.from_pretrained(
            model_name_or_path,
            local_files_only=local_files_only,
        )
        self.name = str(model_name_or_path)

    def encode(self, text: str) -> list[str]:
        return list(self._tokenizer.tokenize(text))


def _p95(values: list[int]) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    return float(ordered[max(0, math.ceil(0.95 * len(ordered)) - 1)])


def audit_tokenizer_fragmentation(
    *,
    texts: Sequence[str],
    domain_terms: Sequence[str],
    tokenizer: TokenizerAdapter,
) -> dict:
    """Report phrase splitting and excess subword splitting separately."""
    clean_texts = [text for text in texts if text and text.strip()]
    whitespace_word_count = sum(len(text.split()) for text in clean_texts)
    token_count = sum(len(tokenizer.encode(text)) for text in clean_texts)

    unique_terms: list[str] = []
    seen_terms: set[str] = set()
    for term in domain_terms:
        clean = term.strip()
        key = clean.casefold()
        if not clean or key in seen_terms:
            continue
        seen_terms.add(key)
        unique_terms.append(clean)

    term_rows: list[dict] = []
    for term in unique_terms:
        # Most model tokenizers are whitespace-sensitive. A leading space
        # approximates a normal mid-sentence occurrence more faithfully than
        # tokenizing every term as if it began a document.
        pieces = [str(piece) for piece in tokenizer.encode(f" {term}")]
        word_count = max(1, len(term.split()))
        term_rows.append(
            {
                "term": term,
                "word_count": word_count,
                "token_count": len(pieces),
                "tokens_per_word": round(len(pieces) / word_count, 4),
                "pieces": pieces,
            }
        )
    term_rows.sort(
        key=lambda row: (
            -row["tokens_per_word"],
            -row["token_count"],
            row["term"].casefold(),
        )
    )

    term_count = len(term_rows)
    multi_token_terms = sum(row["token_count"] > 1 for row in term_rows)
    subword_fragmented_terms = sum(
        row["token_count"] > row["word_count"] for row in term_rows
    )
    term_token_counts = [row["token_count"] for row in term_rows]
    return {
        "schema_version": TOKENIZER_AUDIT_SCHEMA,
        "tokenizer": tokenizer.name,
        "model_tokenizer": getattr(tokenizer, "model_tokenizer", False),
        "term_context": "mid_text_leading_space",
        "text_count": len(clean_texts),
        "whitespace_word_count": whitespace_word_count,
        "token_count": token_count,
        "tokens_per_word": (
            round(token_count / whitespace_word_count, 4)
            if whitespace_word_count
            else 0.0
        ),
        "term_count": term_count,
        "multi_token_terms": multi_token_terms,
        "multi_token_rate": multi_token_terms / term_count if term_count else 0.0,
        "subword_fragmented_terms": subword_fragmented_terms,
        "subword_fragmentation_rate": (
            subword_fragmented_terms / term_count if term_count else 0.0
        ),
        "mean_tokens_per_term": (
            round(sum(term_token_counts) / term_count, 4) if term_count else 0.0
        ),
        "p95_tokens_per_term": _p95(term_token_counts),
        "worst_terms": term_rows[:25],
    }
