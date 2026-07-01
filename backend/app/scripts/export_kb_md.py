"""Export the cross-SDL knowledge base to Markdown pages.

Thin renderer over kb_service/transfer_service: writes index.md (summary, lab
and entity indexes, transfer highlights), entities/<type>--<slug>.md (entity
pages with labs, adoption lags, classification badges and evidence snippets)
and labs/<slug>.md (lab profiles with classification and citation-flow
sections). Every page carries YAML front-matter and cross-links the others
via relative links.

Usage:
    python -m app.scripts.export_kb_md [--output-dir DIR]
"""
from __future__ import annotations

import argparse
import json
import re
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import quote

from sqlalchemy import func, select

from app.config import REPO_ROOT
from app.db import SessionLocal
from app.models import PaperClassification, PaperReference, SdlLab
from app.services.kb_service import (
    entity_index,
    entity_page,
    kb_summary,
    lab_classification_profile,
    lab_profile,
)
from app.services.transfer_service import fastest_spreading, lab_flow_matrix

DEFAULT_OUTPUT_DIR = REPO_ROOT / "outputs" / "kb"

_PAPERS_LIMIT = 30
_FLOW_LIMIT = 10
_HIGHLIGHTS_LIMIT = 10


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", value).strip("-").lower()
    return re.sub(r"-{2,}", "-", slug)[:80] or "unnamed"


# Single source of truth for page filenames and links, shared by all
# renderers so cross-links cannot drift from the written files.

def entity_file(entity_type: str, name: str) -> str:
    return f"{entity_type}--{slugify(name)}.md"


def lab_file(lab_id: str) -> str:
    return f"{slugify(lab_id)}.md"


def entity_link(entity_type: str, name: str, prefix: str = "../") -> str:
    """Link to an entity page. prefix="" from index.md, "../" from subdirs."""
    return f"[{name}]({prefix}entities/{entity_file(entity_type, name)})"


def lab_link(lab_id: str, label: str | None = None, prefix: str = "../") -> str:
    """Link to a lab page. prefix="" from index.md, "../" from subdirs."""
    return f"[{label or lab_id}]({prefix}labs/{lab_file(lab_id)})"


def front_matter(**fields) -> list[str]:
    """YAML front-matter lines; string values are JSON-quoted (valid YAML)."""
    now = datetime.now(UTC)
    lines = ["---"]
    for key, value in fields.items():
        lines.append(
            f"{key}: {json.dumps(value) if isinstance(value, str) else value}"
        )
    lines += [
        f"generated: {now.date().isoformat()}",
        f"timestamp: {now.isoformat(timespec='seconds').replace('+00:00', 'Z')}",
        "---",
        "",
    ]
    return lines


def render_index(
    summary: dict,
    entries: list[dict],
    labs: list[dict],
    highlights: list[dict],
    totals: dict,
) -> str:
    lab_names = {lab["id"]: lab["name"] for lab in labs}
    lines = front_matter(
        type="Knowledge Bundle Index",
        title="Cross-SDL Knowledge Base",
        name="Cross-SDL Knowledge Base",
        description=(
            "Index of AC self-driving-lab entities, lab profiles, "
            "and cross-lab transfer signals."
        ),
        resource="/kb/summary",
        tags=["cross-sdl", "knowledge-base", "paper-attribution"],
        okf_version="0.1",
    ) + [
        "# Cross-SDL Knowledge Base",
        "",
        "## Summary",
        f"- SDL labs: {summary['labs']}",
        f"- Linked papers: {summary['linked_papers']}",
        f"- Cross-lab entities: {summary['cross_lab_entities']}",
    ]
    for etype, count in sorted(summary["entities_by_type"].items()):
        lines.append(f"- Distinct {etype} entities: {count}")
    if totals["references"]:
        lines.append(f"- References: {totals['references']}")
    if totals["classifications"]:
        lines.append(f"- Classified papers: {totals['classifications']}")

    lines += ["", "## Labs", ""]
    lines.append("| Lab | Institution |")
    lines.append("| --- | --- |")
    for lab in labs:
        lines.append(
            f"| {lab_link(lab['id'], lab['name'], prefix='')} "
            f"| {lab['institution']} |"
        )

    if highlights:
        lines += ["", "## Transfer highlights", ""]
        lines.append("| Entity | Type | Origin lab | Adopters | Avg lag (years) |")
        lines.append("| --- | --- | --- | --- | --- |")
        for h in highlights:
            origin = lab_link(
                h["origin_lab"], lab_names.get(h["origin_lab"]), prefix=""
            )
            lines.append(
                f"| {entity_link(h['entity_type'], h['entity'], prefix='')} "
                f"| {h['entity_type']} | {origin} ({h['origin_year']}) "
                f"| {h['adopter_count']} | {h['avg_lag_years']} |"
            )

    by_type: dict[str, list[dict]] = {}
    for entry in entries:
        by_type.setdefault(entry["entity_type"], []).append(entry)
    for etype in sorted(by_type):
        lines += ["", f"## {etype.capitalize()}", ""]
        lines.append("| Entity | Papers | Labs | Years |")
        lines.append("| --- | --- | --- | --- |")
        for entry in by_type[etype]:
            span = (
                f"{entry['first_year'] or '?'}–{entry['last_year'] or '?'}"
                if entry["first_year"] or entry["last_year"]
                else "—"
            )
            lines.append(
                f"| {entity_link(etype, entry['name'], prefix='')} "
                f"| {entry['paper_count']} | {entry['lab_count']} | {span} |"
            )
    lines.append("")
    return "\n".join(lines)


