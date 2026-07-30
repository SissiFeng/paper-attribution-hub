"""Catalyst ontology hierarchy and longest-match behavior."""

import pytest
import yaml

from app.services.ontology_service import (
    ONTOLOGY_PATH,
    _validate_ontology,
    concept_ancestors,
    concept_children,
    concept_id_for_name,
    load_ontology,
    match_ontology_concepts,
)


def test_catalyst_concepts_are_hierarchical_and_versioned():
    ontology = load_ontology()

    assert ontology["ontology_version"] == "sdl-ontology/1.1"
    assert concept_id_for_name("material", "catalyst") == "material:catalyst"
    assert concept_ancestors("material:electrocatalyst") == ["material:catalyst"]
    assert "material:high_entropy_alloy_catalyst" in concept_children(
        "material:catalyst"
    )


def test_longest_catalyst_phrase_suppresses_overlapping_parent():
    text = (
        "IrPdPtRhRu high entropy alloy catalysts were optimized for the "
        "hydrogen evolution reaction."
    )

    materials = match_ontology_concepts(text, "material")
    reactions = match_ontology_concepts(text, "reaction")

    assert [item["concept_id"] for item in materials] == [
        "material:high_entropy_alloy_catalyst"
    ]
    assert materials[0]["surface"] == "high entropy alloy catalysts"
    assert [item["concept_id"] for item in reactions] == [
        "reaction:hydrogen_evolution"
    ]


def test_specific_catalyst_aliases_do_not_collapse_to_generic():
    matches = match_ontology_concepts(
        "The photocatalyst and electrocatalyst were compared.",
        "material",
    )

    assert [item["concept_id"] for item in matches] == [
        "material:photocatalyst",
        "material:electrocatalyst",
    ]


def test_ontology_rejects_ambiguous_aliases():
    raw = yaml.safe_load(ONTOLOGY_PATH.read_text(encoding="utf-8"))
    raw["concepts"].append(
        {
            "id": "material:ambiguous_test",
            "type": "material",
            "name": "ambiguous test material",
            "aliases": ["photo catalyst"],
        }
    )

    with pytest.raises(ValueError, match="Ambiguous material alias"):
        _validate_ontology(raw)
