"""Export the cross-SDL knowledge base as a Karpathy-style "llm-wiki" vault.

Three layers:
  raw sources — paper_attribution.db (papers, lab links, typed entities)
  wiki        — this export: interlinked Markdown pages under llm-wiki/
  schema      — llm-wiki/CLAUDE.md: the conventions future agent sessions follow

The vault is self-contained: index.md catalogs every page with a one-line
summary, log.md is an append-only greppable operations log, wiki/ holds lab /
method / material / instrument / software / concept pages with YAML
front-matter (typed relations) and Obsidian path-style [[wikilinks]], and
graph.html is a standalone interactive graph view with the data embedded
(also written separately as graph.json).

Forward-compatible with fine-grained method extraction: PaperEntity.stage /
usage_snippet and entity_extractor.load_sdl_entity_meta() are read
defensively, so the export works before and after that data lands.

Usage:
    python -m app.scripts.export_llm_wiki [--output-dir DIR]
"""
from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from datetime import UTC, datetime
from math import sqrt
from pathlib import Path

import yaml
from sqlalchemy import select

from app.config import DATA_DIR, REPO_ROOT, settings
from app.db import SessionLocal
from app.models import Paper, PaperEntity, PaperLabLink, SdlLab
from app.scripts.export_kb_md import lab_citation_flows, slugify
from app.services.kb_service import (
    entity_index,
    entity_page,
    kb_summary,
    lab_classification_profile,
    lab_profile,
)
from app.services.transfer_service import fastest_spreading, lab_flow_matrix

try:  # lands with fine-grained method extraction
    from app.services.entity_extractor import load_sdl_entity_meta
except ImportError:
    load_sdl_entity_meta = None

DEFAULT_OUTPUT_DIR = REPO_ROOT / "llm-wiki"
METHOD_STAGES_YAML = DATA_DIR / "method_stages.yaml"

# entity_type → wiki subfolder
TYPE_DIRS = {
    "method": "methods",
    "material": "materials",
    "instrument": "instruments",
    "software": "software",
}

_PAPERS_LIMIT = 20
_USAGE_LIMIT = 15
_ADOPTION_EDGE_ENTITIES = 10


# ── vault paths & wikilinks ─────────────────────────────────────────────────
# Wikilink targets are vault-root-relative paths without ".md" (Obsidian
# resolves these from any page); <target>.md is the file on disk.

def lab_path(lab_id: str) -> str:
    return f"wiki/labs/{slugify(lab_id)}"


def entity_path(entity_type: str, name: str) -> str:
    return f"wiki/{TYPE_DIRS[entity_type]}/{slugify(name)}"


def concept_path(category: str) -> str:
    return f"wiki/concepts/{slugify(category)}"


def wikilink(path: str, label: str) -> str:
    return f"[[{path}|{label}]]"


def lab_link(lab_id: str, lab_names: dict[str, str]) -> str:
    return wikilink(lab_path(lab_id), lab_names.get(lab_id, lab_id))


# ── defensive loaders (concurrent fine-grained-extraction contract) ─────────

def _load_entity_meta() -> dict:
    """Per-entity metadata (e.g. method categories) from sdl_entities.yaml.
    Empty until entity_extractor grows load_sdl_entity_meta()."""
    if load_sdl_entity_meta is None:
        return {}
    try:
        return load_sdl_entity_meta() or {}
    except Exception:
        return {}


def _method_category(meta: dict, name: str) -> str | None:
    """Coarse category for a fine method, tolerating either a flat
    {name: {...}} or a nested {"method(s)": {name: {...}}} meta shape."""
    entry = meta.get(name)
    for key in ("method", "methods"):
        if entry is None and isinstance(meta.get(key), dict):
            entry = meta[key].get(name)
    if isinstance(entry, dict):
        category = entry.get("category")
        return str(category) if category else None
    if isinstance(entry, str):
        return entry
    return None


def load_stage_names(path: Path | None = None) -> dict[str, str]:
    """{stage id: display name} from data/method_stages.yaml, {} if absent."""
    p = Path(path or METHOD_STAGES_YAML)
    if not p.exists():
        return {}
    raw = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    return {
        str(sid): str((cfg or {}).get("name") or sid)
        for sid, cfg in (raw.get("stages") or {}).items()
    }


def _entity_aliases() -> dict[tuple[str, str], list[str]]:
    """{(entity_type, canonical): [aliases]} from the extraction vocabulary."""
    try:
        from app.services.entity_extractor import load_sdl_entities

        vocab = load_sdl_entities()
    except Exception:
        return {}
    aliases: dict[tuple[str, str], list[str]] = defaultdict(list)
    for entity_type, terms in vocab.items():
        for surface, canonical in terms.items():
            if surface != canonical:
                aliases[(entity_type, canonical)].append(surface)
    return dict(aliases)


def collect_method_usage(
    rows: list[tuple],
) -> tuple[dict[str, list[dict]], dict[str, dict[str, int]]]:
    """Usage snippets and stage histograms per normalized method name.

    rows are (entity, paper_year, lab_id_or_None); stage / usage_snippet are
    read with getattr so this works before the columns exist.
    """
    usage: dict[str, list[dict]] = defaultdict(list)
    stage_counts: dict[str, Counter[str]] = defaultdict(Counter)
    for entity, year, lab_id in rows:
        stage = getattr(entity, "stage", None)
        snippet = getattr(entity, "usage_snippet", None)
        if stage:
            stage_counts[entity.normalized_name][str(stage)] += 1
        if snippet:
            usage[entity.normalized_name].append(
                {"lab_id": lab_id, "year": year, "stage": stage, "snippet": str(snippet)}
            )
    return dict(usage), {name: dict(c) for name, c in stage_counts.items()}


