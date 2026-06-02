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


class ClaudeReranker(Reranker):
    """LLM-based reranker using Claude (claude-haiku for low latency + cost).

    Sends all candidates to Claude in one request and asks it to rank by
    relevance.  Much more semantic than BM25/cosine — handles paraphrase,
    implicit relevance, and scientific jargon mismatches that TF-IDF misses.

    Activate with:  PAS_RERANKER=claude  (and PAS_ANTHROPIC_API_KEY set)
    """

    name = "claude"

    def rerank(
        self, query: str, candidates: list[RetrievedChunk]
    ) -> list[RetrievedChunk]:
        if len(candidates) <= 1:
            return candidates
        try:
            import anthropic
        except ImportError as e:
            raise RuntimeError(
                "anthropic package not installed. `pip install anthropic`."
            ) from e

        api_key = os.environ.get("PAS_ANTHROPIC_API_KEY", "")
        if not api_key:
            # Degrade gracefully — return original order rather than crash.
            return candidates

        client = anthropic.Anthropic(api_key=api_key)

        passages = "\n\n".join(
            f"[{i + 1}] {c.text[:600]}" for i, c in enumerate(candidates)
        )
        prompt = (
            f"You are a research-literature relevance ranker.\n\n"
            f"Query: {query}\n\n"
            f"Rank the following {len(candidates)} passages by relevance to the query "
            f"(most relevant first). Return ONLY a JSON array of passage numbers, e.g. [3,1,2].\n\n"
            f"Passages:\n{passages}"
        )

        try:
            response = client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=256,
                messages=[{"role": "user", "content": prompt}],
            )
            text = response.content[0].text
        except Exception:
            return candidates  # network/API failure → fall back to original order

        import json, re  # noqa: E401

        match = re.search(r"\[[\d,\s]+\]", text)
        if not match:
            return candidates

        try:
            indices = json.loads(match.group())
        except (json.JSONDecodeError, ValueError):
            return candidates

        ordered: list[RetrievedChunk] = []
        seen: set[int] = set()
        for idx in indices:
            i = int(idx) - 1  # 1-indexed → 0-indexed
            if 0 <= i < len(candidates) and i not in seen:
                seen.add(i)
                ordered.append(candidates[i])

        # Append anything Claude didn't mention (shouldn't happen but be safe)
        for i, c in enumerate(candidates):
            if i not in seen:
                ordered.append(c)

        return ordered


def get_reranker() -> Reranker:
    """Honor `PAS_RERANKER` env var. Defaults to NullReranker."""
    backend = os.environ.get("PAS_RERANKER", "").lower()
    if backend == "cross-encoder":
        return CrossEncoderReranker(
            os.environ.get("PAS_RERANKER_MODEL", "cross-encoder/ms-marco-MiniLM-L-6-v2")
        )
    if backend == "claude":
        return ClaudeReranker()
    return NullReranker()
