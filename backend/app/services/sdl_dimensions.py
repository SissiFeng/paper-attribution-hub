"""Lightweight SDL classification dimensions.

These dimensions describe how a paper fits the SDL literature. They do not
change attribution labels; they give retrieval, graph views, and reviewers a
more useful slice of the corpus.
"""
from __future__ import annotations

from dataclasses import dataclass
import re


@dataclass(frozen=True)
class SdlDimensions:
    domain: str
    automation_level: str
    autonomy_basis: str
    optimization_method: str
    platform_type: str
    evidence_role: str

    def to_dict(self) -> dict[str, str]:
        return {
            "domain": self.domain,
            "automation_level": self.automation_level,
            "autonomy_basis": self.autonomy_basis,
            "optimization_method": self.optimization_method,
            "platform_type": self.platform_type,
            "evidence_role": self.evidence_role,
        }


def infer_sdl_dimensions(paper, *, topic_score: float = 0.0) -> dict[str, str]:
    text = _paper_text(paper)
    automation_level, autonomy_basis = _infer_automation_level(
        text, paper, topic_score=topic_score
    )
    return SdlDimensions(
        domain=_infer_domain(text, paper),
        automation_level=automation_level,
        autonomy_basis=autonomy_basis,
        optimization_method=_infer_optimization_method(text),
        platform_type=_infer_platform_type(text),
        evidence_role=_infer_evidence_role(text, paper),
    ).to_dict()


def dimensions_from_evidence_summary(summary: list[dict] | None) -> dict[str, str] | None:
    for item in summary or []:
        if item.get("type") == "classification_dimensions":
            dims = item.get("dimensions")
            if isinstance(dims, dict):
                return {str(k): str(v) for k, v in dims.items()}
    return None


def merge_dimensions_into_evidence_summary(
    summary: list[dict] | None, dimensions: dict[str, str]
) -> list[dict]:
    rows = [r for r in (summary or []) if r.get("type") != "classification_dimensions"]
    rows.append({"type": "classification_dimensions", "dimensions": dimensions})
    return rows


def _paper_text(paper) -> str:
    parts: list[str] = [
        getattr(paper, "title", "") or "",
        getattr(paper, "abstract", "") or "",
        " ".join(getattr(paper, "keywords", None) or []),
        " ".join(getattr(paper, "indexed_keywords", None) or []),
        " ".join(getattr(paper, "sdl_tags", None) or []),
        " ".join(getattr(paper, "research_tags", None) or []),
        getattr(paper, "venue", "") or "",
    ]
    return " ".join(parts).lower()


def _infer_domain(text: str, paper) -> str:
    programs = (getattr(paper, "ac_programs", "") or "").lower()
    tags = " ".join(getattr(paper, "research_tags", None) or []).lower()
    sdl_tags = " ".join(getattr(paper, "sdl_tags", None) or []).lower()
    source = f"{text} {tags} {sdl_tags} {programs}"

    # AC groups first. These are the domains users expect to filter by.
    ac_groups = [
        ("human_chip", ("human-chip", "human chip", "organ-on-chip", "organ on chip", "microphysiological")),
        ("formulation", ("formulation", "formulate", "ink", "dispersion", "emulsion", "colloid")),
        ("polymer", ("polymer", "raft", "atrp", "miniemulsion", "macromolecule")),
        ("drug", ("drug", "pharma", "compound screening", "medicinal", "therapeutic")),
        ("organic", ("organic", "photoredox", "molecule", "molecular", "reaction", "synthesis")),
        ("inorganic", ("inorganic", "alloy", "thin-film", "thin film", "oxide", "perovskite", "nanoparticle", "crystal")),
    ]
    for label, needles in ac_groups:
        if _has_any(source, needles):
            return label

    # Secondary buckets for work outside the six AC groups.
    checks = [
        ("energy", ("battery", "electrolyte", "solar", "photovoltaic", "catalyst")),
        ("synthesis_biology", ("biology", "synthetic biology", "protein", "enzyme")),
        ("policy", ("policy", "ethic", "patent", "intellectual property", "workforce")),
        ("software_infrastructure", ("software", "workflow orchestration", "data infrastructure", "chemos")),
        ("materials_general", ("material", "materials discovery")),
        ("chemistry_general", ("chemistry", "chemical", "catalysis")),
    ]
    for label, needles in checks:
        if _has_any(source, needles):
            return label
    return "other"


def _infer_automation_level(text: str, paper, *, topic_score: float) -> tuple[str, str]:
    ai = float(getattr(paper, "ai_decision_score", None) or 0.0)
    automation = float(getattr(paper, "automation_score", None) or 0.0)
    loop = float(getattr(paper, "closed_loop_score", None) or 0.0)
    if (
        ("self-driving" in text and ("lab" in text or "laboratory" in text))
        or "autonomous laboratory" in text
    ):
        return "autonomous", "paper_self_description"
    if "closed-loop" in text or "closed loop" in text:
        return "closed_loop", "paper_self_description"
    if ai > 0 and automation > 0 and loop > 0:
        return "autonomous", "classifier_architecture_signals"
    if automation > 0 or any(n in text for n in ("robotic", "automated", "high-throughput")):
        return "automated", "paper_or_classifier_automation_signal"
    if ai > 0 or topic_score >= 0.4 or any(n in text for n in ("bayesian optimization", "active learning")):
        return "assisted", "method_signal_only"
    return "none", "not_indicated"


def _infer_optimization_method(text: str) -> str:
    checks = [
        ("llm_agent", ("llm", "large language model", "agent")),
        ("rl", ("reinforcement learning", "policy gradient", "q-learning")),
        ("bayesian", ("bayesian optimization", "bayesopt", "gaussian process")),
        ("active_learning", ("active learning", "sequential learning")),
        ("rule_based", ("design of experiments", "doe", "grid search")),
    ]
    for label, needles in checks:
        if any(n in text for n in needles):
            return label
    return "none"


def _infer_platform_type(text: str) -> str:
    if "cloud lab" in text or "cloud laboratory" in text:
        return "cloud_lab"
    if any(n in text for n in ("chemspeed", "opentrons", "robotic arm", "robotic platform")):
        return "physical_sdl"
    if any(n in text for n in ("custom platform", "custom-built", "bespoke platform", "automated platform")):
        return "experimental_workflow"
    if any(n in text for n in ("chemos", "workflow orchestration", "software platform")):
        return "software_infrastructure"
    if any(n in text for n in ("computational workflow", "simulation", "in silico")):
        return "computational_workflow"
    if "review" in text or "perspective" in text:
        return "literature_review"
    return "unspecified"


def _infer_evidence_role(text: str, paper) -> str:
    title = (getattr(paper, "title", "") or "").lower()
    if "review" in title or "perspective" in title or "roadmap" in title:
        return "review"
    if any(n in text for n in ("benchmark", "comparison", "dataset")):
        return "benchmark"
    if any(n in text for n in ("software", "toolkit", "package", "framework")):
        return "tooling"
    if getattr(paper, "ac_high_impact", None):
        return "seminal"
    if any(n in text for n in ("case study", "demonstrat", "we present")):
        return "case_study"
    if any(n in text for n in ("policy", "ethic", "patent", "intellectual property")):
        return "policy"
    return "method"


def _has_any(text: str, needles: tuple[str, ...]) -> bool:
    for needle in needles:
        if not needle:
            continue
        if " " in needle or "-" in needle:
            if needle in text:
                return True
            continue
        if re.search(rf"\b{re.escape(needle)}\b", text):
            return True
    return False