# ── data collection ──────────────────────────────────────────────────────────

def _collect(session) -> dict:
    profiles = [
        lab_profile(session, lab_id)
        for lab_id in session.execute(select(SdlLab.id).order_by(SdlLab.id)).scalars()
    ]
    lab_names = {p["id"]: p["name"] for p in profiles}
    entries = entity_index(session)
    entity_pages = {
        (e["entity_type"], e["name"]): entity_page(session, e["entity_type"], e["name"])
        for e in entries
    }

    paper_labs: dict[str, list[str]] = defaultdict(list)
    for paper_id, lab_id in session.execute(
        select(PaperLabLink.paper_id, PaperLabLink.lab_id).order_by(PaperLabLink.lab_id)
    ):
        paper_labs[paper_id].append(lab_id)
    method_rows = [
        (entity, year, (paper_labs.get(paper_id) or [None])[0])
        for entity, year, paper_id in session.execute(
            select(PaperEntity, Paper.year, Paper.id)
            .join(Paper, Paper.id == PaperEntity.paper_id)
            .where(PaperEntity.entity_type == "method")
            .order_by(Paper.year, Paper.id)
        )
    ]
    usage, stage_counts = collect_method_usage(method_rows)

    meta = _load_entity_meta()
    categories = {
        e["name"]: _method_category(meta, e["name"])
        for e in entries
        if e["entity_type"] == "method"
    }

    # lab → entity_type → [{name, paper_count, first_year}] (from entity pages)
    lab_entities: dict[str, dict[str, list[dict]]] = defaultdict(lambda: defaultdict(list))
    for (entity_type, name), page in entity_pages.items():
        for lab in page["labs"]:
            lab_entities[lab["lab_id"]][entity_type].append(
                {"name": name, "paper_count": lab["paper_count"], "first_year": lab["first_year"]}
            )
    for by_type in lab_entities.values():
        for items in by_type.values():
            items.sort(key=lambda i: (-i["paper_count"], i["name"]))

    return {
        "labs": profiles,
        "lab_names": lab_names,
        "lab_entities": lab_entities,
        "label_profiles": {
            p["id"]: lab_classification_profile(session, p["id"]) for p in profiles
        },
        "flows": lab_citation_flows(lab_flow_matrix(session)),
        "entries": entries,
        "entity_pages": entity_pages,
        "categories": categories,
        "aliases": _entity_aliases(),
        "stage_names": load_stage_names(),
        "usage": usage,
        "stage_counts": stage_counts,
        "summary": kb_summary(session),
        "fastest": fastest_spreading(session, limit=_ADOPTION_EDGE_ENTITIES),
    }


# ── page rendering ───────────────────────────────────────────────────────────

def front_matter(fields: dict) -> str:
    fields = {**fields, "generated": datetime.now(UTC).date().isoformat()}
    return "---\n" + yaml.safe_dump(fields, sort_keys=False, allow_unicode=True) + "---\n\n"


def _span(first, last) -> str:
    if first is None and last is None:
        return "n.d."
    return f"{first or '?'}–{last or '?'}"


def _papers_section(page: dict, lab_names: dict[str, str]) -> list[str]:
    lines = ["## Papers", ""]
    for paper in page["papers"][:_PAPERS_LIMIT]:
        labs = ""
        if paper["labs"]:
            links = ", ".join(lab_link(lab_id, lab_names) for lab_id in paper["labs"])
            labs = f" — labs: {links}"
        badge = f" — `{paper['label']}`" if paper.get("label") else ""
        lines.append(f"- {paper['title']} ({paper['year'] or 'n.d.'}){labs}{badge}")
    if len(page["papers"]) > _PAPERS_LIMIT:
        lines.append(f"- ...and {len(page['papers']) - _PAPERS_LIMIT} more")
    return lines


def _adoption_section(page: dict, lab_names: dict[str, str]) -> list[str]:
    lines = ["## Adoption", ""]
    adoption = page.get("adoption")
    if adoption is None:
        lines.append("No adoption data (no lab-linked papers with a year).")
        return lines
    lines.append(
        f"- Origin: {lab_link(adoption['origin_lab'], lab_names)} ({adoption['origin_year']})"
    )
    for a in adoption["adoptions"]:
        lines.append(
            f"- {lab_link(a['lab'], lab_names)}: first mention {a['first_year']}"
            f" (+{a['lag_years']}y)"
        )
    if not adoption["adoptions"]:
        lines.append("- No later adoptions recorded.")
    return lines


def _labs_table(page: dict, lab_names: dict[str, str]) -> list[str]:
    lines = ["## Labs", ""]
    if not page["labs"]:
        lines.append("No lab-linked papers mention this entity.")
        return lines
    lines += ["| Lab | First year | Papers |", "| --- | --- | --- |"]
    for lab in page["labs"]:
        lines.append(
            f"| {lab_link(lab['lab_id'], lab_names)} | {lab['first_year'] or '—'} "
            f"| {lab['paper_count']} |"
        )
    return lines


