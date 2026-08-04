"""Validated label-dataset loading with explicit train/eval boundaries."""

from __future__ import annotations

import csv
import hashlib
from collections.abc import Collection
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from app.classification_labels import normalize_classification_label

LabelDatasetRole = Literal[
    "training",
    "validation",
    "frozen_holdout",
    "diagnostic_silver",
]
EvaluationDatasetRole = Literal["frozen_holdout", "diagnostic"]

_REQUIRED_COLUMNS = frozenset({"paper_id", "gold_label"})
_LABEL_SCOPES = frozenset(
    {"AC_REPORTING", "STRICT_SDL", "DUAL_AC_SDL", "UNSPECIFIED"}
)
_EVIDENCE_LEVELS = frozenset(
    {
        "TITLE_ONLY",
        "ABSTRACT",
        "FULLTEXT",
        "SUPPORTING_INFORMATION",
        "METADATA_ONLY",
        "UNKNOWN",
    }
)


@dataclass(frozen=True)
class LabelDatasetMetadata:
    label_scope: str
    annotation_sources: tuple[str, ...]
    evidence_levels: tuple[str, ...]
    allowed_claim: str


def _allowed_claim(label_scope: str) -> str:
    if label_scope == "AC_REPORTING":
        return (
            "Measures agreement with AC reporting judgements; it is not strict "
            "SDL classification accuracy."
        )
    if label_scope == "STRICT_SDL":
        return "Measures strict SDL relevance under the dataset's stated evidence policy."
    if label_scope == "DUAL_AC_SDL":
        return "Measures a dataset that explicitly separates AC and SDL judgements."
    if label_scope == "MIXED":
        return (
            "Contains mixed label scopes; report per-scope metrics before making "
            "an aggregate scientific claim."
        )
    return (
        "Label scope is unspecified; metrics are diagnostic and must not be "
        "presented as AC or SDL accuracy."
    )


def load_label_dataset_metadata(path: Path) -> LabelDatasetMetadata:
    """Load the semantic scope attached to a label CSV.

    Legacy files remain readable, but are reported as UNSPECIFIED rather than
    silently being treated as strict SDL ground truth.
    """
    source = Path(path)
    with source.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        scopes: set[str] = set()
        annotation_sources: set[str] = set()
        evidence_levels: set[str] = set()
        for line_number, row in enumerate(reader, start=2):
            scope = str(row.get("label_scope") or "UNSPECIFIED").strip().upper()
            if scope not in _LABEL_SCOPES:
                raise ValueError(
                    f"label dataset has unsupported label_scope at line "
                    f"{line_number}: {scope!r}"
                )
            evidence_level = str(
                row.get("evidence_level") or "UNKNOWN"
            ).strip().upper()
            if evidence_level not in _EVIDENCE_LEVELS:
                raise ValueError(
                    f"label dataset has unsupported evidence_level at line "
                    f"{line_number}: {evidence_level!r}"
                )
            annotation_source = str(
                row.get("annotation_source") or "unspecified"
            ).strip()
            scopes.add(scope)
            evidence_levels.add(evidence_level)
            annotation_sources.add(annotation_source or "unspecified")

    label_scope = (
        next(iter(scopes))
        if len(scopes) == 1
        else ("MIXED" if scopes else "UNSPECIFIED")
    )
    return LabelDatasetMetadata(
        label_scope=label_scope,
        annotation_sources=tuple(sorted(annotation_sources or {"unspecified"})),
        evidence_levels=tuple(sorted(evidence_levels or {"UNKNOWN"})),
        allowed_claim=_allowed_claim(label_scope),
    )


def combine_label_dataset_metadata(
    *metadata: LabelDatasetMetadata,
) -> LabelDatasetMetadata:
    scopes = {item.label_scope for item in metadata}
    label_scope = (
        next(iter(scopes))
        if len(scopes) == 1
        else ("MIXED" if scopes else "UNSPECIFIED")
    )
    return LabelDatasetMetadata(
        label_scope=label_scope,
        annotation_sources=tuple(
            sorted(
                {
                    source
                    for item in metadata
                    for source in item.annotation_sources
                }
            )
        ),
        evidence_levels=tuple(
            sorted(
                {
                    level
                    for item in metadata
                    for level in item.evidence_levels
                }
            )
        ),
        allowed_claim=_allowed_claim(label_scope),
    )


