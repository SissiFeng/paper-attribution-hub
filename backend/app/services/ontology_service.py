"""Versioned ontology checks for cross-SDL transfer candidates.

The ontology gate is deliberately narrow: it verifies only modeled method
capabilities and explicitly declared unit dimensions. It does not claim that a
candidate is experimentally executable. Generated claims therefore always
start in the non-executable ``proposed`` state.
"""

from __future__ import annotations

import hashlib
import re
from functools import lru_cache
from pathlib import Path

import yaml

from app.config import REPO_ROOT
from app.services.text_utils import find_term_hits

ONTOLOGY_PATH = REPO_ROOT / "data" / "sdl_ontology.yaml"


@lru_cache(maxsize=1)
def load_ontology(path: str | Path | None = None) -> dict:
    raw = yaml.safe_load(Path(path or ONTOLOGY_PATH).read_text(encoding="utf-8")) or {}
    return _validate_ontology(raw)


def ontology_summary(ontology: dict | None = None) -> dict:
    registry = ontology or load_ontology()
    by_type: dict[str, int] = {}
    for concept in registry["concepts"].values():
        concept_type = concept["type"]
        by_type[concept_type] = by_type.get(concept_type, 0) + 1
    return {
        "ontology_version": registry["ontology_version"],
        "concepts": len(registry["concepts"]),
        "concepts_by_type": by_type,
        "relations": len(registry["relations"]),
        "knowledge_states": list(registry["knowledge_lifecycle"]["states"]),
    }


def concept(concept_id: str, ontology: dict | None = None) -> dict | None:
    """Return one ontology concept by stable id."""
    registry = ontology or load_ontology()
    return registry["concepts"].get(concept_id)


def concept_id_for_name(
    concept_type: str,
    name: str,
    ontology: dict | None = None,
) -> str | None:
    """Resolve an exact canonical concept name, case-insensitively."""
    registry = ontology or load_ontology()
    return registry["canonical_ids_by_type"].get(concept_type, {}).get(name.lower())


def concept_ancestors(
    concept_id: str,
    ontology: dict | None = None,
) -> list[str]:
    """Return nearest-first ``subclass_of`` ancestors for a concept."""
    registry = ontology or load_ontology()
    parents = registry["parents"]
    ordered: list[str] = []
    seen: set[str] = set()
    frontier = list(parents.get(concept_id, ()))
    while frontier:
        parent = frontier.pop(0)
        if parent in seen:
            continue
        seen.add(parent)
        ordered.append(parent)
        frontier.extend(parents.get(parent, ()))
    return ordered


def concept_children(
    concept_id: str,
    ontology: dict | None = None,
) -> list[str]:
    """Return direct child concept ids in deterministic order."""
    registry = ontology or load_ontology()
    return list(registry["children"].get(concept_id, ()))


def match_ontology_concepts(
    text: str,
    concept_type: str,
    ontology: dict | None = None,
) -> list[dict]:
    """Return non-overlapping longest ontology matches in source order.

    This prevents a phrase such as ``high entropy alloy catalyst`` from being
    collapsed into a second, overlapping generic ``catalyst`` mention. Parent
    concepts remain available through :func:`concept_ancestors`.
    """
    registry = ontology or load_ontology()
    candidates: dict[tuple[int, int, str], dict] = {}
    for surface, concept_id in registry["aliases_by_type"].get(concept_type, ()):
        for hit in find_term_hits(text, surface):
            key = (hit.start, hit.end, concept_id)
            candidates[key] = {
                "concept_id": concept_id,
                "start": hit.start,
                "end": hit.end,
                "surface": text[hit.start : hit.end],
                "negated": hit.negated,
            }
    ranked = sorted(
        candidates.values(),
        key=lambda item: (
            -(item["end"] - item["start"]),
            item["start"],
            item["concept_id"],
        ),
    )
    selected: list[dict] = []
    for candidate in ranked:
        if any(
            candidate["start"] < current["end"]
            and current["start"] < candidate["end"]
            for current in selected
        ):
            continue
        selected.append(candidate)
    selected.sort(key=lambda item: (item["start"], item["end"], item["concept_id"]))
    return selected


