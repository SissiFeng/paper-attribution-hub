"""Schema-constrained NL-to-SQL retrieval over the paper attribution database.

The service deliberately compiles natural-language questions into a small
allow-list of read-only SQLAlchemy query templates. That gives the product a
real NL-to-SQL retrieval channel without letting an LLM execute arbitrary SQL.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import String, desc, distinct, func, or_, select
from sqlalchemy.orm import Session

from app.models import Author, Institution, Paper, PaperAuthor, PaperClassification, PaperProposition
from app.services.embedding_service import tokenize


_LABEL_ALIASES = {
    "core": "CORE_RELEVANT",
    "core_relevant": "CORE_RELEVANT",
    "ac": "CORE_RELEVANT",
    "ac相关": "CORE_RELEVANT",
    "related": "RELATED_RELEVANT",
    "related_relevant": "RELATED_RELEVANT",
    "相关": "RELATED_RELEVANT",
    "sdl": "SDL_FIELD_RELEVANT",
    "field": "SDL_FIELD_RELEVANT",
    "adjacent": "ADJACENT",
    "uncertain": "UNCERTAIN",
    "exclude": "EXCLUDE",
    "excluded": "EXCLUDE",
}

_INTENTS = {
    "count_papers",
    "list_papers",
    "top_authors",
    "top_institutions",
    "top_propositions",
    "review_queue",
}


@dataclass
class NlSqlPlan:
    intent: str
    filters: dict[str, Any] = field(default_factory=dict)
    group_by: str | None = None
    limit: int = 10
    source: str = "heuristic"


@dataclass
class NlSqlResult:
    query: str
    plan: NlSqlPlan
    sql: str
    rows: list[dict[str, Any]]
    summary: str


def _normalise_label(raw: str) -> str | None:
    key = raw.strip().lower().replace("-", "_").replace(" ", "_")
    return _LABEL_ALIASES.get(key)


def _extract_limit(query: str) -> int:
    m = re.search(r"\btop\s+(\d{1,2})\b|\b前\s*(\d{1,2})\b", query, re.I)
    if not m:
        return 10
    value = int(next(g for g in m.groups() if g))
    return max(1, min(value, 50))


def _extract_year_filters(query: str) -> dict[str, int]:
    filters: dict[str, int] = {}
    years = [int(y) for y in re.findall(r"\b(20\d{2}|19\d{2})\b", query)]
    if not years:
        return filters
    q = query.lower()
    if any(word in q for word in ["after", "since", "from", "之后", "以来"]):
        filters["year_from"] = min(years)
    elif any(word in q for word in ["before", "until", "to", "以前", "之前"]):
        filters["year_to"] = max(years)
    elif len(years) >= 2:
        filters["year_from"] = min(years)
        filters["year_to"] = max(years)
    else:
        filters["year"] = years[0]
    return filters


def _extract_labels(query: str) -> list[str]:
    q = query.lower()
    labels: list[str] = []
    for alias, label in _LABEL_ALIASES.items():
        if re.search(rf"(?<![a-z0-9_]){re.escape(alias)}(?![a-z0-9_])", q) and label not in labels:
            labels.append(label)
    return labels


def _extract_text_filter(query: str) -> str | None:
    quoted = re.findall(r'"([^"]{3,80})"|“([^”]{3,80})”', query)
    if quoted:
        return next(part for match in quoted for part in match if part).strip()
    about = re.search(r"\b(?:about|on)\s+([A-Za-z][A-Za-z0-9\-\s]{2,80})", query, re.I)
    if about:
        text = about.group(1)
        text = re.split(r"\b(?:after|before|since|from|by|grouped|top)\b", text, flags=re.I)[0]
        return text.strip() or None
    zh_about = re.search(r"(?:关于|有关)([^，。,.]{2,40})", query)
    if zh_about:
        return zh_about.group(1).strip()
    return None


def _heuristic_plan(query: str) -> NlSqlPlan:
    q = query.lower()
    filters: dict[str, Any] = {}
    filters.update(_extract_year_filters(query))
    labels = _extract_labels(query)
    if labels:
        filters["labels"] = labels
    text_filter = _extract_text_filter(query)
    if text_filter:
        filters["text"] = text_filter

    if any(word in q for word in ["review", "queue", "uncertain", "待审", "审查"]):
        intent = "review_queue"
    elif any(word in q for word in ["author", "coauthor", "people", "person", "collaborator", "作者", "合作者"]):
        intent = "top_authors"
    elif any(word in q for word in ["institution", "university", "partner", "机构", "学校"]):
        intent = "top_institutions"
    elif any(word in q for word in ["method", "funding", "funded", "topic", "proposition", "uses", "方法", "基金", "主题"]):
        intent = "top_propositions"
    elif any(word in q for word in ["count", "how many", "number", "多少", "数量", "几篇"]):
        intent = "count_papers"
    else:
        intent = "list_papers"

    group_by = None
    if intent == "count_papers":
        if any(word in q for word in ["year", "年度", "年份"]):
            group_by = "year"
        elif any(word in q for word in ["label", "category", "等级", "分类"]):
            group_by = "label"

    return NlSqlPlan(intent=intent, filters=filters, group_by=group_by, limit=_extract_limit(query))


def _llm_plan(query: str) -> NlSqlPlan | None:
    """Ask the configured LLM for a constrained query plan, then validate it.

    The model is not allowed to provide SQL. It can only choose one of the
    allow-listed intents and filters, which are compiled by this service.
    """
    from app.config import settings

    provider = settings.llm_provider
    if provider == "auto":
        provider = "kimi" if settings.kimi_api_key else ("anthropic" if settings.anthropic_api_key else "none")
    if provider == "none":
        return None

    prompt = (
        "Convert the user question into JSON for a safe NL-to-SQL planner. "
        "Allowed intents: count_papers, list_papers, top_authors, "
        "top_institutions, top_propositions, review_queue. "
        "Allowed filters: labels, year, year_from, year_to, text. "
        "Allowed group_by: label, year, null. "
        "Return only JSON with keys intent, filters, group_by, limit.\n\n"
        f"Question: {query}"
    )
    try:
        if provider == "kimi" and settings.kimi_api_key:
            import openai

            client = openai.OpenAI(api_key=settings.kimi_api_key, base_url=settings.kimi_base_url)
            resp = client.chat.completions.create(
                model=settings.kimi_model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=256,
                temperature=0.0,
            )
            raw = resp.choices[0].message.content or ""
        elif provider == "anthropic" and settings.anthropic_api_key:
            import anthropic

            client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
            resp = client.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=256,
                temperature=0.0,
                messages=[{"role": "user", "content": prompt}],
            )
            raw = resp.content[0].text
        else:
            return None
        start = raw.find("{")
        end = raw.rfind("}")
        data = json.loads(raw[start : end + 1])
        intent = str(data.get("intent", "list_papers"))
        if intent not in _INTENTS:
            return None
        filters = data.get("filters") if isinstance(data.get("filters"), dict) else {}
        labels = [
            label for label in (
                _normalise_label(str(v)) or str(v).upper()
                for v in filters.get("labels", [])
            )
            if label in set(_LABEL_ALIASES.values())
        ]
        if labels:
            filters["labels"] = sorted(set(labels))
        elif "labels" in filters:
            filters.pop("labels")
        group_by = data.get("group_by")
        if group_by not in {"label", "year", None}:
            group_by = None
        limit = max(1, min(int(data.get("limit") or 10), 50))
        return NlSqlPlan(intent=intent, filters=filters, group_by=group_by, limit=limit, source=f"llm/{provider}")
    except Exception:
        return None


def _paper_filters(stmt, filters: dict[str, Any], *, classification_joined: bool = False):
    if labels := filters.get("labels"):
        if not classification_joined:
            stmt = stmt.join(PaperClassification, PaperClassification.paper_id == Paper.id)
        stmt = stmt.where(PaperClassification.label.in_(labels))
    if year := filters.get("year"):
        stmt = stmt.where(Paper.year == int(year))
    if year_from := filters.get("year_from"):
        stmt = stmt.where(Paper.year >= int(year_from))
    if year_to := filters.get("year_to"):
        stmt = stmt.where(Paper.year <= int(year_to))
    if text := filters.get("text"):
        like = f"%{str(text).lower()}%"
        stmt = stmt.where(
            or_(
                func.lower(Paper.title).like(like),
                func.lower(Paper.abstract).like(like),
                func.lower(func.cast(Paper.keywords, String)).like(like),
                func.lower(func.cast(Paper.indexed_keywords, String)).like(like),
            )
        )
    return stmt


def _compile_sql(stmt) -> str:
    try:
        return str(stmt.compile(compile_kwargs={"literal_binds": True}))
    except Exception:
        return str(stmt)


def _rows(result) -> list[dict[str, Any]]:
    return [dict(row._mapping) for row in result]


def _summarise(plan: NlSqlPlan, rows: list[dict[str, Any]]) -> str:
    if not rows:
        return "No structured database rows matched this query."
    if plan.intent == "count_papers":
        if len(rows) == 1 and "paper_count" in rows[0]:
            return f"Structured query found {rows[0]['paper_count']} matching papers."
        return f"Structured query returned {len(rows)} grouped count rows."
    if plan.intent == "review_queue":
        return f"Structured query found {len(rows)} papers currently prioritized for review."
    return f"Structured query returned {len(rows)} rows for intent={plan.intent}."


def plan_nl_sql(query: str, *, use_llm: bool = True) -> NlSqlPlan:
    if use_llm:
        plan = _llm_plan(query)
        if plan is not None:
            return plan
    return _heuristic_plan(query)


def run_nl_sql(session: Session, query: str, *, use_llm: bool = True) -> NlSqlResult:
    plan = plan_nl_sql(query, use_llm=use_llm)
    filters = plan.filters

    if plan.intent == "count_papers":
        if plan.group_by == "label":
            stmt = (
                select(PaperClassification.label, func.count(distinct(Paper.id)).label("paper_count"))
                .join(Paper, Paper.id == PaperClassification.paper_id)
                .group_by(PaperClassification.label)
                .order_by(desc("paper_count"))
            )
            stmt = _paper_filters(stmt, filters, classification_joined=True)
        elif plan.group_by == "year":
            stmt = select(Paper.year, func.count(Paper.id).label("paper_count")).group_by(Paper.year).order_by(Paper.year)
            stmt = _paper_filters(stmt, filters)
        else:
            stmt = select(func.count(distinct(Paper.id)).label("paper_count"))
            stmt = _paper_filters(stmt, filters)
    elif plan.intent == "top_authors":
        stmt = (
            select(
                Author.id.label("author_id"),
                Author.canonical_name.label("author"),
                Author.is_ac_member,
                func.count(distinct(Paper.id)).label("paper_count"),
            )
            .join(PaperAuthor, PaperAuthor.author_id == Author.id)
            .join(Paper, Paper.id == PaperAuthor.paper_id)
            .group_by(Author.id, Author.canonical_name, Author.is_ac_member)
            .order_by(desc("paper_count"), Author.canonical_name)
            .limit(plan.limit)
        )
        stmt = _paper_filters(stmt, filters)
    elif plan.intent == "top_institutions":
        stmt = (
            select(
                Institution.id.label("institution_id"),
                Institution.canonical_name.label("institution"),
                Institution.is_partner,
                func.count(distinct(Paper.id)).label("paper_count"),
            )
            .join(Author, Author.institution_id == Institution.id)
            .join(PaperAuthor, PaperAuthor.author_id == Author.id)
            .join(Paper, Paper.id == PaperAuthor.paper_id)
            .group_by(Institution.id, Institution.canonical_name, Institution.is_partner)
            .order_by(desc("paper_count"), Institution.canonical_name)
            .limit(plan.limit)
        )
        stmt = _paper_filters(stmt, filters)
    elif plan.intent == "top_propositions":
        stmt = (
            select(
                PaperProposition.predicate,
                PaperProposition.object_value,
                func.count(distinct(PaperProposition.paper_id)).label("paper_count"),
                func.avg(PaperProposition.confidence).label("avg_confidence"),
            )
            .join(Paper, Paper.id == PaperProposition.paper_id)
            .group_by(PaperProposition.predicate, PaperProposition.object_value)
            .order_by(desc("paper_count"), desc("avg_confidence"))
            .limit(plan.limit)
        )
        stmt = _paper_filters(stmt, filters)
    elif plan.intent == "review_queue":
        stmt = (
            select(
                Paper.id.label("paper_id"),
                Paper.title,
                Paper.year,
                PaperClassification.label,
                PaperClassification.confidence,
                PaperClassification.review_priority,
            )
            .join(PaperClassification, PaperClassification.paper_id == Paper.id)
            .where(PaperClassification.needs_review.is_(True))
            .order_by(desc(PaperClassification.review_priority), desc(PaperClassification.confidence))
            .limit(plan.limit)
        )
        stmt = _paper_filters(stmt, filters, classification_joined=True)
    else:
        stmt = (
            select(
                Paper.id.label("paper_id"),
                Paper.title,
                Paper.year,
                Paper.venue,
                PaperClassification.label,
                PaperClassification.confidence,
            )
            .outerjoin(PaperClassification, PaperClassification.paper_id == Paper.id)
            .order_by(desc(PaperClassification.confidence), desc(Paper.year))
            .limit(plan.limit)
        )
        stmt = _paper_filters(stmt, filters, classification_joined=True)

    rows = _rows(session.execute(stmt))
    return NlSqlResult(
        query=query,
        plan=plan,
        sql=_compile_sql(stmt),
        rows=rows,
        summary=_summarise(plan, rows),
    )
