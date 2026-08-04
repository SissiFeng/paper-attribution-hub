"""Active learning loop (v0.7).

Triggered by `submit_review` whenever a reviewer rejects or corrects a label.
The learning portion does two things, both idempotent:

  1. **Optional negative-keyword harvest** — retained for explicitly enabled
     experiments, but off by default because taxonomy mutations do not pass
     the candidate-model promotion gate.

  2. **Retrain hook** — every 20 distinct, eligible reviewed papers become an
     immutable trigger batch. A separate worker retrains the complete model,
     evaluates it out-of-fold (plus dedicated validation when available), and
     retains a passing candidate for shadow evaluation. Production promotion
     is a separate, explicitly enabled authority boundary.

The persisted `human_reviews` row is production feedback and may feed model
training. It never mutates the frozen evaluation holdout.

The review transaction records feedback when the evaluation boundary is
available. A scheduled reconciliation pass backfills any eligible review that
could not be recorded at response time.

`mine_positive_vocabulary` is a separate, read-only function that scans the
AC Publications gold set (ac_known_publication=True) for vocabulary gaps and
surfaces candidates via VocabularySuggestion — it never writes to YAML.
"""
from __future__ import annotations

import os
import re
from collections import Counter

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.label_dataset import load_reserved_evaluation_ids
from app.models import HumanReview, Paper, Topic

def on_review_submitted(
    session: Session,
    paper_id: str,
    *,
    new_label: str,
    previous_label: str | None = None,
    reviewer: str | None = None,
    run_retraining: bool = True,
    commit: bool = True,
) -> dict:
    """Main entry point. Called by the review API after persisting the review.

    Returns a small audit dict so callers can surface what happened in the
    response (and tests can assert on it).
    """
    actions: dict[str, list[str]] = {
        "negative_keywords_added": [],
        "training_feedback_recorded": [],
        "retrained": [],
        "training_runs": [],
        "classification_locked": [],
        "warnings": [],
    }

    paper = session.get(Paper, paper_id)
    if paper is None:
        actions["warnings"].append(f"paper {paper_id} not found")
        return actions

    learning_allowed = False
    evaluation_boundary_available = False
    try:
        reserved_paper_ids = load_reserved_evaluation_ids(
            validation_path=settings.validation_labels_csv,
            holdout_path=settings.eval_labels_csv,
        )
        evaluation_boundary_available = True
        learning_allowed = paper_id not in reserved_paper_ids
    except Exception as e:
        actions["warnings"].append(
            f"automatic learning skipped: evaluation boundary unavailable ({e})"
        )

    review = session.execute(
        select(HumanReview).where(HumanReview.paper_id == paper_id)
    ).scalar_one_or_none()
    if learning_allowed:
        if review is None:
            actions["warnings"].append(
                "training feedback not recorded: human review row is missing"
            )
        else:
            try:
                from app.services.model_evolution import (
                    record_training_feedback,
                )

                event = record_training_feedback(
                    session,
                    paper_id=paper_id,
                    review_id=review.id,
                    human_label=new_label,
                    reviewer=reviewer,
                    incumbent_label=(
                        paper.classification.label
                        if paper.classification is not None
                        else previous_label
                    ),
                    incumbent_confidence=(
                        paper.classification.confidence
                        if paper.classification is not None
                        else None
                    ),
                    commit=False,
                )
                if event is not None:
                    actions["training_feedback_recorded"].append(paper_id)
            except Exception as e:
                actions["warnings"].append(
                    f"training feedback event failed: {e}"
                )
    elif evaluation_boundary_available:
        actions["warnings"].append(
            "automatic learning skipped for validation or holdout paper"
        )

    # 1. Negative-keyword harvest on a downgrade.
    if (
        learning_allowed
        and os.environ.get("PAS_ACTIVE_KEYWORD_HARVEST", "0") == "1"
        and previous_label
        and _is_downgrade(previous_label, new_label)
    ):
        try:
            added = _harvest_negative_keywords(session, paper, previous_label)
            actions["negative_keywords_added"] = added
        except Exception as e:
            actions["warnings"].append(f"harvest failed: {e}")

    # 2. Lock the classification + clear from review queue.
    try:
        from datetime import UTC, datetime

        if paper.classification is not None:
            paper.classification.label = new_label.upper()
            paper.classification.human_confirmed = True
            paper.classification.human_confirmed_by = reviewer
            paper.classification.human_confirmed_at = datetime.now(UTC)
            paper.classification.needs_review = False
            paper.classification.review_priority = 0.0
            session.flush()
            actions["classification_locked"].append(paper_id)
    except Exception as e:
        actions["warnings"].append(f"lock failed: {e}")

    # 3. Maybe retrain.
    if learning_allowed and run_retraining:
        try:
            retrained = maybe_retrain(session)
            if retrained:
                actions["training_runs"].append(retrained.id)
                if retrained.status == "PROMOTED":
                    actions["retrained"].append(
                        retrained.model_version or retrained.id
                    )
        except Exception as e:
            actions["warnings"].append(f"retrain failed: {e}")

    if commit:
        session.commit()
    else:
        session.flush()

    return actions


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


