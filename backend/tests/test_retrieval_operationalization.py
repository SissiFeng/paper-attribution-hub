from sqlalchemy import select

from app.models import Topic
from app.scripts.ingest_scopus_batch import _arch_scores
from app.services.domain_tokenizer import get_vocabulary, reset_vocabulary_cache
from app.services.evidence_extractor import SDL_METHODOLOGY_TERMS
from app.services.proposition_extractor import _METHOD_KEYWORDS
from app.services.retrieval_operationalization import (
    architecture_terms,
    retrieval_query,
    tier1_label_terms,
)
from app.services.topic_classifier import TopicClassifier


def test_operationalization_terms_cover_protocol_examples():
    tier1 = {term.lower() for term in tier1_label_terms()}
    ai = {term.lower() for term in architecture_terms("ai_decision_making")}
    auto = {term.lower() for term in architecture_terms("automated_experimentation")}
    loop = {term.lower() for term in architecture_terms("iterative_closed_loop")}

    assert "self-driven laboratory" in tier1
    assert "accelerated scientific discovery" in tier1
    assert "discovery acceleration" in tier1
    assert "algorithm-guided" in ai
    assert "hte" in auto
    assert "robot scientist" in auto
    assert "self-optimizing" in loop
    assert "adaptive experimentation" in loop
    assert "design-build-test-learn" in loop
    assert "dbtl" in loop


def test_operationalization_preserves_tier_queries():
    tier1 = retrieval_query("tier1")
    tier2 = retrieval_query("tier2")

    assert '"self-driving laborator*"' in tier1
    assert "AND LANGUAGE(english)" in tier1
    assert '"Bayesian optimization"' in tier2
    assert '"closed-loop"' in tier2


def test_scopus_architecture_scores_use_canonical_terms():
    ai, auto, loop = _arch_scores(
        "Algorithm-guided chemistry",
        "An HTE robot scientist uses DBTL for adaptive experimentation.",
    )

    assert ai == 1.0
    assert auto == 1.0
    assert loop == 1.0


def test_fulltext_and_proposition_terms_share_canonical_vocabulary():
    expected = {
        "algorithm-guided",
        "robot scientist",
        "adaptive experimentation",
        "design-build-test-learn",
    }
    evidence_terms = {term.lower() for term in SDL_METHODOLOGY_TERMS}
    proposition_terms = {term.lower() for term in _METHOD_KEYWORDS}

    assert expected <= evidence_terms
    assert expected <= proposition_terms


def test_domain_vocabulary_protects_protocol_terms():
    reset_vocabulary_cache()
    vocab = get_vocabulary()
    protected = set(vocab.normalized_protected_phrases())
    synonyms = vocab.normalized_synonyms()

    assert "self-driven laboratory" in protected
    assert "algorithm-guided" in protected
    assert "design-build-test-learn" in protected
    assert synonyms["self driving laboratory"] == "self-driving laboratory"
    assert synonyms["hte"] == "high-throughput experimentation"


def test_topic_taxonomy_recognizes_protocol_terms(seeded_session):
    topics = list(seeded_session.execute(select(Topic)).scalars())
    classifier = TopicClassifier(topics)
    result = classifier.classify_detailed(
        "Self-driven laboratory for discovery acceleration",
        "A robot scientist performs HTE with algorithm-guided DBTL cycles.",
        "",
    )

    assert result.combined_score > 0
    assert any("self-driven laboratory" in m.hits for m in result.matches)
    assert any("algorithm-guided" in m.hits for m in result.matches)
