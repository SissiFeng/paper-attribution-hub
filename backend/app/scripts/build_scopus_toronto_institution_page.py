"""Build the standalone Toronto Scopus institution-comparison page.

This is an adapter around the existing Tier 1+2 OpenAlex institution pipeline.
It preserves the 176-paper Scopus corpus boundary and reuses the same ordered
authorship, institution identity, author-credit, and multi-affiliation logic.
"""
from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.scripts.build_tier1_tier2_openalex_page import (
    PaperInput,
    build_dataset,
    normalize_doi,
    write_outputs,
)


SCHEMA_VERSION = "scopus_toronto_openalex_institution.v1"
CORPUS_LABEL = "Scopus Toronto · 176 papers"


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            row = json.loads(line)
            if not isinstance(row, dict):
                raise ValueError(f"{path.name}:{line_number} is not a JSON object")
            rows.append(row)
    return rows


def _by_eid(rows: list[dict[str, Any]], source: str) -> dict[str, dict[str, Any]]:
    indexed: dict[str, dict[str, Any]] = {}
    for row in rows:
        eid = str(row.get("eid") or row.get("scopus_eid") or "").strip()
        if not eid:
            raise ValueError(f"{source} contains a row without a Scopus EID")
        if eid in indexed:
            raise ValueError(f"{source} contains duplicate Scopus EID {eid}")
        indexed[eid] = row
    return indexed


def _author_count(scopus: dict[str, Any], work: dict[str, Any] | None) -> int:
    raw = scopus.get("raw") or {}
    author_ids = str(raw.get("作者 ID") or raw.get("Author(s) ID") or "")
    count = len([value for value in author_ids.split(";") if value.strip()])
    return max(count, len((work or {}).get("authorships") or []))


def load_enriched_metadata(
    metadata_dir: Path,
) -> tuple[list[PaperInput], dict[str, list[dict]], dict[str, Any], dict[str, Any]]:
    """Load and reconcile the audited Scopus/OpenAlex export by Scopus EID."""
    root = metadata_dir.expanduser().resolve()
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    scopus = _by_eid(_read_jsonl(root / "scopus_results.jsonl"), "Scopus export")
    enriched = _by_eid(
        _read_jsonl(root / "openalex_metadata.jsonl"), "OpenAlex export"
    )
    if set(scopus) != set(enriched):
        missing = sorted(set(scopus) ^ set(enriched))
        raise ValueError(f"Scopus/OpenAlex EID sets differ: {missing[:5]}")
    expected = int(manifest.get("scopus_unique_records") or 0)
    if expected != len(scopus):
        raise ValueError(
            f"Manifest reports {expected} records but artifacts contain {len(scopus)}"
        )

    papers: list[PaperInput] = []
    works_by_key: dict[str, list[dict]] = {}
    source_doi_by_paper: dict[str, str | None] = {}
    status_by_paper: dict[str, str] = {}
    for eid in sorted(scopus):
        source = scopus[eid]
        match_row = enriched[eid]
        match = match_row.get("match") or {}
        work = match_row.get("openalex")
        source_doi = normalize_doi(source.get("doi")) or None
        paper_id = f"eid:{eid}"
        lookup_key = source_doi or f"scopus-eid:{eid}"
        method = str(match.get("method") or "")
        if isinstance(work, dict) and match.get("matched") is True:
            works_by_key[lookup_key] = [work]
            status = "doi_exact" if method == "doi" else method
        else:
            status = "openalex_unmatched" if source_doi else "missing_doi"
        papers.append(
            PaperInput(
                paper_id=paper_id,
                eids=(eid,),
                doi=lookup_key,
                title=str(source.get("title") or ""),
                year=source.get("year") if isinstance(source.get("year"), int) else None,
                membership="all",
                author_count=_author_count(source, work if isinstance(work, dict) else None),
                input_rows=1,
            )
        )
        source_doi_by_paper[paper_id] = source_doi
        status_by_paper[paper_id] = status

    doi_count = sum(value is not None for value in source_doi_by_paper.values())
    stats = {
        "raw_rows": len(papers),
        "distinct_papers": len(papers),
        "rows_with_doi": doi_count,
        "unique_dois": len({value for value in source_doi_by_paper.values() if value}),
        "missing_doi_rows": len(papers) - doi_count,
        "duplicate_doi_groups": 0,
        "duplicate_rows_beyond_first": 0,
        "corpus_rows": {"all": len(papers)},
    }
    adapter = {
        "source_doi_by_paper": source_doi_by_paper,
        "status_by_paper": status_by_paper,
    }
    return papers, works_by_key, manifest, {"input": stats, "adapter": adapter}


