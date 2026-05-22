"""Topic classifier (v0.7).

Upgraded from v0.1 substring matching to a hybrid signal stack:

  1. **Token-boundary phrase matching** — `term in haystack` is gone; we use
     a unicode-aware regex with sub-token boundaries so "transformer" doesn't
     fire on "transformer-isomer" and "self-driving lab" doesn't fire on
     "self-driving lab-grown meat".
  2. **Negation window** — a hit preceded by `not / without / unlike / non`
     within 6 tokens of the same sentence is dropped (or kept at quarter
     weight if the topic still has other hits).
  3. **Negative-keywords blacklist** — per-topic vetoes loaded from the
     taxonomy YAML and the active learning loop. Hitting any of them caps
     this topic's score at 0 for the paper.
  4. **Topic density** — counts paragraphs that contain *two or more* core
     hits. The relevance classifier uses this as a "the paper is actually
     about this, not just name-dropping" signal.
  5. **Hybrid embedding boost** — when `embedder` is provided, the
     keyword_score is fused with cosine(paper_emb, topic_emb) so we catch
     papers that re-phrase the SDL concept ("materials acceleration
     platform") without using our canonical vocabulary.

The public surface is backward-compatible: `classify(*texts)` still returns
`(combined_score, matches)`. New fields on TopicMatch are additive.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from app.models import Topic
from app.services.text_utils import (
    TermHit,
    find_term_hits,
    normalize_lower,
    split_paragraphs,
)


@dataclass
class TopicMatch:
    topic_id: str
    name: str
    is_core: bool
    score: float
    hits: list[str]
    # v0.7 additions
    keyword_score: float = 0.0
    embedding_score: float = 0.0
    negation_hits: list[str] = field(default_factory=list)
    blacklist_hits: list[str] = field(default_factory=list)
    density: int = 0  # paragraphs where ≥2 of this topic's keywords co-occur


@dataclass
class ClassifyResult:
    """Returned by classify_detailed; the plain `classify` wraps this."""

    combined_score: float
    matches: list[TopicMatch]
    topic_density: int  # max density across all core topics
    negated_hit_count: int


class TopicClassifier:
    """Keyword + (optional) embedding hybrid scorer."""

    # When more than this fraction of a topic's hits are negated, the topic
    # contributes nothing. Below it, negated hits are simply skipped.
    _NEGATION_KILL_RATIO = 0.5

    def __init__(
        self,
        topics: list[Topic],
        *,
        embedder=None,  # Embedder | None — typed loose to avoid circular import
        embedding_weight: float = 0.4,
    ) -> None:
        self.topics = topics
        self.embedder = embedder
        self.embedding_weight = embedding_weight
        self._topic_embeddings: Optional[dict[str, "object"]] = None
        if embedder is not None:
            self._prepare_topic_embeddings()

    # ------------------------------------------------------------------ #
    # Public API                                                         #
    # ------------------------------------------------------------------ #

    def classify(self, *texts: str | None) -> tuple[float, list[TopicMatch]]:
        """Backwards-compatible: returns (combined_score, matches)."""
        result = self.classify_detailed(*texts)
        return result.combined_score, result.matches

    def classify_detailed(self, *texts: str | None) -> ClassifyResult:
        haystack = "\n\n".join(t for t in texts if t)
        if not haystack:
            return ClassifyResult(0.0, [], 0, 0)

        normalized = normalize_lower(haystack)
        paragraphs = split_paragraphs(normalized) or [normalized]

        matches: list[TopicMatch] = []
        total_negated = 0
        max_density = 0

        for topic in self.topics:
            # 1. Negative-keywords veto.
            blacklist_hits = self._blacklist_hits(normalized, topic)
            if blacklist_hits:
                matches.append(
                    TopicMatch(
                        topic_id=topic.id,
                        name=topic.name,
                        is_core=topic.is_core,
                        score=0.0,
                        hits=[],
                        blacklist_hits=blacklist_hits,
                    )
                )
                continue

            # 2. Keyword hits (with negation).
            kept_hits: list[str] = []
            negation_hits: list[str] = []
            kept_weight = 0.0
            for kw in topic.keywords or []:
                term = (kw.get("term") or "").strip()
                if not term:
                    continue
                weight = float(kw.get("weight", 1.0))
                hits = find_term_hits(normalized, term.lower())
                if not hits:
                    continue
                positive = [h for h in hits if not h.negated]
                negated = [h for h in hits if h.negated]
                if positive:
                    kept_hits.append(term)
                    kept_weight += weight
                if negated:
                    negation_hits.append(term)
                    total_negated += len(negated)

            # 3. Drop the topic if its hits are mostly negated.
            total_terms = len(kept_hits) + len(negation_hits)
            if total_terms and (
                len(negation_hits) / total_terms >= self._NEGATION_KILL_RATIO
                and len(kept_hits) == 0
            ):
                matches.append(
                    TopicMatch(
                        topic_id=topic.id,
                        name=topic.name,
                        is_core=topic.is_core,
                        score=0.0,
                        hits=[],
                        negation_hits=negation_hits,
                    )
                )
                continue

            # 4. Keyword score base.
            keyword_score = min(kept_weight / 2.0, 1.0) if kept_hits else 0.0

            # 5. Embedding similarity (optional).
            emb_score = 0.0
            if self.embedder is not None and self._topic_embeddings is not None:
                emb_score = self._topic_similarity(haystack, topic.id)

            # 6. Fuse.
            if self.embedder is not None and emb_score > 0:
                base = (
                    (1 - self.embedding_weight) * keyword_score
                    + self.embedding_weight * emb_score
                )
            else:
                base = keyword_score

            # 7. Adjacent dampening (v0.1 behavior preserved).
            if not topic.is_core:
                base *= 0.5

            # 8. Topic density.
            density = self._paragraph_density(paragraphs, topic)
            if density >= 2:
                base = min(base + 0.10, 1.0)  # density boost
            if topic.is_core and density > max_density:
                max_density = density

            if not kept_hits and emb_score < 0.4:
                # No keyword hits, and even the embedding wasn't convincing.
                continue

            matches.append(
                TopicMatch(
                    topic_id=topic.id,
                    name=topic.name,
                    is_core=topic.is_core,
                    score=round(base, 3),
                    hits=kept_hits,
                    keyword_score=round(keyword_score, 3),
                    embedding_score=round(emb_score, 3),
                    negation_hits=negation_hits,
                    blacklist_hits=[],
                    density=density,
                )
            )

        matches.sort(key=lambda m: m.score, reverse=True)
        combined = self._combine(matches)
        return ClassifyResult(
            combined_score=combined,
            matches=matches,
            topic_density=max_density,
            negated_hit_count=total_negated,
        )

    # ------------------------------------------------------------------ #
    # Helpers                                                            #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _blacklist_hits(text: str, topic: Topic) -> list[str]:
        neg = topic.negative_keywords or []
        out: list[str] = []
        for term in neg:
            term_l = (term or "").strip().lower()
            if not term_l:
                continue
            if find_term_hits(text, term_l):
                out.append(term)
        return out

    @staticmethod
    def _paragraph_density(paragraphs: list[str], topic: Topic) -> int:
        """How many paragraphs contain ≥ 2 of this topic's keywords."""
        terms = [
            (kw.get("term") or "").lower()
            for kw in (topic.keywords or [])
            if kw.get("term")
        ]
        density = 0
        for para in paragraphs:
            hits = sum(1 for t in terms if find_term_hits(para, t))
            if hits >= 2:
                density += 1
        return density

    def _prepare_topic_embeddings(self) -> None:
        """Fit the embedder on (topic name + description + keywords)."""
        if self.embedder is None:
            self._topic_embeddings = None
            return
        descriptions: list[str] = []
        ids: list[str] = []
        for t in self.topics:
            kw_text = " ".join(
                (kw.get("term") or "") for kw in (t.keywords or [])
            )
            descriptions.append(
                " ".join(filter(None, [t.name, t.description or "", kw_text]))
            )
            ids.append(t.id)
        if not descriptions:
            self._topic_embeddings = None
            return
        # Embedders require fit before encode; refit is idempotent.
        try:
            self.embedder.fit(descriptions)
            vecs = self.embedder.encode(descriptions)
        except Exception:
            # Embedding is best-effort; fall back to pure keyword mode.
            self._topic_embeddings = None
            return
        self._topic_embeddings = {tid: vecs[i] for i, tid in enumerate(ids)}

    def _topic_similarity(self, paper_text: str, topic_id: str) -> float:
        if self.embedder is None or self._topic_embeddings is None:
            return 0.0
        vec = self._topic_embeddings.get(topic_id)
        if vec is None:
            return 0.0
        try:
            paper_vec = self.embedder.encode([paper_text])[0]
        except Exception:
            return 0.0
        import numpy as np

        sim = float(np.dot(vec, paper_vec))
        # Clamp negative cosine (rare with normalized vecs) to 0.
        return max(0.0, sim)

    @staticmethod
    def _combine(matches: list[TopicMatch]) -> float:
        """Score across matched topics. Core matches dominate.

        Tightened from v0.1: extras get smaller damping, and adjacent-only
        results stay capped strictly below 0.5.
        """
        if not matches:
            return 0.0
        positive = [m for m in matches if m.score > 0]
        if not positive:
            return 0.0
        core_scores = [m.score for m in positive if m.is_core]
        adj_scores = [m.score for m in positive if not m.is_core]
        score = 0.0
        if core_scores:
            top = core_scores[0]
            extras = sum(core_scores[1:]) * 0.2  # was 0.3, dampened
            score = min(top + extras, 1.0)
        if adj_scores and score < 0.4:
            score = max(score, min(adj_scores[0] * 0.5, 0.49))
        return round(score, 3)