def render_entity(page: dict, lab_names: dict[str, str]) -> str:
    lines = front_matter(
        type="Knowledge Entity",
        title=page["entity"],
        name=page["entity"],
        description=(
            f"Cross-SDL {page['entity_type']} entity mentioned by "
            f"{len(page['papers'])} paper(s)."
        ),
        resource=(
            f"/kb/entities/{quote(page['entity_type'])}/"
            f"{quote(page['entity'], safe='')}"
        ),
        tags=["cross-sdl", "entity", page["entity_type"]],
        entity_type=page["entity_type"],
    ) + [
        f"# {page['entity']} ({page['entity_type']})",
        "",
        "## Labs",
    ]
    if page["labs"]:
        lines.append("| Lab | First year | Papers |")
        lines.append("| --- | --- | --- |")
        for lab in page["labs"]:
            lines.append(
                f"| {lab_link(lab['lab_id'], lab['lab_name'])} "
                f"| {lab['first_year'] or '—'} | {lab['paper_count']} |"
            )
    else:
        lines.append("No lab-linked papers mention this entity.")

    lines += ["", "## Adoption"]
    adoption = page.get("adoption")
    if adoption is None:
        lines.append("No adoption data (no lab-linked papers with a year).")
    else:
        origin = lab_link(
            adoption["origin_lab"], lab_names.get(adoption["origin_lab"])
        )
        lines.append(f"- Origin: {origin} ({adoption['origin_year']})")
        if adoption["adoptions"]:
            for a in adoption["adoptions"]:
                lines.append(
                    f"- {lab_link(a['lab'], lab_names.get(a['lab']))}: "
                    f"first mention {a['first_year']} (+{a['lag_years']}y)"
                )
        else:
            lines.append("- No later adoptions recorded.")

    lines += ["", "## Papers"]
    for paper in page["papers"][:_PAPERS_LIMIT]:
        labs = ""
        if paper["labs"]:
            links = ", ".join(
                lab_link(lab_id, lab_names.get(lab_id)) for lab_id in paper["labs"]
            )
            labs = f" — labs: {links}"
        badge = f" — {paper['label']}" if paper.get("label") else ""
        lines.append(f"- {paper['title']} ({paper['year'] or 'n.d.'}){labs}{badge}")
    if len(page["papers"]) > _PAPERS_LIMIT:
        lines.append(f"- ...and {len(page['papers']) - _PAPERS_LIMIT} more")

    lines += ["", "## Evidence"]
    if page["evidence"]:
        for ev in page["evidence"]:
            lines.append(f"- **{ev['paper_title']}**: {ev['text']}")
    else:
        lines.append("No evidence snippets linked.")

    lines += ["", "## SAG-lite Event Trail"]
    if page.get("events"):
        for event in page["events"]:
            labs = ", ".join(
                lab_link(lab_id, lab_names.get(lab_id)) for lab_id in event["labs"]
            )
            stage = f" — {event['stage']}" if event.get("stage") else ""
            source = f" — chunk `{event['source_chunk_id']}`" if event.get("source_chunk_id") else ""
            related = ""
            if event["related_entities"]:
                labels = ", ".join(
                    f"{item['entity_type']}:{item['name']}"
                    for item in event["related_entities"][:5]
                )
                related = f" Related: {labels}."
            lines.append(
                f"- **{event['paper_title']}** ({event['year'] or 'n.d.'})"
                f"{stage}{source}: {event['snippet']}{related}"
            )
            if labs:
                lines.append(f"  - Labs: {labs}")
    else:
        lines.append("No derived events for this entity yet.")
    lines.append("")
    return "\n".join(lines)