def _render_entity(entry: dict, data: dict) -> dict:
    """One wiki page record for a method/material/instrument/software entity."""
    entity_type, name = entry["entity_type"], entry["name"]
    page = data["entity_pages"][(entity_type, name)]
    aliases = data["aliases"].get((entity_type, name), [])
    category = data["categories"].get(name) if entity_type == "method" else None
    stage_hist = data["stage_counts"].get(name) if entity_type == "method" else None
    usage_rows = data["usage"].get(name, []) if entity_type == "method" else []
    stage_names = data["stage_names"]

    fm: dict = {"type": entity_type, "name": name}
    if category:
        fm["category"] = category
    if aliases:
        fm["aliases"] = aliases
    fm["used_by_labs"] = [lab["lab_id"] for lab in page["labs"]]
    fm["paper_count"] = entry["paper_count"]
    if stage_hist:
        fm["stages"] = stage_hist

    lines = [f"# {name}", "", f"- Type: {entity_type}"]
    if category:
        lines.append(f"- Category: {wikilink(concept_path(category), category.title())}")
    if aliases:
        lines.append(f"- Aliases: {', '.join(aliases)}")
    lines.append(f"- Papers: {entry['paper_count']} ({_span(entry['first_year'], entry['last_year'])})")
    lines += ["", *_labs_table(page, data["lab_names"])]

    if stage_hist:
        lines += ["", "## Stages", ""]
        for stage, count in sorted(stage_hist.items(), key=lambda kv: (-kv[1], kv[0])):
            lines.append(f"- {stage_names.get(stage, stage)}: {count}")

    if usage_rows:
        lines += ["", "## Usage", ""]
        for row in usage_rows[:_USAGE_LIMIT]:
            snippet = " ".join(row["snippet"].split())
            when = str(row["year"] or "n.d.")
            if row["stage"]:
                when += f", {stage_names.get(row['stage'], row['stage'])}"
            prefix = (
                f"{lab_link(row['lab_id'], data['lab_names'])} " if row["lab_id"] else ""
            )
            lines.append(f'- {prefix}({when}): "{snippet}"')

    lines += ["", *_adoption_section(page, data["lab_names"])]
    lines += ["", *_papers_section(page, data["lab_names"]), ""]

    one_liner = (
        f"{entity_type}, {_span(entry['first_year'], entry['last_year'])}"
        f" ({entry['paper_count']} papers, {entry['lab_count']} labs)"
    )
    return {
        "path": entity_path(entity_type, name),
        "title": name,
        "section": TYPE_DIRS[entity_type].capitalize(),
        "subsection": category,
        "one_liner": one_liner,
        "text": front_matter(fm) + "\n".join(lines),
        "body": "\n".join(lines),
    }


def _render_lab(profile: dict, data: dict) -> dict:
    lab_id = profile["id"]
    ents = data["lab_entities"].get(lab_id, {})
    label_counts = data["label_profiles"].get(lab_id, [])
    flow = data["flows"].get(lab_id, {"cites": [], "cited_by": []})
    categories = data["categories"]

    fm = {
        "type": "lab",
        "name": profile["name"],
        "lab_id": lab_id,
        "institution": profile["institution"],
        "pi_names": profile["pi_names"],
        "paper_count": profile["paper_count"],
    }
    for entity_type, dirname in TYPE_DIRS.items():
        names = [item["name"] for item in ents.get(entity_type, [])]
        if names:
            fm[f"uses_{dirname}"] = names
    collabs = profile["collaborations"]
    if collabs:
        fm["collaborates_with"] = [c["lab_id"] for c in collabs]

    lines = [
        f"# {profile['name']}",
        "",
        f"- Institution: {profile['institution']}",
        f"- PIs: {', '.join(profile['pi_names']) or 'Not specified'}",
        f"- Domain focus: {profile['domain_focus'] or 'Not specified'}",
        f"- Platform stack: {', '.join(profile['platform_stack'] or []) or 'Not specified'}",
        f"- Automation level: {profile['automation_level'] or 'Not specified'}",
        f"- Papers: {profile['paper_count']} ({_span(profile['first_year'], profile['last_year'])})",
        f"- Entities unique to this lab: {profile['entities_unique_to_lab']}",
    ]

    if label_counts:
        lines += ["", "## Classification profile", ""]
        for item in label_counts:
            lines.append(f"- {item['label']}: {item['count']}")

    methods = ents.get("method", [])
    if methods:
        lines += ["", "## Methods"]
        by_category: dict[str | None, list[dict]] = defaultdict(list)
        for item in methods:
            by_category[categories.get(item["name"])].append(item)
        grouped = any(cat is not None for cat in by_category)
        for cat in sorted(by_category, key=lambda c: (c is None, c or "")):
            if grouped:
                title = cat.title() if cat else "Other"
                lines += ["", f"### {title}", ""]
            else:
                lines.append("")
            for item in by_category[cat]:
                lines.append(
                    f"- {wikilink(entity_path('method', item['name']), item['name'])}"
                    f" ({item['paper_count']} papers)"
                )

    for entity_type in ("material", "instrument", "software"):
        items = ents.get(entity_type, [])
        if items:
            lines += ["", f"## {TYPE_DIRS[entity_type].capitalize()}", ""]
            for item in items:
                lines.append(
                    f"- {wikilink(entity_path(entity_type, item['name']), item['name'])}"
                    f" ({item['paper_count']} papers)"
                )

    if collabs:
        lines += ["", "## Collaborations", ""]
        for c in collabs:
            lines.append(
                f"- {lab_link(c['lab_id'], data['lab_names'])}: {c['shared_papers']} shared paper(s)"
            )

    if flow["cites"] or flow["cited_by"]:
        lines += ["", "## Citation flows"]
        for key, heading in (("cites", "Cites"), ("cited_by", "Cited by")):
            if flow[key]:
                lines += ["", f"### {heading}", ""]
                for f in flow[key]:
                    lines.append(
                        f"- {lab_link(f['lab_id'], data['lab_names'])}: {f['count']} reference(s)"
                    )
    lines.append("")

    return {
        "path": lab_path(lab_id),
        "title": profile["name"],
        "section": "Labs",
        "subsection": None,
        "one_liner": (
            "; ".join(filter(None, (profile["institution"], profile["domain_focus"])))
            + f" ({profile['paper_count']} papers, {_span(profile['first_year'], profile['last_year'])})"
        ),
        "text": front_matter(fm) + "\n".join(lines),
        "body": "\n".join(lines),
    }