def ensure_distinct_label_paths(**paths: Path) -> None:
    """Reject role configurations that point at the same physical path."""
    resolved: dict[Path, str] = {}
    for role, path in paths.items():
        normalized = Path(path).expanduser().resolve()
        previous_role = resolved.get(normalized)
        if previous_role is not None:
            raise ValueError(
                f"label dataset roles {previous_role!r} and {role!r} "
                f"must use different paths: {normalized}"
            )
        resolved[normalized] = role


def ensure_disjoint_label_ids(**datasets: Collection[str]) -> None:
    """Reject paper ids assigned to more than one dataset role."""
    roles = list(datasets)
    for index, left_role in enumerate(roles):
        left_ids = set(datasets[left_role])
        for right_role in roles[index + 1 :]:
            overlap = left_ids & set(datasets[right_role])
            if overlap:
                raise ValueError(
                    f"label dataset roles {left_role!r} and {right_role!r} "
                    "overlap; they must have disjoint paper ids: "
                    f"{sorted(overlap)}"
                )


def load_label_dataset(
    path: Path,
    *,
    role: LabelDatasetRole,
    allow_missing: bool = False,
) -> dict[str, str]:
    """Load a label CSV and reject malformed or conflicting records."""
    source = Path(path)
    if not source.exists():
        if allow_missing:
            return {}
        raise FileNotFoundError(f"{role} label dataset not found: {source}")

    with source.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        columns = set(reader.fieldnames or [])
        missing_columns = _REQUIRED_COLUMNS - columns
        if missing_columns:
            raise ValueError(
                f"{role} label dataset is missing columns: "
                f"{sorted(missing_columns)}"
            )

        labels: dict[str, str] = {}
        for line_number, row in enumerate(reader, start=2):
            paper_id = str(row.get("paper_id") or "").strip()
            if not paper_id:
                raise ValueError(
                    f"{role} label dataset has an empty paper_id at line "
                    f"{line_number}"
                )
            label = normalize_classification_label(row.get("gold_label"))
            if label is None:
                raise ValueError(
                    f"{role} label dataset has an unsupported label at line "
                    f"{line_number}: {row.get('gold_label')!r}"
                )
            previous = labels.get(paper_id)
            if previous is not None and previous != label:
                raise ValueError(
                    f"{role} label dataset has conflicting labels for "
                    f"{paper_id!r}: {previous!r} and {label!r}"
                )
            labels[paper_id] = label
    return labels


def load_reserved_evaluation_ids(
    *,
    validation_path: Path,
    holdout_path: Path,
) -> set[str]:
    """Return paper ids that must never feed an automatic learning path."""
    validation = load_label_dataset(
        validation_path,
        role="validation",
    )
    holdout = load_label_dataset(
        holdout_path,
        role="frozen_holdout",
    )
    ensure_disjoint_label_ids(
        validation=validation,
        frozen_holdout=holdout,
    )
    return set(validation) | set(holdout)


def evaluation_dataset_identity(
    primary_path: Path,
    *,
    silver_path: Path | None = None,
) -> tuple[str, str]:
    """Return a display id and content hash for the exact evaluated files."""
    digest = hashlib.sha256()
    names: list[str] = []
    for role, path in (
        ("primary", Path(primary_path)),
        ("silver", Path(silver_path) if silver_path is not None else None),
    ):
        if path is None:
            continue
        content = path.read_bytes()
        digest.update(role.encode("utf-8"))
        digest.update(b"\0")
        digest.update(content)
        names.append(path.name)
    content_hash = digest.hexdigest()
    dataset_id = f"{'+'.join(names)}@sha256:{content_hash[:12]}"
    return dataset_id, content_hash


def evaluation_dataset_role(
    path: Path,
    *,
    configured_holdout_path: Path,
    includes_silver: bool,
) -> EvaluationDatasetRole:
    if includes_silver:
        return "diagnostic"
    if Path(path).expanduser().resolve() == Path(
        configured_holdout_path
    ).expanduser().resolve():
        return "frozen_holdout"
    return "diagnostic"
