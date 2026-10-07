"""Join a package selection manifest to frozen paper metadata for Experiment A."""

from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import tempfile
from datetime import date
from pathlib import Path
from typing import Any

from app.domain_adaptation.memory_evidence_experiment import (
    ExperimentADesignInput,
    ExperimentADesignPolicy,
    ExperimentAPaper,
    ModelCutoffEvidence,
)


def _report_type(selection_tier: str) -> str:
    normalized = selection_tier.casefold()
    if normalized.startswith("primary_"):
        return "primary_experiment"
    if "review" in normalized:
        return "review"
    if "case_study" in normalized:
        return "case_study"
    return "unknown"


def _openalex_publication_date(raw_metadata: dict[str, Any]) -> str | None:
    value = (
        raw_metadata.get("tier1_metadata_agent", {})
        .get("openalex", {})
        .get("publication_date")
    )
    return value if isinstance(value, str) and value else None


def _write_new(path: Path, content: bytes) -> None:
    if path.exists():
        raise FileExistsError(f"Refusing to overwrite existing input: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            dir=path.parent,
            prefix=f".{path.name}.",
            delete=False,
        ) as temporary:
            temporary.write(content)
            temporary_path = Path(temporary.name)
        temporary_path.replace(path)
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def prepare_memory_evidence_experiment(
    *,
    experiment_id: str,
    domain: str,
    selection_manifest_path: str | Path,
    database_path: str | Path,
    cutoff_registry_path: str | Path,
    output_path: str | Path,
    policy: ExperimentADesignPolicy | None = None,
) -> dict[str, object]:
    selection = json.loads(
        Path(selection_manifest_path).read_text(encoding="utf-8")
    )
    selected_papers = selection.get("papers")
    if not isinstance(selected_papers, list) or not selected_papers:
        raise ValueError("Selection manifest must contain a non-empty papers list")
    cutoff_payload = json.loads(
        Path(cutoff_registry_path).read_text(encoding="utf-8")
    )
    model_cutoffs = [
        ModelCutoffEvidence.model_validate(item)
        for item in cutoff_payload.get("model_cutoffs", [])
    ]
    if not model_cutoffs:
        raise ValueError("Cutoff registry must contain at least one model")

    connection = sqlite3.connect(database_path)
    connection.row_factory = sqlite3.Row
    papers: list[ExperimentAPaper] = []
    missing: list[str] = []
    try:
        for selected in sorted(selected_papers, key=lambda item: item["paper_id"]):
            row = connection.execute(
                """SELECT id, doi, raw_metadata, citation_count,
                citation_count_source, citation_count_updated_at
                FROM papers WHERE id = ?""",
                (selected["paper_id"],),
            ).fetchone()
            if row is None:
                missing.append(f"{selected['paper_id']}:database_row")
                continue
            raw_text = row["raw_metadata"] or "{}"
            try:
                raw_metadata = json.loads(raw_text)
            except json.JSONDecodeError:
                missing.append(f"{selected['paper_id']}:raw_metadata_json")
                continue
            publication_text = _openalex_publication_date(raw_metadata)
            citation_updated = row["citation_count_updated_at"]
            required = {
                "publication_date": publication_text,
                "citation_count": row["citation_count"],
                "citation_count_source": row["citation_count_source"],
                "citation_snapshot_date": citation_updated,
                "source_markdown_sha256": selected.get(
                    "source_markdown_sha256"
                ),
            }
            absent = [key for key, value in required.items() if value is None]
            if absent:
                missing.extend(
                    f"{selected['paper_id']}:{field}" for field in absent
                )
                continue
            publication_date = date.fromisoformat(str(publication_text))
            precision = (
                "year"
                if publication_date.month == 1 and publication_date.day == 1
                else "day"
            )
            papers.append(
                ExperimentAPaper(
                    paper_id=selected["paper_id"],
                    doi=selected.get("doi") or row["doi"],
                    publication_date=publication_date,
                    publication_date_precision=precision,
                    publication_date_source="openalex_metadata_snapshot",
                    report_type=_report_type(selected["selection_tier"]),
                    citation_count=row["citation_count"],
                    citation_source=row["citation_count_source"],
                    citation_snapshot_date=str(citation_updated)[:10],
                    source_markdown_sha256=selected[
                        "source_markdown_sha256"
                    ],
                )
            )
    finally:
        connection.close()
    if missing:
        raise ValueError(
            "Experiment A metadata is incomplete: " + ", ".join(sorted(missing))
        )

    spec = ExperimentADesignInput(
        experiment_id=experiment_id,
        domain=domain,
        policy=policy or ExperimentADesignPolicy(),
        model_cutoffs=model_cutoffs,
        papers=papers,
    )
    content = (
        json.dumps(
            spec.model_dump(mode="json"),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n"
    ).encode("utf-8")
    destination = Path(output_path)
    _write_new(destination, content)
    return {
        "output_path": str(destination),
        "paper_count": len(papers),
        "primary_paper_count": sum(
            item.report_type == "primary_experiment" for item in papers
        ),
        "model_count": len(model_cutoffs),
        "input_sha256": hashlib.sha256(content).hexdigest(),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Prepare a frozen Experiment A design input from a package."
    )
    parser.add_argument("--experiment-id", required=True)
    parser.add_argument("--domain", required=True)
    parser.add_argument("--selection-manifest", type=Path, required=True)
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--cutoff-registry", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    result = prepare_memory_evidence_experiment(
        experiment_id=args.experiment_id,
        domain=args.domain,
        selection_manifest_path=args.selection_manifest,
        database_path=args.database,
        cutoff_registry_path=args.cutoff_registry,
        output_path=args.output,
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