_LABEL_RANK = {
    "CORE_RELEVANT": 4,
    "RELATED_RELEVANT": 3,
    "ADJACENT": 2,
    "UNCERTAIN": 1,
    "EXCLUDE": 0,
    "INCLUDE": 3,  # treat reviewer "INCLUDE" as RELATED for ranking
}


def _is_downgrade(prev_label: str, new_label: str) -> bool:
    return _LABEL_RANK.get(prev_label.upper(), 0) > _LABEL_RANK.get(
        new_label.upper(), 0
    )


_WORD_RE = re.compile(r"[A-Za-z][A-Za-z0-9\-]{2,}")
_STOPWORDS = {
    "the", "of", "and", "for", "with", "this", "that", "from", "we",
    "our", "are", "has", "have", "was", "were", "been", "being",
    "all", "their", "they", "them", "its", "his", "her", "into",
    "such", "than", "then", "also", "more", "most", "other", "via",
    "use", "using", "used", "based", "many", "some", "each", "any",
    "show", "shown", "shows", "found", "find", "between", "across",
    "paper", "work", "study", "method", "results", "results.",
    "abstract", "introduction", "conclusion", "experiment", "experiments",
    "approach", "approaches", "data", "dataset", "datasets",
}


def _harvest_negative_keywords(
    session: Session,
    paper: Paper,
    previous_label: str,
) -> list[str]:
    """Extract the abstract's most distinctive bigrams and add them as
    negative_keywords to whichever core topic the classifier matched."""
    text = " ".join(filter(None, [paper.title or "", paper.abstract or ""]))
    if not text or paper.classification is None:
        return []
    matched = paper.classification.matched_topics or []
    # Target the highest-scoring core topic — that's the one that probably
    # triggered the (now-rejected) classification.
    core = [m for m in matched if m.get("is_core") and m.get("score", 0) > 0]
    if not core:
        return []
    target = max(core, key=lambda m: m.get("score", 0))
    target_topic_id = target.get("topic_id")
    if not target_topic_id:
        return []
    topic = session.get(Topic, target_topic_id)
    if topic is None:
        return []

    # Filter out the AC vocabulary already in this topic so we don't blacklist
    # legitimate vocabulary.
    existing_terms = {
        (kw.get("term") or "").lower()
        for kw in (topic.keywords or [])
    }

    tokens = [t.lower() for t in _WORD_RE.findall(text)]
    tokens = [t for t in tokens if t not in _STOPWORDS]
    bigrams = [
        f"{a} {b}"
        for a, b in zip(tokens, tokens[1:])
        if a not in _STOPWORDS and b not in _STOPWORDS
    ]
    # Score bigrams: frequency in this paper minus frequency in topic's
    # existing keyword vocabulary.
    counter = Counter(bigrams)
    # Drop any that are substrings of existing topic keywords.
    candidates = [
        (bg, count)
        for bg, count in counter.most_common(20)
        if not any(bg in t or t in bg for t in existing_terms)
    ]
    # Cap to top 3 to avoid runaway taxonomy growth.
    top3 = [bg for bg, _ in candidates[:3]]
    if not top3:
        return []

    current_neg = list(topic.negative_keywords or [])
    additions = [
        bg for bg in top3 if bg not in current_neg and bg not in existing_terms
    ]
    if not additions:
        return []
    topic.negative_keywords = current_neg + additions
    session.flush()
    return additions


def maybe_retrain(session: Session):
    """Run one claimed model-evolution batch, if the threshold was reached."""
    from app.services.model_evolution import maybe_run_model_evolution

    return maybe_run_model_evolution(session)


# ---------------------------------------------------------------------------
# Bulk re-classify after taxonomy update
# ---------------------------------------------------------------------------


