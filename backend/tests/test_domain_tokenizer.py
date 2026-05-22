from app.services.domain_tokenizer import DomainTokenizer, DomainVocabulary


def test_protects_multi_word_phrase():
    vocab = DomainVocabulary(
        protected=["self-driving lab", "Bayesian optimization"],
    )
    t = DomainTokenizer(vocab)
    out = t.tokenize("The self-driving lab uses Bayesian optimization daily.")
    assert "self_driving_lab" in out
    assert "bayesian_optimization" in out
    # Surrounding plain words still tokenize.
    assert "uses" in out
    assert "daily" in out


def test_canonical_synonym_collapses_to_canonical_form():
    vocab = DomainVocabulary(
        synonyms={"autonomous lab": "self-driving laboratory"},
        protected=["self-driving laboratory"],
    )
    t = DomainTokenizer(vocab)
    out = t.tokenize("The autonomous lab discovered new materials.")
    assert "self_driving_laboratory" in out


def test_negative_phrase_detection():
    vocab = DomainVocabulary(negatives=["closed-loop control"])
    t = DomainTokenizer(vocab)
    assert t.has_negative_phrase(
        "The plant uses closed-loop control for fluid handling."
    )
    assert not t.has_negative_phrase("Closed-loop experimentation accelerates discovery.")


def test_empty_vocab_falls_back_to_basic_tokenizer():
    t = DomainTokenizer(DomainVocabulary())
    out = t.tokenize("Hello world!")
    assert out == ["hello", "world"]


def test_loads_real_vocabulary_yaml(seeded_session):
    """Default vocabulary file ships with the project — verify it loads."""
    from app.services.domain_tokenizer import get_vocabulary, reset_vocabulary_cache

    reset_vocabulary_cache()
    vocab = get_vocabulary()
    assert any("self-driving" in p.lower() for p in vocab.protected)
    assert "uoft" in vocab.normalized_synonyms()
