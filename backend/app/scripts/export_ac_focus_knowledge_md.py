"""Export AC focused publications into per-paper knowledge files.

This is a branch-style utility: it reads the curated AC Publications focused
CSV, optionally enriches rows with cross-SDL reasoning extraction JSON, and
writes a canonical JSON plus a Markdown page for each paper.

Usage:
    python -m app.scripts.export_ac_focus_knowledge_md --limit 10
"""
from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterable

from app.config import DATA_DIR, REPO_ROOT

DEFAULT_CSV = DATA_DIR / "ac_publications_focused_grid_view.csv.gz"
DEFAULT_CROSS_SDL_ROOT = REPO_ROOT.parent / "cross-sdl_knowledge_transfer_engine"
DEFAULT_OUTPUT_DIR = REPO_ROOT / "outputs" / "ac_focus_knowledge_md"
DEFAULT_JSON_DIRNAME = "knowledge_json"


@dataclass(frozen=True)
class AcFocusPaper:
    key: str
    title: str
    doi: str
    url: str
    year: str
    authors: str
    ac_members: str
    venue: str
    category: str
    peer_reviewed: str
    summary: str
    abstract: str
    ac_programs: str
    membership_status: str
    sdl: str
    research_tags: str
    applied_tags: str
    high_impact: str
    highly_relevant: str
    acknowledges_ac: str

    @property
    def paper_id(self) -> str:
        seed = normalize_doi(self.doi) or normalize_title(self.title) or self.key
        return "acfocus_" + hashlib.sha1(seed.encode("utf-8")).hexdigest()[:12]


@dataclass(frozen=True)
class ExtractionItem:
    value: str
    source: str
    confidence: float
    evidence: str = ""


@dataclass(frozen=True)
class ValidationReport:
    score: float
    coverage: dict[str, bool]
    missing: list[str]
    notes: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class AcPaperKnowledge:
    paper_id: str
    title: str
    metadata: dict[str, Any]
    source_summary: str
    abstract: str
    hardware: list[ExtractionItem]
    methods: list[ExtractionItem]
    problems: list[ExtractionItem]
    hypotheses: list[ExtractionItem]
    evidence: list[ExtractionItem]
    conclusions: list[ExtractionItem]
    entities: list[ExtractionItem]
    materials: list[ExtractionItem]
    properties: list[ExtractionItem]
    measurements: list[ExtractionItem]
    conditions: list[ExtractionItem]
    mechanisms: list[ExtractionItem]
    outcomes: list[ExtractionItem]
    sdl_tags: list[str]
    reasoning_motifs: list[ExtractionItem]
    general_principles: list[ExtractionItem]
    failure_paths: list[ExtractionItem]
    provenance: dict[str, Any]
    validation: ValidationReport


def normalize_doi(value: str | None) -> str:
    doi = (value or "").strip().lower()
    doi = re.sub(r"^https?://(?:dx\.)?doi\.org/", "", doi)
    doi = doi.removeprefix("doi:")
    return doi.strip()


def normalize_title(value: str | None) -> str:
    title = (value or "").lower()
    title = re.sub(r"[^a-z0-9]+", " ", title)
    return " ".join(title.split())


