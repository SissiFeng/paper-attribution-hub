"""Reporting assistant.

Implements newidea.md's strict contract:

    "报告文字可以由 LLM 生成，但数字必须来自 SQL aggregation.
     别让模型发明增长率。"

Architecture:

    1. SQL aggregations produce a list of `MetricTriple(key, label, value, source_link)`.
    2. Templated prose stitches the metrics into English sentences with
       `[src:<metric_key>]` tags. Every number that appears in the prose
       must be backed by a triple — the templating layer enforces this.
    3. (Optional) An LLM rewriter takes the same triples + the templated
       baseline and produces nicer prose. Strict prompt: only use the given
       numbers, never invent new ones, every claim still tagged.

`[src:<metric_key>]` tags survive both backends. The frontend renders them
as clickable links back to the underlying analytics query so any reader
can verify the number themselves.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.services.analytics_service import (
    ImpactReport,
    build_impact_report,
)
from app.services.drift_service import build_drift_report
from app.report_evidence_policy import (
    ReportEvidencePolicy,
)
from app.services.filter_spec import (
    PaperFilter,
    apply_filter,
    canonical_filter_payload,
    canonical_filter_query_string,
    filter_fingerprint,
    filtered_paper_ids,
    paper_set_sha256,
)
from app.models import (
    Institution,
    Paper,
)


SUPPORTED_SECTIONS = (
    "overview",
    "growth",
    "themes",
    "emerging",
    "drift",
)

REPORT_ENTITIES = (
    "none",
    "university_of_toronto",
    "toronto",
    "ac_activity",
    "ac_sdl_overlap",
)

UNIVERSITY_OF_TORONTO_ALIASES = (
    "university of toronto",
    "uoft",
    "u of t",
    "utoronto",
    "university toronto",
)


@dataclass
class MetricTriple:
    key: str
    label: str
    value: object
    source_link: str  # URL path to /analytics/... query that produced this number


@dataclass
class ReportSection:
    key: str
    title: str
    prose: str          # templated English with [src:<metric_key>] tags
    metrics: list[MetricTriple]


@dataclass
class ReportResult:
    period_label: str
    sections: list[ReportSection]
    generated_at: datetime
    backend: str  # "template" or "anthropic"
    evidence_policy: dict


# ---------------------------------------------------------------------------
# Metric extraction (the only place numbers come from)
# ---------------------------------------------------------------------------


def _qs(
    filt: PaperFilter,
    *,
    evidence_policy: ReportEvidencePolicy | None = None,
    **overrides: object,
) -> str:
    """Build a query-string suffix that re-creates this report scope.

    The user filter is encoded as-is; the evidence policy is encoded as
    explicit report_evidence_* params. The report-metric endpoint rebuilds
    the effective scope from the same pair, so a deep link replays exactly
    the same paper set without leaking effective-filter fields into the
    user-filter URL.
    """
    policy_overrides: dict[str, object] = {}
    if evidence_policy is not None:
        policy_overrides.update(evidence_policy.query_params())
    if getattr(filt, "_report_entity", None) is not None:
        policy_overrides["report_entity"] = filt._report_entity
    policy_overrides.update(overrides)
    query = canonical_filter_query_string(filt, **policy_overrides)
    return f"?{query}" if query else ""


def _extract_overview_metrics(
    impact: ImpactReport, filt: PaperFilter
) -> list[MetricTriple]:
    total_attributed = sum(p.value for p in impact.yoy_attributed.points)
    years = [p.year for p in impact.yoy_attributed.points]
    earliest = min(years) if years else None
    latest = max(years) if years else None

    metrics = [
        MetricTriple(
            key="overview.total_attributed",
            label="AC-attributed papers in window",
            value=total_attributed,
            source_link="",
        ),
        MetricTriple(
            key="overview.window_from",
            label="window start year",
            value=earliest,
            source_link="",
        ),
        MetricTriple(
            key="overview.window_to",
            label="window end year",
            value=latest,
            source_link="",
        ),
    ]
    return metrics


def _extract_growth_metrics(impact: ImpactReport, filt: PaperFilter) -> list[MetricTriple]:
    del filt  # aggregation already applied the effective scope

    pts = impact.yoy_attributed.points
    metrics: list[MetricTriple] = []
    if len(pts) >= 2:
        first, last = pts[0], pts[-1]
        delta = None
        if first.value > 0:
            delta = round((last.value - first.value) / first.value * 100.0, 1)
        metrics.append(
            MetricTriple(
                key="growth.first_year_value",
                label=f"AC-attributed papers in {first.year}",
                value=first.value,
                source_link="",
            )
        )
        metrics.append(
            MetricTriple(
                key="growth.last_year_value",
                label=f"AC-attributed papers in {last.year}",
                value=last.value,
                source_link="",
            )
        )
        if delta is not None:
            metrics.append(
                MetricTriple(
                    key="growth.delta_pct",
                    label="growth from first year to last year",
                    value=delta,
                    source_link="",
                )
            )
    return metrics


def _extract_theme_metrics(impact: ImpactReport, filt: PaperFilter) -> list[MetricTriple]:
    del filt  # aggregation already applied the effective scope

    metrics: list[MetricTriple] = []
    for i, theme in enumerate(impact.top_growing_themes[:3]):
        metrics.append(
            MetricTriple(
                key=f"themes.top_{i}.name",
                label=f"top growing theme #{i + 1}",
                value=theme.name,
                source_link="",
            )
        )
        delta_value = theme.delta_pct if theme.delta_pct != float("inf") else "new"
        metrics.append(
            MetricTriple(
                key=f"themes.top_{i}.delta",
                label=f"delta percent for {theme.name}",
                value=delta_value,
                source_link="",
            )
        )
        metrics.append(
            MetricTriple(
                key=f"themes.top_{i}.value_now",
                label=f"recent paper count for {theme.name}",
                value=theme.value_now,
                source_link="",
            )
        )
    return metrics


def _extract_emerging_metrics(impact: ImpactReport, filt: PaperFilter) -> list[MetricTriple]:
    del filt  # aggregation already applied the effective scope

    metrics: list[MetricTriple] = []
    for i, inst in enumerate(impact.emerging_institutions[:3]):
        metrics.append(
            MetricTriple(
                key=f"emerging.institution_{i}.label",
                label=f"emerging institution #{i + 1}",
                value=inst.label,
                source_link="",
            )
        )
        metrics.append(
            MetricTriple(
                key=f"emerging.institution_{i}.first_year",
                label=f"first year for {inst.label}",
                value=inst.first_year,
                source_link="",
            )
        )
    return metrics


def _extract_drift_metrics(session: Session, filt: PaperFilter) -> list[MetricTriple]:
    report = build_drift_report(session, filt)
    metrics: list[MetricTriple] = [
        MetricTriple(
            key="drift.threshold",
            label="cosine similarity threshold",
            value=report.drift_threshold,
            source_link="",
        ),
        MetricTriple(
            key="drift.event_count",
            label="drift events detected",
            value=len(report.drift_events),
            source_link="",
        ),
    ]
    if report.drift_events:
        first = report.drift_events[0]
        metrics.append(
            MetricTriple(
                key="drift.first.from_year",
                label="first drift event from year",
                value=first.from_year,
                source_link="",
            )
        )
        metrics.append(
            MetricTriple(
                key="drift.first.to_year",
                label="first drift event to year",
                value=first.to_year,
                source_link="",
            )
        )
        if first.new_topics:
            metrics.append(
                MetricTriple(
                    key="drift.first.new_topics",
                    label="topics emerging in first drift event",
                    value=", ".join(first.new_topics[:3]),
                    source_link="",
                )
            )
    return metrics


# ---------------------------------------------------------------------------
# Templated prose
# ---------------------------------------------------------------------------


def _by_key(metrics: list[MetricTriple]) -> dict[str, MetricTriple]:
    return {m.key: m for m in metrics}


def _render_overview(metrics: list[MetricTriple]) -> str:
    by_key = _by_key(metrics)
    total = by_key.get("overview.total_attributed")
    yf = by_key.get("overview.window_from")
    yt = by_key.get("overview.window_to")
    if not total or total.value == 0:
        return (
            "There are no AC-attributed papers in the selected window "
            "[src:overview.total_attributed]."
        )
    if yf and yt and yf.value and yt.value and yf.value != yt.value:
        return (
            f"Between {yf.value} [src:overview.window_from] and {yt.value} "
            f"[src:overview.window_to], the corpus contains "
            f"{total.value} [src:overview.total_attributed] AC-attributed "
            f"papers (CORE_RELEVANT or RELATED_RELEVANT)."
        )
    return (
        f"The corpus contains {total.value} [src:overview.total_attributed] "
        "AC-attributed papers in the selected window."
    )


def _render_growth(metrics: list[MetricTriple]) -> str:
    by_key = _by_key(metrics)
    first = by_key.get("growth.first_year_value")
    last = by_key.get("growth.last_year_value")
    delta = by_key.get("growth.delta_pct")
    if not (first and last):
        return "Not enough year-over-year data to summarize growth."
    if delta is None or delta.value is None:
        return (
            f"AC-attributed paper count went from {first.value} "
            f"[src:growth.first_year_value] to {last.value} "
            f"[src:growth.last_year_value] across the window."
        )
    direction = "grew" if (
        isinstance(delta.value, (int, float)) and delta.value >= 0
    ) else "shrank"
    return (
        f"AC-attributed output {direction} from {first.value} "
        f"[src:growth.first_year_value] to {last.value} "
        f"[src:growth.last_year_value], a {delta.value}% change "
        f"[src:growth.delta_pct]."
    )


def _render_themes(metrics: list[MetricTriple]) -> str:
    by_key = _by_key(metrics)
    parts: list[str] = []
    for i in range(3):
        name = by_key.get(f"themes.top_{i}.name")
        delta = by_key.get(f"themes.top_{i}.delta")
        count = by_key.get(f"themes.top_{i}.value_now")
        if not name:
            continue
        delta_str = "new this period" if delta and delta.value == "new" else (
            f"{delta.value}%" if delta else "n/a"
        )
        parts.append(
            f"{name.value} [src:themes.top_{i}.name] "
            f"(growth {delta_str} [src:themes.top_{i}.delta], "
            f"now {count.value if count else 'n/a'} paper(s) "
            f"[src:themes.top_{i}.value_now])"
        )
    if not parts:
        return "No core themes have meaningful growth in the selected window."
    return "Top growing themes: " + "; ".join(parts) + "."


def _render_emerging(metrics: list[MetricTriple]) -> str:
    by_key = _by_key(metrics)
    parts: list[str] = []
    for i in range(3):
        label = by_key.get(f"emerging.institution_{i}.label")
        first_year = by_key.get(f"emerging.institution_{i}.first_year")
        if not label:
            continue
        parts.append(
            f"{label.value} [src:emerging.institution_{i}.label] (first contribution {first_year.value if first_year else 'n/a'} [src:emerging.institution_{i}.first_year])"
        )
    if not parts:
        return "No new institutions appear inside the selected window."
    return "Emerging institutional collaborators: " + "; ".join(parts) + "."


def _render_drift(metrics: list[MetricTriple]) -> str:
    by_key = _by_key(metrics)
    count = by_key.get("drift.event_count")
    if not count or count.value == 0:
        return (
            "No adjacent-year cosine similarity fell below the configured "
            "threshold [src:drift.threshold]; 0 drift events were detected "
            "[src:drift.event_count]."
        )
    parts = [
        f"Detected {count.value} drift event(s) [src:drift.event_count]."
    ]
    yf = by_key.get("drift.first.from_year")
    yt = by_key.get("drift.first.to_year")
    if yf and yt:
        parts.append(
            f"The first occurred between {yf.value} [src:drift.first.from_year] "
            f"and {yt.value} [src:drift.first.to_year]."
        )
    new_topics = by_key.get("drift.first.new_topics")
    if new_topics:
        parts.append(
            f"New topics that emerged: {new_topics.value} "
            "[src:drift.first.new_topics]."
        )
    return " ".join(parts)


SECTION_BUILDERS = {
    "overview": ("Overview", _extract_overview_metrics, _render_overview),
    "growth": ("Growth", _extract_growth_metrics, _render_growth),
    "themes": ("Top themes", _extract_theme_metrics, _render_themes),
    "emerging": ("Emerging collaborators", _extract_emerging_metrics, _render_emerging),
    "drift": ("Topic drift", _extract_drift_metrics, _render_drift),
}


_SRC_TAG_RE = re.compile(r"\[src:([a-zA-Z0-9_.]+)\]")


def _validate_prose(prose: str, allowed_keys: set[str]) -> None:
    """Make sure every [src:...] tag in the prose corresponds to an actual
    metric triple. Raises ValueError on a mismatch — this is the contract
    that guarantees the LLM didn't invent a number."""
    for tag in _SRC_TAG_RE.findall(prose):
        if tag not in allowed_keys:
            raise ValueError(
                f"Prose references unknown metric key '{tag}'. "
                "Reporting backend tried to claim a number we didn't compute."
            )


