from app.config import settings
from app.services.autoresearch_service import (
    run_classification_autoresearch,
    run_rag_autoresearch,
)


def test_classification_autoresearch_reports_gold_gates(fulltext_seeded_session):
    from app.services.relevance_classifier import classify_all

    classify_all(fulltext_seeded_session)
    report = run_classification_autoresearch(
        fulltext_seeded_session,
        eval_labels_path=settings.eval_labels_csv,
        k=5,
    )

    assert report["target"] == "classification"
    assert report["human_eval"]["n_evaluated"] == 11
    assert report["human_eval"]["dataset_role"] == "frozen_holdout"
    assert len(report["human_eval"]["dataset_hash"]) == 64
    assert any(g["name"] == "frozen_holdout_dataset" for g in report["gates"])
    assert any(g["name"] == "human_gold_accuracy_100" for g in report["gates"])
    assert "ac_publications_eval" in report


def test_classification_autoresearch_rejects_custom_diagnostic_dataset(
    fulltext_seeded_session, tmp_path
):
    from app.services.relevance_classifier import classify_all

    classify_all(fulltext_seeded_session)
    custom_labels = tmp_path / "custom_labels.csv"
    custom_labels.write_bytes(settings.eval_labels_csv.read_bytes())

    report = run_classification_autoresearch(
        fulltext_seeded_session,
        eval_labels_path=custom_labels,
        k=5,
    )

    role_gate = next(
        gate for gate in report["gates"] if gate["name"] == "frozen_holdout_dataset"
    )
    assert report["human_eval"]["dataset_role"] == "diagnostic"
    assert role_gate["status"] == "fail"
    assert report["accepted"] is False


def test_rag_autoresearch_scores_evidence_retrieval(fulltext_seeded_session):
    report = run_rag_autoresearch(
        fulltext_seeded_session,
        top_k=5,
        min_recall_at_k=0.0,
    )

    assert report["target"] == "rag"
    assert report["coverage"]["non_abstract_chunks"] > 0
    assert report["metrics"]["tasks"] > 0
    assert report["metrics"]["recall_at_k"] is not None
    assert 0.0 <= report["metrics"]["recall_at_k"] <= 1.0
    assert all("retrieved_chunk_ids" in row for row in report["task_results"])


def test_rag_autoresearch_reports_empty_database(session):
    report = run_rag_autoresearch(session)

    assert report["accepted"] is False
    assert report["metrics"]["tasks"] == 0
    assert any(g["name"] == "evidence_tasks_present" for g in report["gates"])