def reclassify_after_review(session: Session) -> int:
    """Re-run classify_all so the updated negative_keywords / model take
    effect immediately. Returns the number of papers re-labeled."""
    from app.services.relevance_classifier import classify_all

    papers = classify_all(session)
    return len(papers)


# ---------------------------------------------------------------------------
# Positive-vocabulary mining
# ---------------------------------------------------------------------------


def mine_positive_vocabulary(
    session: Session,
    *,
    max_suggestions: int = 20,
    min_positive_freq: int = 3,
    background_sample: int = 500,
) -> list:
    """Mine AC gold-set abstracts for vocabulary gaps.

    Compares ac_known_publication=True papers against a background sample to
    surface bigrams that are:
      - Distinctive to AC papers AND high absolute frequency
        → action "add_protected_phrase" (keep as single BM25 token)
      - Distinctive but lower frequency
        → action "add_keyword" (candidate for topic_taxonomy.yaml)

    Returns list[VocabularySuggestion] for human approval.
    Does NOT write to domain_vocabulary.yaml or topic_taxonomy.yaml.
    """
    from app.services.drift_service import VocabularySuggestion, _distinctive_bigrams

    pos_rows = session.execute(
        select(Paper.title, Paper.abstract).where(Paper.ac_known_publication.is_(True))
    ).all()
    if not pos_rows:
        return []

    bg_rows = session.execute(
        select(Paper.title, Paper.abstract)
        .where(Paper.ac_known_publication.is_(False))
        .limit(background_sample)
    ).all()

    pos_text = " ".join(f"{t or ''} {a or ''}" for t, a in pos_rows).lower()
    bg_text = " ".join(f"{t or ''} {a or ''}" for t, a in bg_rows).lower()

    # Build the set of already-known terms so we never re-suggest them.
    vocab = _get_vocab_terms()
    topics = session.execute(select(Topic)).scalars().all()
    for t in topics:
        for kw in t.keywords or []:
            vocab.add((kw.get("term") or "").lower())
        for neg in t.negative_keywords or []:
            vocab.add(neg.lower())

    candidates = _distinctive_bigrams(pos_text, bg_text, existing_terms=vocab)
    if not candidates:
        return []

    # Absolute bigram frequency in positive corpus (for protected_phrase decision).
    pos_tokens = [tok for tok in _WORD_RE.findall(pos_text) if tok not in _STOPWORDS]
    pos_bigram_freq: Counter = Counter(
        f"{a} {b}" for a, b in zip(pos_tokens, pos_tokens[1:])
    )

    suggestions = []
    for term, score in candidates[:max_suggestions]:
        abs_freq = pos_bigram_freq.get(term, 0)
        topic_id, topic_name = _best_topic_match(term, topics)
        if abs_freq >= min_positive_freq:
            action = "add_protected_phrase"
            rationale = (
                f"Appears {abs_freq}× in AC gold-set abstracts "
                f"(distinctiveness {score:.1f} vs background). "
                "Protecting as a phrase token prevents BM25 from splitting it."
            )
        else:
            action = "add_keyword"
            rationale = (
                f"Distinctive to AC gold-set (score {score:.1f}); "
                f"absolute frequency {abs_freq} — review before adding."
            )
        suggestions.append(
            VocabularySuggestion(
                topic_id=topic_id,
                topic_name=topic_name,
                suggested_term=term,
                score=round(score, 3),
                action=action,
                rationale=rationale,
            )
        )

    return suggestions


def _get_vocab_terms() -> set:
    """Return all terms already in domain_vocabulary.yaml as a flat set."""
    from app.services.domain_tokenizer import get_vocabulary

    vocab = get_vocabulary()
    terms: set[str] = set()
    for p in vocab.protected:
        terms.add(p.lower())
    for src, dst in vocab.synonyms.items():
        terms.add(src.lower())
        terms.add(dst.lower())
    return terms


def _best_topic_match(term: str, topics) -> tuple[str, str]:
    """Return (topic_id, topic_name) for the core topic whose keyword tokens
    most overlap with the candidate term's tokens.  Falls back to a sentinel
    when no match is found."""
    term_tokens = set(term.split())
    best_id, best_name, best_overlap = "__vocabulary__", "domain_vocabulary", 0
    for t in topics:
        if not t.is_core:
            continue
        kw_tokens = {
            tok
            for kw in (t.keywords or [])
            for tok in (kw.get("term") or "").lower().split()
        }
        overlap = len(term_tokens & kw_tokens)
        if overlap > best_overlap:
            best_overlap, best_id, best_name = overlap, t.id, t.name
    return best_id, best_name