def _render_concept(category: str, members: list[dict], data: dict) -> dict:
    """One page per coarse method category, linking its fine methods."""
    total_papers = sum(m["paper_count"] for m in members)
    fm = {
        "type": "concept",
        "name": category,
        "methods": [m["name"] for m in members],
    }
    lines = [
        f"# {category.title()}",
        "",
        f"Method family with {len(members)} fine-grained method(s).",
        "",
        "## Methods",
        "",
        "| Method | Papers | Labs |",
        "| --- | --- | --- |",
    ]
    lab_papers: Counter[str] = Counter()
    for m in members:
        lines.append(
            f"| {wikilink(entity_path('method', m['name']), m['name'])} "
            f"| {m['paper_count']} | {m['lab_count']} |"
        )
        for lab in data["entity_pages"][("method", m["name"])]["labs"]:
            lab_papers[lab["lab_id"]] += lab["paper_count"]
    if lab_papers:
        lines += ["", "## Labs using this family", ""]
        for lab_id, count in sorted(lab_papers.items(), key=lambda kv: (-kv[1], kv[0])):
            lines.append(f"- {lab_link(lab_id, data['lab_names'])}: {count} method-paper(s)")
    lines.append("")

    return {
        "path": concept_path(category),
        "title": category.title(),
        "section": "Concepts",
        "subsection": None,
        "one_liner": f"method family: {len(members)} methods ({total_papers} method-papers)",
        "text": front_matter(fm) + "\n".join(lines),
        "body": "\n".join(lines),
    }


def _render_overview(data: dict) -> dict:
    summary = data["summary"]
    stage_names = data["stage_names"]
    lines = [
        "# Cross-SDL Knowledge Base — Overview",
        "",
        "## Corpus",
        f"- SDL labs: {summary['labs']}",
        f"- Lab-linked papers: {summary['linked_papers']}",
        f"- Cross-lab entities: {summary['cross_lab_entities']}",
    ]
    for entity_type, count in sorted(summary["entities_by_type"].items()):
        lines.append(f"- Distinct {entity_type} entities: {count}")

    top_labs = sorted(data["labs"], key=lambda p: (-p["paper_count"], p["id"]))[:10]
    if top_labs:
        lines += ["", "## Top labs", "", "| Lab | Institution | Papers |", "| --- | --- | --- |"]
        for p in top_labs:
            lines.append(
                f"| {lab_link(p['id'], data['lab_names'])} | {p['institution']} "
                f"| {p['paper_count']} |"
            )

    if data["fastest"]:
        lines += [
            "",
            "## Fastest-spreading entities",
            "",
            "| Entity | Type | Origin | Adopters | Avg lag (years) |",
            "| --- | --- | --- | --- | --- |",
        ]
        for f in data["fastest"]:
            lines.append(
                f"| {wikilink(entity_path(f['entity_type'], f['entity']), f['entity'])} "
                f"| {f['entity_type']} "
                f"| {lab_link(f['origin_lab'], data['lab_names'])} ({f['origin_year']}) "
                f"| {f['adopter_count']} | {f['avg_lag_years']} |"
            )

    stage_totals: Counter[str] = Counter()
    for hist in data["stage_counts"].values():
        stage_totals.update(hist)
    if stage_totals:
        lines += ["", "## Stage landscape", ""]
        for stage, count in stage_totals.most_common():
            lines.append(f"- {stage_names.get(stage, stage)}: {count} method mention(s)")

    families = sorted({c for c in data["categories"].values() if c})
    if families:
        lines += ["", "## Method families", ""]
        for category in families:
            members = [n for n, c in data["categories"].items() if c == category]
            lines.append(
                f"- {wikilink(concept_path(category), category.title())}: {len(members)} method(s)"
            )
    lines.append("")

    return {
        "path": "wiki/overview",
        "title": "Overview",
        "section": None,
        "subsection": None,
        "one_liner": "synthesis: corpus totals, top labs, fastest-spreading entities, stage landscape",
        "text": front_matter({"type": "overview", "name": "Cross-SDL Knowledge Base"})
        + "\n".join(lines),
        "body": "\n".join(lines),
    }


def _build_pages(data: dict) -> list[dict]:
    pages = [_render_overview(data)]
    pages += [_render_lab(profile, data) for profile in data["labs"]]
    pages += [_render_entity(entry, data) for entry in data["entries"]]
    entries_by_name = {
        e["name"]: e for e in data["entries"] if e["entity_type"] == "method"
    }
    for category in sorted({c for c in data["categories"].values() if c}):
        members = [
            entries_by_name[name]
            for name, cat in sorted(data["categories"].items())
            if cat == category and name in entries_by_name
        ]
        pages.append(_render_concept(category, members, data))
    return pages