def ontology_gate_readiness(target: dict, ontology: dict | None = None) -> dict:
    registry = ontology or load_ontology()
    profile = target.get("ontology_profile") or {}
    reasons: list[str] = []
    if profile.get("ontology_version") != registry["ontology_version"]:
        reasons.append("target ontology profile is missing or has a different version")
    if not profile.get("capability_inventory_complete"):
        reasons.append("target capability inventory is incomplete")
    if not profile.get("unit_dimension_inventory_complete"):
        reasons.append("target unit-dimension inventory is incomplete")
    return {
        "ready": not reasons,
        "ontology_version": registry["ontology_version"],
        "reasons": reasons,
    }


def evaluate_candidate_compatibility(
    tkus: list,
    target: dict,
    ontology: dict | None = None,
) -> dict:
    registry = ontology or load_ontology()
    profile = target.get("ontology_profile") or {}
    concepts = registry["concepts"]

    declared_methods: set[str] = set()
    suggested_methods: dict[str, dict] = {}
    incomplete_mappings: set[str] = set()
    unknown_references: set[str] = set()
    explicit_capabilities: set[str] = set()
    required_unit_dimensions: set[str] = set()

    for tku in tkus:
        core = tku.method_core or {}
        tku_id = str(getattr(tku, "id", None) or getattr(tku, "paper_id", "unknown"))
        if (
            core.get("ontology_version") != registry["ontology_version"]
            or core.get("ontology_mapping_complete") is not True
        ):
            incomplete_mappings.add(tku_id)
        for reference in core.get("method_concepts") or []:
            if _is_concept(reference, "method", concepts):
                declared_methods.add(reference)
            else:
                unknown_references.add(str(reference))
        for reference in core.get("requires_capabilities") or []:
            if _is_concept(reference, "capability", concepts):
                explicit_capabilities.add(reference)
            else:
                unknown_references.add(str(reference))
        for reference in (tku.problem_signature or {}).get(
            "required_unit_dimensions"
        ) or []:
            if _is_concept(reference, "unit_dimension", concepts):
                required_unit_dimensions.add(reference)
            else:
                unknown_references.add(str(reference))
        for term in _method_terms(core):
            for surface, concept_id in registry["method_aliases"]:
                if find_term_hits(term, surface):
                    suggested_methods.setdefault(
                        concept_id,
                        {"concept_id": concept_id, "matched_terms": set()},
                    )["matched_terms"].add(term)

    required_capabilities = set(explicit_capabilities)
    relation_evidence: list[dict] = []
    for relation in registry["relations"]:
        if (
            relation["predicate"] == "requires_capability"
            and relation["source"] in declared_methods
        ):
            required_capabilities.add(relation["target"])
            relation_evidence.append(
                {
                    "method_concept": relation["source"],
                    "requires_capability": relation["target"],
                }
            )

    available_capabilities: set[str] = set()
    for reference in profile.get("capabilities") or []:
        if _is_concept(reference, "capability", concepts):
            available_capabilities.add(reference)
        else:
            unknown_references.add(str(reference))
    available_dimensions: set[str] = set()
    for reference in profile.get("supported_unit_dimensions") or []:
        if _is_concept(reference, "unit_dimension", concepts):
            available_dimensions.add(reference)
        else:
            unknown_references.add(str(reference))
    missing_capabilities = required_capabilities - available_capabilities
    missing_dimensions = required_unit_dimensions - available_dimensions
    inventory_complete = bool(profile.get("capability_inventory_complete"))
    unit_inventory_complete = bool(
        profile.get("unit_dimension_inventory_complete")
    )

    blockers: list[str] = []
    if profile.get("ontology_version") != registry["ontology_version"]:
        blockers.append(
            "Target profile is missing or uses a different ontology version."
        )
    if unknown_references:
        blockers.append("Unknown ontology references must be mapped before promotion.")
    if incomplete_mappings:
        blockers.append(
            "TKUs need complete mappings for this ontology version: "
            + ", ".join(sorted(incomplete_mappings))
            + "."
        )
    if not required_capabilities and not required_unit_dimensions:
        blockers.append("No modeled capability or unit requirements were found.")
    if missing_capabilities:
        label = ", ".join(sorted(missing_capabilities))
        if inventory_complete:
            blockers.append(f"Target lacks required capabilities: {label}.")
        else:
            blockers.append(f"Target capability inventory cannot confirm: {label}.")
    if missing_dimensions:
        label = ", ".join(sorted(missing_dimensions))
        if unit_inventory_complete:
            blockers.append(f"Target lacks required unit dimensions: {label}.")
        else:
            blockers.append(f"Target unit inventory cannot confirm: {label}.")

    if (
        incomplete_mappings
        or unknown_references
        or profile.get("ontology_version") != registry["ontology_version"]
    ):
        status = "unknown"
    elif missing_capabilities and inventory_complete:
        status = "incompatible"
    elif missing_dimensions and unit_inventory_complete:
        status = "incompatible"
    elif missing_capabilities or missing_dimensions or (
        not required_capabilities and not required_unit_dimensions
    ):
        status = "unknown"
    else:
        status = "compatible"

    return {
        "status": status,
        "scope": "modeled_requirements_only",
        "ontology_version": registry["ontology_version"],
        "declared_methods": sorted(declared_methods),
        "suggested_method_mappings": [
            {
                "concept_id": item["concept_id"],
                "matched_terms": sorted(item["matched_terms"]),
            }
            for item in sorted(
                suggested_methods.values(), key=lambda item: item["concept_id"]
            )
        ],
        "relation_evidence": relation_evidence,
        "required_capabilities": sorted(required_capabilities),
        "available_capabilities": sorted(available_capabilities),
        "missing_capabilities": sorted(missing_capabilities),
        "required_unit_dimensions": sorted(required_unit_dimensions),
        "missing_unit_dimensions": sorted(missing_dimensions),
        "unknown_references": sorted(unknown_references),
        "incomplete_mappings": sorted(incomplete_mappings),
        "blocking_issues": blockers,
    }


