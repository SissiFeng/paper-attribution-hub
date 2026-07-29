"""Evolutionary cross-SDL transfer search.

This layer sits above transfer_designer. Instead of drafting one proposal from
the top-k TKU matches, it treats combinations of TKUs as a small design
population, recombines them, and keeps a trace that can be exported into the
llm-wiki vault for later agent self-search.
"""
from __future__ import annotations

import json
import random
import re
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from itertools import combinations
from pathlib import Path
from statistics import mean

import yaml
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.config import REPO_ROOT
from app.models import TransferKnowledgeUnit
from app.scripts.export_kb_md import slugify
from app.services.ontology_service import (
    build_proposed_claim,
    evaluate_candidate_compatibility,
    ontology_gate_readiness,
    ontology_summary,
)
from app.services.transfer_designer import load_target, match_tkus

AUTOSEARCH_DIR = REPO_ROOT / "llm-wiki" / "autosearch"
KNOWLEDGE_JSON_DIR = REPO_ROOT / "outputs" / "ac_focus_knowledge_md" / "knowledge_json"


@dataclass(frozen=True)
class EvolutionConfig:
    target_id: str
    source_domain: str | None = None
    source_pool: int = 24
    population_size: int = 12
    generations: int = 6
    genome_size: int = 3
    mutation_rate: float = 0.35
    seed: int = 7
    include_knowledge_json: bool = True
    ontology_gate: bool = False


@dataclass(frozen=True)
class SourceTku:
    source_domain: str
    problem_signature: dict
    method_core: dict
    assumptions: list
    lessons: list
    domain_bindings: list


@dataclass(frozen=True)
class Candidate:
    id: str
    paper_ids: tuple[str, ...]
    score: float
    components: dict[str, float]
    hypothesis: str
    transfer_plan: list[str]
    assumptions_to_test: list[str]
    risks: list[str]
    citations: list[str]
    ontology_compatibility: dict
    knowledge_claim: dict


def run_evolutionary_transfer_search(
    session: Session,
    config: EvolutionConfig,
) -> dict:
    """Run a deterministic GA-style search over TKU combinations."""
    config = _normalize_config(config)
    target = load_target(config.target_id)
    if target is None:
        raise ValueError(f"Unknown transfer target '{config.target_id}'")
    readiness = ontology_gate_readiness(target)
    if config.ontology_gate and not readiness["ready"]:
        raise ValueError(
            f"Ontology gate is not ready for '{config.target_id}': "
            + "; ".join(readiness["reasons"])
        )

    matches = _source_matches(session, target, config)
    if not matches:
        return _empty_result(target, config)

    rng = random.Random(config.seed)
    pool_by_id = {m["paper"]["id"]: m for m in matches}
    population = _initial_population(
        [m["paper"]["id"] for m in matches],
        genome_size=config.genome_size,
        population_size=config.population_size,
    )
    trace: list[dict] = []
    archive: list[Candidate] = []

    for generation in range(config.generations):
        scored = [
            _score_candidate(tuple(ids), pool_by_id, target, generation)
            for ids in population
            if ids
        ]
        scored.sort(key=lambda c: (-c.score, c.id))
        archive.extend(scored)
        trace.append(
            {
                "generation": generation,
                "best_score": scored[0].score if scored else 0.0,
                "best_candidate": asdict(scored[0]) if scored else None,
                "population": [asdict(c) for c in scored[: config.population_size]],
            }
        )
        population = _next_generation(
            [c.paper_ids for c in scored],
            list(pool_by_id),
            config,
            rng,
        )

    archive.extend(
        _score_candidate(tuple(ids), pool_by_id, target, config.generations)
        for ids in population
        if ids
    )
    ranked = _dedupe_candidates(archive)
    if config.ontology_gate:
        ranked.sort(
            key=lambda c: (
                c.ontology_compatibility["status"] != "compatible",
                -c.score,
                c.id,
            )
        )
    else:
        ranked.sort(key=lambda c: (-c.score, c.id))

    selected = ranked[0] if ranked else None
    accepted = bool(selected) and selected.score >= 8.0
    if config.ontology_gate:
        accepted = bool(accepted) and (
            selected.ontology_compatibility["status"] == "compatible"
        )

    return {
        "target": {
            "id": target["id"],
            "name": target.get("name", target["id"]),
            "description": target.get("description", "").strip(),
        },
        "config": asdict(config),
        "ontology": {
            **ontology_summary(),
            "gate_enabled": config.ontology_gate,
        },
        "source_count": len(matches),
        "accepted": accepted,
        "best": asdict(selected) if selected else None,
        "candidates": [asdict(c) for c in ranked[: config.population_size]],
        "trace": trace,
        "recommendations": _recommendations(selected, config.ontology_gate),
    }