def _render_index(pages: list[dict]) -> str:
    lines = [
        "# Cross-SDL llm-wiki — Index",
        "",
        f"- {wikilink('wiki/overview', 'Overview')} — "
        + next(p["one_liner"] for p in pages if p["path"] == "wiki/overview"),
    ]
    sections = ("Labs", "Methods", "Materials", "Instruments", "Software", "Concepts")
    for section in sections:
        section_pages = [p for p in pages if p["section"] == section]
        if not section_pages:
            continue
        lines += ["", f"## {section}", ""]
        if section == "Methods" and any(p["subsection"] for p in section_pages):
            by_family: dict[str | None, list[dict]] = defaultdict(list)
            for p in section_pages:
                by_family[p["subsection"]].append(p)
            for family in sorted(by_family, key=lambda f: (f is None, f or "")):
                lines += [f"### {family.title() if family else 'Other'}", ""]
                for p in by_family[family]:
                    lines.append(f"- {wikilink(p['path'], p['title'])} — {p['one_liner']}")
                lines.append("")
            lines.pop()
        else:
            for p in section_pages:
                lines.append(f"- {wikilink(p['path'], p['title'])} — {p['one_liner']}")
    lines.append("")
    return front_matter({"type": "index", "name": "Cross-SDL llm-wiki"}) + "\n".join(lines)


# ── graph data ───────────────────────────────────────────────────────────────

def _node_size(base: float, count: int, cap: float) -> float:
    return round(min(cap, base + 2 * sqrt(max(count, 0))), 1)


def _build_graph(data: dict, pages: list[dict]) -> dict:
    md_by_path = {p["path"]: p["body"] for p in pages}
    nodes: list[dict] = []
    edges: list[dict] = []

    for profile in data["labs"]:
        path = lab_path(profile["id"])
        nodes.append(
            {
                "id": path,
                "label": profile["name"],
                "type": "lab",
                "papers": profile["paper_count"],
                "size": _node_size(14, profile["paper_count"], 46),
                "md": md_by_path.get(path, ""),
            }
        )

    for entry in data["entries"]:
        entity_type, name = entry["entity_type"], entry["name"]
        path = entity_path(entity_type, name)
        node = {
            "id": path,
            "label": name,
            "type": entity_type,
            "papers": entry["paper_count"],
            "labs": entry["lab_count"],
            "size": _node_size(8, entry["paper_count"], 30),
            "md": md_by_path.get(path, ""),
        }
        category = data["categories"].get(name) if entity_type == "method" else None
        if category:
            node["category"] = category
        nodes.append(node)

        # lab—entity "uses": weight >= 2 to control density, but keep all
        # edges for rare entities (and at least the strongest one) so no
        # entity node orphans.
        lab_edges = [
            {
                "source": lab_path(lab["lab_id"]),
                "target": path,
                "type": "uses",
                "weight": lab["paper_count"],
            }
            for lab in data["entity_pages"][(entity_type, name)]["labs"]
        ]
        kept = [e for e in lab_edges if e["weight"] >= 2 or entry["paper_count"] < 2]
        if lab_edges and not kept:
            kept = [max(lab_edges, key=lambda e: e["weight"])]
        edges += kept

    for category in sorted({c for c in data["categories"].values() if c}):
        path = concept_path(category)
        nodes.append(
            {
                "id": path,
                "label": category.title(),
                "type": "concept",
                "size": 18,
                "md": md_by_path.get(path, ""),
            }
        )
        for name, cat in sorted(data["categories"].items()):
            if cat == category and ("method", name) in data["entity_pages"]:
                edges.append(
                    {
                        "source": entity_path("method", name),
                        "target": path,
                        "type": "member",
                        "weight": 1,
                    }
                )

    seen_pairs: set[tuple[str, str]] = set()
    for profile in data["labs"]:
        for c in profile["collaborations"]:
            if c["shared_papers"] < 2:
                continue
            pair = tuple(sorted((profile["id"], c["lab_id"])))
            if pair in seen_pairs:
                continue
            seen_pairs.add(pair)
            edges.append(
                {
                    "source": lab_path(pair[0]),
                    "target": lab_path(pair[1]),
                    "type": "collab",
                    "weight": c["shared_papers"],
                }
            )

    for f in data["fastest"]:
        page = data["entity_pages"].get((f["entity_type"], f["entity"]))
        adoption = (page or {}).get("adoption")
        if not adoption:
            continue
        for a in adoption["adoptions"]:
            edges.append(
                {
                    "source": lab_path(adoption["origin_lab"]),
                    "target": lab_path(a["lab"]),
                    "type": "adoption",
                    "weight": 1,
                    "entity": f["entity"],
                }
            )

    return {
        "generated": datetime.now(UTC).date().isoformat(),
        "categories": sorted({c for c in data["categories"].values() if c}),
        "nodes": nodes,
        "edges": edges,
    }


# ── vault-root files ─────────────────────────────────────────────────────────

LOG_HEADER = (
    "# Log\n\nAppend-only operations log. Grep `## [` to list entries.\n"
)


def append_log(path: Path, operation: str, title: str) -> None:
    if not path.exists():
        path.write_text(LOG_HEADER, encoding="utf-8")
    date = datetime.now(UTC).date().isoformat()
    with path.open("a", encoding="utf-8") as fh:
        fh.write(f"\n## [{date}] {operation} | {title}\n")


