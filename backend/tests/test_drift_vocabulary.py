"""v0.7 drift_service: VocabularySuggestion surfaces in DriftReport."""
from app.services.drift_service import _distinctive_bigrams


def test_distinctive_bigrams_picks_year_specific_terms():
    to_text = (
        "materials acceleration platform is the future. materials acceleration "
        "platform delivered our latest result. materials acceleration platform."
    )
    from_text = "older Bayesian optimization work."
    bigrams = _distinctive_bigrams(
        to_text, from_text, existing_terms={"bayesian optimization"}
    )
    assert any("materials acceleration" in bg for bg, _ in bigrams)


def test_distinctive_bigrams_skips_existing_vocab():
    to_text = "self-driving lab self-driving lab self-driving lab"
    from_text = "boring control text"
    bigrams = _distinctive_bigrams(
        to_text, from_text, existing_terms={"self-driving lab"}
    )
    # Already in vocab → should not be suggested.
    assert not any("self-driving" in bg for bg, _ in bigrams)


def test_drift_report_includes_vocab_suggestions(seeded_session):
    from app.services.drift_service import build_drift_report
    from app.services.filter_spec import PaperFilter
    from app.services.relevance_classifier import classify_all

    classify_all(seeded_session)
    report = build_drift_report(
        seeded_session, PaperFilter(), drift_threshold=0.99
    )
    # The report must at least produce the new list (possibly empty for
    # the tiny sample corpus).
    assert isinstance(report.vocabulary_suggestions, list)
