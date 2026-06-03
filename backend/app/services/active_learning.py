"""Active learning loop (v0.7).

Triggered by `submit_review` whenever a reviewer rejects or corrects a label.
The loop does three things, all idempotent:

  1. **Negative-keyword harvest** — if a reviewer reclassifies CORE/RELATED
     down to EXCLUDE/ADJACENT, the abstract's top distinguishing n-grams
     (the ones that survive after the AC vocabulary is removed) become
     negative_keywords on the topic the system *thought* it matched. This
     mirrors how a human reviewer adds vetoed phrases.

  2. **Eval label append** — the corrected label is appended to
     `data/eval_labels.csv` so the next `run_eval` and the next training
     run pick it up.

  3. **Retrain hook** — when the human_reviews table accumulates N new
     rows since the last train (default 5), `maybe_retrain` writes a fresh
     learned_classifier.joblib. This keeps the loop self-driving without
     a separate cron job.

Everything here is best-effort; failures log and continue, because review
submission must never be blocked by training-side issues.

`mine_positive_vocabulary` is a separate, read-only function that scans the
AC Publications gold set (ac_known_publication=True) for vocabulary gaps and
surfaces candidates via VocabularySuggestion — it never writes to YAML.
"""
from __future__ import annotations

import os
import re
from collections import Counter
from pathlib import Path
from typing import Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.models import HumanReview, Paper, Topic

# ---------------------------------------------------------------------------
# Triggering
# ---------------------------------------------------------------------------


def _retrain_every_n_reviews() -> int:
    return max(1, int(os.environ.get("PAS_ACTIVE_RETRAIN_EVERY", "10")))


def on_review_submitted(
    session: Session,
    paper_id: str,
    *,
    new_label: str,
    previous_label: str | None = None,
    reviewer: str | None = None,
) -> dict:
    """Main entry point. Called by the review API after persisting the review.

    Returns a small audit dict so callers can surface what happened in the
    response (and tests can assert on it).
    """
    actions: dict[str, list[str]] = {
        "negative_keywords_added": [],
        "eval_labels_updated": [],
        "retrained": [],
        "classification_locked": [],
        "warnings": [],
    }

    paper = session.get(Paper, paper_id)
    if paper is None:
        actions["warnings"].append(f"paper {paper_id} not found")
        return actions

    # 1. Negative-keyword harvest on a downgrade.
    if previous_label and _is_downgrade(previous_label, new_label):
        try:
            added = _harvest_negative_keywords(session, paper, previous_label)
            actions["negative_keywords_added"] = added
        except Exception as e:
            actions["warnings"].append(f"harvest failed: {e}")

    # 2. Append to eval_labels.csv.
    try:
        _append_eval_label(paper_id, new_label, reviewer=reviewer)
        actions["eval_labels_updated"].append(paper_id)
    except Exception as e:
        actions["warnings"].append(f"eval append failed: {e}")

    # 3. Lock the classification + clear from review queue.
    try:
        from datetime import UTC, datetime

        if paper.classification is not None:
            paper.classification.label = new_label.upper()
            paper.classification.human_confirmed = True
            paper.classification.human_confirmed_by = reviewer
            paper.classification.human_confirmed_at = datetime.now(UTC)
            paper.classification.needs_review = False
            paper.classification.review_priority = 0.0
            session.commit()
            actions["classification_locked"].append(paper_id)
    except Exception as e:
        actions["warnings"].append(f"lock failed: {e}")

    # 4. Maybe retrain.
    try:
        retrained = maybe_retrain(session)
        if retrained:
            actions["retrained"].append(retrained)
    except Exception as e:
        actions["warnings"].append(f"retrain failed: {e}")

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


def _append_eval_label(
    paper_id: str, label: str, *, reviewer: str | None
) -> None:
    """Idempotently upsert the row in eval_labels.csv."""
    path = Path(settings.eval_labels_csv)
    if not path.exists():
        # Create header if missing.
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            "paper_id,gold_label,gold_topics,notes\n", encoding="utf-8"
        )

    lines = path.read_text(encoding="utf-8").splitlines()
    if not lines:
        lines = ["paper_id,gold_label,gold_topics,notes"]
    header = lines[0]
    new_lines = [header]
    found = False
    for row in lines[1:]:
        cols = row.split(",", 3)
        if cols and cols[0].strip() == paper_id:
            note = f"reviewer:{reviewer}" if reviewer else "reviewer"
            new_lines.append(
                f"{paper_id},{label},,{note}"
            )
            found = True
        else:
            new_lines.append(row)
    if not found:
        note = f"reviewer:{reviewer}" if reviewer else "reviewer"
        new_lines.append(f"{paper_id},{label},,{note}")
    path.write_text("\n".join(new_lines) + "\n", encoding="utf-8")


def maybe_retrain(session: Session) -> str | None:
    """Retrain when reviewer activity has accumulated enough new examples.

    Returns the path of the new model or None.
    """
    n_reviews = session.scalar(select(_count_reviews()))
    if n_reviews is None:
        return None
    # Crude trigger: every N reviews, retrain. Idempotent in the sense that
    # we always re-train from scratch on the full set.
    if n_reviews == 0 or n_reviews % _retrain_every_n_reviews() != 0:
        return None
    try:
        from app.services.learned_classifier import (
            build_training_set,
            save_model,
            train_from_examples,
        )

        examples = build_training_set(session)
        if len(examples) < 4:
            return None
        clf = train_from_examples(examples)
        out = save_model(clf)
        return str(out)
    except Exception:
        return None


def _count_reviews():
    """select count(*) from human_reviews — broken out to make tests easy."""
    from sqlalchemy import func

    return func.count(HumanReview.id)


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
