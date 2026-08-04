"""Section-ablation harness: measure which section carries which claim.

Build ablation variants of a full-text paper, score each with an injected
scorer (decoupled from the production classifier), and report the information
gain each section adds over the abstract-only baseline.
"""

from __future__ import annotations

from app.services.eval_harness.section_ablation import (
    ScoreResult,
    build_ablation_variants,
    information_gain,
    run_ablation,
)


def test_builds_expected_variants_when_all_sections_present():
    variants = build_ablation_variants(
        {"abstract", "methods", "acknowledgements", "references"}
    )
    names = {v.name for v in variants}
    assert "abstract_only" in names
    assert "abstract_methods" in names
    assert "abstract_acknowledgements" in names
    assert "full" in names
    assert "full_no_acknowledgements" in names
    assert "full_no_references" in names


def test_skips_variants_whose_sections_are_unavailable():
    # No acknowledgements section -> no ack-dependent variants.
    variants = build_ablation_variants({"abstract", "methods"})
    names = {v.name for v in variants}
    assert "abstract_only" in names
    assert "abstract_methods" in names
    assert "abstract_acknowledgements" not in names
    assert "full_no_references" not in names  # references not available


def test_abstract_only_always_present_even_with_just_abstract():
    variants = build_ablation_variants({"abstract"})
    assert [v.name for v in variants] == ["abstract_only"]


def test_run_ablation_scores_each_variant():
    variants = build_ablation_variants({"abstract", "methods"})

    def scorer(section_types):
        # Methods presence flips BORDERLINE -> SDL and lifts confidence.
        if "methods" in section_types:
            return ScoreResult(label="SDL", confidence=0.9, evidence_types=("method",))
        return ScoreResult(label="BORDERLINE", confidence=0.5, evidence_types=())

    outcomes = {o.variant: o for o in run_ablation(variants, scorer)}
    assert outcomes["abstract_only"].result.label == "BORDERLINE"
    assert outcomes["abstract_methods"].result.label == "SDL"


def test_information_gain_flags_section_that_changes_the_label():
    variants = build_ablation_variants({"abstract", "methods", "acknowledgements"})

    def scorer(section_types):
        if "acknowledgements" in section_types:
            return ScoreResult("SDL", 0.95, ("funding",))
        return ScoreResult("BORDERLINE", 0.5, ())

    outcomes = run_ablation(variants, scorer)
    gains = {g.variant: g for g in information_gain(outcomes)}

    # Adding methods alone changes nothing; adding acknowledgements flips label.
    assert gains["abstract_methods"].label_changed is False
    assert gains["abstract_acknowledgements"].label_changed is True
    assert gains["abstract_acknowledgements"].confidence_delta > 0
