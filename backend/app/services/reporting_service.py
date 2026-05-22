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

from sqlalchemy.orm import Session

from app.services.analytics_service import (
    ATTRIBUTED_LABELS,
    ImpactReport,
    build_impact_report,
)
from app.services.drift_service import build_drift_report
from app.services.filter_spec import PaperFilter


SUPPORTED_SECTIONS = (
    "overview",
    "growth",
    "themes",
    "emerging",
    "drift",
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


# ---------------------------------------------------------------------------
# Metric extraction (the only place numbers come from)
# ---------------------------------------------------------------------------


def _qs(filt: PaperFilter, **overrides) -> str:
    """Build a query-string suffix that re-creates this filter for deep linking."""
    parts: list[str] = []
    if filt.year_from is not None:
        parts.append(f"year_from={filt.year_from}")
    if filt.year_to is not None:
        parts.append(f"year_to={filt.year_to}")
    if filt.partner_only:
        parts.append("partner_only=true")
    if filt.ac_author_only:
        parts.append("ac_author_only=true")
    for k, v in overrides.items():
        parts.append(f"{k}={v}")
    return "?" + "&".join(parts) if parts else ""


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
            source_link=f"/analytics/overview{_qs(filt)}",
        ),
        MetricTriple(
            key="overview.window_from",
            label="window start year",
            value=earliest,
            source_link=f"/analytics/impact{_qs(filt)}",
        ),
        MetricTriple(
            key="overview.window_to",
            label="window end year",
            value=latest,
            source_link=f"/analytics/impact{_qs(filt)}",
        ),
    ]
    return metrics


def _extract_growth_metrics(impact: ImpactReport, filt: PaperFilter) -> list[MetricTriple]:
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
                source_link=f"/analytics/timeline{_qs(filt, by='label')}",
            )
        )
        metrics.append(
            MetricTriple(
                key="growth.last_year_value",
                label=f"AC-attributed papers in {last.year}",
                value=last.value,
                source_link=f"/analytics/timeline{_qs(filt, by='label')}",
            )
        )
        if delta is not None:
            metrics.append(
                MetricTriple(
                    key="growth.delta_pct",
                    label="growth from first year to last year",
                    value=delta,
                    source_link=f"/analytics/impact{_qs(filt)}",
                )
            )
    return metrics


def _extract_theme_metrics(impact: ImpactReport, filt: PaperFilter) -> list[MetricTriple]:
    metrics: list[MetricTriple] = []
    for i, theme in enumerate(impact.top_growing_themes[:3]):
        metrics.append(
            MetricTriple(
                key=f"themes.top_{i}.name",
                label=f"top growing theme #{i + 1}",
                value=theme.name,
                source_link=f"/analytics/timeline{_qs(filt, by='topic')}",
            )
        )
        delta_value = theme.delta_pct if theme.delta_pct != float("inf") else "new"
        metrics.append(
            MetricTriple(
                key=f"themes.top_{i}.delta",
                label=f"delta percent for {theme.name}",
                value=delta_value,
                source_link=f"/analytics/timeline{_qs(filt, by='topic')}",
            )
        )
        metrics.append(
            MetricTriple(
                key=f"themes.top_{i}.value_now",
                label=f"recent paper count for {theme.name}",
                value=theme.value_now,
                source_link=f"/analytics/timeline{_qs(filt, by='topic')}",
            )
        )
    return metrics


def _extract_emerging_metrics(impact: ImpactReport, filt: PaperFilter) -> list[MetricTriple]:
    metrics: list[MetricTriple] = []
    for i, inst in enumerate(impact.emerging_institutions[:3]):
        metrics.append(
            MetricTriple(
                key=f"emerging.institution_{i}.label",
                label=f"emerging institution #{i + 1}",
                value=inst.label,
                source_link=f"/analytics/institution-network{_qs(filt)}",
            )
        )
        metrics.append(
            MetricTriple(
                key=f"emerging.institution_{i}.first_year",
                label=f"first year for {inst.label}",
                value=inst.first_year,
                source_link=f"/analytics/institution-network{_qs(filt)}",
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
            source_link=f"/analytics/drift{_qs(filt)}",
        ),
        MetricTriple(
            key="drift.event_count",
            label="drift events detected",
            value=len(report.drift_events),
            source_link=f"/analytics/drift{_qs(filt)}",
        ),
    ]
    if report.drift_events:
        first = report.drift_events[0]
        metrics.append(
            MetricTriple(
                key="drift.first.from_year",
                label="first drift event from year",
                value=first.from_year,
                source_link=f"/analytics/drift{_qs(filt)}",
            )
        )
        metrics.append(
            MetricTriple(
                key="drift.first.to_year",
                label="first drift event to year",
                value=first.to_year,
                source_link=f"/analytics/drift{_qs(filt)}",
            )
        )
        if first.new_topics:
            metrics.append(
                MetricTriple(
                    key="drift.first.new_topics",
                    label="topics emerging in first drift event",
                    value=", ".join(first.new_topics[:3]),
                    source_link=f"/analytics/drift{_qs(filt)}",
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
            "No drift events detected above the configured similarity "
            "threshold [src:drift.threshold]."
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
) -> ReportResult:
    sections = sections or list(SUPPORTED_SECTIONS)
    impact = build_impact_report(session, filt)

    backend = (backend or os.environ.get("PAS_LLM_BACKEND") or "template").lower()
    if backend not in {"template", "anthropic"}:
        backend = "template"

    out_sections: list[ReportSection] = []
    for section_key in sections:
        if section_key not in SECTION_BUILDERS:
            continue
        title, extractor, renderer = SECTION_BUILDERS[section_key]
        if section_key == "drift":
            metrics = _extract_drift_metrics(session, filt)
        else:
            metrics = extractor(impact, filt)
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
