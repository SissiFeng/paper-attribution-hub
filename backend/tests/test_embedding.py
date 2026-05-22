import numpy as np

from app.services.embedding_service import TfidfEmbedder, tokenize


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