def build_report(
    session: Session,
    filt: PaperFilter,
    *,
    sections: list[str] | None = None,
    backend: str | None = None,
    evidence_policy: ReportEvidencePolicy | None = None,
    report_entity: str | None = None,
) -> ReportResult:
    sections = sections or list(SUPPORTED_SECTIONS)
    evidence_policy = evidence_policy or ReportEvidencePolicy()
    entity_filt = apply_report_entity(session, filt, report_entity)
    if report_entity:
        entity_filt._report_entity = report_entity
    effective_filt = apply_report_evidence_policy(entity_filt, evidence_policy)
    impact = build_impact_report(session, effective_filt)
    audit = build_report_evidence_audit(
        session, entity_filt, effective_filt, evidence_policy
    )
    if report_entity and report_entity != "none":
        audit["report_entity"] = report_entity

    backend = (backend or os.environ.get("PAS_LLM_BACKEND") or "template").lower()
    if backend not in {"template", "anthropic"}:
        backend = "template"

    out_sections: list[ReportSection] = []
    for section_key in sections:
        if section_key not in SECTION_BUILDERS:
            continue
        title, extractor, renderer = SECTION_BUILDERS[section_key]
        if section_key == "drift":
            metrics = _extract_drift_metrics(session, effective_filt)
        else:
            metrics = extractor(impact, effective_filt)
        for metric in metrics:
            link_filt = (
                entity_filt if getattr(entity_filt, "_report_entity", None) else filt
            )
            metric.source_link = (
                f"/analytics/report-metric{_qs(
                    link_filt,
                    evidence_policy=evidence_policy,
                    metric_key=metric.key,
                )}"
            )
        templated = renderer(metrics)
        _validate_prose(templated, {m.key for m in metrics})

        if backend == "anthropic":
            try:
                prose = _rewrite_with_anthropic(templated, metrics)
                _validate_prose(prose, {m.key for m in metrics})
            except Exception:
                # Never fail the report just because the LLM call failed.
                prose = templated
        else:
            prose = templated

        out_sections.append(
            ReportSection(
                key=section_key,
                title=title,
                prose=prose,
                metrics=metrics,
            )
        )

    period_label = _format_period_label(filt)
    return ReportResult(
        period_label=period_label,
        sections=out_sections,
        generated_at=datetime.now(UTC),
        backend=backend,
        evidence_policy=audit.get("evidence_policy", evidence_policy.canonical()),
    )


