"""Portable, deterministic bundle export for evidence-preserving wiki pages."""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import tempfile
import uuid
from collections import Counter, defaultdict
from pathlib import Path
from typing import Sequence

import yaml
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Paper
from app.services.wiki_compiler import WIKI_COMPILER_VERSION, compile_wiki

BUNDLE_SCHEMA_VERSION = "pas-evidence-wiki-bundle-v0.1"
VALIDATION_SCHEMA_VERSION = "pas-evidence-wiki-validation-v0.1"


class EvidenceWikiBundleError(RuntimeError):
    pass


def _json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _slug(value: str) -> str:
    cleaned = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return cleaned[:64] or "paper"


def _page_path(paper_id: str, title: str) -> str:
    suffix = _sha256_text(paper_id)[:12]
    return f"papers/{_slug(title)}-{suffix}.md"


def _write_text(root: Path, relative_path: str, content: str) -> dict:
    path = root / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return {
        "path": relative_path,
        "sha256": _sha256_text(content),
        "bytes": len(content.encode()),
    }


def _render_root_index(pages: list[dict]) -> str:
    lines = [
        "# PAS Evidence Wiki Bundle",
        "",
        "Deterministic, read-only projections of recorded paper evidence.",
        "",
        "- [Paper index](papers/index.md)",
        "- [By attribution decision](indexes/by-decision.md)",
        "- [By invocation status](indexes/by-status.md)",
        "- [By evidence provider](indexes/by-evidence-provider.md)",
        "- [Manifest](manifest.json)",
        "- [Validation report](validation-report.json)",
        "",
        f"Pages: {len(pages)}",
        "",
    ]
    return "\n".join(lines)


def _page_link(page: dict, *, from_dir: str) -> str:
    path = page["path"]
    if from_dir == "papers":
        path = Path(path).name
    elif from_dir == "indexes":
        path = f"../{path}"
    label = " ".join(str(page["title"]).split()).replace("[", "\\[").replace(
        "]", "\\]"
    )
    return f"[{label}]({path})"


def _render_paper_index(pages: list[dict]) -> str:
    lines = ["# Papers", ""]
    for page in pages:
        decision = page["source_metadata"].get("decision") or "NO_DECISION"
        status = page["source_metadata"]["attribution_status"]
        lines.append(
            f"- {_page_link(page, from_dir='papers')} — `{decision}` / `{status}`"
        )
    return "\n".join(lines).rstrip() + "\n"