def render_lab(profile: dict, label_counts: list[dict], flows: dict) -> str:
    span = (
        f"{profile['first_year']}–{profile['last_year']}"
        if profile["first_year"] is not None
        else "—"
    )
    lines = front_matter(
        type="SDL Lab",
        title=profile["name"],
        name=profile["name"],
        description=(
            f"{profile['name']} knowledge profile at {profile['institution']}."
        ),
        resource=f"/kb/labs/{quote(profile['id'], safe='')}/profile",
        tags=["cross-sdl", "lab", "paper-attribution"],
        lab_id=profile["id"],
        institution=profile["institution"],
    ) + [
        f"# {profile['name']}",
        "",
        f"- Institution: {profile['institution']}",
        f"- PIs: {', '.join(profile['pi_names']) or 'Not specified'}",
        f"- Domain focus: {profile['domain_focus']}",
        f"- Platform stack: {', '.join(profile['platform_stack'] or []) or 'Not specified'}",
        f"- Automation level: {profile['automation_level'] or 'Not specified'}",
        f"- Papers: {profile['paper_count']} ({span})",
        f"- Entities unique to this lab: {profile['entities_unique_to_lab']}",
        "",
        "## SDL Tags",
    ]
    if profile["sdl_tag_histogram"]:
        for item in profile["sdl_tag_histogram"]:
            lines.append(f"- {item['tag']}: {item['count']}")
    else:
        lines.append("No sdl_tags on linked papers.")

    lines += ["", "## Top Entities"]
    for etype, items in profile["top_entities"].items():
        lines += ["", f"### {etype.capitalize()}"]
        if items:
            for item in items:
                lines.append(
                    f"- {entity_link(etype, item['name'])}"
                    f" ({item['paper_count']} papers)"
                )
        else:
            lines.append("None extracted.")

    lines += ["", "## Collaborations"]
    if profile["collaborations"]:
        for collab in profile["collaborations"]:
            lines.append(
                f"- {lab_link(collab['lab_id'], collab['name'])}: "
                f"{collab['shared_papers']} shared paper(s)"
            )
    else:
        lines.append("No shared papers with other labs.")

    if label_counts:
        lines += ["", "## Classification profile"]
        for item in label_counts:
            lines.append(f"- {item['label']}: {item['count']}")

    if flows["cites"] or flows["cited_by"]:
        lines += ["", "## Citation flows"]
        if flows["cites"]:
            lines += ["", "### Cites"]
            for flow in flows["cites"]:
                lines.append(
                    f"- {lab_link(flow['lab_id'], flow['name'])}: "
                    f"{flow['count']} reference(s)"
                )
        if flows["cited_by"]:
            lines += ["", "### Cited by"]
            for flow in flows["cited_by"]:
                lines.append(
                    f"- {lab_link(flow['lab_id'], flow['name'])}: "
                    f"{flow['count']} reference(s)"
                )
    lines.append("")
    return "\n".join(lines)


def lab_citation_flows(flows: dict) -> dict[str, dict]:
    """Split the lab×lab matrix into per-lab top cites / cited-by lists."""
    labs = flows["labs"]
    per_lab: dict[str, dict] = {}
    for i, lab in enumerate(labs):
        cites = sorted(
            (
                {"lab_id": labs[j]["id"], "name": labs[j]["name"], "count": count}
                for j, count in enumerate(flows["matrix"][i])
                if count
            ),
            key=lambda f: (-f["count"], f["lab_id"]),
        )[:_FLOW_LIMIT]
        cited_by = sorted(
            (
                {"lab_id": labs[j]["id"], "name": labs[j]["name"], "count": row[i]}
                for j, row in enumerate(flows["matrix"])
                if row[i]
            ),
            key=lambda f: (-f["count"], f["lab_id"]),
        )[:_FLOW_LIMIT]
        per_lab[lab["id"]] = {"cites": cites, "cited_by": cited_by}
    return per_lab


def export_kb(output_dir: Path) -> int:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "entities").mkdir(exist_ok=True)
    (output_dir / "labs").mkdir(exist_ok=True)

    count = 0
    with SessionLocal() as session:
        labs = [
            {"id": lab_id, "name": name, "institution": institution}
            for lab_id, name, institution in session.execute(
                select(SdlLab.id, SdlLab.name, SdlLab.institution).order_by(SdlLab.id)
            )
        ]
        lab_names = {lab["id"]: lab["name"] for lab in labs}
        totals = {
            "references": session.scalar(
                select(func.count()).select_from(PaperReference)
            )
            or 0,
            "classifications": session.scalar(
                select(func.count()).select_from(PaperClassification)
            )
            or 0,
        }
        entries = entity_index(session)
        (output_dir / "index.md").write_text(
            render_index(
                kb_summary(session),
                entries,
                labs,
                fastest_spreading(session, limit=_HIGHLIGHTS_LIMIT),
                totals,
            ),
            encoding="utf-8",
        )
        count += 1
        for entry in entries:
            page = entity_page(session, entry["entity_type"], entry["name"])
            filename = entity_file(entry["entity_type"], entry["name"])
            (output_dir / "entities" / filename).write_text(
                render_entity(page, lab_names), encoding="utf-8"
            )
            count += 1
        flows = lab_citation_flows(lab_flow_matrix(session))
        for lab in labs:
            profile = lab_profile(session, lab["id"])
            (output_dir / "labs" / lab_file(lab["id"])).write_text(
                render_lab(
                    profile,
                    lab_classification_profile(session, lab["id"]),
                    flows[lab["id"]],
                ),
                encoding="utf-8",
            )
            count += 1
    return count


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args()

    count = export_kb(args.output_dir)
    print(f"Wrote {count} Markdown files to {args.output_dir}")


if __name__ == "__main__":
    main()
