"""Topic drift detection.

For each year in the filtered window we build a normalized topic-frequency
vector: vector[topic_id] = (papers whose matched_topics include topic_id) /
total papers that year. Cosine similarity between adjacent years tells us
whether the corpus's research mix is moving.

A "drift event" is a year-pair whose cosine similarity drops below a
configurable threshold (default 0.7). The output also includes the top-N
topics per year so the frontend can render the year-by-year evolution.

No LLM. Pure SQL + numpy.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

import numpy as np
from sqlalchemy.orm import Session

from app.models import Paper
from app.services.analytics_service import _papers_for
from app.services.filter_spec import PaperFilter


@dataclass
class TopicShare:
    topic_id: str
    name: str
    share: float
    paper_count: int


@dataclass
class YearTopics:
    year: int
    total_papers: int
    top_topics: list[TopicShare]


@dataclass
class DriftEvent:
    """Adjacent-year similarity drop. Positive `delta` means the corpus moved
    away from its prior topic mix between `from_year` and `to_year`."""

    from_year: int
    to_year: int
    cosine_similarity: float
    new_topics: list[str]    # topics that appeared in to_year but not from_year
    faded_topics: list[str]  # topics in from_year but not in to_year


@dataclass
class VocabularySuggestion:
    """v0.7: a term the system thinks should join (or leave) a topic's
    vocabulary, surfaced for human approval rather than auto-applied."""

    topic_id: str
    topic_name: str
    suggested_term: str
    score: float
    action: str  # "add_keyword" | "add_negative_keyword"
    rationale: str


@dataclass
class DriftReport:
    per_year: list[YearTopics]
    drift_events: list[DriftEvent]
    drift_threshold: float
    vocabulary_suggestions: list[VocabularySuggestion] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.vocabulary_suggestions is None:
            self.vocabulary_suggestions = []


def _topic_vectors(
    papers: list[Paper],
) -> tuple[dict[int, dict[str, float]], dict[int, dict[str, int]], dict[str, str]]:
    """Returns (year → topic_id → share, year → topic_id → paper_count, topic_id → display name)."""
    counts: dict[int, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    paper_counts: dict[int, int] = defaultdict(int)
    names: dict[str, str] = {}

    for p in papers:
        if p.year is None or p.classification is None:
            continue
        paper_counts[p.year] += 1
        for tm in p.classification.matched_topics or []:
            if (tm.get("score") or 0) < 0.3:
                continue
            topic_id = tm.get("topic_id")
            if not topic_id:
                continue
            counts[p.year][topic_id] += 1
            names[topic_id] = tm.get("name") or topic_id

    shares: dict[int, dict[str, float]] = {}
    raw_counts: dict[int, dict[str, int]] = {}
    for year, topic_counts in counts.items():
        total = paper_counts[year] or 1
        shares[year] = {tid: c / total for tid, c in topic_counts.items()}
        raw_counts[year] = dict(topic_counts)
    return shares, raw_counts, names


def _cosine(a: dict[str, float], b: dict[str, float]) -> float:
    keys = sorted(set(a) | set(b))
    if not keys:
        return 0.0
    va = np.array([a.get(k, 0.0) for k in keys], dtype=np.float64)
    vb = np.array([b.get(k, 0.0) for k in keys], dtype=np.float64)
    na = float(np.linalg.norm(va))
    nb = float(np.linalg.norm(vb))
    if na == 0.0 or nb == 0.0:
        return 0.0
    return float(np.dot(va, vb) / (na * nb))


def build_drift_report(
    session: Session,
    filt: PaperFilter,
    *,
    drift_threshold: float = 0.7,
    top_n_per_year: int = 5,
) -> DriftReport:
    papers = _papers_for(session, filt)
    shares, raw_counts, names = _topic_vectors(papers)
    years = sorted(shares)

    per_year: list[YearTopics] = []
    for year in years:
        topic_shares = shares[year]
        topic_counts = raw_counts[year]
        ordered = sorted(
            topic_shares.items(), key=lambda kv: -kv[1]
        )[:top_n_per_year]
        per_year.append(
            YearTopics(
                year=year,
                total_papers=sum(topic_counts.values()),
                top_topics=[
                    TopicShare(
                        topic_id=tid,
                        name=names.get(tid, tid),
                        share=round(share, 4),
                        paper_count=topic_counts.get(tid, 0),
                    )
                    for tid, share in ordered
                ],
            )
        )

    drift_events: list[DriftEvent] = []
    for prev_year, next_year in zip(years, years[1:]):
        similarity = _cosine(shares[prev_year], shares[next_year])
        if similarity >= drift_threshold:
            continue
        prev_topics = set(shares[prev_year])
        next_topics = set(shares[next_year])
        drift_events.append(
            DriftEvent(
                from_year=prev_year,
                to_year=next_year,
                cosine_similarity=round(similarity, 3),
                new_topics=sorted(
                    [names.get(t, t) for t in (next_topics - prev_topics)]
                ),
                faded_topics=sorted(
                    [names.get(t, t) for t in (prev_topics - next_topics)]
                ),
            )
        )

    vocab_suggestions = _suggest_vocabulary(session, papers, drift_events)

    return DriftReport(
        per_year=per_year,
        drift_events=drift_events,
        drift_threshold=drift_threshold,
        vocabulary_suggestions=vocab_suggestions,
    )


# ---------------------------------------------------------------------------
# v0.7 #10: vocabulary suggestions
# ---------------------------------------------------------------------------


def _suggest_vocabulary(
    session: Session,
    papers: list[Paper],
    drift_events: list[DriftEvent],
) -> list[VocabularySuggestion]:
    """When the corpus drifts, surface candidate new keywords for review.

    Strategy: for each drift event, pick papers from the `to_year` whose
    classification matched the topic that *appears* in next_year (so they
    survived the keyword check), and compute the top distinctive bigrams
    relative to the `from_year` cohort. Those bigrams become 'add_keyword'
    suggestions for the topics whose share grew.

    The suggestions are NOT auto-applied — they go through reviewers (and
    the active learning loop will accept them by appending to the YAML).
    """
    from collections import Counter
    from app.models import Topic

    suggestions: list[VocabularySuggestion] = []
    if not drift_events:
        return suggestions

    # Map paper → year + matched core topic ids
    paper_topic_yearly: dict[int, dict[str, list[Paper]]] = defaultdict(
        lambda: defaultdict(list)
    )
    for p in papers:
        if p.year is None or p.classification is None:
            continue
        for tm in p.classification.matched_topics or []:
            if not tm.get("is_core") or (tm.get("score") or 0) < 0.3:
                continue
            paper_topic_yearly[p.year][tm.get("topic_id")].append(p)

    topics_by_id = {
        t.id: t for t in session.execute(__import__("sqlalchemy").select(Topic)).scalars()
    }

    for event in drift_events:
        # For each topic whose share grew in to_year, compute TF-IDF-ish
        # distinctive bigrams.
        to_papers_by_topic = paper_topic_yearly.get(event.to_year) or {}
        from_papers_by_topic = paper_topic_yearly.get(event.from_year) or {}
        for topic_id, to_ps in to_papers_by_topic.items():
            topic = topics_by_id.get(topic_id)
            if topic is None or not topic.is_core:
                continue
            # Build "to-year word counter" and "from-year word counter".
            to_text = " ".join(
                f"{p.title or ''} {p.abstract or ''}" for p in to_ps
            ).lower()
            from_text = " ".join(
                f"{p.title or ''} {p.abstract or ''}"
                for p in (from_papers_by_topic.get(topic_id) or [])
            ).lower()

            new_bigrams = _distinctive_bigrams(
                to_text, from_text, existing_terms={
                    (kw.get("term") or "").lower()
                    for kw in (topic.keywords or [])
                },
            )
            for bg, score in new_bigrams[:3]:
                suggestions.append(
                    VocabularySuggestion(
                        topic_id=topic_id,
                        topic_name=topic.name,
                        suggested_term=bg,
                        score=round(score, 3),
                        action="add_keyword",
                        rationale=(
                            f"Bigram appeared {score:.0f}x more often in "
                            f"{event.to_year} papers than {event.from_year} "
                            f"papers matching this topic."
                        ),
                    )
                )
    return suggestions


_BIGRAM_RE = __import__("re").compile(r"[a-z][a-z0-9\-]{2,}")
_BG_STOP = {
    "the", "of", "and", "for", "with", "this", "that", "from",
    "we", "our", "are", "has", "have", "was", "were", "been",
    "all", "their", "they", "them", "its", "his", "her", "into",
    "such", "than", "then", "also", "more", "most", "other", "via",
    "use", "using", "used", "based", "many", "some", "each", "any",
}


def _distinctive_bigrams(
    to_text: str, from_text: str, *, existing_terms: set[str]
) -> list[tuple[str, float]]:
    from collections import Counter

    def _bigrams(text: str) -> Counter:
        toks = [t for t in _BIGRAM_RE.findall(text) if t not in _BG_STOP]
        return Counter(f"{a} {b}" for a, b in zip(toks, toks[1:]))

    to_c = _bigrams(to_text)
    from_c = _bigrams(from_text)
    # Build a word-level index of existing terms so reversed bigrams like
    # "lab self-driving" of an existing "self-driving lab" are skipped.
    existing_word_pairs: set[frozenset] = set()
    for term in existing_terms:
        toks = _BIGRAM_RE.findall(term)
        if len(toks) >= 2:
            existing_word_pairs.add(frozenset(toks[:2]))
    out: list[tuple[str, float]] = []
    for bg, to_freq in to_c.items():
        if any(bg in t or t in bg for t in existing_terms):
            continue
        bg_tokens = bg.split()
        if len(bg_tokens) == 2 and frozenset(bg_tokens) in existing_word_pairs:
            continue
        from_freq = from_c.get(bg, 0)
        score = to_freq - 0.5 * from_freq
        if score >= 2:
            out.append((bg, float(score)))
    out.sort(key=lambda kv: -kv[1])
    return out
