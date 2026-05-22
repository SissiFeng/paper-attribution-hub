"""Pluggable embedding backends.

Default: TF-IDF in pure numpy. No PyTorch, no model downloads, fully
deterministic, runs in tests. Good enough for hundreds of papers, and the
interface is identical to sentence-transformers so production can swap.

To use sentence-transformers instead:
    pip install sentence-transformers
    export PAS_EMBEDDING_BACKEND=sbert
    export PAS_EMBEDDING_MODEL=all-MiniLM-L6-v2

The Embedder is fit-once / encode-many. After `fit(corpus)`, both `encode`
and `similarity` operate in the learned space.
"""
from __future__ import annotations

import math
import os
import re
from abc import ABC, abstractmethod

import numpy as np

_TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z0-9\-]+")


def tokenize(text: str) -> list[str]:
    """Plain word splitter. Domain-aware retokenization is layered on top by
    `app.services.domain_tokenizer.DomainTokenizer.tokenize()`. Indexers that
    care about multi-word terms should use the domain tokenizer instead."""
    return [t.lower() for t in _TOKEN_RE.findall(text)]


def domain_tokenize(text: str) -> list[str]:
    """Domain-aware tokenizer (parse.md §8). Drops in for `tokenize()` whenever
    multi-word terms matter. Cached vocabulary; cheap to call many times."""
    from app.services.domain_tokenizer import DomainTokenizer, get_vocabulary

    return DomainTokenizer(get_vocabulary()).tokenize(text)


class Embedder(ABC):
    backend: str

    @abstractmethod
    def fit(self, corpus: list[str]) -> "Embedder": ...

    @abstractmethod
    def encode(self, texts: list[str]) -> np.ndarray:
        """Return ndarray of shape (n_texts, dim). L2-normalized rows."""

    def similarity(self, query_emb: np.ndarray, corpus_emb: np.ndarray) -> np.ndarray:
        """Cosine similarity for normalized vectors == dot product."""
        if query_emb.ndim == 1:
            query_emb = query_emb.reshape(1, -1)
        return (query_emb @ corpus_emb.T).flatten()


class TfidfEmbedder(Embedder):
    """Pure-numpy TF-IDF. Sublinear TF + IDF + L2 normalization.

    Uses the domain-aware tokenizer by default so multi-word terms like
    "self-driving laboratory" remain a single feature.
    """

    backend = "tfidf"

    def __init__(
        self,
        min_df: int = 1,
        max_features: int | None = 4096,
        tokenizer=None,
    ) -> None:
        self.min_df = min_df
        self.max_features = max_features
        self.vocab: dict[str, int] = {}
        self.idf: np.ndarray = np.zeros(0)
        self._tokenize = tokenizer or domain_tokenize

    def fit(self, corpus: list[str]) -> "TfidfEmbedder":
        df: dict[str, int] = {}
        for text in corpus:
            for term in set(self._tokenize(text)):
                df[term] = df.get(term, 0) + 1

        filtered = [
            (term, count) for term, count in df.items() if count >= self.min_df
        ]
        filtered.sort(key=lambda kv: (-kv[1], kv[0]))
        if self.max_features:
            filtered = filtered[: self.max_features]

        n_docs = max(len(corpus), 1)
        self.vocab = {term: i for i, (term, _) in enumerate(filtered)}
        self.idf = np.array(
            [math.log((1 + n_docs) / (1 + df[term])) + 1.0 for term, _ in filtered],
            dtype=np.float32,
        )
        return self

    def encode(self, texts: list[str]) -> np.ndarray:
        if not self.vocab:
            raise RuntimeError("TfidfEmbedder.fit() must be called before encode().")
        rows: list[np.ndarray] = []
        dim = len(self.vocab)
        for text in texts:
            vec = np.zeros(dim, dtype=np.float32)
            counts: dict[int, int] = {}
            for tok in self._tokenize(text):
                idx = self.vocab.get(tok)
                if idx is None:
                    continue
                counts[idx] = counts.get(idx, 0) + 1
            for idx, count in counts.items():
                vec[idx] = (1.0 + math.log(count)) * self.idf[idx]
            norm = float(np.linalg.norm(vec))
            if norm > 0:
                vec /= norm
            rows.append(vec)
        return np.vstack(rows) if rows else np.zeros((0, dim), dtype=np.float32)


class SbertEmbedder(Embedder):
    """sentence-transformers wrapper. Loaded lazily — module-level import would
    pull in PyTorch and defeat the whole point of the optional dep."""

    backend = "sbert"

    def __init__(self, model_name: str = "all-MiniLM-L6-v2") -> None:
        self.model_name = model_name
        self._model = None

    def fit(self, corpus: list[str]) -> "SbertEmbedder":
        # sentence-transformers has nothing to fit, but we lazy-load here so a
        # failure surfaces during `build_index`, not at API request time.
        try:
            from sentence_transformers import SentenceTransformer  # type: ignore
        except ImportError as e:
            raise RuntimeError(
                "sentence-transformers is not installed. "
                "`pip install sentence-transformers` or switch PAS_EMBEDDING_BACKEND back to tfidf."
            ) from e
        self._model = SentenceTransformer(self.model_name)
        return self

    def encode(self, texts: list[str]) -> np.ndarray:
        if self._model is None:
            self.fit([])
        assert self._model is not None
        vecs = self._model.encode(texts, normalize_embeddings=True)
        return np.asarray(vecs, dtype=np.float32)


def get_embedder() -> Embedder:
    backend = os.environ.get("PAS_EMBEDDING_BACKEND", "tfidf").lower()
    if backend == "sbert":
        return SbertEmbedder(
            os.environ.get("PAS_EMBEDDING_MODEL", "all-MiniLM-L6-v2")
        )
    return TfidfEmbedder()