def build_toronto_dataset(
    metadata_dir: Path,
    *,
    generated_at: str | None = None,
) -> dict[str, Any]:
    papers, works_by_key, source_manifest, context = load_enriched_metadata(
        metadata_dir
    )
    generated_at = generated_at or datetime.now(UTC).isoformat()
    method_counts = Counter(context["adapter"]["status_by_paper"].values())
    dataset = build_dataset(
        papers,
        works_by_key,
        generated_at=generated_at,
        source_name="Scopus UI CSV export",
        source_sha256=str(source_manifest.get("scopus_input_sha256") or ""),
        input_stats=context["input"],
        fetch_stats={
            "api_calls": 0,
            "cache_hits": 0,
            "source": "audited_scopus_openalex_export",
        },
    )
    source_dois = context["adapter"]["source_doi_by_paper"]
    statuses = context["adapter"]["status_by_paper"]
    for paper in dataset["papers"]:
        paper["d"] = source_dois[paper["i"]]
        paper["s"] = statuses[paper["i"]]

    manifest = dataset["manifest"]
    manifest["schema_version"] = SCHEMA_VERSION
    manifest["corpus"] = {
        "id": "scopus_toronto_self_driving_lab_176",
        "label": CORPUS_LABEL,
        "query": source_manifest.get("scopus_query"),
        "membership_source": "Scopus UI CSV export",
    }
    manifest["data_boundary"] = {
        "mode": "scopus_membership_openalex_metadata_only_local_snapshot",
        "included": [
            "176-paper Scopus query membership and bibliographic identity",
            "OpenAlex ordered authorships",
            "OpenAlex institution, lineage, and ROR assertions",
        ],
        "excluded": [
            "Zotero Tier 1 or Tier 2 membership",
            "PDF or full text",
            "classification outputs and reviews",
            "PAS primary database",
            "Scopus affiliations as OpenAlex fallback",
        ],
    }
    manifest["openalex"]["match_status"] = dict(sorted(method_counts.items()))
    manifest["openalex"]["source_manifest"] = "../scopus-toronto-176-openalex/manifest.json"
    manifest["codebook"]["paper_membership"] = {"all": CORPUS_LABEL}
    return dataset


