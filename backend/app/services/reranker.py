"""Pluggable reranker slot for retrieval (parse.md §11.9).

By default the system uses `NullReranker` — the linear BM25/cosine blend
from `HybridIndex` is already enough for a few hundred chunks.

A cross-encoder reranker is available when sentence-transformers is
installed and `PAS_RERANKER=cross-encoder` is set. Cross-encoders re-score
the top-K candidates by reading the query and the candidate together
(unlike bi-encoders), which usually fixes the "looks similar, isn't" cases
that hurt attribution accuracy at narrow margins.

Tests load `NullReranker` so they don't need any ML dependency.
"""
from __future__ import annotations

import os
from abc import ABC, abstractmethod
from dataclasses import replace

from app.services.retrieval_service import RetrievedChunk


class Reranker(ABC):
    name: str

    @abstractmethod
    def rerank(
        self, query: str, candidates: list[RetrievedChunk]
    ) -> list[RetrievedChunk]: ...


class NullReranker(Reranker):
    """Default: keep the order produced by HybridIndex."""

    name = "none"

    def rerank(
        self, query: str, candidates: list[RetrievedChunk]
    ) -> list[RetrievedChunk]:
        return candidates


class CrossEncoderReranker(Reranker):
    """sentence-transformers CrossEncoder. Loaded lazily."""

    name = "cross-encoder"

    def __init__(self, model_name: str = "cross-encoder/ms-marco-MiniLM-L-6-v2") -> None:
        self.model_name = model_name
        self._model = None

    def _ensure_loaded(self):
        if self._model is not None:
            return
        try:
            from sentence_transformers import CrossEncoder  # type: ignore
        except ImportError as e:
            raise RuntimeError(
                "sentence-transformers is not installed. "
                "`pip install sentence-transformers` or unset PAS_RERANKER."
            ) from e
        self._model = CrossEncoder(self.model_name)

    def rerank(
        self, query: str, candidates: list[RetrievedChunk]
    ) -> list[RetrievedChunk]:
        if not candidates:
            return candidates
        self._ensure_loaded()
        pairs = [(query, c.text) for c in candidates]
        scores = self._model.predict(pairs)  # type: ignore[union-attr]
        scored = [
            replace(c, score=float(scores[i]))
            for i, c in enumerate(candidates)
        ]
        scored.sort(key=lambda c: -c.score)
        return scored


def get_reranker() -> Reranker:
    """Honor `PAS_RERANKER` env var. Defaults to NullReranker."""
    backend = os.environ.get("PAS_RERANKER", "").lower()
    if backend == "cross-encoder":
        return CrossEncoderReranker(
            os.environ.get("PAS_RERANKER_MODEL", "cross-encoder/ms-marco-MiniLM-L-6-v2")
        )
    return NullReranker()