def build_proposed_claim(
    *,
    target: dict,
    paper_ids: tuple[str, ...],
    hypothesis: str,
    citations: list[str],
    compatibility: dict,
    ontology: dict | None = None,
) -> dict:
    registry = ontology or load_ontology()
    identity = "|".join(
        [
            registry["ontology_version"],
            str(target.get("id", "")),
            *sorted(paper_ids),
            hypothesis,
        ]
    )
    claim_id = "claim-" + hashlib.sha256(identity.encode("utf-8")).hexdigest()[:16]
    actions = sorted(
        transition["action"]
        for transition in registry["knowledge_lifecycle"]["transitions"]
        if transition["from"] == "proposed"
    )
    return {
        "id": claim_id,
        "kind": "cross_sdl_transfer_hypothesis",
        "state": "proposed",
        "executable": False,
        "ontology_version": registry["ontology_version"],
        "target_id": target.get("id"),
        "statement": hypothesis,
        "evidence_refs": citations,
        "compatibility_status": compatibility["status"],
        "blocking_issues": list(compatibility["blocking_issues"]),
        "allowed_next_actions": actions,
    }


def _validate_ontology(raw: dict) -> dict:
    version = raw.get("ontology_version")
    if not isinstance(version, str) or not version.strip():
        raise ValueError("ontology_version is required")

    concept_types = set(raw.get("concept_types") or [])
    relation_types = {item["id"]: item for item in raw.get("relation_types") or []}
    concepts: dict[str, dict] = {}
    for concept in raw.get("concepts") or []:
        concept_id = concept.get("id")
        if not concept_id or concept_id in concepts:
            raise ValueError(
                f"Duplicate or missing ontology concept id: {concept_id!r}"
            )
        if concept.get("type") not in concept_types:
            raise ValueError(f"Unknown concept type for {concept_id}")
        concepts[concept_id] = concept

    aliases_by_type: dict[str, list[tuple[str, str]]] = {
        concept_type: [] for concept_type in concept_types
    }
    canonical_ids_by_type: dict[str, dict[str, str]] = {
        concept_type: {} for concept_type in concept_types
    }
    alias_ids_by_type: dict[str, dict[str, str]] = {
        concept_type: {} for concept_type in concept_types
    }
    for concept_id, concept in concepts.items():
        concept_type = concept["type"]
        canonical_key = str(concept["name"]).strip().lower()
        existing = canonical_ids_by_type[concept_type].get(canonical_key)
        if existing is not None and existing != concept_id:
            raise ValueError(
                f"Duplicate canonical {concept_type} name: {concept['name']!r}"
            )
        canonical_ids_by_type[concept_type][canonical_key] = concept_id
        for surface in [concept["name"], *(concept.get("aliases") or [])]:
            alias_key = re.sub(r"[\s-]+", " ", str(surface).strip().lower())
            existing_alias = alias_ids_by_type[concept_type].get(alias_key)
            if existing_alias is not None and existing_alias != concept_id:
                raise ValueError(
                    f"Ambiguous {concept_type} alias {surface!r}: "
                    f"{existing_alias} and {concept_id}"
                )
            alias_ids_by_type[concept_type][alias_key] = concept_id
            aliases_by_type[concept_type].append((surface, concept_id))
    for aliases in aliases_by_type.values():
        aliases.sort(key=lambda item: (-len(item[0]), item[0], item[1]))

    relations = list(raw.get("relations") or [])
    parents: dict[str, list[str]] = {}
    children: dict[str, list[str]] = {}
    for relation in relations:
        spec = relation_types.get(relation.get("predicate"))
        source = concepts.get(relation.get("source"))
        target = concepts.get(relation.get("target"))
        if spec is None or source is None or target is None:
            raise ValueError(f"Invalid ontology relation: {relation}")
        if (
            source["type"] != spec["source_type"]
            or target["type"] != spec["target_type"]
        ):
            raise ValueError(f"Ontology relation type mismatch: {relation}")
        if relation["predicate"] == "subclass_of":
            parents.setdefault(relation["source"], []).append(relation["target"])
            children.setdefault(relation["target"], []).append(relation["source"])
    for values in parents.values():
        values.sort()
    for values in children.values():
        values.sort()
    _validate_parent_graph(parents)

    lifecycle = raw.get("knowledge_lifecycle") or {}
    states = set(lifecycle.get("states") or [])
    if "proposed" not in states:
        raise ValueError("Knowledge lifecycle must include proposed")
    for transition in lifecycle.get("transitions") or []:
        if transition.get("from") not in states or transition.get("to") not in states:
            raise ValueError(f"Invalid knowledge lifecycle transition: {transition}")

    return {
        "ontology_version": version,
        "concepts": concepts,
        "method_aliases": aliases_by_type.get("method", []),
        "aliases_by_type": aliases_by_type,
        "canonical_ids_by_type": canonical_ids_by_type,
        "parents": parents,
        "children": children,
        "relations": relations,
        "knowledge_lifecycle": lifecycle,
    }


def _validate_parent_graph(parents: dict[str, list[str]]) -> None:
    """Reject cycles in the subclass graph."""
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(node: str) -> None:
        if node in visiting:
            raise ValueError(f"Ontology subclass cycle at {node}")
        if node in visited:
            return
        visiting.add(node)
        for parent in parents.get(node, ()):
            visit(parent)
        visiting.remove(node)
        visited.add(node)

    for node in parents:
        visit(node)


def _is_concept(reference, expected_type: str, concepts: dict[str, dict]) -> bool:
    return (
        isinstance(reference, str)
        and reference in concepts
        and concepts[reference]["type"] == expected_type
    )


def _method_terms(method_core: dict) -> list[str]:
    terms: list[str] = []
    for key in ("workflow", "surrogate_model", "acquisition", "loop"):
        value = method_core.get(key)
        if isinstance(value, str) and value.strip():
            terms.append(value.strip())
    terms.extend(
        value.strip()
        for value in method_core.get("key_components") or []
        if isinstance(value, str) and value.strip()
    )
    return terms