def export_autosearch_run(report: dict, output_dir: Path | None = None) -> Path:
    """Write a self-contained run card for Karpathy-style llm-wiki search."""
    base = Path(output_dir or AUTOSEARCH_DIR)
    base.mkdir(parents=True, exist_ok=True)
    target = report["target"]
    best = report.get("best") or {}
    date = datetime.now(UTC).date().isoformat()
    path = base / f"{target['id']}--{date}--evolution.md"
    fm = {
        "type": "autosearch-run",
        "target": target["id"],
        "accepted": report["accepted"],
        "generated": date,
        "best_score": best.get("score"),
        "ontology_version": (report.get("ontology") or {}).get("ontology_version"),
        "knowledge_state": (best.get("knowledge_claim") or {}).get("state"),
    }
    path.write_text(_render_report_markdown(report, fm), encoding="utf-8")
    _append_autosearch_log(base.parent / "log.md", target["name"], path)
    return path


def _source_matches(session: Session, target: dict, config: EvolutionConfig) -> list[dict]:
    limit = max(config.source_pool, config.population_size)
    try:
        matches = match_tkus(
            session,
            target,
            source_domain=config.source_domain,
            limit=limit,
        )
    except SQLAlchemyError:
        session.rollback()
        matches = []
    if config.include_knowledge_json:
        matches.extend(_knowledge_json_matches(target, config))
    matches.sort(key=lambda m: (-m["score"], m["paper"]["id"]))
    seen: set[str] = set()
    out: list[dict] = []
    target_domain = _target_domain(target.get("id"))
    for match in matches:
        paper_id = match["paper"]["id"]
        if target_domain and match["tku"].source_domain == target_domain:
            continue
        if paper_id in seen:
            continue
        seen.add(paper_id)
        out.append(match)
        if len(out) >= limit:
            break
    return out


def _normalize_config(config: EvolutionConfig) -> EvolutionConfig:
    return EvolutionConfig(
        target_id=config.target_id,
        source_domain=config.source_domain,
        source_pool=_clamp_int(config.source_pool, 1, 200),
        population_size=_clamp_int(config.population_size, 1, 50),
        generations=_clamp_int(config.generations, 0, 30),
        genome_size=_clamp_int(config.genome_size, 1, 5),
        mutation_rate=max(0.0, min(float(config.mutation_rate), 1.0)),
        seed=config.seed,
        include_knowledge_json=config.include_knowledge_json,
        ontology_gate=config.ontology_gate,
    )


def _clamp_int(value: int, low: int, high: int) -> int:
    return max(low, min(int(value), high))


