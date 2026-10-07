"""Hybrid retrieval over paper chunks.

Pipeline:
  1. Pre-filter chunks by metadata (paper_id / section_type / year).
  2. BM25 keyword score (top 50).
  3. Cosine vector score (top 50).
  4. RRF fusion, then graph-centrality re-ranking boost.
  5. Return top-k as `RetrievedChunk`.

Graph-centrality boost (Point 1): each paper's composite graph importance
  (PPR network_score + citation_score + bridge_score) is loaded at index-build
  time and used to multiply the RRF score so AC-central papers surface higher.

Proposition-first channel (Point 2): `search_propositions()` + `is_structured_query()`
  let callers skip chunk search for method/funding/structured queries.
"""
from __future__ import annotations

import math
from collections.abc import Iterable
from dataclasses import dataclass

import numpy as np
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Paper, PaperChunk
from app.services.embedding_service import Embedder, domain_tokenize as tokenize

# How much graph centrality boosts text-relevance score.
# 0 = pure text; higher values weight central papers more.
_GRAPH_WEIGHT = 0.3

# Verb/noun signals that indicate a structured (proposition-answerable) query.
_STRUCTURED_SIGNALS = {
    "use", "uses", "method", "technique", "approach", "funded", "funding",
    "grant", "mechanism", "employs", "implements", "developed",
    "proposed", "built on", "based on", "platform", "domain", "autonomy",
    "automation", "failure", "limitation", "constraint",
}


@dataclass
class IndexedChunk:
    chunk_id: str
    paper_id: str
    section_type: str
    section_title: str | None
    text: str
    # Contextually-prefixed text used by BM25 + embedding. Falls back to
    # `text` for pre-v0.4 chunks that didn't have it populated.
    indexed_text: str
    tokens: list[str]
    embedding: np.ndarray
    year: int | None


@dataclass
class RetrievedChunk:
    chunk_id: str
    paper_id: str
    section_type: str
    section_title: str | None
    text: str
    bm25_score: float
    cosine_score: float
    score: float
    graph_score: float = 0.0  # composite graph importance used in re-ranking


@dataclass
class PropositionHit:
    paper_id: str
    predicate: str
    object_value: str
    claim_text: str
    confidence: float
    source_section: str | None
    score: float  # search relevance score