CLAUDE_MD = """\
# llm-wiki — Cross-SDL Knowledge Base (schema layer)

You read it; the LLM writes it. This vault is generated from the
paper-attribution database — edit upstream (data/*.yaml, the DB, the
exporter), then regenerate. Hand edits to wiki/ pages are overwritten.

## Three layers

1. **Raw sources** — `backend/paper_attribution.db` (papers, paper→lab links,
   typed entities) plus `data/sdl_labs.yaml`, `data/sdl_entities.yaml`,
   `data/method_stages.yaml`.
2. **Wiki** — this folder: interlinked Markdown pages under `wiki/`,
   cataloged in `index.md`, visualized in `graph.html`.
3. **Schema** — this file: layout, naming, front-matter contract, operations.

## Layout

    index.md          catalog: every wiki page, one-liner each, by category
    log.md            append-only ops log; entries are `## [YYYY-MM-DD] <op> | <Title>`
    graph.html        standalone interactive graph (data embedded; open in a browser)
    graph.json        the same nodes+edges data, for programmatic use
    wiki/overview.md  synthesis page: corpus totals, top labs, fastest spreaders
    wiki/labs/        one page per SDL lab
    wiki/methods/     fine-grained methods (grouped by category in index.md)
    wiki/materials/   wiki/instruments/  wiki/software/
    wiki/concepts/    one page per coarse method category (family)

## Naming & links

- Filenames are slugs: lowercase, `-` separators (see `slugify`).
- All intra-wiki references are Obsidian path-style wikilinks relative to the
  vault root, e.g. `[[wiki/labs/matter-lab|Matter Lab]]`,
  `[[wiki/methods/bayesian-optimization|bayesian optimization]]`.
- Graph node ids equal these wikilink paths.

## Front-matter contract

Every wiki page starts with YAML front-matter containing at least `type`
(lab | method | material | instrument | software | concept | overview),
`name`, and `generated`. Typed relations:

- labs: `uses_methods`, `uses_materials`, `uses_instruments`,
  `uses_software`, `collaborates_with`, `paper_count`
- methods: `category` (when known), `aliases`, `used_by_labs`,
  `paper_count`, `stages` ({stage id: mentions}, when stage data exists)
- other entities: `aliases`, `used_by_labs`, `paper_count`
- concepts: `methods` (member fine-grained methods)

## Operations

- **ingest** — rebuild the vault after new papers / extraction runs:
  run the pipeline (entity extraction, lab mapping), then
  `cd backend && python -m app.scripts.export_llm_wiki`.
  Each run appends one `ingest` entry to log.md; wiki pages are regenerated
  in place.
- **query** — answering questions from this vault: read `index.md` first to
  find the right page(s); follow wikilinks; `wiki/overview.md` has the
  headline numbers. Grep is reliable: pages are plain Markdown.
- **lint** — consistency checks: every `[[target]]` should resolve to
  `<target>.md` under the vault root; every wiki page should be listed in
  `index.md`; front-matter must parse as YAML. The exporter regenerates a
  consistent state, so a failing lint means hand edits or a stale export —
  re-run ingest.
"""


def export_llm_wiki(output_dir: Path) -> dict:
    """Write the vault; returns counts for reporting/logging."""
    output_dir.mkdir(parents=True, exist_ok=True)
    for sub in (*TYPE_DIRS.values(), "labs", "concepts"):
        (output_dir / "wiki" / sub).mkdir(parents=True, exist_ok=True)

    with SessionLocal() as session:
        data = _collect(session)

    pages = _build_pages(data)
    for page in pages:
        (output_dir / f"{page['path']}.md").write_text(page["text"], encoding="utf-8")
    (output_dir / "index.md").write_text(_render_index(pages), encoding="utf-8")
    (output_dir / "CLAUDE.md").write_text(CLAUDE_MD, encoding="utf-8")

    graph = _build_graph(data, pages)
    graph_json = json.dumps(graph, ensure_ascii=False, separators=(",", ":"))
    (output_dir / "graph.json").write_text(graph_json, encoding="utf-8")
    (output_dir / "graph.html").write_text(
        GRAPH_HTML_TEMPLATE.replace(
            "/*__GRAPH_DATA__*/ null", graph_json.replace("</", "<\\/")
        ),
        encoding="utf-8",
    )

    summary = data["summary"]
    db_name = settings.database_url.rsplit("/", 1)[-1] or settings.database_url
    entity_total = sum(summary["entities_by_type"].values())
    append_log(
        output_dir / "log.md",
        "ingest",
        f"Rebuilt from {db_name} ({summary['labs']} labs, {entity_total} entities, "
        f"{summary['linked_papers']} linked papers, {len(pages)} wiki pages)",
    )
    return {
        "pages": len(pages),
        "nodes": len(graph["nodes"]),
        "edges": len(graph["edges"]),
        # +4: index.md, CLAUDE.md, graph.html, graph.json (log.md is appended)
        "files": len(pages) + 4,
    }


# ── standalone graph view ────────────────────────────────────────────────────
# Self-contained: data embedded below, ECharts + marked from CDN with a
# graceful fallback, works from file://.