def _format_period_label(filt: PaperFilter) -> str:
    if filt.year_from is not None and filt.year_to is not None:
        return f"{filt.year_from}–{filt.year_to}"
    if filt.year_from is not None:
        return f"{filt.year_from}–present"
    if filt.year_to is not None:
        return f"through {filt.year_to}"
    return "full corpus"


# ---------------------------------------------------------------------------
# Optional Anthropic LLM rewriter (off by default)
# ---------------------------------------------------------------------------


def _rewrite_with_anthropic(templated: str, metrics: list[MetricTriple]) -> str:
    """Pass the templated prose + metric table to Claude with a strict prompt
    forbidding number invention. The LLM is allowed to rewrite sentence
    structure but must preserve every [src:...] tag and may only state
    numeric values that appear in the metric list.

    Loaded lazily — no hard dep on the `anthropic` package.
    """
    try:
        import anthropic  # type: ignore
    except ImportError as e:
        raise RuntimeError(
            "anthropic package not installed; falling back to template."
        ) from e

    api_key = os.environ.get("PAS_ANTHROPIC_API_KEY") or os.environ.get(
        "ANTHROPIC_API_KEY"
    )
    if not api_key:
        raise RuntimeError("PAS_ANTHROPIC_API_KEY is not set.")

    model = os.environ.get("PAS_ANTHROPIC_MODEL", "claude-sonnet-4-6")
    client = anthropic.Anthropic(api_key=api_key)

    table = "\n".join(
        f"  [{m.key}] {m.label} = {m.value}" for m in metrics
    )
    system = (
        "You rewrite analytics reports for research leadership. STRICT RULES:\n"
        "1. Use only the numbers listed in METRICS. Never invent or extrapolate.\n"
        "2. Keep every [src:<key>] tag wherever a number appears.\n"
        "3. Do not add new [src:...] tags that aren't in the METRICS list.\n"
        "4. One short paragraph, clear and professional. No filler.\n"
        "5. If the templated text already reads cleanly, return it verbatim."
    )
    user = (
        f"METRICS:\n{table}\n\n"
        f"TEMPLATED:\n{templated}\n\n"
        "Rewrite the templated text following the rules above."
    )
    response = client.messages.create(
        model=model,
        max_tokens=512,
        temperature=0.0,
        system=system,
        messages=[{"role": "user", "content": user}],
    )
    chunks = []
    for block in response.content:
        if getattr(block, "type", None) == "text":
            chunks.append(block.text)
    rewritten = ("".join(chunks)).strip()
    return rewritten or templated