class HybridIndex:
    def __init__(
        self,
        chunks: list[IndexedChunk],
        embedder: Embedder,
        bm25_k1: float = 1.5,
        bm25_b: float = 0.75,
        graph_scores: dict[str, float] | None = None,
    ) -> None:
        self.chunks = chunks
        self.embedder = embedder
        self.k1 = bm25_k1
        self.b = bm25_b
        # paper_id → composite graph importance (0–1 after normalisation)
        self.graph_scores: dict[str, float] = graph_scores or {}

        self.embeddings = (
            np.vstack([c.embedding for c in chunks])
            if chunks
            else np.zeros((0, 1), dtype=np.float32)
        )

        # BM25 statistics.
        self.doc_lens = np.array([len(c.tokens) for c in chunks], dtype=np.float32)
        self.avg_len = float(self.doc_lens.mean()) if len(chunks) else 0.0
        self.df: dict[str, int] = {}
        for c in chunks:
            for term in set(c.tokens):
                self.df[term] = self.df.get(term, 0) + 1
        self.n_docs = len(chunks)

    @classmethod
    def from_session(
        cls,
        session: Session,
        embedder: Embedder,
        max_chunks: int | None = 2000,
        load_graph_scores: bool = False,
    ) -> "HybridIndex":
        # Graph scores are expensive (loads ALL PaperClassification rows).
        # Disabled by default to keep index memory bounded.
        graph_scores: dict[str, float] = {}
        if load_graph_scores:
            from app.models import PaperClassification
            raw: dict[str, float] = {}
            for pid, net, cit, gs in session.execute(
                select(
                    PaperClassification.paper_id,
                    PaperClassification.network_score,
                    PaperClassification.citation_score,
                    PaperClassification.graph_signals,
                )
            ).all():
                bridge = float((gs or {}).get("bridge_score", 0.0))
                raw[pid] = float(net or 0) + 0.5 * float(cit or 0) + 0.3 * bridge
            if raw:
                mx = max(raw.values()) or 1.0
                graph_scores = {pid: v / mx for pid, v in raw.items()}

        chunk_statement = (
            select(PaperChunk, Paper.year)
            .join(Paper, Paper.id == PaperChunk.paper_id)
            .order_by(PaperChunk.created_at.desc())
        )
        if max_chunks is not None:
            chunk_statement = chunk_statement.limit(max_chunks)
        rows = session.execute(chunk_statement).all()
        # Refit the embedder on the exact corpus we'll query against
        # (`indexed_text` for v0.4 chunks, `chunk_text` otherwise). Stored
        # vectors are recomputed in this fit-space so query vectors line up
        # dimensionally — callers don't need to remember to refit.
        index_corpus = [
            (chunk.indexed_text or chunk.chunk_text) for chunk, _ in rows
        ]
        if index_corpus:
            embedder.fit(index_corpus)
            refit_matrix = embedder.encode(index_corpus)
        else:
            refit_matrix = None
        chunks: list[IndexedChunk] = []
        for idx, (chunk, year) in enumerate(rows):
            if refit_matrix is not None:
                emb = refit_matrix[idx]
            elif chunk.embedding is not None:
                emb = np.asarray(chunk.embedding, dtype=np.float32)
            else:
                emb = np.zeros(1, dtype=np.float32)
            indexed_text = chunk.indexed_text or chunk.chunk_text
            chunks.append(
                IndexedChunk(
                    chunk_id=chunk.id,
                    paper_id=chunk.paper_id,
                    section_type=chunk.section_type,
                    section_title=(chunk.chunk_metadata or {}).get("section_title"),
                    text=chunk.chunk_text,
                    indexed_text=indexed_text,
                    tokens=tokenize(indexed_text),
                    embedding=emb,
                    year=year,
                )
            )
        return cls(chunks=chunks, embedder=embedder, graph_scores=graph_scores)

    def _bm25(
        self,
        query_tokens: list[str],
        candidate_indices: Iterable[int],
    ) -> np.ndarray:
        scores = np.zeros(len(self.chunks), dtype=np.float32)
        if not query_tokens or self.n_docs == 0:
            return scores
        idx_arr = np.fromiter(candidate_indices, dtype=np.int64)
        if idx_arr.size == 0:
            return scores
        for term in set(query_tokens):
            df = self.df.get(term, 0)
            if df == 0:
                continue
            idf = math.log((self.n_docs - df + 0.5) / (df + 0.5) + 1.0)
            for i in idx_arr:
                tf = sum(1 for tok in self.chunks[i].tokens if tok == term)
                if tf == 0:
                    continue
                dl = self.doc_lens[i]
                denom = tf + self.k1 * (
                    1 - self.b + self.b * (dl / (self.avg_len or 1.0))
                )
                scores[i] += idf * ((tf * (self.k1 + 1)) / max(denom, 1e-6))
        return scores

    def search(
        self,
        query: str,
        *,
        paper_ids: Iterable[str] | None = None,
        section_types: Iterable[str] | None = None,
        year_range: tuple[int | None, int | None] | None = None,
        top_k: int = 10,
        alpha: float = 0.5,
    ) -> list[RetrievedChunk]:
        if not self.chunks:
            return []

        paper_filter = set(paper_ids) if paper_ids else None
        section_filter = set(section_types) if section_types else None
        year_lo = year_range[0] if year_range else None
        year_hi = year_range[1] if year_range else None

        candidate_indices: list[int] = []
        for i, c in enumerate(self.chunks):
            if paper_filter and c.paper_id not in paper_filter:
                continue
            if section_filter and c.section_type not in section_filter:
                continue
            if year_lo is not None and (c.year is None or c.year < year_lo):
                continue
            if year_hi is not None and (c.year is None or c.year > year_hi):
                continue
            candidate_indices.append(i)
        if not candidate_indices:
            return []

        query_tokens = tokenize(query)
        bm25_scores = self._bm25(query_tokens, candidate_indices)

        query_emb = self.embedder.encode([query])
        cos = self.embedder.similarity(query_emb, self.embeddings)

        cand = np.array(candidate_indices, dtype=np.int64)
        bm25_local = bm25_scores[cand]
        cos_local = cos[cand]

        # Reciprocal Rank Fusion — more robust than linear blend when score
        # distributions differ in magnitude between BM25 and cosine.
        # RRF(d) = 1/(k + rank_bm25(d)) + 1/(k + rank_cosine(d)), k=60 standard.
        rrf_k = 60
        bm25_order = np.argsort(-bm25_local)
        cos_order = np.argsort(-cos_local)
        bm25_ranks = np.empty_like(bm25_order)
        bm25_ranks[bm25_order] = np.arange(len(bm25_order))
        cos_ranks = np.empty_like(cos_order)
        cos_ranks[cos_order] = np.arange(len(cos_order))
        rrf_scores = 1.0 / (rrf_k + bm25_ranks) + 1.0 / (rrf_k + cos_ranks)

        # Also compute legacy linear blend for callers that want it.
        bm25_norm = bm25_local / (bm25_local.max() if bm25_local.max() > 0 else 1.0)
        cos_norm = np.clip(cos_local, 0.0, 1.0)
        blended = alpha * bm25_norm + (1.0 - alpha) * cos_norm

        # RRF is default; fall back to linear blend only when alpha=1.0 (BM25-only).
        final_scores = rrf_scores if alpha != 1.0 else blended

        # Graph-centrality re-ranking boost.
        # Multiplier: 1 + GRAPH_WEIGHT * normalised_importance keeps text-weak
        # papers from being buried entirely; it surfaces AC-central papers above
        # equally-relevant but peripheral ones.
        graph_importance = np.array(
            [self.graph_scores.get(self.chunks[int(cand[j])].paper_id, 0.0)
             for j in range(len(cand))],
            dtype=np.float32,
        )
        final_scores = final_scores * (1.0 + _GRAPH_WEIGHT * graph_importance)

        order = np.argsort(-final_scores)[:top_k]
        out: list[RetrievedChunk] = []
        for rel_idx in order:
            i = int(cand[rel_idx])
            c = self.chunks[i]
            out.append(
                RetrievedChunk(
                    chunk_id=c.chunk_id,
                    paper_id=c.paper_id,
                    section_type=c.section_type,
                    section_title=c.section_title,
                    text=c.text,
                    bm25_score=float(bm25_local[rel_idx]),
                    cosine_score=float(cos_local[rel_idx]),
                    score=float(final_scores[rel_idx]),
                    graph_score=float(graph_importance[rel_idx]),
                )
            )
        return out


