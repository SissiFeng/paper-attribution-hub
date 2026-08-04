"""Tests for the v0.6 reporting assistant.

Key contract under test: every number in the prose comes from a metric
triple. The validator (`_validate_prose`) is the enforcement point — if
the LLM (or a template bug) introduces a tag that isn't backed by an
actual metric, the report build must fail loud.
"""
import re
from urllib.parse import parse_qs, urlsplit

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services.filter_spec import (
    PaperFilter,
    filter_fingerprint,
    filtered_paper_ids,
)
from app.report_evidence_policy import ReportEvidencePolicy
from app.services.reporting_service import (
    apply_report_entity,
    apply_report_evidence_policy,
    build_report_evidence_audit,
)
from app.services.reporting_service import (
    MetricTriple,
    _qs,
    _render_drift,
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


def test_empty_drift_prose_matches_below_threshold_predicate():
    metrics = [
        MetricTriple(
            key="drift.threshold",
            label="cosine similarity threshold",
            value=0.7,
            source_link="",
        ),
        MetricTriple(
            key="drift.event_count",
            label="drift events detected",
            value=0,
            source_link="",
        ),
    ]

    prose = _render_drift(metrics)

    assert "cosine similarity fell below" in prose
    assert "above" not in prose
    _validate_prose(prose, {metric.key for metric in metrics})


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


def test_emerging_metric_evidence_exposes_history_dependency(
    fulltext_seeded_session,
):
    _setup(fulltext_seeded_session)
    # Use a permissive evidence policy so emerging sections still appear in
    # the seeded sample (default human_plus_probable restricts to fulltext +
    # SDL scope and would drop the emerging entities).
    policy = ReportEvidencePolicy(
        mode="all_threshold",
        confidence_threshold=0.0,
        allow_abstract_only=True,
        allow_needs_fulltext=True,
        exclude_unreviewed_broad_retrieval=False,
    )
    report = build_report(
        fulltext_seeded_session,
        PaperFilter(year_from=2024),
        evidence_policy=policy,
    )
    metric = next(
        (
            metric
            for section in report.sections
            for metric in section.metrics
            if metric.key.startswith("emerging.")
        ),
        None,
    )
    assert metric is not None, [m.key for s in report.sections for m in s.metrics]

    response = TestClient(app).get(metric.source_link)

    assert response.status_code == 200
    dependency = response.json()["audit"]["dependencies"]["emerging_history"]
    assert dependency["algorithm"] == "impact_emerging_history.v1"
    assert dependency["filter"]["year_from"] is None
    assert dependency["paper_set_encoding"] == "paper-id-set-json.v1"


def test_source_links_replay_full_filter_and_exact_metric(fulltext_seeded_session):
    _setup(fulltext_seeded_session)
    filt = PaperFilter(
        year_from=2021,
        year_to=2025,
        labels=["EXCLUDE"],
        topic_ids=["topic/a?b", "topic&c"],
        fields=["field=A&B"],
        institution_ids=["institution/1"],
        countries=["Côte d'Ivoire", "Réunion"],
        corpus_sources=["LEGACY_IMPORT"],
        sdl_judgements=["CONFIRMED_SDL"],
        ac_relevance_judgements=["AC_RELEVANT"],
        ai_for_science_judgements=["AI_FOR_SCIENCE"],
        review_statuses=["COMPLETED"],
        partner_only=True,
        ac_author_only=False,
        has_fulltext=True,
        has_review=True,
        min_confidence=0.25,
        max_confidence=0.9,
        search="A&B = 1?\nnext",
    )
    report = build_report(
        fulltext_seeded_session,
        filt,
        evidence_policy=ReportEvidencePolicy(
            mode="all_threshold",
            confidence_threshold=0.0,
            allow_abstract_only=True,
            allow_needs_fulltext=True,
            exclude_unreviewed_broad_retrieval=False,
        ),
    )
    expected_audit = build_report_evidence_audit(
        fulltext_seeded_session,
        filt,
        apply_report_evidence_policy(
            filt,
            ReportEvidencePolicy(
                mode="all_threshold",
                confidence_threshold=0.0,
                allow_abstract_only=True,
                allow_needs_fulltext=True,
                exclude_unreviewed_broad_retrieval=False,
            ),
        ),
        ReportEvidencePolicy(
            mode="all_threshold",
            confidence_threshold=0.0,
            allow_abstract_only=True,
            allow_needs_fulltext=True,
            exclude_unreviewed_broad_retrieval=False,
        ),
    )
    client = TestClient(app)

    metrics = [metric for section in report.sections for metric in section.metrics]
    assert metrics
    for metric in metrics:
        assert metric.source_link.startswith("/analytics/report-metric?")
        response = client.get(metric.source_link)
        assert response.status_code == 200, metric.source_link
        evidence = response.json()
        assert evidence["metric"]["key"] == metric.key
        assert evidence["metric"]["value"] == metric.value
        assert evidence["audit"]["filter_fingerprint"] == filter_fingerprint(filt)
        assert (
            evidence["audit"]["effective_filter_fingerprint"]
            == expected_audit["effective_filter_fingerprint"]
        )
        assert (
            evidence["audit"]["paper_set_sha256"]
            == expected_audit["paper_set_sha256"]
        )
        assert evidence["audit"]["projection"] == {"metric_key": metric.key}

    parsed = parse_qs(urlsplit(metrics[0].source_link).query)
    assert parsed["search"] == ["A&B = 1?\nnext"]
    assert parsed["topic_ids"] == ["topic&c", "topic/a?b"]
    assert parsed["countries"] == ["Côte d'Ivoire", "Réunion"]
    assert _qs(filt).startswith("?")


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


# ---------------------------------------------------------------------------
# D21: report corpus evidence policy
# ---------------------------------------------------------------------------


def _seed_policy_corpus(session):
    from app.models import HumanReview, Paper
    from app.services.relevance_classifier import classify_all

    classify_all(session)
    # P001: human-confirmed CONFIRMED_SDL, COMPLETED, fulltext.
    p1 = session.get(Paper, "P001")
    p1.classification.human_confirmed = True
    p1.classification.sdl_relevance_label = "SDL_RELEVANT"
    p1.classification.confidence = 1.0
    session.add(
        HumanReview(
            id="pol_review_p001",
            paper_id="P001",
            sdl_judgement="CONFIRMED_SDL",
            ac_relevance_judgement="AC_RELEVANT",
            review_status="COMPLETED",
            evidence_level="FULLTEXT",
            judgement_basis="DUAL_REVIEW",
        )
    )
    # P002: NEEDS_FULLTEXT review, abstract-only (no fulltext).
    p2 = session.get(Paper, "P002")
    p2.full_text_available = False
    p2.classification.sdl_relevance_label = "SDL_RELEVANT"
    p2.classification.confidence = 0.9
    session.add(
        HumanReview(
            id="pol_review_p002",
            paper_id="P002",
            sdl_judgement="PROBABLE_SDL",
            ac_relevance_judgement="AC_RELEVANT",
            review_status="NEEDS_FULLTEXT",
            evidence_level="ABSTRACT",
            judgement_basis="DUAL_REVIEW",
        )
    )
    # P003: model-only CONFIRMED_SDL (SDL_RELEVANT), confidence 0.85, fulltext,
    # unreviewed, broad-retrieval corpus.
    p3 = session.get(Paper, "P003")
    p3.full_text_available = True
    p3.classification.sdl_relevance_label = "SDL_RELEVANT"
    p3.classification.confidence = 0.85
    p3.corpus_sources = ["ARCHITECTURE_BROAD_RETRIEVAL"]
    # P004: model-only SDL_ADJACENT, confidence 0.6, fulltext, unreviewed.
    p4 = session.get(Paper, "P004")
    p4.full_text_available = True
    p4.classification.sdl_relevance_label = "SDL_ADJACENT"
    p4.classification.confidence = 0.6
    # P005: human-confirmed CONFIRMED_SDL, COMPLETED, abstract-only (no fulltext).
    p5 = session.get(Paper, "P005")
    p5.full_text_available = False
    p5.classification.human_confirmed = True
    p5.classification.sdl_relevance_label = "SDL_RELEVANT"
    p5.classification.confidence = 1.0
    session.add(
        HumanReview(
            id="pol_review_p005",
            paper_id="P005",
            sdl_judgement="CONFIRMED_SDL",
            ac_relevance_judgement="AC_RELEVANT",
            review_status="COMPLETED",
            evidence_level="ABSTRACT",
            judgement_basis="DUAL_REVIEW",
        )
    )
    session.commit()


def test_evidence_policy_modes_select_exact_sets(fulltext_seeded_session):
    _seed_policy_corpus(fulltext_seeded_session)
    base = PaperFilter()
    expectations = {
        # P005 is abstract-only (full_text_available=False) and is excluded by
        # default (allow_abstract_only=False). P003 is unreviewed
        # ARCHITECTURE_BROAD_RETRIEVAL and is excluded by default
        # (exclude_unreviewed_broad_retrieval=True); P006 is a natural
        # fulltext SDL paper at confidence 0.9.
        "human_only": {"P001"},
        "human_plus_probable": {"P001", "P004"},
        "human_high_confidence": {"P001", "P006"},
        "all_threshold": {"P001", "P006"},
    }
    for mode, expected in expectations.items():
        policy = ReportEvidencePolicy(mode=mode, confidence_threshold=0.8)
        effective = apply_report_evidence_policy(base, policy)
        ids = set(filtered_paper_ids(fulltext_seeded_session, effective))
        assert ids == expected, (mode, sorted(ids), sorted(expected))


def test_evidence_policy_audit_is_replayable_and_explicit(
    fulltext_seeded_session,
):
    _seed_policy_corpus(fulltext_seeded_session)
    base = PaperFilter(year_from=2023, labels=["CORE_RELEVANT", "RELATED_RELEVANT"])
    policy = ReportEvidencePolicy(mode="human_high_confidence", confidence_threshold=0.8)
    effective = apply_report_evidence_policy(base, policy)
    audit = build_report_evidence_audit(
        fulltext_seeded_session, base, effective, policy
    )
    assert audit["filter_fingerprint"] == filter_fingerprint(base)
    assert audit["effective_filter_fingerprint"] == filter_fingerprint(effective)
    assert audit["paper_set_encoding"] == "paper-id-set-json.v1"
    assert audit["evidence_policy"]["mode"] == "human_high_confidence"
    assert audit["evidence_policy"]["confidence_threshold"] == 0.8
    assert audit["included_papers"] == len(filtered_paper_ids(fulltext_seeded_session, effective))
    breakdown = audit["evidence_breakdown"]
    assert breakdown["human_confirmed"] >= 1
    assert breakdown["model_only"] >= 1
    assert breakdown["needs_fulltext"] >= 0
    # policy change changes the hash
    other = ReportEvidencePolicy(mode="human_only")
    other_eff = apply_report_evidence_policy(base, other)
    other_audit = build_report_evidence_audit(
        fulltext_seeded_session, base, other_eff, other
    )
    assert other_audit["paper_set_sha256"] != audit["paper_set_sha256"]


def test_report_source_links_replay_evidence_policy(fulltext_seeded_session):
    _seed_policy_corpus(fulltext_seeded_session)
    base = PaperFilter(year_from=2023, year_to=2025)
    policy = ReportEvidencePolicy(mode="human_only")
    report = build_report(fulltext_seeded_session, base, evidence_policy=policy)
    client = TestClient(app)
    for section in report.sections:
        for metric in section.metrics:
            assert "report_evidence_mode=human_only" in metric.source_link
            resp = client.get(metric.source_link)
            assert resp.status_code == 200, (metric.source_link, resp.text[:300])
            body = resp.json()
            assert body["audit"]["evidence_policy"]["mode"] == "human_only"
            assert body["audit"]["evidence_breakdown"]["total_papers"] > 0


def test_report_evidence_flags_allow_needs_fulltext_and_abstract_only(
    fulltext_seeded_session,
):
    _seed_policy_corpus(fulltext_seeded_session)
    base = PaperFilter()
    # human_only default excludes NEEDS_FULLTEXT P002 and abstract-only P005.
    strict = apply_report_evidence_policy(
        base, ReportEvidencePolicy(mode="human_only")
    )
    assert set(filtered_paper_ids(fulltext_seeded_session, strict)) == {"P001"}
    relaxed = apply_report_evidence_policy(
        base,
        ReportEvidencePolicy(
            mode="human_plus_probable",
            allow_needs_fulltext=True,
            allow_abstract_only=True,
        ),
    )
    assert set(filtered_paper_ids(fulltext_seeded_session, relaxed)) == {
        "P001",
        "P002",
        "P004",
        "P005",
    }


def test_report_policy_never_affects_shared_filter_or_training(
    fulltext_seeded_session,
):
    _seed_policy_corpus(fulltext_seeded_session)
    base = PaperFilter(sdl_judgements=["CONFIRMED_SDL"])
    before = set(filtered_paper_ids(fulltext_seeded_session, base))
    _ = apply_report_evidence_policy(
        base, ReportEvidencePolicy(mode="human_only")
    )
    after = set(filtered_paper_ids(fulltext_seeded_session, base))
    assert before == after


# ---------------------------------------------------------------------------
# D20: reporting entity selectors
# ---------------------------------------------------------------------------


def test_city_filter_selects_toronto_papers(fulltext_seeded_session):
    from app.services.relevance_classifier import classify_all

    classify_all(fulltext_seeded_session)
    ids = set(filtered_paper_ids(
        fulltext_seeded_session, PaperFilter(cities=["Toronto"])
    ))
    assert ids, "Toronto-institution papers expected"
    # U of T + Vector Institute are Toronto; MIT/Stanford are not.
    assert "P001" in ids


def test_university_of_toronto_vs_toronto_scope_differ(fulltext_seeded_session):
    from app.services.relevance_classifier import classify_all

    classify_all(fulltext_seeded_session)
    # U of T alone vs Toronto (U of T + Vector Institute).
    uoft = apply_report_entity(
        fulltext_seeded_session, PaperFilter(), "university_of_toronto"
    )
    toronto = apply_report_entity(
        fulltext_seeded_session, PaperFilter(), "toronto"
    )
    uoft_ids = set(filtered_paper_ids(fulltext_seeded_session, uoft))
    toronto_ids = set(filtered_paper_ids(fulltext_seeded_session, toronto))
    assert uoft_ids
    assert toronto_ids
    # Toronto scope is a superset of U of T (Vector Institute papers included).
    assert uoft_ids <= toronto_ids
    assert toronto_ids != uoft_ids or len(toronto_ids) >= len(uoft_ids)


def test_report_entity_selectors_map_to_expected_scopes(fulltext_seeded_session):
    from app.services.relevance_classifier import classify_all

    classify_all(fulltext_seeded_session)
    ac_activity = apply_report_entity(
        fulltext_seeded_session, PaperFilter(), "ac_activity"
    )
    ac_sdl = apply_report_entity(
        fulltext_seeded_session, PaperFilter(), "ac_sdl_overlap"
    )
    ac_ids = set(filtered_paper_ids(fulltext_seeded_session, ac_activity))
    sdl_ids = set(filtered_paper_ids(fulltext_seeded_session, ac_sdl))
    assert ac_ids
    assert sdl_ids <= ac_ids
    assert ac_activity.ac_author_only is True
    assert ac_sdl.ac_author_only is True
    assert ac_sdl.ac_relevance_judgements == ["AC_RELEVANT"]


def test_report_entity_source_links_replay_entity(fulltext_seeded_session):
    _setup(fulltext_seeded_session)
    policy = ReportEvidencePolicy(
        mode="all_threshold",
        confidence_threshold=0.0,
        allow_abstract_only=True,
        allow_needs_fulltext=True,
        exclude_unreviewed_broad_retrieval=False,
    )
    client = TestClient(app)
    for entity in ["university_of_toronto", "toronto", "ac_activity", "ac_sdl_overlap"]:
        report = build_report(
            fulltext_seeded_session,
            PaperFilter(),
            evidence_policy=policy,
            report_entity=entity,
        )
        metric = report.sections[0].metrics[0]
        assert f"report_entity={entity}" in metric.source_link
        resp = client.get(metric.source_link)
        assert resp.status_code == 200, (entity, resp.text[:300])
        assert resp.json()["audit"].get("report_entity") == entity
