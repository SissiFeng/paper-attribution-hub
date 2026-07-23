"""Section-ablation harness.

Construct ablation variants of a full-text paper, score each with an injected
scorer, and report the claim-specific information gain each section adds over
the abstract-only baseline. The scorer is injected so this harness never
depends on (or edits) the production classifier internals.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

BASELINE = "abstract_only"

# Section types the ablation focuses on (the claim-bearing ones).
_ABSTRACT = "abstract"
_ADDITIVE = ("methods", "acknowledgements", "references")


@dataclass(frozen=True)
class AblationVariant:
    name: str
    section_types: frozenset[str]


@dataclass(frozen=True)
class ScoreResult:
    label: str
    confidence: float
    evidence_types: tuple[str, ...] = ()


@dataclass(frozen=True)
class VariantOutcome:
    variant: str
    section_types: frozenset[str]
    result: ScoreResult


@dataclass(frozen=True)
class SectionGain:
    variant: str
    label_changed: bool
    confidence_delta: float


def build_ablation_variants(available: set[str]) -> list[AblationVariant]:
    """Return the ablation variants realizable from the available section types.

    Always includes ``abstract_only``. Adds one ``abstract_<section>`` per
    additive section present, plus ``full`` and ``full_no_<section>`` leave-one-out
    variants when there is more than one section to work with.
    """
    variants: list[AblationVariant] = [
        AblationVariant(BASELINE, frozenset({_ABSTRACT}))
    ]
    present_additive = [s for s in _ADDITIVE if s in available]

    for section in present_additive:
        variants.append(
            AblationVariant(f"abstract_{section}", frozenset({_ABSTRACT, section}))
        )

    if present_additive:
        full = frozenset({_ABSTRACT, *present_additive})
        variants.append(AblationVariant("full", full))
        if len(present_additive) > 1:
            for section in present_additive:
                variants.append(
                    AblationVariant(
                        f"full_no_{section}", full - {section}
                    )
                )
    return variants


def run_ablation(
    variants: list[AblationVariant],
    scorer: Callable[[frozenset[str]], ScoreResult],
) -> list[VariantOutcome]:
    return [
        VariantOutcome(
            variant=v.name, section_types=v.section_types, result=scorer(v.section_types)
        )
        for v in variants
    ]


def information_gain(
    outcomes: list[VariantOutcome], baseline: str = BASELINE
) -> list[SectionGain]:
    """Per non-baseline variant: did it change the label / confidence vs baseline?"""
    by_name = {o.variant: o for o in outcomes}
    base = by_name.get(baseline)
    if base is None:
        return []
    gains: list[SectionGain] = []
    for outcome in outcomes:
        if outcome.variant == baseline:
            continue
        gains.append(
            SectionGain(
                variant=outcome.variant,
                label_changed=outcome.result.label != base.result.label,
                confidence_delta=round(
                    outcome.result.confidence - base.result.confidence, 4
                ),
            )
        )
    return gains