def slugify(value: str, fallback: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", value).strip("-").lower()
    slug = re.sub(r"-{2,}", "-", slug)
    return (slug or fallback)[:90]


def split_list(value: str | None) -> list[str]:
    if not value:
        return []
    parts = re.split(r"[,;|]", value)
    return [p.strip() for p in parts if p.strip()]


def load_ac_focus_csv(csv_path: Path) -> list[AcFocusPaper]:
    opener = gzip.open if csv_path.suffix == ".gz" else open
    with opener(csv_path, "rt", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        return [
            AcFocusPaper(
                key=(row.get("Key") or "").strip(),
                title=(row.get("Title") or "").strip(),
                doi=normalize_doi(row.get("DOI")),
                url=(row.get("Url") or "").strip(),
                year=(row.get("Publication Year") or "").strip(),
                authors=(row.get("Author") or row.get("Short author list") or "").strip(),
                ac_members=(row.get("AC Members") or "").strip(),
                venue=(row.get("Publication Title") or row.get("Short Journal Name") or "").strip(),
                category=(row.get("Catagory") or "").strip(),
                peer_reviewed=(row.get("Peer Reviewed") or "").strip(),
                summary=(row.get("One sentence summary") or "").strip(),
                abstract=(row.get("Abstract Note") or "").strip(),
                ac_programs=(row.get("AC Funded Programs") or "").strip(),
                membership_status=(row.get("Membership status (from AC Members)") or "").strip(),
                sdl=(row.get("SDL") or "").strip(),
                research_tags=(row.get("Research Tags") or "").strip(),
                applied_tags=(row.get("Applied Tags") or "").strip(),
                high_impact=(row.get("High Impact") or "").strip(),
                highly_relevant=(row.get("Highly Relevant") or "").strip(),
                acknowledges_ac=(row.get("Acknowledges AC") or "").strip(),
            )
            for row in reader
            if (row.get("Title") or "").strip()
        ]


def load_cross_sdl_index(
    manifest_path: Path | None,
    reasoning_dir: Path | None,
) -> dict[str, dict[str, Any]]:
    """Return DOI/title lookup entries pointing to cross-SDL JSON when present."""
    index: dict[str, dict[str, Any]] = {}
    manifest: list[dict[str, Any]] = []
    if manifest_path and manifest_path.exists():
        manifest = json.loads(manifest_path.read_text())

    for item in manifest:
        paper_id = item.get("paper_id") or ""
        reasoning_path = reasoning_dir / f"{paper_id}.json" if reasoning_dir else None
        entry = {
            "paper_id": paper_id,
            "phase0": item,
            "reasoning_path": str(reasoning_path) if reasoning_path and reasoning_path.exists() else "",
        }
        doi = normalize_doi(item.get("doi"))
        title = normalize_title(item.get("title"))
        if doi:
            index[f"doi:{doi}"] = entry
        if title:
            index[f"title:{title}"] = entry

    if reasoning_dir and reasoning_dir.exists():
        for path in reasoning_dir.glob("*.json"):
            if path.name == "corpus_manifest.json":
                continue
            try:
                data = json.loads(path.read_text())
            except json.JSONDecodeError:
                continue
            phase0 = data.get("phase0") or {}
            entry = {
                "paper_id": data.get("paper_id") or path.stem,
                "phase0": phase0,
                "reasoning_path": str(path),
            }
            doi = normalize_doi(phase0.get("doi"))
            title = normalize_title(phase0.get("title"))
            if doi:
                index[f"doi:{doi}"] = entry
            if title:
                index[f"title:{title}"] = entry
    return index


def match_cross_sdl(paper: AcFocusPaper, index: dict[str, dict[str, Any]]) -> dict[str, Any] | None:
    if paper.doi:
        hit = index.get(f"doi:{paper.doi}")
        if hit:
            return hit
    title = normalize_title(paper.title)
    return index.get(f"title:{title}") if title else None


def load_reasoning(match: dict[str, Any] | None) -> dict[str, Any] | None:
    if not match or not match.get("reasoning_path"):
        return None
    path = Path(match["reasoning_path"])
    if not path.exists():
        return None
    return json.loads(path.read_text())


def _pick_sentences(text: str, patterns: Iterable[str], limit: int = 4) -> list[str]:
    if not text:
        return []
    sentences = re.split(r"(?<=[.!?])\s+", text.strip())
    hits: list[str] = []
    for sentence in sentences:
        lowered = sentence.lower()
        if any(re.search(pattern, lowered) for pattern in patterns):
            hits.append(sentence.strip())
        if len(hits) >= limit:
            break
    return hits


def _items(values: Iterable[str], source: str, confidence: float, evidence: str = "") -> list[ExtractionItem]:
    seen: set[str] = set()
    items: list[ExtractionItem] = []
    for raw in values:
        value = str(raw or "").strip()
        if not value or value in seen:
            continue
        seen.add(value)
        items.append(ExtractionItem(value=value, source=source, confidence=confidence, evidence=evidence))
    return items


def infer_hardware(paper: AcFocusPaper, reasoning: dict[str, Any] | None) -> list[str]:
    text_parts = [paper.summary, paper.abstract]
    phase1 = (reasoning or {}).get("phase1") or {}
    if phase1.get("method"):
        text_parts.append(str(phase1["method"]))
    text = " ".join(part for part in text_parts if part)
    patterns = [
        r"\brobot(?:ic|s)?\b",
        r"\bplatform\b",
        r"\bprinter\b",
        r"\bmicroscope\b",
        r"\bspectro(?:meter|scopy)\b",
        r"\breactor\b",
        r"\bworkstation\b",
        r"\bopentrons\b",
        r"\bautonomous\b",
        r"\bhigh-throughput\b",
        r"\bautomated\b",
        r"\bcontinuous printing\b",
    ]
    return _pick_sentences(text, patterns)


def _paper_text(paper: AcFocusPaper, reasoning: dict[str, Any] | None) -> str:
    phase1 = (reasoning or {}).get("phase1") or {}
    phase2 = (reasoning or {}).get("phase2") or {}
    parts = [
        paper.title,
        paper.summary,
        paper.abstract,
        str(phase1.get("method") or ""),
        str(phase1.get("evidence") or ""),
        " ".join(phase2.get("entities") or []),
        " ".join(phase2.get("outcomes") or []),
    ]
    return " ".join(part for part in parts if part)


def infer_materials(paper: AcFocusPaper, reasoning: dict[str, Any] | None) -> list[str]:
    phase2 = (reasoning or {}).get("phase2") or {}
    material_pattern = re.compile(
        r"\b(materials?|alloys?|polymers?|membranes?|catalysts?|electrolytes?|molecules?|"
        r"compounds?|ceramics?|perovskites?|nanoparticles?|proteins?|cells?|ions?|metals?|"
        r"semiconductors?)\b"
    )
    entity_candidates = [
        value for value in (phase2.get("entities") or [])
        if material_pattern.search(value.lower())
    ]
    text_hits = _pick_sentences(
        _paper_text(paper, reasoning),
        [
            r"\bmaterial(?:s)?\b",
            r"\balloy(?:s)?\b",
            r"\bpolymer(?:s)?\b",
            r"\bmembrane(?:s)?\b",
            r"\bcatalyst(?:s)?\b",
            r"\belectrolyte(?:s)?\b",
            r"\bperovskite(?:s)?\b",
            r"\bceramic(?:s)?\b",
            r"\bmolecule(?:s)?\b",
            r"\bsemiconductor(?:s)?\b",
        ],
        limit=3,
    )
    return entity_candidates + text_hits


def infer_properties(paper: AcFocusPaper, reasoning: dict[str, Any] | None) -> list[str]:
    return _pick_sentences(
        _paper_text(paper, reasoning),
        [
            r"\bpropert(?:y|ies)\b",
            r"\bstability\b",
            r"\bconductivity\b",
            r"\bmobility\b",
            r"\bactivity\b",
            r"\bselectivity\b",
            r"\bband gap\b",
            r"\benergy\b",
            r"\baccuracy\b",
            r"\byield\b",
            r"\bstiffness\b",
            r"\bporosity\b",
            r"\bd\s*[_-]?\s*33\b",
            r"\bcoefficient\b",
        ],
        limit=5,
    )


def infer_measurements(paper: AcFocusPaper, reasoning: dict[str, Any] | None) -> list[str]:
    return _pick_sentences(
        _paper_text(paper, reasoning),
        [
            r"\bmeasurement(?:s)?\b",
            r"\bcharacteri[sz]ation\b",
            r"\bspectroscop(?:y|ic)\b",
            r"\bmicroscop(?:y|ic)\b",
            r"\bnmr\b",
            r"\bx-ray\b",
            r"\bxrd\b",
            r"\beds\b",
            r"\bcompression testing\b",
            r"\bstress-strain\b",
            r"\bbenchmark(?:ed|ing)?\b",
            r"\btested\b",
        ],
        limit=5,
    )


def infer_conditions(paper: AcFocusPaper, reasoning: dict[str, Any] | None) -> list[str]:
    return _pick_sentences(
        _paper_text(paper, reasoning),
        [
            r"\btemperature\b",
            r"\bpressure\b",
            r"\bhumidity\b",
            r"\bconcentration\b",
            r"\bph\b",
            r"\bvoltage\b",
            r"\bcurrent\b",
            r"\btime\b",
            r"\brate\b",
            r"\batmosphere\b",
            r"\bcondition(?:s)?\b",
        ],
        limit=5,
    )


def method_values(paper: AcFocusPaper, reasoning: dict[str, Any] | None) -> list[str]:
    phase1 = (reasoning or {}).get("phase1") or {}
    if phase1.get("method"):
        return [str(phase1["method"]).strip()]
    if paper.summary:
        return [paper.summary]
    abstract = paper.abstract[:800].strip()
    return [abstract] if abstract else []


def validate_knowledge(
    *,
    hardware: list[ExtractionItem],
    methods: list[ExtractionItem],
    evidence: list[ExtractionItem],
    entities: list[ExtractionItem],
    materials: list[ExtractionItem],
    properties: list[ExtractionItem],
    measurements: list[ExtractionItem],
    conditions: list[ExtractionItem],
    mechanisms: list[ExtractionItem],
    outcomes: list[ExtractionItem],
    source_summary: str,
    abstract: str,
    has_cross_sdl_match: bool,
) -> ValidationReport:
    coverage = {
        "source_summary": bool(source_summary),
        "abstract": bool(abstract),
        "hardware": bool(hardware),
        "method": bool(methods),
        "evidence": bool(evidence),
        "entities": bool(entities),
        "materials": bool(materials),
        "properties": bool(properties),
        "measurements": bool(measurements),
        "conditions": bool(conditions),
        "mechanisms": bool(mechanisms),
        "outcomes": bool(outcomes),
        "cross_sdl_match": has_cross_sdl_match,
    }
    weights = {
        "source_summary": 0.08,
        "abstract": 0.10,
        "hardware": 0.10,
        "method": 0.12,
        "evidence": 0.10,
        "entities": 0.07,
        "materials": 0.07,
        "properties": 0.07,
        "measurements": 0.06,
        "conditions": 0.04,
        "mechanisms": 0.08,
        "outcomes": 0.06,
        "cross_sdl_match": 0.05,
    }
    score = round(sum(weights[k] for k, present in coverage.items() if present), 2)
    missing = [k for k, present in coverage.items() if not present]
    notes: list[str] = []
    if not has_cross_sdl_match:
        notes.append("No cross-SDL extraction matched this paper; fields are derived from CSV only.")
    if "hardware" in missing or "method" in missing:
        notes.append("Full-text or LLM extraction is needed for reliable hardware/method coverage.")
    return ValidationReport(score=score, coverage=coverage, missing=missing, notes=notes)


def build_knowledge(
    paper: AcFocusPaper,
    match: dict[str, Any] | None = None,
    reasoning: dict[str, Any] | None = None,
) -> AcPaperKnowledge:
    phase0 = (reasoning or {}).get("phase0") or (match or {}).get("phase0") or {}
    phase1 = (reasoning or {}).get("phase1") or {}
    phase2 = (reasoning or {}).get("phase2") or {}
    phase3 = (reasoning or {}).get("phase3") or {}
    phase4 = (reasoning or {}).get("phase4") or {}
    hardware = _items(infer_hardware(paper, reasoning), "heuristic_text_scan", 0.55)
    methods = _items(
        method_values(paper, reasoning),
        "cross_sdl_phase1" if phase1.get("method") else "csv_summary_or_abstract",
        0.82 if phase1.get("method") else 0.45,
    )
    problems = _items([phase1.get("problem", "")], "cross_sdl_phase1", 0.82)
    hypotheses = _items([phase1.get("hypothesis", "")], "cross_sdl_phase1", 0.82)
    evidence_items = _items([phase1.get("evidence", "")], "cross_sdl_phase1", 0.82)
    conclusions = _items([phase1.get("conclusion", "")], "cross_sdl_phase1", 0.82)
    entities = _items(
        phase2.get("entities") or split_list(paper.research_tags),
        "cross_sdl_phase2" if phase2.get("entities") else "csv_research_tags",
        0.82 if phase2.get("entities") else 0.45,
    )
    materials = _items(infer_materials(paper, reasoning), "heuristic_text_scan", 0.55)
    properties = _items(infer_properties(paper, reasoning), "heuristic_text_scan", 0.55)
    measurements = _items(infer_measurements(paper, reasoning), "heuristic_text_scan", 0.55)
    conditions = _items(infer_conditions(paper, reasoning), "heuristic_text_scan", 0.55)
    mechanisms = _items(phase2.get("mechanisms") or [], "cross_sdl_phase2", 0.82)
    outcomes = _items(
        phase2.get("outcomes") or split_list(paper.applied_tags),
        "cross_sdl_phase2" if phase2.get("outcomes") else "csv_applied_tags",
        0.82 if phase2.get("outcomes") else 0.45,
    )
    motifs = _items(phase3.get("layer3_motifs") or [], "cross_sdl_phase3", 0.82)
    principles = _items(phase3.get("layer4_principles") or [], "cross_sdl_phase3", 0.82)
    attempts = phase4.get("attempts") or []
    failure_paths = _items(
        [
            f"{attempt.get('result', 'unknown')}: {attempt.get('description', '')} Evidence: {attempt.get('evidence', '')}"
            for attempt in attempts
        ],
        "cross_sdl_phase4",
        0.75,
    )
    source_summary = paper.summary
    abstract = paper.abstract or str(phase0.get("abstract", ""))[:2000]
    sdl_tags = list(dict.fromkeys(
        split_list(paper.sdl) + split_list(paper.research_tags) + split_list(paper.applied_tags)
    ))
    provenance = {
        "csv_source": str(DEFAULT_CSV.relative_to(REPO_ROOT) if DEFAULT_CSV.exists() else DEFAULT_CSV),
        "cross_sdl_id": (match or {}).get("paper_id", ""),
        "cross_sdl_reasoning_json": (match or {}).get("reasoning_path", ""),
        "cross_sdl_extraction_quality": (reasoning or {}).get("extraction_quality"),
        "cross_sdl_notes": (reasoning or {}).get("extraction_notes", ""),
    }
    validation = validate_knowledge(
        hardware=hardware,
        methods=methods,
        evidence=evidence_items,
        entities=entities,
        materials=materials,
        properties=properties,
        measurements=measurements,
        conditions=conditions,
        mechanisms=mechanisms,
        outcomes=outcomes,
        source_summary=source_summary,
        abstract=abstract,
        has_cross_sdl_match=bool(match),
    )

    return AcPaperKnowledge(
        paper_id=paper.paper_id,
        title=paper.title,
        metadata={
            "doi": paper.doi,
            "url": paper.url,
            "year": paper.year or phase0.get("year"),
            "authors": paper.authors,
            "venue": paper.venue,
            "category": paper.category,
            "peer_reviewed": paper.peer_reviewed,
            "ac_members": split_list(paper.ac_members),
            "ac_programs": split_list(paper.ac_programs),
            "membership_status": split_list(paper.membership_status),
            "flags": {
                "acknowledges_ac": paper.acknowledges_ac or "blank",
                "highly_relevant": paper.highly_relevant or "blank",
                "high_impact": paper.high_impact or "blank",
            },
        },
        source_summary=source_summary,
        abstract=abstract,
        hardware=hardware,
        methods=methods,
        problems=problems,
        hypotheses=hypotheses,
        evidence=evidence_items,
        conclusions=conclusions,
        entities=entities,
        materials=materials,
        properties=properties,
        measurements=measurements,
        conditions=conditions,
        mechanisms=mechanisms,
        outcomes=outcomes,
        sdl_tags=sdl_tags,
        reasoning_motifs=motifs,
        general_principles=principles,
        failure_paths=failure_paths,
        provenance=provenance,
        validation=validation,
    )


def _item_values(items: list[ExtractionItem], fallback: str) -> list[str]:
    return [item.value for item in items] if items else [fallback]


def knowledge_to_dict(knowledge: AcPaperKnowledge) -> dict[str, Any]:
    return asdict(knowledge)


def render_markdown_from_knowledge(knowledge: AcPaperKnowledge) -> str:
    metadata = knowledge.metadata
    flags = metadata.get("flags", {})
    provenance = knowledge.provenance

    lines = [
        f"# {knowledge.title}",
        "",
        "## Metadata",
        f"- Paper ID: `{knowledge.paper_id}`",
        f"- Cross-SDL ID: `{provenance.get('cross_sdl_id') or 'not matched'}`",
        f"- DOI: {metadata.get('doi') or 'Not specified'}",
        f"- URL: {metadata.get('url') or 'Not specified'}",
        f"- Year: {metadata.get('year') or 'Not specified'}",
        f"- Authors: {metadata.get('authors') or 'Not specified'}",
        f"- Venue: {metadata.get('venue') or 'Not specified'}",
        f"- Category: {metadata.get('category') or 'Not specified'}",
        f"- Peer reviewed: {metadata.get('peer_reviewed') or 'Not specified'}",
        f"- AC members: {', '.join(metadata.get('ac_members') or []) or 'Not specified'}",
        f"- AC programs: {', '.join(metadata.get('ac_programs') or []) or 'Not specified'}",
        f"- AC membership status: {', '.join(metadata.get('membership_status') or []) or 'Not specified'}",
        f"- Flags: acknowledges_ac={flags.get('acknowledges_ac', 'blank')}, highly_relevant={flags.get('highly_relevant', 'blank')}, high_impact={flags.get('high_impact', 'blank')}",
        "",
        "## Validation",
        f"- Score: {knowledge.validation.score}",
        f"- Missing: {', '.join(knowledge.validation.missing) or 'none'}",
        f"- Notes: {'; '.join(knowledge.validation.notes) or 'No validation notes.'}",
        "",
        "## Source Summary",
        knowledge.source_summary or "Not specified in CSV.",
        "",
        "## Abstract",
        knowledge.abstract or "Not specified in CSV/cross-SDL corpus.",
        "",
        "## Scientific Elements",
        "### Hardware / Physical System",
    ]
    lines.extend(f"- {item}" for item in _item_values(
        knowledge.hardware, "Not specified in the available CSV/cross-SDL text."
    ))

    lines.extend([
        "",
        "### Method",
        "\n".join(f"- {item}" for item in _item_values(knowledge.methods, "Not specified.")),
        "",
        "### Problem",
        "\n".join(f"- {item}" for item in _item_values(knowledge.problems, "Not specified by cross-SDL extraction.")),
        "",
        "### Hypothesis",
        "\n".join(f"- {item}" for item in _item_values(knowledge.hypotheses, "Not specified by cross-SDL extraction.")),
        "",
        "### Evidence",
        "\n".join(f"- {item}" for item in _item_values(knowledge.evidence, "Not specified by cross-SDL extraction.")),
        "",
        "### Conclusion",
        "\n".join(f"- {item}" for item in _item_values(knowledge.conclusions, "Not specified by cross-SDL extraction.")),
        "",
        "## Scientific Objects And Mechanisms",
        "### Entities",
    ])
    lines.extend(f"- {item}" for item in _item_values(knowledge.entities, "Not specified."))

    lines.append("")
    lines.append("### Materials / Systems")
    lines.extend(f"- {item}" for item in _item_values(knowledge.materials, "Not specified."))

    lines.append("")
    lines.append("### Properties")
    lines.extend(f"- {item}" for item in _item_values(knowledge.properties, "Not specified."))

    lines.append("")
    lines.append("### Measurements")
    lines.extend(f"- {item}" for item in _item_values(knowledge.measurements, "Not specified."))

    lines.append("")
    lines.append("### Conditions")
    lines.extend(f"- {item}" for item in _item_values(knowledge.conditions, "Not specified."))

    lines.append("")
    lines.append("### Mechanisms")
    lines.extend(f"- {item}" for item in _item_values(knowledge.mechanisms, "Not specified."))

    lines.append("")
    lines.append("### Outcomes")
    lines.extend(f"- {item}" for item in _item_values(knowledge.outcomes, "Not specified."))

    lines.extend([
        "",
        "## Cross-SDL Transfer",
        "### SDL / Domain Tags",
    ])
    lines.extend(f"- {item}" for item in knowledge.sdl_tags) if knowledge.sdl_tags else lines.append("- Not specified.")

    lines.append("")
    lines.append("### Reasoning Motifs")
    lines.extend(f"- {item}" for item in _item_values(
        knowledge.reasoning_motifs, "Not specified by cross-SDL extraction."
    ))

    lines.append("")
    lines.append("### General Principles")
    lines.extend(f"- {item}" for item in _item_values(
        knowledge.general_principles, "Not specified by cross-SDL extraction."
    ))

    lines.append("")
    lines.append("## Failure Paths / Caveats")
    lines.extend(f"- {item}" for item in _item_values(
        knowledge.failure_paths, "No explicit failure path available in CSV/cross-SDL extraction."
    ))
    lines.extend([
        "",
        "## Extraction Provenance",
        f"- CSV source: `{provenance.get('csv_source')}`",
        f"- Cross-SDL reasoning JSON: `{provenance.get('cross_sdl_reasoning_json') or 'not available'}`",
        f"- Cross-SDL extraction quality: {provenance.get('cross_sdl_extraction_quality') if provenance.get('cross_sdl_extraction_quality') is not None else 'not available'}",
        f"- Notes: {provenance.get('cross_sdl_notes') or 'No additional notes.'}",
        "",
    ])
    return "\n".join(lines)


def render_markdown(
    paper: AcFocusPaper,
    match: dict[str, Any] | None = None,
    reasoning: dict[str, Any] | None = None,
) -> str:
    return render_markdown_from_knowledge(build_knowledge(paper, match, reasoning))


def export_markdown(
    csv_path: Path = DEFAULT_CSV,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    cross_sdl_root: Path = DEFAULT_CROSS_SDL_ROOT,
    limit: int | None = None,
    force: bool = False,
) -> tuple[int, int]:
    papers = load_ac_focus_csv(csv_path)
    if limit is not None:
        papers = papers[:limit]

    reasoning_dir = cross_sdl_root / "data" / "reasoning"
    manifest_path = reasoning_dir / "corpus_manifest.json"
    index = load_cross_sdl_index(manifest_path, reasoning_dir)

    output_dir.mkdir(parents=True, exist_ok=True)
    json_dir = output_dir / DEFAULT_JSON_DIRNAME
    json_dir.mkdir(parents=True, exist_ok=True)
    matched = 0
    index_lines = ["# AC Focus Knowledge Files", ""]
    for i, paper in enumerate(papers, 1):
        match = match_cross_sdl(paper, index)
        reasoning = load_reasoning(match)
        if match:
            matched += 1
        filename = f"{i:03d}-{slugify(paper.title, paper.paper_id)}.md"
        json_filename = f"{i:03d}-{slugify(paper.title, paper.paper_id)}.json"
        knowledge = build_knowledge(paper, match, reasoning)
        out_path = output_dir / filename
        json_path = json_dir / json_filename
        if not out_path.exists() or force:
            out_path.write_text(render_markdown_from_knowledge(knowledge), encoding="utf-8")
        if not json_path.exists() or force:
            json_path.write_text(
                json.dumps(knowledge_to_dict(knowledge), ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        index_lines.append(
            f"- [{paper.title}]({filename})"
            f" — {paper.year or 'n.d.'}; cross-SDL: {(match or {}).get('paper_id', 'not matched')};"
            f" validation: {knowledge.validation.score}; JSON: [{json_filename}]({DEFAULT_JSON_DIRNAME}/{json_filename})"
        )

    (output_dir / "index.md").write_text("\n".join(index_lines) + "\n", encoding="utf-8")
    return len(papers), matched


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--csv", type=Path, default=DEFAULT_CSV)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--cross-sdl-root", type=Path, default=DEFAULT_CROSS_SDL_ROOT)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    total, matched = export_markdown(
        csv_path=args.csv,
        output_dir=args.output_dir,
        cross_sdl_root=args.cross_sdl_root,
        limit=args.limit,
        force=args.force,
    )
    print(f"Exported {total} Markdown files to {args.output_dir}")
    print(f"Matched {matched} papers to cross-SDL reasoning/corpus metadata")


if __name__ == "__main__":
    main()