# ---------------------------------------------------------------------------
# D21: report corpus evidence policy
# ---------------------------------------------------------------------------


def apply_report_evidence_policy(
    filt: PaperFilter,
    policy: ReportEvidencePolicy,
) -> PaperFilter:
    """Return the effective PaperFilter that backs externally reported figures.

    The policy is layered on top of the user-selected filter:
      * SDL judgement scope — the policy (or explicit sdl_judgements) wins,
        replacing any user-supplied sdl_judgements (reports are SDL figures).
      * review_statuses — restrict to COMPLETED unless needs-fulltext papers
        are explicitly allowed.
      * model-only confidence — applied only to unreviewed model labels; human
        reviews keep their judgement regardless of the classifier confidence.
      * abstract-only evidence — excluded unless explicitly allowed.
      * unreviewed ARCHITECTURE_BROAD_RETRIEVAL papers — excluded unless the
        user explicitly opted out (default True).
    """
    sdl_judgements = policy.effective_sdl_judgements()
    updates: dict = {
        "sdl_judgements": sdl_judgements,
    }
    if policy.mode == "human_only":
        updates["require_review"] = True
        if not policy.allow_needs_fulltext:
            updates["review_statuses"] = ["COMPLETED"]
    elif policy.mode == "human_plus_probable":
        if not policy.allow_needs_fulltext:
            updates["review_statuses"] = ["COMPLETED"]
            updates["review_statuses_include_unreviewed"] = True
        # Unreviewed model papers are only "probable" scope, not confirmed.
        updates["unreviewed_sdl_labels"] = ["SDL_ADJACENT"]
    elif not policy.allow_needs_fulltext:
        # Reviewed papers must be COMPLETED; unreviewed papers are allowed
        # (subject to the other flags below).
        updates["review_statuses"] = ["COMPLETED"]
        updates["review_statuses_include_unreviewed"] = True
    if policy.mode in {"human_high_confidence", "all_threshold"}:
        # Model-only (unreviewed) papers require the confidence floor.
        updates["unreviewed_min_confidence"] = policy.confidence_threshold
    if not policy.allow_abstract_only:
        updates["has_fulltext"] = True
    if policy.exclude_unreviewed_broad_retrieval:
        updates["exclude_unreviewed_corpus_sources"] = [
            "ARCHITECTURE_BROAD_RETRIEVAL"
        ]
    return filt.model_copy(update=updates)


