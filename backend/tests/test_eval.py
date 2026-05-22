from app.config import settings
from app.services.eval_service import compute_metrics, run_evaluation


def test_compute_metrics_handles_perfect_predictions():
    gold = {"a": "CORE_RELEVANT", "b": "EXCLUDE"}
    pred = {"a": "CORE_RELEVANT", "b": "EXCLUDE"}
    report = compute_metrics(pred, gold)
    assert report.accuracy == 1.0
    assert report.macro_f1 == 1.0
    assert report.n_evaluated == 2


def test_compute_metrics_partial():
    gold = {"a": "CORE_RELEVANT", "b": "EXCLUDE", "c": "EXCLUDE"}
    pred = {"a": "CORE_RELEVANT", "b": "EXCLUDE", "c": "CORE_RELEVANT"}
    report = compute_metrics(pred, gold)
    assert 0.6 <= report.accuracy <= 0.7  # 2 / 3


def test_full_pipeline_eval_runs_with_fulltext(fulltext_seeded_session):
    """End-to-end: classify with full text + run eval against the gold set."""
    from app.services.relevance_classifier import classify_all

    classify_all(fulltext_seeded_session)
    report = run_evaluation(fulltext_seeded_session, settings.eval_labels_csv, k=5)
    assert report.n_evaluated == 11
    # We don't pin a specific F1 number, but the v0.2 fulltext win should land
    # the classifier well above the 0.40 baseline mentioned in the spec.
    assert report.accuracy >= 0.7
    # Evidence recall must be computable (we have funding chunks in P001/P003/P006).
    assert report.evidence_recall_at_k is not None
