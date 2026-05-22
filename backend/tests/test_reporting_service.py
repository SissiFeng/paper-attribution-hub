"""Tests for the v0.6 reporting assistant.

Key contract under test: every number in the prose comes from a metric
triple. The validator (`_validate_prose`) is the enforcement point — if
the LLM (or a template bug) introduces a tag that isn't backed by an
actual metric, the report build must fail loud.
"""
import re

import pytest

from app.services.filter_spec import PaperFilter
from app.services.reporting_service import (
    _validate_prose,
    build_report,
)


def _setup(session):
    from app.services.relevance_classifier import classify_all

    classify_all(session)


def test_report_uses_template_backend_by_default(fulltext_seeded_session):
    _setup(fulltext_seeded_session)
    report = build_report(fulltext_seeded_session, PaperFilter())
    assert report.backend == "template"
    assert report.sections


def test_each_section_prose_has_only_known_metric_tags(fulltext_seeded_session):
    _setup(fulltext_seeded_session)
    report = build_report(fulltext_seeded_session, PaperFilter())
    for section in report.sections:
        allowed = {m.key for m in section.metrics}
        # Should not raise — but also assert explicitly.
        _validate_prose(section.prose, allowed)
        tags = re.findall(r"\[src:([a-zA-Z0-9_.]+)\]", section.prose)
        for tag in tags:
            assert tag in allowed, (
                f"Section {section.key} references unknown metric '{tag}'"
            )


def test_validator_raises_on_unknown_tag():
    with pytest.raises(ValueError):
        _validate_prose("foo [src:bogus.key] bar", set())


def test_growth_section_quotes_real_numbers(fulltext_seeded_session):
    _setup(fulltext_seeded_session)
    report = build_report(
        fulltext_seeded_session, PaperFilter(year_from=2023, year_to=2025)
    )
    growth = next(s for s in report.sections if s.key == "growth")
    # Pull every numeric value mentioned in the prose and verify each one
    # appears as a metric value (no hallucinated digits).
    metric_values = {str(m.value) for m in growth.metrics}
    numbers_in_prose = re.findall(r"\b\d+(?:\.\d+)?\b", growth.prose)
    for n in numbers_in_prose:
        assert n in metric_values, (
            f"Number '{n}' appeared in prose without a backing metric. "
            f"Allowed: {metric_values}"
        )


def test_source_links_point_at_analytics(fulltext_seeded_session):
    _setup(fulltext_seeded_session)
    report = build_report(fulltext_seeded_session, PaperFilter())
    for section in report.sections:
        for m in section.metrics:
            assert m.source_link.startswith("/analytics/"), m.source_link


def test_period_label_handles_no_window(fulltext_seeded_session):
    _setup(fulltext_seeded_session)
    report = build_report(fulltext_seeded_session, PaperFilter())
    assert report.period_label == "full corpus"


def test_period_label_handles_explicit_window(fulltext_seeded_session):
    _setup(fulltext_seeded_session)
    report = build_report(
        fulltext_seeded_session, PaperFilter(year_from=2021, year_to=2025)
    )
    assert report.period_label == "2021–2025"