def apply_report_entity(
    session: Session,
    filt: PaperFilter,
    entity: str | None,
) -> PaperFilter:
    """Map a D20 reporting entity to an explicit PaperFilter scope.

    university_of_toronto -> the resolved U of T institution id
    toronto               -> papers with a Toronto-institution affiliation
    ac_activity           -> papers with at least one AC-member author
    ac_sdl_overlap        -> AC-member papers that are also in SDL scope
    """
    if not entity or entity == "none":
        return filt
    updates: dict = {}
    if entity == "university_of_toronto":
        inst = _resolve_institution(session, UNIVERSITY_OF_TORONTO_ALIASES)
        if inst is not None:
            updates["institution_ids"] = [inst.id]
    elif entity == "toronto":
        updates["cities"] = ["Toronto"]
    elif entity == "ac_activity":
        updates["ac_author_only"] = True
    elif entity == "ac_sdl_overlap":
        updates["ac_author_only"] = True
        updates["ac_relevance_judgements"] = ["AC_RELEVANT"]
    return filt.model_copy(update=updates)


def _resolve_institution(
    session: Session, aliases: tuple[str, ...]
) -> Institution | None:
    """Resolve a canonical institution by exact name or alias (case-insensitive)."""
    from sqlalchemy import select

    candidates = list(
        session.execute(
            select(Institution).where(
                Institution.canonical_name.ilike(f"%{aliases[0]}%")
            )
        ).scalars()
    )
    if candidates:
        return candidates[0]
    for institution in session.execute(select(Institution)).scalars():
        names = {institution.canonical_name, *(institution.aliases or [])}
        normalized = {str(name).strip().lower() for name in names}
        if any(alias in normalized for alias in aliases):
            return institution
    return None