# ---------------------------------------------------------------------------
# Point 2: Proposition-first retrieval
# ---------------------------------------------------------------------------

def is_structured_query(query: str) -> bool:
    """Heuristic: does this query ask about methods, funding, or mechanisms?"""
    q = query.lower()
    return any(signal in q for signal in _STRUCTURED_SIGNALS)


def search_propositions(
    session: Session,
    query: str,
    *,
    top_k: int = 5,
    predicates: list[str] | None = None,
) -> list[PropositionHit]:
    """Keyword search over PaperProposition records.

    Useful for structured queries like "which papers use Bayesian optimization?"
    Returns propositions ranked by token overlap × confidence.
    """
    from app.models import PaperProposition

    query_tokens = set(tokenize(query))
    stmt = select(PaperProposition)
    if predicates:
        stmt = stmt.where(PaperProposition.predicate.in_(predicates))

    scored: list[tuple[float, PaperProposition]] = []
    for prop in session.execute(stmt).scalars():
        text = f"{prop.predicate} {prop.object_value} {prop.claim_text}"
        text_tokens = set(tokenize(text))
        hits = len(query_tokens & text_tokens)
        if hits == 0:
            continue
        score = (hits / max(len(query_tokens), 1)) * float(prop.confidence)
        scored.append((score, prop))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [
        PropositionHit(
            paper_id=prop.paper_id,
            predicate=prop.predicate,
            object_value=prop.object_value,
            claim_text=prop.claim_text,
            confidence=float(prop.confidence),
            source_section=prop.source_section,
            score=score,
        )
        for score, prop in scored[:top_k]
    ]