GRAPH_HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>AC Cross-SDL 知识图谱 Knowledge Graph</title>
<script src="https://cdnjs.cloudflare.com/ajax/libs/echarts/5.5.0/echarts.min.js"></script>
<script src="https://cdnjs.cloudflare.com/ajax/libs/marked/12.0.2/marked.min.js"></script>
<style>
  :root {
    --bg: #1e1e2e; --bg2: #24243a; --panel: #181825; --line: #313244;
    --text: #c0caf5; --muted: #7f849c; --accent: #7aa2f7;
  }
  * { box-sizing: border-box; }
  html, body { margin: 0; height: 100%; background: var(--bg); color: var(--text);
    font: 13px/1.5 -apple-system, "Segoe UI", "PingFang SC", "Noto Sans CJK SC", sans-serif; }
  #app { display: flex; flex-direction: column; height: 100%; }
  header { display: flex; align-items: center; gap: 14px; flex-wrap: wrap;
    padding: 10px 16px; border-bottom: 1px solid var(--line); background: var(--bg2); }
  header h1 { font-size: 15px; margin: 0; font-weight: 600; white-space: nowrap; }
  #search { background: var(--panel); border: 1px solid var(--line); color: var(--text);
    border-radius: 6px; padding: 5px 10px; width: 220px; outline: none; }
  #search:focus { border-color: var(--accent); }
  #toggles { display: flex; gap: 10px; flex-wrap: wrap; align-items: center; }
  #toggles label { display: flex; align-items: center; gap: 4px; cursor: pointer;
    color: var(--muted); user-select: none; }
  #toggles input { accent-color: var(--accent); }
  .chip { width: 9px; height: 9px; border-radius: 50%; display: inline-block; }
  #main { flex: 1; display: flex; min-height: 0; }
  #chart { flex: 1; min-width: 0; }
  #panel { width: 380px; max-width: 45%; border-left: 1px solid var(--line);
    background: var(--panel); display: none; flex-direction: column; }
  #panel.open { display: flex; }
  #panel-head { display: flex; align-items: baseline; gap: 8px; padding: 12px 14px 6px; }
  #panel-title { font-size: 15px; font-weight: 600; flex: 1; }
  #panel-type { color: var(--muted); font-size: 11px; }
  #panel-close { cursor: pointer; color: var(--muted); border: none; background: none;
    font-size: 16px; padding: 0 2px; }
  #panel-close:hover { color: var(--text); }
  #panel-body { overflow-y: auto; padding: 0 14px 14px; flex: 1; }
  #panel-body h1 { font-size: 17px; } #panel-body h2 { font-size: 14px; margin-top: 18px; }
  #panel-body h3 { font-size: 13px; }
  #panel-body a.wl { color: var(--accent); text-decoration: none; cursor: pointer; }
  #panel-body a.wl:hover { text-decoration: underline; }
  #panel-body table { border-collapse: collapse; font-size: 12px; }
  #panel-body th, #panel-body td { border: 1px solid var(--line); padding: 3px 7px; }
  #panel-body code { background: var(--bg2); border-radius: 3px; padding: 1px 4px; font-size: 11px; }
  #panel-body pre { white-space: pre-wrap; font-size: 11px; }
  footer { padding: 6px 16px; border-top: 1px solid var(--line); color: var(--muted);
    font-size: 11px; display: flex; gap: 16px; background: var(--bg2); }
  .fallback { padding: 40px; color: var(--muted); max-width: 560px; margin: 0 auto; }
</style>
</head>
<body>
<div id="app">
  <header>
    <h1>AC Cross-SDL 知识图谱 Knowledge Graph</h1>
    <input id="search" type="search" placeholder="搜索 search…">
    <div id="toggles"></div>
  </header>
  <div id="main">
    <div id="chart"></div>
    <aside id="panel">
      <div id="panel-head">
        <span id="panel-title"></span><span id="panel-type"></span>
        <button id="panel-close" title="close">✕</button>
      </div>
      <div id="panel-body"></div>
    </aside>
  </div>
  <footer><span id="stats"></span>
    <span>点击节点查看页面 click a node for its wiki page · 滚轮缩放 scroll to zoom</span>
  </footer>
</div>
<script>
const DATA = /*__GRAPH_DATA__*/ null;

const COLORS = { lab: "#7aa2f7", method: "#bb9af7", material: "#9ece6a",
  instrument: "#e0af68", software: "#2ac3de", concept: "#c0caf5" };
const CAT_PALETTE = ["#bb9af7", "#f7768e", "#ff9e64", "#73daca", "#b4f9f8",
  "#c53b53", "#41a6b5", "#ffc777", "#4fd6be", "#fca7ea"];
const TYPE_LABELS = { lab: "实验室 labs", method: "方法 methods",
  material: "材料 materials", instrument: "仪器 instruments",
  software: "软件 software", concept: "概念 concepts" };

function colorFor(n) {
  if (n.type === "method" && n.category) {
    return CAT_PALETTE[DATA.categories.indexOf(n.category) % CAT_PALETTE.length];
  }
  return COLORS[n.type] || "#888";
}

const byId = {};
DATA.nodes.forEach(n => { byId[n.id] = n; });
const presentTypes = [...new Set(DATA.nodes.map(n => n.type))]
  .sort((a, b) => Object.keys(COLORS).indexOf(a) - Object.keys(COLORS).indexOf(b));
const hasAdoption = DATA.edges.some(e => e.type === "adoption");
const state = { query: "", types: {}, adoption: true };
presentTypes.forEach(t => { state.types[t] = true; });

// type toggles + legend chips
const togglesEl = document.getElementById("toggles");
function addToggle(key, text, color) {
  const label = document.createElement("label");
  const box = document.createElement("input");
  box.type = "checkbox"; box.checked = true;
  box.addEventListener("change", () => {
    if (key === "adoption") state.adoption = box.checked;
    else state.types[key] = box.checked;
    render();
  });
  label.appendChild(box);
  if (color) {
    const chip = document.createElement("span");
    chip.className = "chip"; chip.style.background = color;
    label.appendChild(chip);
  }
  label.appendChild(document.createTextNode(text));
  togglesEl.appendChild(label);
}
presentTypes.forEach(t => addToggle(t, TYPE_LABELS[t] || t, COLORS[t]));
if (hasAdoption) addToggle("adoption", "采纳 adoption edges", "#f7768e");

function visible() {
  const nodes = DATA.nodes.filter(n => state.types[n.type]);
  const ids = new Set(nodes.map(n => n.id));
  const edges = DATA.edges.filter(e => ids.has(e.source) && ids.has(e.target)
    && (e.type !== "adoption" || state.adoption));
  return { nodes, edges };
}

