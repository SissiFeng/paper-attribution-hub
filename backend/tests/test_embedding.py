import numpy as np
import pytest

from app.services.embedding_service import (
    STORAGE_EMBEDDING_DIMENSION,
    TfidfEmbedder,
    embedding_for_storage,
    tokenize,
)


def test_tokenize_basic():
    assert tokenize("Closed-loop, Bayesian Optimization!") == [
        "closed-loop",
        "bayesian",
        "optimization",
    ]


def test_tfidf_is_deterministic():
    corpus = [
        "Self-driving lab discovers materials.",
        "We use Bayesian optimization in a closed-loop experiment.",
        "Climate models in the IPCC report.",
    ]
    a = TfidfEmbedder().fit(corpus)
    b = TfidfEmbedder().fit(corpus)
    va = a.encode(corpus)
    vb = b.encode(corpus)
    assert np.allclose(va, vb)


def test_similarity_separates_topics():
    corpus = [
        "Self-driving lab discovers organic laser materials autonomously.",
        "We use Bayesian optimization in a closed-loop experiment for catalysis.",
        "A broad review of climate modeling approaches and the IPCC report.",
    ]
    emb = TfidfEmbedder().fit(corpus)
    matrix = emb.encode(corpus)
    query = emb.encode(["closed-loop Bayesian optimization"])
    sims = emb.similarity(query, matrix)
    # Doc 1 (catalysis + Bayesian + closed-loop) should rank above doc 2 (climate review).
    assert sims[1] > sims[2]


def test_embedding_for_storage_pads_and_truncates_to_pgvector_width():
    short = embedding_for_storage(np.array([0.6, 0.8], dtype=np.float32))
    assert len(short) == STORAGE_EMBEDDING_DIMENSION
    assert short[:2] == pytest.approx([0.6, 0.8])
    assert not any(short[2:])

    long = embedding_for_storage(
        np.ones(STORAGE_EMBEDDING_DIMENSION + 1, dtype=np.float32)
    )
    assert len(long) == STORAGE_EMBEDDING_DIMENSION
    assert np.linalg.norm(long) == pytest.approx(1.0)