def build_report_evidence_audit(
    session: Session,
    user_filt: PaperFilter,
    effective_filt: PaperFilter,
    policy: ReportEvidencePolicy,
) -> dict:
    """Replayable audit of exactly which persisted paper set backs the report.

    The paper-set hash is computed over the effective (policy-applied) scope,
    so a change in evidence policy — not just in the shared filter — changes
    the hash and is always visible to the reader.
    """
    paper_ids = filtered_paper_ids(session, effective_filt)
    breakdown = _evidence_breakdown(session, effective_filt, policy)
    return {
        "filter": canonical_filter_payload(user_filt),
        "filter_fingerprint": filter_fingerprint(user_filt),
        "effective_filter": canonical_filter_payload(effective_filt),
        "effective_filter_fingerprint": filter_fingerprint(effective_filt),
        "paper_set_sha256": paper_set_sha256(paper_ids),
        "paper_set_encoding": "paper-id-set-json.v1",
        "included_papers": len(paper_ids),
        "algorithm": "report_evidence_policy.v1",
        "evidence_policy": policy.canonical(),
        "evidence_breakdown": breakdown,
        "metric_definitions": {
            "included_papers": (
                "Distinct persisted papers matching the user filter after applying "
                "the report evidence policy."
            ),
        },
        "generated_at": datetime.now(UTC).isoformat(),
    }


def _evidence_breakdown(
    session: Session,
    effective_filt: PaperFilter,
    policy: ReportEvidencePolicy,
) -> dict:
    """Count evidence composition of the effective paper set."""
    papers = list(
        session.execute(
            apply_filter(select(Paper), effective_filt)
        ).scalars()
    )
    human_confirmed = 0
    model_only = 0
    needs_fulltext = 0
    abstract_only = 0
    broad_unreviewed = 0
    for paper in papers:
        reviewed = paper.review is not None
        confirmed = bool(paper.classification and paper.classification.human_confirmed)
        if confirmed:
            human_confirmed += 1
        elif not reviewed:
            model_only += 1
        if paper.review and paper.review.review_status == "NEEDS_FULLTEXT":
            needs_fulltext += 1
        if not (paper.full_text_available or policy.allow_abstract_only):
            abstract_only += 1
        sources = paper.corpus_sources or []
        if (
            not reviewed
            and "ARCHITECTURE_BROAD_RETRIEVAL" in sources
            and policy.exclude_unreviewed_broad_retrieval
        ):
            broad_unreviewed += 1
    return {
        "total_papers": len(papers),
        "human_confirmed": human_confirmed,
        "model_only": model_only,
        "needs_fulltext": needs_fulltext,
        "abstract_only": abstract_only,
        "broad_retrieval_unreviewed": broad_unreviewed,
    }
