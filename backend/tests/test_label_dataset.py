import pytest

from app.config import settings
from app.label_dataset import (
    ensure_distinct_label_paths,
    evaluation_dataset_identity,
    evaluation_dataset_role,
    load_label_dataset,
    load_label_dataset_metadata,
    load_reserved_evaluation_ids,
)


def test_default_label_dataset_roles_use_distinct_paths():
    ensure_distinct_label_paths(
        training=settings.training_labels_csv,
        validation=settings.validation_labels_csv,
        frozen_holdout=settings.eval_labels_csv,
        diagnostic_silver=settings.eval_labels_silver_csv,
    )


def test_distinct_path_check_rejects_training_holdout_alias(tmp_path):
    shared = tmp_path / "labels.csv"

    with pytest.raises(ValueError, match="must use different paths"):
        ensure_distinct_label_paths(training=shared, frozen_holdout=shared)


def test_label_loader_rejects_unsupported_label(tmp_path):
    path = tmp_path / "labels.csv"
    path.write_text(
        "paper_id,gold_label,gold_topics,notes\nP001,MAYBE,,bad\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="unsupported label"):
        load_label_dataset(path, role="training")


def test_label_loader_rejects_conflicting_duplicate(tmp_path):
    path = tmp_path / "labels.csv"
    path.write_text(
        "paper_id,gold_label,gold_topics,notes\n"
        "P001,CORE_RELEVANT,,first\n"
        "P001,EXCLUDE,,second\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="conflicting labels"):
        load_label_dataset(path, role="frozen_holdout")


def test_label_loader_normalizes_review_alias(tmp_path):
    path = tmp_path / "labels.csv"
    path.write_text(
        "paper_id,gold_label,gold_topics,notes\nP001,INCLUDE,,legacy\n",
        encoding="utf-8",
    )

    assert load_label_dataset(path, role="training") == {
        "P001": "RELATED_RELEVANT"
    }


def test_reserved_evaluation_ids_combine_validation_and_holdout(tmp_path):
    validation = tmp_path / "validation.csv"
    validation.write_text(
        "paper_id,gold_label\nP001,CORE_RELEVANT\n",
        encoding="utf-8",
    )
    holdout = tmp_path / "holdout.csv"
    holdout.write_text(
        "paper_id,gold_label\nP002,EXCLUDE\n",
        encoding="utf-8",
    )

    assert load_reserved_evaluation_ids(
        validation_path=validation,
        holdout_path=holdout,
    ) == {"P001", "P002"}


def test_reserved_evaluation_ids_fail_closed_when_metadata_missing(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_reserved_evaluation_ids(
            validation_path=tmp_path / "missing-validation.csv",
            holdout_path=tmp_path / "missing-holdout.csv",
        )


def test_validation_and_holdout_ids_must_be_disjoint(tmp_path):
    validation = tmp_path / "validation.csv"
    validation.write_text(
        "paper_id,gold_label\nP001,CORE_RELEVANT\n",
        encoding="utf-8",
    )
    holdout = tmp_path / "holdout.csv"
    holdout.write_text(
        "paper_id,gold_label\nP001,EXCLUDE\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="must have disjoint paper ids"):
        load_reserved_evaluation_ids(
            validation_path=validation,
            holdout_path=holdout,
        )


def test_dataset_role_only_trusts_configured_holdout_path(tmp_path):
    configured = tmp_path / "eval_labels.csv"
    configured.write_text("paper_id,gold_label\n", encoding="utf-8")
    custom = tmp_path / "custom.csv"
    custom.write_text("paper_id,gold_label\n", encoding="utf-8")

    assert evaluation_dataset_role(
        configured,
        configured_holdout_path=configured,
        includes_silver=False,
    ) == "frozen_holdout"
    assert evaluation_dataset_role(
        custom,
        configured_holdout_path=configured,
        includes_silver=False,
    ) == "diagnostic"


def test_dataset_identity_changes_with_content(tmp_path):
    labels = tmp_path / "labels.csv"
    labels.write_text(
        "paper_id,gold_label\nP001,EXCLUDE\n", encoding="utf-8"
    )
    first_id, first_hash = evaluation_dataset_identity(labels)
    labels.write_text(
        "paper_id,gold_label\nP001,CORE_RELEVANT\n", encoding="utf-8"
    )
    second_id, second_hash = evaluation_dataset_identity(labels)

    assert first_id != second_id
    assert first_hash != second_hash


def test_label_metadata_preserves_ac_reporting_scope(tmp_path):
    labels = tmp_path / "labels.csv"
    labels.write_text(
        "paper_id,gold_label,label_scope,annotation_source,evidence_level\n"
        "P001,CORE_RELEVANT,AC_REPORTING,historical_reporting_review,UNKNOWN\n",
        encoding="utf-8",
    )

    metadata = load_label_dataset_metadata(labels)

    assert metadata.label_scope == "AC_REPORTING"
    assert metadata.annotation_sources == ("historical_reporting_review",)
    assert metadata.evidence_levels == ("UNKNOWN",)
    assert "not strict sdl" in metadata.allowed_claim.lower()


def test_label_metadata_rejects_unsupported_scope(tmp_path):
    labels = tmp_path / "labels.csv"
    labels.write_text(
        "paper_id,gold_label,label_scope\n"
        "P001,CORE_RELEVANT,EVERYTHING\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="unsupported label_scope"):
        load_label_dataset_metadata(labels)