function edgeStyle(e) {
  if (e.type === "adoption") return { type: "dashed", color: "#f7768e",
    width: 1.6, opacity: 0.85, curveness: 0.25 };
  if (e.type === "collab") return { color: "#7aa2f7",
    width: Math.min(1 + e.weight / 2, 4), opacity: 0.5, curveness: 0.1 };
  if (e.type === "member") return { color: "#565f89", width: 1, opacity: 0.5, curveness: 0.1 };
  return { color: "#3b4261", width: Math.min(0.5 + e.weight / 2, 3),
    opacity: 0.45, curveness: 0.05 };
}

function buildOption() {
  const { nodes, edges } = visible();
  const q = state.query.trim().toLowerCase();
  const match = n => !q || n.label.toLowerCase().includes(q);
  return {
    backgroundColor: "transparent",
    tooltip: {
      backgroundColor: "#181825", borderColor: "#313244", textStyle: { color: "#c0caf5" },
      formatter: p => {
        if (p.dataType === "edge") {
          const e = p.data.raw;
          return e.type + (e.entity ? ": " + e.entity : "") + (e.weight > 1 ? " (" + e.weight + ")" : "");
        }
        const n = p.data.raw;
        return "<b>" + n.label + "</b><br>" + n.type +
          (n.category ? " · " + n.category : "") +
          (n.papers != null ? " · " + n.papers + " papers" : "");
      },
    },
    series: [{
      type: "graph", layout: "force", roam: true,
      force: { repulsion: 140, gravity: 0.12, edgeLength: [40, 160], friction: 0.15 },
      scaleLimit: { min: 0.3, max: 12 },
      emphasis: { focus: "adjacency", label: { show: true } },
      label: { color: "#c0caf5", fontSize: 10, position: "right" },
      lineStyle: { curveness: 0.05 },
      data: nodes.map(n => ({
        id: n.id, name: n.label, symbolSize: n.size, raw: n,
        itemStyle: { color: colorFor(n), shadowBlur: 14, shadowColor: colorFor(n),
          opacity: match(n) ? 1 : 0.07 },
        label: { show: match(n) && (n.type === "lab" || n.type === "concept" || !!q) },
      })),
      edges: edges.map(e => ({ source: e.source, target: e.target, raw: e,
        lineStyle: edgeStyle(e) })),
    }],
  };
}

// side panel: render the node's wiki page; wikilinks resolve to graph nodes
const panel = document.getElementById("panel");
const panelBody = document.getElementById("panel-body");
function mdToHtml(md) {
  md = md.replace(/\\[\\[([^\\]|]+)\\|([^\\]]+)\\]\\]/g,
        (m, p, t) => '<a class="wl" data-id="' + p + '">' + t + "</a>")
      .replace(/\\[\\[([^\\]]+)\\]\\]/g,
        (m, p) => '<a class="wl" data-id="' + p + '">' + p + "</a>");
  if (window.marked) return marked.parse(md);
  const pre = document.createElement("pre");
  pre.textContent = md;
  return pre.outerHTML;
}
function openPanel(node) {
  document.getElementById("panel-title").textContent = node.label;
  document.getElementById("panel-type").textContent =
    node.type + (node.category ? " · " + node.category : "");
  panelBody.innerHTML = mdToHtml(node.md || "*No page body.*");
  panel.classList.add("open");
  panelBody.scrollTop = 0;
  if (window.chart) chart.resize();
}
document.getElementById("panel-close").addEventListener("click", () => {
  panel.classList.remove("open");
  if (window.chart) chart.resize();
});
panelBody.addEventListener("click", ev => {
  const a = ev.target.closest("a.wl");
  if (!a) return;
  ev.preventDefault();
  focusNode(a.dataset.id);
});
function focusNode(id) {
  const node = byId[id];
  if (!node) return;
  if (!state.types[node.type]) {
    state.types[node.type] = true;
    [...togglesEl.querySelectorAll("label")].forEach(l => {
      if (l.textContent === (TYPE_LABELS[node.type] || node.type)) {
        l.querySelector("input").checked = true;
      }
    });
    render();
  }
  openPanel(node);
  if (window.chart) {
    const idx = visible().nodes.findIndex(n => n.id === id);
    if (idx >= 0) {
      chart.dispatchAction({ type: "downplay", seriesIndex: 0 });
      chart.dispatchAction({ type: "highlight", seriesIndex: 0, dataIndex: idx });
    }
  }
}

function render() {
  const { nodes, edges } = visible();
  document.getElementById("stats").textContent =
    nodes.length + " 节点 nodes · " + edges.length + " 边 edges · generated " + DATA.generated;
  if (window.chart) chart.setOption(buildOption(), { notMerge: true });
}

document.getElementById("search").addEventListener("input", ev => {
  state.query = ev.target.value;
  render();
});

if (typeof echarts === "undefined") {
  document.getElementById("chart").innerHTML =
    '<div class="fallback"><b>图表库加载失败 / chart library unavailable.</b><br><br>' +
    "ECharts is loaded from a CDN; offline it cannot render. The data is still " +
    "here: " + DATA.nodes.length + " nodes / " + DATA.edges.length + " edges — see " +
    "<code>graph.json</code> and the Markdown pages under <code>wiki/</code>.</div>";
  render();
} else {
  window.chart = echarts.init(document.getElementById("chart"), null, { renderer: "canvas" });
  chart.on("click", p => { if (p.dataType === "node") openPanel(p.data.raw); });
  window.addEventListener("resize", () => chart.resize());
  render();
}
</script>
</body>
</html>
"""


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args()

    stats = export_llm_wiki(args.output_dir)
    print(
        f"Wrote llm-wiki vault to {args.output_dir}: {stats['pages']} wiki pages, "
        f"graph with {stats['nodes']} nodes / {stats['edges']} edges"
    )


if __name__ == "__main__":
    main()