def _render_grouped_index(
    title: str, pages: list[dict], key: str, *, evidence_provider: bool = False
) -> str:
    grouped: dict[str, list[dict]] = defaultdict(list)
    for page in pages:
        metadata = page["source_metadata"]
        if evidence_provider:
            values = sorted(
                {
                    item["provider"]
                    for item in metadata["evidence_requirements"]
                    if item.get("provider")
                }
            ) or ["NO_PROVIDER"]
        else:
            values = [metadata.get(key) or "NO_DECISION"]
        for value in values:
            grouped[str(value)].append(page)

    lines = [f"# {title}", ""]
    for value in sorted(grouped):
        lines.extend([f"## {value}", ""])
        for page in grouped[value]:
            lines.append(f"- {_page_link(page, from_dir='indexes')}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _bundle_counts(pages: list[dict]) -> dict:
    statuses = Counter()
    decisions = Counter()
    evidence_polarities = Counter()
    for page in pages:
        metadata = page["source_metadata"]
        statuses[metadata["attribution_status"]] += 1
        decisions[metadata.get("decision") or "NO_DECISION"] += 1
        for item in metadata["evidence_requirements"]:
            evidence_polarities[item["polarity"]] += 1
    return {
        "pages": len(pages),
        "invocation_statuses": dict(sorted(statuses.items())),
        "decisions": dict(sorted(decisions.items())),
        "evidence_polarities": dict(sorted(evidence_polarities.items())),
    }


def _safe_artifact_path(root: Path, relative_path: str) -> Path | None:
    path = Path(relative_path)
    if path.is_absolute() or ".." in path.parts:
        return None
    resolved_root = root.resolve()
    resolved_path = (root / path).resolve()
    if resolved_path != resolved_root and resolved_root not in resolved_path.parents:
        return None
    return root / path


def _frontmatter(content: str) -> dict | None:
    if not content.startswith("---\n"):
        return None
    parts = content.split("---\n", 2)
    if len(parts) != 3:
        return None
    try:
        parsed = yaml.safe_load(parts[1])
    except yaml.YAMLError:
        return None
    return parsed if isinstance(parsed, dict) else None


def validate_evidence_wiki_bundle(root: Path) -> dict:
    """Run fixed structural, checksum, evidence, temporal, and review checks."""
    root = Path(root)
    issues: list[dict] = []
    checks = Counter()

    def check(condition: bool, name: str, *, paper_id: str | None = None) -> None:
        checks[name] += 1
        if not condition:
            issue = {"check": name}
            if paper_id:
                issue["paper_id"] = paper_id
            issues.append(issue)

    manifest_path = root / "manifest.json"
    if not manifest_path.is_file():
        return {
            "schema_version": VALIDATION_SCHEMA_VERSION,
            "status": "failed",
            "checks_run": 1,
            "issues": [{"check": "manifest_exists"}],
        }
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {
            "schema_version": VALIDATION_SCHEMA_VERSION,
            "status": "failed",
            "checks_run": 1,
            "issues": [{"check": "manifest_is_valid_json"}],
        }

    check(manifest.get("schema_version") == BUNDLE_SCHEMA_VERSION, "manifest_schema")
    check(manifest.get("status") == "complete", "manifest_status")
    check(bool(manifest.get("compiler_version")), "compiler_version")
    pages = manifest.get("pages")
    check(isinstance(pages, list), "manifest_pages_list")
    if not isinstance(pages, list):
        pages = []
    counts = manifest.get("counts")
    check(isinstance(counts, dict), "manifest_counts_object")
    if not isinstance(counts, dict):
        counts = {}
    check(counts.get("pages") == len(pages), "page_count")

    index_contents = []
    indexes = manifest.get("indexes")
    check(isinstance(indexes, list), "manifest_indexes_list")
    if not isinstance(indexes, list):
        indexes = []
    for artifact in indexes:
        check(isinstance(artifact, dict), "index_manifest_object")
        if not isinstance(artifact, dict):
            continue
        path = _safe_artifact_path(root, artifact.get("path", ""))
        check(path is not None, "index_path_safe")
        if path is None:
            continue
        check(path.is_file() and not path.is_symlink(), "index_exists")
        if not path.is_file():
            continue
        content = path.read_text(encoding="utf-8")
        index_contents.append(content)
        check(_sha256_text(content) == artifact.get("sha256"), "index_checksum")

    for page in pages:
        check(isinstance(page, dict), "page_manifest_object")
        if not isinstance(page, dict):
            continue
        paper_id = str(page.get("paper_id", ""))
        path = _safe_artifact_path(root, page.get("path", ""))
        check(path is not None, "page_path_safe", paper_id=paper_id)
        if path is None:
            continue
        check(
            path.is_file() and not path.is_symlink(),
            "page_exists",
            paper_id=paper_id,
        )
        if not path.is_file():
            continue
        content = path.read_text(encoding="utf-8")
        check(
            _sha256_text(content) == page.get("content_hash"),
            "page_checksum",
            paper_id=paper_id,
        )
        frontmatter = _frontmatter(content)
        check(frontmatter is not None, "frontmatter_valid", paper_id=paper_id)
        if frontmatter:
            pas = frontmatter.get("pas") or {}
            check(isinstance(pas, dict), "frontmatter_pas_object", paper_id=paper_id)
            if not isinstance(pas, dict):
                pas = {}
            check(
                pas.get("source_snapshot_hash") == page.get("source_snapshot_hash"),
                "source_snapshot_hash",
                paper_id=paper_id,
            )

        metadata = page.get("source_metadata") or {}
        check(isinstance(metadata, dict), "source_metadata_object", paper_id=paper_id)
        if not isinstance(metadata, dict):
            metadata = {}
        status = metadata.get("attribution_status")
        decision = metadata.get("decision")
        check(bool(status), "invocation_status_present", paper_id=paper_id)
        check(page.get("compile_status") == "complete", "compile_complete", paper_id=paper_id)
        if frontmatter:
            check(frontmatter.get("status") == status, "frontmatter_status", paper_id=paper_id)
            check(pas.get("decision") == decision, "frontmatter_decision", paper_id=paper_id)
            check(
                pas.get("authority") == metadata.get("authority"),
                "frontmatter_authority",
                paper_id=paper_id,
            )
        if metadata.get("invocation_id"):
            snapshot_fresh = metadata.get("input_snapshot_fresh")
            check(
                isinstance(snapshot_fresh, bool),
                "input_snapshot_fresh_recorded",
                paper_id=paper_id,
            )
            if snapshot_fresh is False:
                check(
                    "Snapshot freshness: stale" in content
                    and "rerun the Attribution Skill" in content,
                    "stale_snapshot_action_present",
                    paper_id=paper_id,
                )
        if decision:
            check(
                f"Decision: {decision}" in content,
                "decision_present",
                paper_id=paper_id,
            )
        else:
            check(
                "No attribution decision was recorded" in content
                or "No evidence packet or attribution decision was recorded" in content
                or status == "NOT_INVOKED",
                "no_decision_explicit",
                paper_id=paper_id,
            )

        requirements = metadata.get("evidence_requirements") or []
        check(isinstance(requirements, list), "evidence_requirements_list", paper_id=paper_id)
        if not isinstance(requirements, list):
            requirements = []
        requirements = [item for item in requirements if isinstance(item, dict)]
        evidence_ids = {item.get("evidence_id") for item in requirements}
        supporting = set(metadata.get("supporting_evidence_ids") or [])
        contradicting = set(metadata.get("contradicting_evidence_ids") or [])
        check(
            supporting.isdisjoint(contradicting),
            "evidence_polarities_disjoint",
            paper_id=paper_id,
        )
        check(
            supporting | contradicting <= evidence_ids,
            "decision_evidence_resolves",
            paper_id=paper_id,
        )
        for requirement in requirements:
            for field in (
                "evidence_id",
                "provider",
                "source_record_id",
                "temporal_status",
            ):
                check(
                    bool(requirement.get(field))
                    and str(requirement[field]) in content,
                    f"evidence_{field}",
                    paper_id=paper_id,
                )
            for field in ("content_hash", "source_chunk_id"):
                if requirement.get(field):
                    check(
                        str(requirement[field]) in content,
                        f"evidence_{field}",
                        paper_id=paper_id,
                    )
            if requirement.get("page_start"):
                check(
                    "Pages:" in content,
                    "evidence_pages",
                    paper_id=paper_id,
                )

        if decision == "REVIEW_REQUIRED":
            review_action = metadata.get("review_action")
            check(
                bool(review_action) and str(review_action) in content,
                "review_action_present",
                paper_id=paper_id,
            )
        check(
            any(page.get("path", "") in index for index in index_contents),
            "page_indexed",
            paper_id=paper_id,
        )

    aggregate = {
        artifact["path"]: artifact["sha256"]
        for artifact in indexes
        if isinstance(artifact, dict)
        and isinstance(artifact.get("path"), str)
        and isinstance(artifact.get("sha256"), str)
    }
    aggregate.update(
        {
            page["path"]: page["content_hash"]
            for page in pages
            if isinstance(page, dict)
            and isinstance(page.get("path"), str)
            and isinstance(page.get("content_hash"), str)
        }
    )
    check(
        manifest.get("bundle_content_hash") == _sha256_text(_json(aggregate)),
        "bundle_content_hash",
    )

    return {
        "schema_version": VALIDATION_SCHEMA_VERSION,
        "status": "passed" if not issues else "failed",
        "checks_run": sum(checks.values()),
        "check_counts": dict(sorted(checks.items())),
        "issues": issues,
    }


def _replace_directory(staging: Path, output_dir: Path) -> None:
    backup = output_dir.with_name(f".{output_dir.name}.backup-{uuid.uuid4().hex}")
    had_existing = output_dir.exists()
    if had_existing:
        os.replace(output_dir, backup)
    try:
        os.replace(staging, output_dir)
    except Exception:
        if had_existing and backup.exists():
            os.replace(backup, output_dir)
        raise
    if backup.exists():
        shutil.rmtree(backup)


def export_evidence_wiki_bundle(
    session: Session,
    output_dir: Path,
    *,
    paper_ids: Sequence[str] | None = None,
) -> dict:
    """Compile, validate, and atomically publish a portable evidence bundle."""
    output_dir = Path(output_dir).resolve()
    if output_dir == Path(output_dir.anchor):
        raise EvidenceWikiBundleError("Refusing to use a filesystem root as output")
    if output_dir.exists() and not output_dir.is_dir():
        raise EvidenceWikiBundleError("Bundle output must be a directory")
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(
        tempfile.mkdtemp(prefix=f".{output_dir.name}.staging-", dir=output_dir.parent)
    )
    try:
        if paper_ids is None:
            selected_ids = list(
                session.execute(select(Paper.id).order_by(Paper.id)).scalars()
            )
        else:
            selected_ids = sorted(set(paper_ids))

        pages: list[dict] = []
        for paper_id in selected_ids:
            page = compile_wiki(session, paper_id)
            if page.compile_status != "complete":
                raise EvidenceWikiBundleError(
                    f"Paper {paper_id!r} has compile status {page.compile_status!r}"
                )
            path = _page_path(paper_id, page.title)
            artifact = _write_text(staging, path, page.content_md or "")
            if artifact["sha256"] != page.content_hash:
                raise EvidenceWikiBundleError(
                    f"Paper {paper_id!r} content hash does not reconcile"
                )
            pages.append(
                {
                    "paper_id": paper_id,
                    "title": page.title,
                    "path": path,
                    "content_hash": page.content_hash,
                    "source_snapshot_hash": page.source_snapshot_hash,
                    "compile_status": page.compile_status,
                    "source_metadata": page.source_metadata or {},
                }
            )
        pages.sort(key=lambda item: item["paper_id"])

        indexes = [
            _write_text(staging, "index.md", _render_root_index(pages)),
            _write_text(staging, "papers/index.md", _render_paper_index(pages)),
            _write_text(
                staging,
                "indexes/by-decision.md",
                _render_grouped_index("By Attribution Decision", pages, "decision"),
            ),
            _write_text(
                staging,
                "indexes/by-status.md",
                _render_grouped_index(
                    "By Invocation Status", pages, "attribution_status"
                ),
            ),
            _write_text(
                staging,
                "indexes/by-evidence-provider.md",
                _render_grouped_index(
                    "By Evidence Provider",
                    pages,
                    "provider",
                    evidence_provider=True,
                ),
            ),
        ]
        aggregate = {
            item["path"]: item["sha256"]
            for item in [
                *indexes,
                *(
                    {"path": page["path"], "sha256": page["content_hash"]}
                    for page in pages
                ),
            ]
        }
        manifest = {
            "schema_version": BUNDLE_SCHEMA_VERSION,
            "compiler_version": WIKI_COMPILER_VERSION,
            "status": "complete",
            "bundle_content_hash": _sha256_text(_json(aggregate)),
            "counts": _bundle_counts(pages),
            "indexes": indexes,
            "pages": pages,
        }
        _write_text(
            staging,
            "manifest.json",
            json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        )
        validation = validate_evidence_wiki_bundle(staging)
        _write_text(
            staging,
            "validation-report.json",
            json.dumps(validation, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        )
        if validation["status"] != "passed":
            raise EvidenceWikiBundleError(
                f"Bundle validation failed with {len(validation['issues'])} issue(s)"
            )
        _replace_directory(staging, output_dir)
        return manifest
    except Exception:
        if staging.exists():
            shutil.rmtree(staging)
        raise