def render_page(template: str) -> str:
    """Retarget the reviewed standalone Institution Compare UI to this corpus."""
    replacements = {
        "Standalone Tier 1 and Tier 2 OpenAlex metadata-only institution contribution comparison.":
            "Standalone Scopus Toronto OpenAlex metadata-only institution contribution comparison.",
        "Institution contribution comparison · Tier 1 + Tier 2":
            "Institution contribution comparison · Scopus Toronto 176",
        "Tier 1 + Tier 2 local": "Scopus Toronto local",
        "Tier 1 + Tier 2 · OpenAlex metadata only":
            "Scopus Toronto · 176 papers · OpenAlex metadata only",
        "Full-text Markdown, extracted evidence, classifications, reviews, and the existing Tier 1\n                snapshot are not inputs to this local page.":
            "Zotero Tier 1/Tier 2, full text, classifications, and reviews are not inputs to this local page.",
        '<option value="all">Tier 1 + Tier 2</option>\n                  <option value="tier1">Tier 1 incl. overlap</option>\n                  <option value="overlap">Tier 1 + 2 overlap</option>\n                  <option value="tier2">Tier 2 only</option>':
            '<option value="all">Scopus Toronto · 176 papers</option>',
        'max="2025" placeholder="2025"': 'max="2028" placeholder="2028"',
        '<dd id="audit-corpus">Tier 1 + Tier 2</dd>':
            '<dd id="audit-corpus">Scopus Toronto · 176 papers</dd>',
        'aria-label="Ask Tier 1 + Tier 2"': 'aria-label="Ask Scopus Toronto corpus"',
        "Ask Tier 1 + Tier 2": "Ask Scopus Toronto",
        "./data/tier1-tier2-openalex-institution-data.js":
            "./data/scopus-toronto-176-openalex-institution-data.js",
        "Keep this page next to data/tier1-tier2-openalex-institution-data.js.":
            "Keep this page next to data/scopus-toronto-176-openalex-institution-data.js.",
        'const corpusLabels = { all: "Tier 1 + Tier 2", tier1: "Tier 1 incl. overlap", overlap: "Tier 1 + 2 overlap", tier2: "Tier 2 only" };':
            'const corpusLabels = { all: "Scopus Toronto · 176 papers" };',
        'if (["all", "tier1", "overlap", "tier2"].includes(params.get("corpus"))) state.corpus = params.get("corpus");':
            'if (params.get("corpus") === "all") state.corpus = "all";',
        "if (Number.isInteger(yearTo) && yearTo <= 2025) state.yearTo = yearTo;":
            "if (Number.isInteger(yearTo) && yearTo <= 2028) state.yearTo = yearTo;",
        "tier1_tier2_openalex_institution_${state.corpus}_${state.role}_${state.scheme}.csv":
            "scopus_toronto_176_institution_${state.role}_${state.scheme}.csv",
    }
    result = template
    for old, new in replacements.items():
        if old not in result:
            raise ValueError(f"Institution page template marker not found: {old[:80]}")
        result = result.replace(old, new)
    return result


def write_page(template_path: Path, output_path: Path) -> None:
    output = output_path.expanduser().resolve()
    if output.is_symlink():
        raise ValueError(f"Refusing to overwrite symlink: {output}")
    page = render_page(template_path.expanduser().resolve().read_text(encoding="utf-8"))
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(page, encoding="utf-8")


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def main() -> int:
    root = _repo_root()
    parser = argparse.ArgumentParser(
        description="Build the local Scopus Toronto institution comparison page."
    )
    parser.add_argument(
        "--metadata-dir",
        type=Path,
        default=root / "reports" / "scopus-toronto-176-openalex",
    )
    parser.add_argument(
        "--template",
        type=Path,
        default=root / "frontend/public/tier1-tier2-openalex-institution-comparison.html",
    )
    parser.add_argument(
        "--data-js",
        type=Path,
        default=root / "frontend/public/data/scopus-toronto-176-openalex-institution-data.js",
    )
    parser.add_argument(
        "--page",
        type=Path,
        default=root / "frontend/public/scopus-toronto-176-institution-comparison.html",
    )
    parser.add_argument(
        "--artifact-dir",
        type=Path,
        default=root / "reports/scopus-toronto-176-institution",
    )
    args = parser.parse_args()

    dataset = build_toronto_dataset(args.metadata_dir)
    outputs = write_outputs(dataset, data_js=args.data_js, artifact_dir=args.artifact_dir)
    write_page(args.template, args.page)
    summary = {
        "status": "completed",
        "counts": dataset["manifest"]["counts"],
        "openalex": dataset["manifest"]["openalex"],
        "page": str(args.page.resolve()),
        "outputs": {key: value for key, value in outputs.items() if key != "default_report"},
        "default_report": {
            key: value
            for key, value in outputs["default_report"].items()
            if key != "institutions"
        },
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