def _knowledge_json_matches(target: dict, config: EvolutionConfig) -> list[dict]:
    if not KNOWLEDGE_JSON_DIR.exists():
        return []

    matches: list[dict] = []
    for path in sorted(KNOWLEDGE_JSON_DIR.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        tku = _knowledge_json_to_tku(data)
        if not tku.method_core.get("workflow"):
            continue
        if config.source_domain and tku.source_domain != config.source_domain:
            continue
        score, breakdown = _score_source_tku(tku, target, data)
        matches.append(
            {
                "tku": tku,
                "paper": {
                    "id": data.get("paper_id") or path.stem,
                    "title": data.get("title") or path.stem,
                    "year": _int_or_none((data.get("metadata") or {}).get("year")),
                    "labs": [],
                },
                "score": score,
                "score_breakdown": breakdown,
            }
        )
    return matches


def _knowledge_json_to_tku(data: dict) -> SourceTku:
    methods = _field_values(data, "methods")
    mechanisms = _field_values(data, "mechanisms")
    principles = _field_values(data, "general_principles")
    problems = _field_values(data, "problems")
    evidence = _field_values(data, "evidence")
    conclusions = _field_values(data, "conclusions")
    failures = [
        item for item in _field_values(data, "failure_paths")
        if _is_negative_path(item)
    ]
    bindings = (
        _field_values(data, "materials")
        + _field_values(data, "properties")
        + _field_values(data, "measurements")
    )
    method_text = " ".join(methods + mechanisms + principles).lower()
    source_domain = _infer_domain(data)
    problem_signature = {
        "task_type": _infer_task_type(method_text + " " + " ".join(problems).lower()),
        "evaluation_cost": "medium",
        "search_space": _infer_search_space(method_text + " " + data.get("abstract", "").lower()),
        "objectives": "multi" if "multi" in method_text or len(_field_values(data, "outcomes")) > 1 else "single",
        "budget_evaluations": None,
        "batch_size": None,
        "noise": None,
    }
    lessons = [
        {"text": item, "polarity": "positive"} for item in _unique(conclusions + evidence)
    ]
    lessons.extend({"text": item, "polarity": "negative"} for item in failures)
    return SourceTku(
        source_domain=source_domain,
        problem_signature=problem_signature,
        method_core={
            "workflow": _compact_phrase(methods[0]) if methods else "",
            "surrogate_model": _first_matching(method_text, ("gaussian process", "random forest", "neural network", "machine learning")),
            "acquisition": _first_matching(method_text, ("expected improvement", "thompson sampling", "active learning", "bayesian optimization")),
            "loop": "design-make-test-analyze" if "closed" in method_text or "self-driving" in method_text else None,
            "key_components": [
                _compact_phrase(v) for v in _unique(methods[1:] + mechanisms + principles)
            ][:8],
        },
        assumptions=problems[:4],
        lessons=lessons[:8],
        domain_bindings=_unique(bindings)[:8],
    )


def _score_source_tku(tku: SourceTku, target: dict, data: dict) -> tuple[float, dict]:
    sig = tku.problem_signature
    tsig = target.get("typical_signature") or {}
    score = 0.0
    breakdown: dict[str, object] = {}
    for field, points in (
        ("task_type", 3.0),
        ("search_space", 2.0),
        ("objectives", 2.0),
        ("evaluation_cost", 1.0),
    ):
        if sig.get(field) and sig.get(field) == tsig.get(field):
            score += points
            breakdown[field] = points
    terms = _all_components([tku])
    overlap = [
        kw for kw in target.get("keywords") or []
        if any(kw.lower() in term or term in kw.lower() for term in terms)
    ]
    if overlap:
        points = float(min(len(overlap), 3))
        score += points
        breakdown["keyword_overlap"] = {"points": points, "terms": overlap}
    quality = _float_or_zero((data.get("validation") or {}).get("score"))
    quality_points = round(min(quality * 3, 3.0), 3)
    score += quality_points
    breakdown["knowledge_quality"] = quality_points
    if tku.source_domain and tku.source_domain != target.get("id"):
        score += 1.0
        breakdown["cross_domain"] = 1.0
    return round(score, 3), breakdown


def _initial_population(
    paper_ids: list[str], genome_size: int, population_size: int
) -> list[tuple[str, ...]]:
    size = max(1, min(genome_size, len(paper_ids)))
    combos = [tuple(c) for c in combinations(paper_ids[: max(population_size, size)], size)]
    if not combos:
        combos = [tuple(paper_ids[:size])]
    return combos[:population_size]


def _next_generation(
    ranked: list[tuple[str, ...]],
    pool_ids: list[str],
    config: EvolutionConfig,
    rng: random.Random,
) -> list[tuple[str, ...]]:
    if not ranked:
        return []
    elites = ranked[: max(2, config.population_size // 3)]
    next_pop = list(elites)
    while len(next_pop) < config.population_size:
        left = rng.choice(elites)
        right = rng.choice(ranked[: max(2, len(ranked) // 2)])
        merged = list(dict.fromkeys((*left[:2], *right[:2])))
        if rng.random() < config.mutation_rate:
            merged.append(rng.choice(pool_ids))
        next_pop.append(_normalize_genome(merged, pool_ids, config.genome_size))
    return _dedupe_genomes(next_pop)[: config.population_size]


def _normalize_genome(
    paper_ids: list[str], pool_ids: list[str], genome_size: int
) -> tuple[str, ...]:
    out = list(dict.fromkeys(pid for pid in paper_ids if pid in pool_ids))
    for pid in pool_ids:
        if len(out) >= genome_size:
            break
        if pid not in out:
            out.append(pid)
    return tuple(sorted(out[:genome_size]))


def _score_candidate(
    paper_ids: tuple[str, ...],
    pool_by_id: dict[str, dict],
    target: dict,
    generation: int,
) -> Candidate:
    matches = [pool_by_id[pid] for pid in paper_ids if pid in pool_by_id]
    tkus: list[TransferKnowledgeUnit] = [m["tku"] for m in matches]
    match_strength = mean([m["score"] for m in matches]) if matches else 0.0
    domains = {t.source_domain for t in tkus if t.source_domain}
    workflows = {
        str((t.method_core or {}).get("workflow", "")).lower()
        for t in tkus
        if (t.method_core or {}).get("workflow")
    }
    components = _all_components(tkus)
    target_keywords = [str(k).lower() for k in target.get("keywords") or []]
    overlap = len({c for c in components if any(k in c or c in k for k in target_keywords)})
    negative_lessons = _lessons(tkus, polarity="negative")
    positive_lessons = _lessons(tkus, polarity=None)
    assumptions = _strings(tkus, "assumptions")

    novelty = min(len(domains), 3) + min(len(workflows), 3)
    transferability = min(overlap, 4) + min(len(positive_lessons), 3)
    evidence = min(len(paper_ids), 3) + min(len(assumptions), 3)
    risk_penalty = min(len(negative_lessons), 4) * 0.6
    score = round(match_strength + novelty + transferability + evidence - risk_penalty, 3)

    hypothesis = _hypothesis(target, tkus, components)
    citations = [f"[src:{pid}]" for pid in paper_ids]
    compatibility = evaluate_candidate_compatibility(tkus, target)
    knowledge_claim = build_proposed_claim(
        target=target,
        paper_ids=paper_ids,
        hypothesis=hypothesis,
        citations=citations,
        compatibility=compatibility,
    )
    return Candidate(
        id=f"cand-{generation}-{slugify('-'.join(paper_ids))[:48]}",
        paper_ids=paper_ids,
        score=score,
        components={
            "match_strength": round(match_strength, 3),
            "novelty": round(novelty, 3),
            "transferability": round(transferability, 3),
            "evidence": round(evidence, 3),
            "risk_penalty": round(risk_penalty, 3),
        },
        hypothesis=hypothesis,
        transfer_plan=_transfer_plan(tkus),
        assumptions_to_test=assumptions[:6],
        risks=negative_lessons[:6],
        citations=citations,
        ontology_compatibility=compatibility,
        knowledge_claim=knowledge_claim,
    )


def _all_components(tkus: list[TransferKnowledgeUnit]) -> set[str]:
    terms: set[str] = set()
    for tku in tkus:
        core = tku.method_core or {}
        for key in ("workflow", "surrogate_model", "acquisition", "loop"):
            value = core.get(key)
            if isinstance(value, str) and value.strip():
                terms.add(value.lower())
        for comp in core.get("key_components") or []:
            if isinstance(comp, str) and comp.strip():
                terms.add(comp.lower())
    return terms


def _lessons(tkus: list[TransferKnowledgeUnit], polarity: str | None) -> list[str]:
    out: list[str] = []
    for tku in tkus:
        for lesson in tku.lessons or []:
            if not isinstance(lesson, dict) or not isinstance(lesson.get("text"), str):
                continue
            if polarity is None or lesson.get("polarity") == polarity:
                out.append(lesson["text"].strip())
    return _unique(out)


def _strings(tkus: list[TransferKnowledgeUnit], attr: str) -> list[str]:
    values: list[str] = []
    for tku in tkus:
        for item in getattr(tku, attr) or []:
            if isinstance(item, str) and item.strip():
                values.append(item.strip())
    return _unique(values)


def _transfer_plan(tkus: list[TransferKnowledgeUnit]) -> list[str]:
    steps: list[str] = []
    for tku in tkus:
        core = tku.method_core or {}
        workflow = core.get("workflow")
        if isinstance(workflow, str) and workflow.strip():
            steps.append(f"Adapt workflow: {workflow.strip()}")
        acquisition = core.get("acquisition")
        if isinstance(acquisition, str) and acquisition.strip():
            steps.append(f"Test search policy: {acquisition.strip()}")
    return _unique(steps)[:6]


def _hypothesis(
    target: dict, tkus: list[TransferKnowledgeUnit], components: set[str]
) -> str:
    target_name = target.get("name", target.get("id", "target SDL"))
    top = _hypothesis_components(target, components)
    if not top:
        return f"{target_name} may benefit from a cross-domain closed-loop design, but the matched TKUs need richer method cores."
    joined = ", ".join(top)
    domains = ", ".join(sorted({t.source_domain for t in tkus if t.source_domain}))
    return f"{target_name} may transfer {joined} from {domains} into a new experiment loop."


def _dedupe_genomes(genomes: list[tuple[str, ...]]) -> list[tuple[str, ...]]:
    seen: set[tuple[str, ...]] = set()
    out: list[tuple[str, ...]] = []
    for genome in genomes:
        key = tuple(sorted(genome))
        if key not in seen:
            seen.add(key)
            out.append(key)
    return out


def _dedupe_candidates(candidates: list[Candidate]) -> list[Candidate]:
    by_key: dict[tuple[str, ...], Candidate] = {}
    for candidate in candidates:
        key = tuple(sorted(candidate.paper_ids))
        if key not in by_key or candidate.score > by_key[key].score:
            by_key[key] = candidate
    return list(by_key.values())


def _unique(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        key = re.sub(r"\s+", " ", item.strip().lower())
        if key and key not in seen:
            seen.add(key)
            out.append(item.strip())
    return out


def _field_values(data: dict, field: str) -> list[str]:
    values: list[str] = []
    raw = data.get(field) or []
    if not isinstance(raw, list):
        return values
    for item in raw:
        if isinstance(item, dict):
            value = item.get("value") or item.get("text")
        else:
            value = item
        if isinstance(value, str) and value.strip():
            values.append(value.strip())
    return _unique(values)


def _target_domain(target_id: str | None) -> str | None:
    return {
        "sdl1": "materials",
        "sdl2": "catalysis",
        "sdl3": "medicinal",
        "sdl4": "polymer",
        "sdl5": "formulation",
    }.get(target_id or "")


def _compact_phrase(value: str, max_words: int = 10) -> str:
    text = re.sub(r"\s+", " ", value.strip())
    text = re.sub(r"^(using|implementing|employing|combining)\s+", "", text, flags=re.I)
    known = (
        "bayesian optimization",
        "active learning",
        "genetic algorithm",
        "evolutionary algorithm",
        "machine learning",
        "deep learning",
        "large language model",
        "gaussian process",
        "design of experiments",
        "high-throughput screening",
        "closed-loop optimization",
        "property prediction",
        "self-driving laboratory",
        "multi-objective optimization",
        "robotic automation",
        "quantum machine learning",
        "molecular representation",
        "feature representation",
    )
    lower = text.lower()
    if "mbdf" in lower or "density of functionals" in lower:
        return "quantum machine learning representation"
    hits = [term for term in known if term in lower]
    if hits:
        return " + ".join(hits[:3])
    words = text.split()
    return " ".join(words[:max_words])


def _hypothesis_components(target: dict, components: set[str]) -> list[str]:
    compact = [_compact_phrase(c, max_words=6).lower() for c in components]
    compact = _dedupe_component_phrases(_unique(compact))
    target_keywords = [str(k).lower() for k in target.get("keywords") or []]
    prioritized = [
        c for c in compact
        if any(k in c or c in k for k in target_keywords)
    ]
    fallback = [c for c in compact if c not in prioritized]
    return (prioritized + fallback)[:3]


def _dedupe_component_phrases(phrases: list[str]) -> list[str]:
    out: list[str] = []
    for phrase in sorted(phrases, key=lambda p: (p.count("+"), len(p))):
        parts = {p.strip() for p in phrase.split("+")}
        if any(parts.issubset({p.strip() for p in existing.split("+")}) for existing in out):
            continue
        if any({p.strip() for p in existing.split("+")}.issubset(parts) for existing in out):
            out = [
                existing
                for existing in out
                if not {p.strip() for p in existing.split("+")}.issubset(parts)
            ]
        out.append(phrase)
    return out


def _infer_domain(data: dict) -> str:
    text = " ".join(
        [
            data.get("title") or "",
            data.get("abstract") or "",
            " ".join(data.get("sdl_tags") or []),
            " ".join(_field_values(data, "materials")),
        ]
    ).lower()
    for domain, terms in {
        "polymer": ("polymer", "monomer", "hydrogel"),
        "catalysis": ("catalyst", "catalysis", "electrocatalyst"),
        "battery": ("battery", "electrolyte", "lithium"),
        "formulation": ("formulation", "emulsion", "mixture"),
        "medicinal": ("drug", "ligand", "protein", "bioassay", "therapeutic"),
        "robotics": ("robot", "automation", "self-driving"),
        "materials": ("material", "mof", "perovskite", "semiconductor"),
    }.items():
        if any(term in text for term in terms):
            return domain
    tags = data.get("sdl_tags") or []
    if tags:
        return slugify(str(tags[0])).split("-")[0]
    return "unknown"


def _is_negative_path(value: str) -> bool:
    lower = value.lower()
    if lower.startswith("success:"):
        return False
    return any(term in lower for term in ("failure", "negative", "limitation", "partial"))


def _infer_task_type(text: str) -> str:
    if any(term in text for term in ("generate", "generative", "inverse design")):
        return "generation"
    if any(term in text for term in ("predict", "prediction", "classification")):
        return "prediction"
    if any(term in text for term in ("characterization", "measurement", "imaging")):
        return "characterization"
    if any(term in text for term in ("automation", "robotic", "self-driving")):
        return "automation"
    return "optimization"


def _infer_search_space(text: str) -> str:
    has_discrete = any(term in text for term in ("discrete", "categorical", "molecule", "ligand"))
    has_continuous = any(
        term in text for term in ("continuous", "composition", "temperature", "ratio")
    )
    if has_discrete and has_continuous:
        return "mixed"
    if has_discrete:
        return "discrete"
    if has_continuous:
        return "continuous"
    return "mixed"


def _first_matching(text: str, terms: tuple[str, ...]) -> str | None:
    return next((term for term in terms if term in text), None)


def _int_or_none(value) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _float_or_zero(value) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _recommendations(best: Candidate | None, ontology_gate: bool = False) -> list[str]:
    if best is None:
        return ["Extract or load TKUs before running evolutionary transfer search."]
    recs = [
        "Review the best hypothesis manually before treating it as scientific knowledge.",
        "Run the assumptions_to_test as explicit SDL feasibility checks.",
    ]
    if best.components["risk_penalty"] > 0:
        recs.append("Negative source lessons are present; keep them as design constraints.")
    if ontology_gate and best.ontology_compatibility["status"] != "compatible":
        recs.append(
            "Ontology gate blocked acceptance; resolve every compatibility issue."
        )
    return recs


def _empty_result(target: dict, config: EvolutionConfig) -> dict:
    return {
        "target": {
            "id": target["id"],
            "name": target.get("name", target["id"]),
            "description": target.get("description", "").strip(),
        },
        "config": asdict(config),
        "ontology": {
            **ontology_summary(),
            "gate_enabled": config.ontology_gate,
        },
        "source_count": 0,
        "accepted": False,
        "best": None,
        "candidates": [],
        "trace": [],
        "recommendations": ["No matching TKUs found. Run TKU extraction or load examples first."],
    }


def _render_report_markdown(report: dict, front_matter: dict) -> str:
    lines = [
        "---",
        yaml.safe_dump(front_matter, sort_keys=False, allow_unicode=True).strip(),
        "---",
        "",
        f"# Evolutionary autosearch: {report['target']['name']}",
        "",
        f"- Accepted: {report['accepted']}",
        f"- Source TKUs searched: {report['source_count']}",
        "",
    ]
    best = report.get("best")
    if best:
        lines += [
            "## Best candidate",
            "",
            f"- Score: {best['score']}",
            f"- Sources: {' '.join(best['citations'])}",
            f"- Hypothesis: {best['hypothesis']}",
            f"- Ontology compatibility: {best['ontology_compatibility']['status']}",
            f"- Knowledge state: {best['knowledge_claim']['state']}",
            f"- Executable: {best['knowledge_claim']['executable']}",
            "",
            "### Transfer plan",
            "",
        ]
        lines.extend(f"- {step}" for step in best["transfer_plan"])
        lines += ["", "### Assumptions to test", ""]
        lines.extend(f"- {item}" for item in best["assumptions_to_test"])
        lines += ["", "### Risks", ""]
        lines.extend(f"- {item}" for item in best["risks"] or ["No negative lessons in selected sources."])
    lines += ["", "## Generation trace", ""]
    for entry in report["trace"]:
        lines.append(
            f"- generation {entry['generation']}: best_score={entry['best_score']}"
        )
    lines += ["", "## Machine-readable report", "", "```json"]
    lines.append(json.dumps(report, ensure_ascii=False, indent=2))
    lines.append("```")
    return "\n".join(lines) + "\n"


def _append_autosearch_log(path: Path, target_name: str, run_path: Path) -> None:
    if not path.exists():
        path.write_text("# Log\n\nAppend-only operations log.\n", encoding="utf-8")
    date = datetime.now(UTC).date().isoformat()
    rel = run_path.relative_to(path.parent)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(f"\n## [{date}] autosearch | Evolutionary transfer: {target_name}\n")
        fh.write(f"- Run: [[{rel.with_suffix('').as_posix()}|{run_path.stem}]]\n")
