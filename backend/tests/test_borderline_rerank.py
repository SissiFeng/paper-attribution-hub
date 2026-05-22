"""v0.7 cross-encoder borderline rerank stub coverage."""
from app.services.relevance_classifier import (
    ClassificationResult,
    LABEL_EXCLUDE,
    LABEL_UNCERTAIN,
    _apply_rerank_to_borderline,
)


class _StubRerankerLowScore:
    """Always returns a low logit → forces downgrade."""

    name = "stub"

    def rerank(self, query, candidates):
        from app.services.retrieval_service import RetrievedChunk
        from dataclasses import replace

        return [replace(c, score=-3.0) for c in candidates]


class _StubRerankerHighScore:
    name = "stub-high"

    def rerank(self, query, candidates):
        from dataclasses import replace

        return [replace(c, score=3.0) for c in candidates]


def _fake_paper(pid="P_X", t="t", a="a"):
    from types import SimpleNamespace

    return SimpleNamespace(id=pid, title=t, abstract=a)


def _result(label=LABEL_UNCERTAIN, conf=0.5):
    return ClassificationResult(
        label=label,
        confidence=conf,
        author_score=0.0,
        institution_score=0.0,
        topic_score=0.0,
        network_score=0.0,
        fulltext_evidence_score=0.0,
        citation_score=0.0,
        matched_people=[],
        matched_institutions=[],
        matched_topics=[],
    )


def test_low_rerank_downgrades_uncertain_to_exclude(monkeypatch):
    monkeypatch.setattr(
        "app.services.relevance_classifier.get_reranker",
        lambda: _StubRerankerLowScore(),
    )
    paper = _fake_paper()
    results = {paper.id: _result()}
    _apply_rerank_to_borderline([paper], results)
    assert results[paper.id].label == LABEL_EXCLUDE
    assert results[paper.id].rerank_applied is True


def test_high_rerank_promotes_uncertain_to_related(monkeypatch):
    monkeypatch.setattr(
        "app.services.relevance_classifier.get_reranker",
        lambda: _StubRerankerHighScore(),
    )
    paper = _fake_paper()
    results = {paper.id: _result()}
    _apply_rerank_to_borderline([paper], results)
    assert results[paper.id].label == "RELATED_RELEVANT"


def test_null_reranker_is_noop():
    # Default NullReranker leaves labels untouched.
    paper = _fake_paper()
    results = {paper.id: _result(LABEL_UNCERTAIN, 0.5)}
    _apply_rerank_to_borderline([paper], results)
    assert results[paper.id].label == LABEL_UNCERTAIN
    assert results[paper.id].rerank_applied is False
