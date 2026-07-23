"""Weak-supervision label model: learn LF accuracies, dedup correlated sources.

Replaces hand-weighted evidence sums. Each labeling function votes
POSITIVE / NEGATIVE / ABSTAIN; the model learns which LFs are reliable from
their agreement, and collapses votes that share an underlying source so three
API names for one Crossref record don't cast three votes.
"""

from __future__ import annotations

from app.services.weak_supervision.label_model import (
    ABSTAIN,
    NEGATIVE,
    POSITIVE,
    LabelModel,
    LFVote,
    dedup_votes,
)


def _v(name, vote, provenance=None):
    return LFVote(lf_name=name, vote=vote, provenance_key=provenance)


def test_dedup_collapses_votes_sharing_a_provenance_key():
    votes = [
        _v("openalex_funding", POSITIVE, "crossref:funding:10.1/x"),
        _v("unpaywall_funding", POSITIVE, "crossref:funding:10.1/x"),
        _v("ack_text", POSITIVE, "fulltext:ack:P1"),
    ]
    deduped = dedup_votes(votes)
    # The two API names for the same Crossref record collapse to one vote.
    assert len(deduped) == 2
    provenances = {v.provenance_key for v in deduped}
    assert provenances == {"crossref:funding:10.1/x", "fulltext:ack:P1"}


def test_dedup_keeps_votes_without_provenance_distinct():
    votes = [_v("a", POSITIVE), _v("b", POSITIVE)]
    assert len(dedup_votes(votes)) == 2


def test_reliable_lf_earns_more_weight_than_a_noisy_one():
    # "good" always matches the majority; "noise" alternates against it.
    dataset = [
        [_v("good", POSITIVE), _v("ally", POSITIVE), _v("noise", NEGATIVE)],
        [_v("good", POSITIVE), _v("ally", POSITIVE), _v("noise", NEGATIVE)],
        [_v("good", NEGATIVE), _v("ally", NEGATIVE), _v("noise", POSITIVE)],
        [_v("good", NEGATIVE), _v("ally", NEGATIVE), _v("noise", POSITIVE)],
    ]
    model = LabelModel().fit(dataset)
    assert model.weight("good") > model.weight("noise")


def test_predict_unanimous_positive_is_confident_positive():
    model = LabelModel().fit([[_v("a", POSITIVE), _v("b", POSITIVE)]])
    result = model.predict([_v("a", POSITIVE), _v("b", POSITIVE)])
    assert result.label == POSITIVE
    assert result.prob_positive > 0.7


def test_predict_all_abstain_is_abstain():
    model = LabelModel().fit([[_v("a", POSITIVE)]])
    result = model.predict([_v("a", ABSTAIN), _v("b", ABSTAIN)])
    assert result.label == ABSTAIN


def test_several_reliable_lfs_outvote_one_noisy_lf():
    dataset = [
        [_v("r1", POSITIVE), _v("r2", POSITIVE), _v("r3", POSITIVE), _v("n", NEGATIVE)],
        [_v("r1", NEGATIVE), _v("r2", NEGATIVE), _v("r3", NEGATIVE), _v("n", POSITIVE)],
    ] * 3
    model = LabelModel().fit(dataset)
    # A new item where the 3 reliable LFs say POSITIVE and the noisy one dissents.
    result = model.predict(
        [_v("r1", POSITIVE), _v("r2", POSITIVE), _v("r3", POSITIVE), _v("n", NEGATIVE)]
    )
    assert result.label == POSITIVE


def test_dedup_applied_inside_predict():
    model = LabelModel().fit([[_v("a", POSITIVE)]])
    # Same provenance twice must not double-count.
    result = model.predict(
        [
            _v("openalex", POSITIVE, "crossref:x"),
            _v("unpaywall", POSITIVE, "crossref:x"),
        ]
    )
    assert result.contributing_lf_count == 1
