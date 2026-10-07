from __future__ import annotations


class FakeBaseTokenizer:
    name = "fake-base-tokenizer"

    def encode(self, text: str) -> list[str]:
        terms = {
            "Bayesian optimization": ["Bayesian", "optimization"],
            "BoTorch": ["BoTorch"],
            "LiNi0.8Mn0.1Co0.1O2": ["Li", "Ni", "0.8", "Mn", "0.1", "Co", "0.1", "O2"],
        }
        return terms.get(text.strip(), text.split())


class ContextSensitiveTokenizer:
    name = "context-sensitive-tokenizer"
    model_tokenizer = True

    def encode(self, text: str) -> list[str]:
        if text == " BoTorch":
            return [" BoTorch"]
        if text == "BoTorch":
            return ["Bo", "Torch"]
        return text.split()


def test_tokenizer_audit_separates_multiword_terms_from_subword_fragmentation():
    from app.services.tokenizer_fragmentation import audit_tokenizer_fragmentation

    report = audit_tokenizer_fragmentation(
        texts=[
            "Bayesian optimization with BoTorch.",
            "LiNi0.8Mn0.1Co0.1O2 was synthesized.",
        ],
        domain_terms=[
            "Bayesian optimization",
            "BoTorch",
            "LiNi0.8Mn0.1Co0.1O2",
            "botorch",
        ],
        tokenizer=FakeBaseTokenizer(),
    )

    assert report["schema_version"] == "pas-tokenizer-fragmentation-audit-v0.1"
    assert report["tokenizer"] == "fake-base-tokenizer"
    assert report["text_count"] == 2
    assert report["term_count"] == 3
    assert report["term_context"] == "mid_text_leading_space"
    assert report["multi_token_terms"] == 2
    assert report["subword_fragmented_terms"] == 1
    assert report["multi_token_rate"] == 2 / 3
    assert report["subword_fragmentation_rate"] == 1 / 3
    assert report["worst_terms"][0] == {
        "term": "LiNi0.8Mn0.1Co0.1O2",
        "word_count": 1,
        "token_count": 8,
        "tokens_per_word": 8.0,
        "pieces": ["Li", "Ni", "0.8", "Mn", "0.1", "Co", "0.1", "O2"],
    }


def test_domain_retrieval_adapter_is_explicitly_not_a_model_tokenizer():
    from app.services.domain_tokenizer import DomainVocabulary
    from app.services.tokenizer_fragmentation import DomainRetrievalTokenizerAdapter

    adapter = DomainRetrievalTokenizerAdapter(
        DomainVocabulary(protected=["Bayesian optimization"])
    )

    assert adapter.name == "pas-domain-retrieval-tokenizer"
    assert adapter.model_tokenizer is False
    assert adapter.encode("Bayesian optimization loop") == [
        "bayesian_optimization",
        "loop",
    ]


def test_model_term_fragmentation_uses_mid_text_context():
    from app.services.tokenizer_fragmentation import audit_tokenizer_fragmentation

    report = audit_tokenizer_fragmentation(
        texts=[],
        domain_terms=["BoTorch"],
        tokenizer=ContextSensitiveTokenizer(),
    )

    assert report["subword_fragmented_terms"] == 0
    assert report["worst_terms"][0]["pieces"] == [" BoTorch"]
