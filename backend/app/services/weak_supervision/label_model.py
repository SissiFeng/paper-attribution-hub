"""A lightweight, interpretable weak-supervision label model.

Each labeling function (LF) votes POSITIVE / NEGATIVE / ABSTAIN. The model
learns each LF's reliability from how often it agrees with the weighted
consensus (an agreement-based EM, the Dawid-Skene / Snorkel intuition), then
produces a probabilistic label. Votes that share a ``provenance_key`` are
deduplicated first so correlated sources (e.g. OpenAlex + Unpaywall both
echoing one Crossref record) count once.

Not modeled yet: correlation between LFs beyond source dedup. Documented as a
follow-up; do not treat the learned weights as fully decorrelated.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

POSITIVE = "POSITIVE"
NEGATIVE = "NEGATIVE"
ABSTAIN = "ABSTAIN"

_VOTE_VALUE = {POSITIVE: 1.0, NEGATIVE: -1.0, ABSTAIN: 0.0}
_MIN_ACC = 0.55  # floor so an LF never gets negative/zero log-odds weight
_MAX_ACC = 0.99
_DEFAULT_ACC = 0.7


@dataclass(frozen=True)
class LFVote:
    lf_name: str
    vote: str
    provenance_key: str | None = None


@dataclass(frozen=True)
class LabelModelResult:
    label: str
    prob_positive: float
    confidence: float
    contributing_lf_count: int
    lf_weights: dict[str, float] = field(default_factory=dict)


def dedup_votes(votes: list[LFVote]) -> list[LFVote]:
    """Collapse votes that share a non-null provenance_key to a single vote."""
    seen: set[str] = set()
    out: list[LFVote] = []
    for vote in votes:
        key = vote.provenance_key
        if key is not None:
            if key in seen:
                continue
            seen.add(key)
        out.append(vote)
    return out


def _acc_to_weight(acc: float) -> float:
    acc = min(_MAX_ACC, max(_MIN_ACC, acc))
    return math.log(acc / (1.0 - acc))


class LabelModel:
    def __init__(self, max_iter: int = 20) -> None:
        self._max_iter = max_iter
        self._weights: dict[str, float] = {}

    def weight(self, lf_name: str) -> float:
        return self._weights.get(lf_name, _acc_to_weight(_DEFAULT_ACC))

    def _consensus_value(self, votes: list[LFVote], weights: dict[str, float]) -> float:
        return sum(
            weights.get(v.lf_name, _acc_to_weight(_DEFAULT_ACC)) * _VOTE_VALUE[v.vote]
            for v in votes
        )

    def fit(self, dataset: list[list[LFVote]]) -> "LabelModel":
        """Estimate per-LF weights from agreement with the weighted consensus."""
        deduped = [dedup_votes(item) for item in dataset]
        lf_names = {v.lf_name for item in deduped for v in item}
        weights = {name: _acc_to_weight(_DEFAULT_ACC) for name in lf_names}

        for _ in range(self._max_iter):
            # Consensus sign per item under current weights.
            consensus = [
                1.0 if self._consensus_value(item, weights) >= 0 else -1.0
                for item in deduped
            ]
            new_weights: dict[str, float] = {}
            for name in lf_names:
                agree = total = 0
                for item, cons in zip(deduped, consensus):
                    for v in item:
                        if v.lf_name != name or v.vote == ABSTAIN:
                            continue
                        total += 1
                        if _VOTE_VALUE[v.vote] * cons > 0:
                            agree += 1
                acc = agree / total if total else _DEFAULT_ACC
                new_weights[name] = _acc_to_weight(acc)
            if new_weights == weights:
                break
            weights = new_weights

        self._weights = weights
        return self

    def predict(self, votes: list[LFVote]) -> LabelModelResult:
        deduped = dedup_votes(votes)
        active = [v for v in deduped if v.vote != ABSTAIN]
        if not active:
            return LabelModelResult(
                label=ABSTAIN,
                prob_positive=0.5,
                confidence=0.0,
                contributing_lf_count=0,
                lf_weights=dict(self._weights),
            )
        score = self._consensus_value(active, self._weights)
        prob_positive = 1.0 / (1.0 + math.exp(-score))
        label = POSITIVE if prob_positive >= 0.5 else NEGATIVE
        return LabelModelResult(
            label=label,
            prob_positive=prob_positive,
            confidence=abs(prob_positive - 0.5) * 2.0,
            contributing_lf_count=len(active),
            lf_weights=dict(self._weights),
        )
