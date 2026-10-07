"""Deterministic, schema-constrained text-to-SQL for PAS.

Natural-language input is mapped to a small allow-list of read-only SQLAlchemy
templates. No LLM plans, writes, executes, summarises, or repairs a query. A
question that cannot be mapped unambiguously fails closed.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import desc, distinct, exists, func, or_, select
from sqlalchemy.orm import Session

from app.country_normalization import canonical_country_entries
from app.models import (
    Author,
    Institution,
    Paper,
    PaperAuthor,
    PaperChunk,
    PaperClassification,
    PaperProposition,
)
from app.services.filter_spec import (
    PAPER_SET_ENCODING,
    PaperFilter,
    apply_filter,
    canonical_filter_payload,
    filter_fingerprint,
    paper_set_sha256,
)


PLANNER_ID = "deterministic-template.v2"
ANSWER_RENDERER_ID = "deterministic-sql-answer.v1"
ALLOWED_TABLES = (
    "papers",
    "paper_classifications",
    "paper_authors",
    "authors",
    "institutions",
    "paper_propositions",
    "paper_chunks",
    "human_reviews",
)

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

_COUNT_MARKERS = ("count", "how many", "number of", "多少", "数量", "几篇")
_LIST_MARKERS = ("which papers", "list papers", "show papers", "find papers", "哪些论文", "列出论文")
_TOP_MARKERS = ("top", "most", "leading", "rank", "前", "最多", "排名")
_AUTHOR_MARKERS = ("author", "coauthor", "people", "person", "collaborator", "作者", "合作者")
_INSTITUTION_MARKERS = ("institution", "university", "partner", "机构", "学校", "大学")
_REVIEW_MARKERS = ("review queue", "needs review", "待审", "审查队列")
_FORBIDDEN_SQL_SYNTAX = re.compile(
    r"\b(?:drop|delete|insert|update|alter|create|truncate|attach|detach|"
    r"pragma|grant|revoke|execute|exec|union\s+select)\b",
    re.I,
)


class NlSqlUnsupportedError(ValueError):
    """Raised when a question cannot safely map to one deterministic template."""


@dataclass
class NlSqlPlan:
    intent: str
    filters: dict[str, Any] = field(default_factory=dict)
    group_by: str | None = None
    limit: int = 10
    source: str = PLANNER_ID


@dataclass
class NlSqlResult:
    query: str
    plan: NlSqlPlan
    sql: str
    parameters: dict[str, Any]
    rows: list[dict[str, Any]]
    summary: str
    audit: dict[str, Any]


def _contains_any(query: str, markers: tuple[str, ...]) -> bool:
    return any(marker in query for marker in markers)


def _extract_limit(query: str) -> int:
    match = re.search(
        r"\b(?:top|first|limit)\s+(\d{1,2})\b|\b前\s*(\d{1,2})\b",
        query,
        re.I,
    )
    if not match:
        return 10
    value = int(next(group for group in match.groups() if group))
    return max(1, min(value, 50))


def _extract_year_filters(query: str) -> dict[str, int]:
    years = [int(year) for year in re.findall(r"\b(20\d{2}|19\d{2})\b", query)]
    if not years:
        return {}
    if len(years) >= 2:
        return {"year_from": min(years), "year_to": max(years)}
    normalized = query.casefold()
    if _contains_any(normalized, ("after", "since", "from", "之后", "以来", "起")):
        return {"year_from": years[0]}
    if _contains_any(normalized, ("before", "until", "以前", "之前", "截至")):
        return {"year_to": years[0]}
    return {"year": years[0]}


def _extract_labels(query: str) -> list[str]:
    normalized = query.casefold()
    labels: list[str] = []
    for alias, label in _LABEL_ALIASES.items():
        if (
            re.search(
                rf"(?<![a-z0-9_]){re.escape(alias)}(?![a-z0-9_])",
                normalized,
            )
            and label not in labels
        ):
            labels.append(label)
    return labels


def _quoted_phrase(query: str) -> str | None:
    quoted = re.findall(r'"([^"\n]{2,100})"|“([^”\n]{2,100})”', query)
    if not quoted:
        return None
    return next(part for match in quoted for part in match if part).strip()


def _clean_relation_object(value: str) -> str | None:
    cleaned = value.strip(" \t\n\r?.!,;:，。！？；：")
    cleaned = re.split(
        r"\b(?:after|before|since|between|from|during|top|grouped)\b|"
        r"(?:之后|之前|以来|按年份|前\s*\d+)",
        cleaned,
        maxsplit=1,
        flags=re.I,
    )[0]
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned[:100] if len(cleaned) >= 2 else None


def _extract_relation_filter(query: str) -> tuple[str | None, str | None]:
    normalized = query.casefold()
    predicate: str | None = None
    if _contains_any(
        normalized,
        ("funded", "funding", "funder", "grant", "基金", "资助"),
    ):
        predicate = "funded_by"
    elif _contains_any(normalized, ("topic", "theme", "主题", "领域")):
        predicate = "belongs_to_topic"
    elif _contains_any(
        normalized,
        (
            " use ",
            " uses ",
            " using ",
            "method",
            "platform",
            "technique",
            "instrument",
            "方法",
            "平台",
            "仪器",
        ),
    ):
        predicate = "uses_method"
    if predicate is None:
        return None, None

    quoted = _quoted_phrase(query)
    if quoted:
        return predicate, quoted

    patterns = {
        "funded_by": (
            r"\b(?:funded|financed|supported)\s+by\s+(.{2,100})$",
            r"(?:由|受)(.{2,60})(?:资助|支持)",
        ),
        "uses_method": (
            r"\b(?:use|uses|used|using)\s+(.{2,100})$",
            r"(?:使用|采用)([^，。,.]{2,60})",
        ),
        "belongs_to_topic": (
            r"\b(?:topic|theme)\s+(?:is|of|about)?\s*(.{2,100})$",
            r"(?:主题|领域)(?:是|为|关于)?([^，。,.]{2,60})",
        ),
    }
    for pattern in patterns[predicate]:
        match = re.search(pattern, query, re.I)
        if match:
            return predicate, _clean_relation_object(match.group(1))
    return predicate, None


def _extract_text_filter(query: str, *, relation_object: str | None) -> str | None:
    if relation_object:
        return None
    quoted = _quoted_phrase(query)
    if quoted:
        return quoted
    match = re.search(
        r"\b(?:about|on)\s+([A-Za-z][A-Za-z0-9\-\s]{2,100})",
        query,
        re.I,
    )
    if match:
        return _clean_relation_object(match.group(1))
    match = re.search(r"(?:关于|有关)([^，。,.]{2,60})", query)
    return match.group(1).strip() if match else None


def _deterministic_plan(query: str) -> NlSqlPlan:
    if _FORBIDDEN_SQL_SYNTAX.search(query):
        raise NlSqlUnsupportedError(
            "Raw SQL and write-oriented syntax are not accepted by strict text-to-SQL"
        )
    normalized = f" {query.casefold().strip()} "
    relation_predicate, relation_object = _extract_relation_filter(query)
    filters: dict[str, Any] = _extract_year_filters(query)
    labels = _extract_labels(query)
    if labels:
        filters["labels"] = labels
    text_filter = _extract_text_filter(query, relation_object=relation_object)
    if text_filter:
        filters["text"] = text_filter
    if relation_predicate:
        filters["proposition_predicate"] = relation_predicate
    if relation_object:
        filters["proposition_object"] = relation_object

    is_count = _contains_any(normalized, _COUNT_MARKERS)
    is_list = _contains_any(normalized, _LIST_MARKERS) or bool(
        re.search(r"\bwhich\b.{0,40}\bpapers?\b", normalized, re.I)
    )
    is_top = _contains_any(normalized, _TOP_MARKERS)
    has_author = _contains_any(normalized, _AUTHOR_MARKERS)
    has_institution = _contains_any(normalized, _INSTITUTION_MARKERS)

    if _contains_any(normalized, _REVIEW_MARKERS):
        intent = "review_queue"
    elif is_count and has_institution and _contains_any(normalized, (" by ", "按", "每个")):
        intent = "top_institutions"
    elif is_count and has_author and _contains_any(normalized, (" by ", "按", "每个")):
        intent = "top_authors"
    elif is_count:
        intent = "count_papers"
    elif is_list:
        intent = "list_papers"
    elif is_top and has_author:
        intent = "top_authors"
    elif is_top and has_institution:
        intent = "top_institutions"
    elif is_top and relation_predicate:
        intent = "top_propositions"
    elif relation_predicate and _contains_any(normalized, ("what", "which", "哪些", "什么")):
        intent = "top_propositions"
    else:
        raise NlSqlUnsupportedError(
            "Question is outside the deterministic SQL grammar. Supported forms: "
            "count papers (optionally by year/label), list papers, top authors, "
            "top institutions, top methods/topics/funders, and review queue."
        )

    group_by = None
    if intent == "count_papers":
        if _contains_any(normalized, ("year", "年度", "年份")):
            group_by = "year"
        elif _contains_any(normalized, ("label", "category", "等级", "分类")):
            group_by = "label"

    return NlSqlPlan(
        intent=intent,
        filters=filters,
        group_by=group_by,
        limit=_extract_limit(query),
    )


def plan_nl_sql(query: str, *, use_llm: bool | None = None) -> NlSqlPlan:
    """Return a deterministic plan; explicitly reject attempts to enable an LLM."""
    if use_llm is True:
        raise NlSqlUnsupportedError("LLM planning is disabled for strict text-to-SQL")
    return _deterministic_plan(query)


def _phrase_in_query(phrase: str, query: str) -> bool:
    normalized = re.sub(r"\s+", " ", phrase.casefold()).strip()
    if len(normalized) < 3:
        return False
    return normalized in query


def _entity_candidate(query: str, plan: NlSqlPlan) -> str | None:
    if plan.filters.get("text") or plan.filters.get("proposition_object"):
        return None
    match = re.search(
        r"\b(?:from|at|by|in)\s+([^?!.，。！？]{2,100})[?!.，。！？]*$|"
        r"(?:来自|由|在)([^，。！？]{2,60})[，。！？]*$",
        query,
        re.I,
    )
    if not match:
        return None
    candidate = next(group for group in match.groups() if group)
    candidate = _clean_relation_object(candidate)
    if candidate is None or re.fullmatch(r"(?:19|20)\d{2}", candidate):
        return None
    if candidate.casefold() in {
        "the current scope",
        "current scope",
        "the corpus",
        "corpus",
        "the database",
        "database",
        "distinct papers",
        "year",
        "label",
    }:
        return None
    return candidate


def _resolve_entities(session: Session, query: str, plan: NlSqlPlan) -> None:
    candidate = _entity_candidate(query, plan)
    if candidate is None:
        return
    normalized_query = re.sub(r"\s+", " ", candidate.casefold())

    institution_matches: list[tuple[int, str]] = []
    for institution in session.execute(select(Institution)).scalars():
        names = [institution.canonical_name, *(institution.aliases or [])]
        matched_lengths = [
            len(name)
            for name in names
            if _phrase_in_query(str(name), normalized_query)
        ]
        if matched_lengths:
            institution_matches.append((max(matched_lengths), institution.id))
    if institution_matches:
        longest = max(length for length, _id in institution_matches)
        plan.filters["institution_ids"] = sorted(
            {_id for length, _id in institution_matches if length == longest}
        )

    country_matches: list[tuple[int, str]] = []
    seen_countries: set[str] = set()
    for raw_country in session.execute(select(Institution.country)).scalars():
        for entry in canonical_country_entries(raw_country):
            if entry.identity in seen_countries:
                continue
            seen_countries.add(entry.identity)
            if _phrase_in_query(entry.display, normalized_query):
                country_matches.append((len(entry.display), entry.display))
    if country_matches:
        longest = max(length for length, _country in country_matches)
        plan.filters["countries"] = sorted(
            {country for length, country in country_matches if length == longest}
        )

    author_matches: list[tuple[int, str]] = []
    for author in session.execute(select(Author)).scalars():
        names = [author.canonical_name, *(author.aliases or [])]
        matched_lengths = [
            len(name)
            for name in names
            if _phrase_in_query(str(name), normalized_query)
        ]
        if matched_lengths:
            author_matches.append((max(matched_lengths), author.id))
    if author_matches:
        longest = max(length for length, _id in author_matches)
        plan.filters["author_ids"] = sorted(
            {_id for length, _id in author_matches if length == longest}
        )


def _query_filter(plan: NlSqlPlan) -> PaperFilter:
    filters = plan.filters
    year = filters.get("year")
    return PaperFilter(
        year_from=year if year is not None else filters.get("year_from"),
        year_to=year if year is not None else filters.get("year_to"),
        labels=filters.get("labels", []),
        institution_ids=filters.get("institution_ids", []),
        countries=filters.get("countries", []),
        search=filters.get("text"),
    )


def _escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _scope_statement(
    base_filter: PaperFilter,
    plan: NlSqlPlan,
    paper_ids: list[str] | None,
):
    stmt = apply_filter(select(Paper.id), base_filter)
    stmt = apply_filter(stmt, _query_filter(plan))
    if paper_ids is not None:
        stmt = stmt.where(Paper.id.in_(paper_ids))
    if author_ids := plan.filters.get("author_ids"):
        stmt = stmt.where(
            exists().where(
                PaperAuthor.paper_id == Paper.id,
                PaperAuthor.author_id.in_(author_ids),
            )
        )
    if predicate := plan.filters.get("proposition_predicate"):
        proposition_conditions = [
            PaperProposition.paper_id == Paper.id,
            PaperProposition.predicate == predicate,
        ]
        if object_value := plan.filters.get("proposition_object"):
            pattern = f"%{_escape_like(str(object_value).casefold())}%"
            proposition_conditions.append(
                or_(
                    func.lower(PaperProposition.object_value).like(
                        pattern,
                        escape="\\",
                    ),
                    func.lower(PaperProposition.claim_text).like(
                        pattern,
                        escape="\\",
                    ),
                )
            )
            fulltext_match = exists().where(
                PaperChunk.paper_id == Paper.id,
                func.lower(PaperChunk.chunk_text).like(pattern, escape="\\"),
            )
            stmt = stmt.where(
                or_(exists().where(*proposition_conditions), fulltext_match)
            )
        else:
            stmt = stmt.where(exists().where(*proposition_conditions))
    return stmt.distinct()


def _proposition_conditions(plan: NlSqlPlan) -> list[Any]:
    conditions: list[Any] = []
    if predicate := plan.filters.get("proposition_predicate"):
        conditions.append(PaperProposition.predicate == predicate)
    if object_value := plan.filters.get("proposition_object"):
        pattern = f"%{_escape_like(str(object_value).casefold())}%"
        conditions.append(
            or_(
                func.lower(PaperProposition.object_value).like(
                    pattern,
                    escape="\\",
                ),
                func.lower(PaperProposition.claim_text).like(
                    pattern,
                    escape="\\",
                ),
            )
        )
    return conditions


def _statement_for_plan(plan: NlSqlPlan, scope_stmt):
    scope = scope_stmt.subquery("strict_sql_scope")
    in_scope = Paper.id.in_(select(scope.c.id))
    if plan.intent == "count_papers":
        if plan.group_by == "label":
            return (
                select(
                    PaperClassification.label,
                    func.count(distinct(Paper.id)).label("paper_count"),
                )
                .join(Paper, Paper.id == PaperClassification.paper_id)
                .where(in_scope)
                .group_by(PaperClassification.label)
                .order_by(desc("paper_count"), PaperClassification.label)
            )
        if plan.group_by == "year":
            return (
                select(
                    Paper.year,
                    func.count(distinct(Paper.id)).label("paper_count"),
                )
                .where(in_scope)
                .group_by(Paper.year)
                .order_by(Paper.year)
            )
        return select(func.count(distinct(Paper.id)).label("paper_count")).where(
            in_scope
        )
    if plan.intent == "top_authors":
        return (
            select(
                Author.id.label("author_id"),
                Author.canonical_name.label("author"),
                Author.is_ac_member,
                func.count(distinct(Paper.id)).label("paper_count"),
            )
            .join(PaperAuthor, PaperAuthor.author_id == Author.id)
            .join(Paper, Paper.id == PaperAuthor.paper_id)
            .where(in_scope)
            .group_by(Author.id, Author.canonical_name, Author.is_ac_member)
            .order_by(desc("paper_count"), Author.canonical_name, Author.id)
            .limit(plan.limit)
        )
    if plan.intent == "top_institutions":
        return (
            select(
                Institution.id.label("institution_id"),
                Institution.canonical_name.label("institution"),
                Institution.is_partner,
                func.count(distinct(Paper.id)).label("paper_count"),
            )
            .join(Author, Author.institution_id == Institution.id)
            .join(PaperAuthor, PaperAuthor.author_id == Author.id)
            .join(Paper, Paper.id == PaperAuthor.paper_id)
            .where(in_scope)
            .group_by(
                Institution.id,
                Institution.canonical_name,
                Institution.is_partner,
            )
            .order_by(
                desc("paper_count"),
                Institution.canonical_name,
                Institution.id,
            )
            .limit(plan.limit)
        )
    if plan.intent == "top_propositions":
        return (
            select(
                PaperProposition.predicate,
                PaperProposition.object_value,
                func.count(distinct(PaperProposition.paper_id)).label("paper_count"),
                func.avg(PaperProposition.confidence).label("avg_confidence"),
            )
            .join(Paper, Paper.id == PaperProposition.paper_id)
            .where(in_scope, *_proposition_conditions(plan))
            .group_by(PaperProposition.predicate, PaperProposition.object_value)
            .order_by(
                desc("paper_count"),
                desc("avg_confidence"),
                PaperProposition.predicate,
                PaperProposition.object_value,
            )
            .limit(plan.limit)
        )
    if plan.intent == "review_queue":
        return (
            select(
                Paper.id.label("paper_id"),
                Paper.title,
                Paper.year,
                PaperClassification.label,
                PaperClassification.confidence,
                PaperClassification.review_priority,
            )
            .join(PaperClassification, PaperClassification.paper_id == Paper.id)
            .where(in_scope, PaperClassification.needs_review.is_(True))
            .order_by(
                desc(PaperClassification.review_priority),
                desc(PaperClassification.confidence),
                Paper.id,
            )
            .limit(plan.limit)
        )
    return (
        select(
            Paper.id.label("paper_id"),
            Paper.title,
            Paper.year,
            Paper.venue,
            PaperClassification.label,
            PaperClassification.confidence,
        )
        .outerjoin(PaperClassification, PaperClassification.paper_id == Paper.id)
        .where(in_scope)
        .order_by(
            desc(PaperClassification.confidence),
            desc(Paper.year),
            Paper.id,
        )
        .limit(plan.limit)
    )


def _json_value(value: Any) -> Any:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, (list, tuple, set)):
        return [_json_value(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _json_value(item) for key, item in value.items()}
    return str(value)


def _compile_parameterized(stmt) -> tuple[str, dict[str, Any]]:
    compiled = stmt.compile(compile_kwargs={"render_postcompile": True})
    return str(compiled), {
        str(key): _json_value(value) for key, value in compiled.params.items()
    }


def _rows(result) -> list[dict[str, Any]]:
    return [
        {str(key): _json_value(value) for key, value in row._mapping.items()}
        for row in result
    ]


def _summary(
    plan: NlSqlPlan,
    rows: list[dict[str, Any]],
    *,
    chinese: bool,
    base_scope_paper_count: int,
) -> str:
    if not rows:
        if chinese:
            return (
                f"在当前 {base_scope_paper_count} 篇论文的范围内，没有找到结构化匹配。"
                "这不代表全文中没有相关内容；可以改用更宽泛的表述并检索全文证据。"
            )
        return (
            f"No structured matches were found among the {base_scope_paper_count} "
            "papers in the current scope. This does not mean the full text contains "
            "no relevant evidence; try broader wording or search the indexed full text."
        )
    if plan.intent == "count_papers":
        if len(rows) == 1 and "paper_count" in rows[0]:
            count = rows[0]["paper_count"]
            if count == 0:
                if chinese:
                    return (
                        f"在当前 {base_scope_paper_count} 篇论文的范围内，没有找到"
                        "符合这些结构化条件的论文。"
                    )
                return (
                    f"No papers matched those structured conditions within the current "
                    f"scope of {base_scope_paper_count} papers."
                )
            return (
                f"数据库查询返回 {count} 篇匹配论文。"
                if chinese
                else f"The database query returned {count} matching papers."
            )
        dimension = plan.group_by or "group"
        values = "; ".join(
            f"{row.get(dimension) if row.get(dimension) is not None else 'Unknown'}: {row['paper_count']}"
            for row in rows
        )
        return f"按{dimension}统计：{values}。" if chinese else f"Counts by {dimension}: {values}."

    lines: list[str] = []
    for row in rows:
        if plan.intent == "list_papers":
            lines.append(
                f"[{row['paper_id']}] {row['title']} "
                f"({row.get('year') or 'year unknown'}; {row.get('label') or 'unclassified'})"
            )
        elif plan.intent == "top_authors":
            lines.append(f"{row['author']}: {row['paper_count']} distinct papers")
        elif plan.intent == "top_institutions":
            lines.append(f"{row['institution']}: {row['paper_count']} distinct papers")
        elif plan.intent == "top_propositions":
            lines.append(
                f"{row['predicate']} — {row['object_value']}: "
                f"{row['paper_count']} distinct papers"
            )
        else:
            lines.append(
                f"[{row['paper_id']}] {row['title']} "
                f"(priority {float(row['review_priority']):.3f})"
            )
    heading = (
        f"数据库查询返回 {len(rows)} 行："
        if chinese
        else f"The database query returned {len(rows)} rows:"
    )
    return f"{heading}\n" + "\n".join(f"- {line}" for line in lines)


def run_nl_sql(
    session: Session,
    query: str,
    *,
    base_filter: PaperFilter | None = None,
    paper_ids: list[str] | None = None,
    use_llm: bool | None = None,
) -> NlSqlResult:
    plan = plan_nl_sql(query, use_llm=use_llm)
    _resolve_entities(session, query, plan)
    active_filter = base_filter or PaperFilter()
    normalized_paper_ids = None
    if paper_ids is not None:
        normalized_paper_ids = list(dict.fromkeys(paper_ids))
    base_scope_stmt = apply_filter(select(Paper.id), active_filter)
    if normalized_paper_ids is not None:
        base_scope_stmt = base_scope_stmt.where(Paper.id.in_(normalized_paper_ids))
    base_scope_ids = list(session.execute(base_scope_stmt.distinct()).scalars())
    scope_stmt = _scope_statement(active_filter, plan, normalized_paper_ids)
    scope_ids = list(session.execute(scope_stmt).scalars())
    stmt = _statement_for_plan(plan, scope_stmt)
    sql, parameters = _compile_parameterized(stmt)
    rows = _rows(session.execute(stmt))
    sql_fingerprint = hashlib.sha256(
        json.dumps(
            {"sql": sql, "parameters": parameters},
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    audit = {
        "planner": PLANNER_ID,
        "answer_renderer": ANSWER_RENDERER_ID,
        "read_only": True,
        "llm_used": False,
        "allowed_intents": sorted(_INTENTS),
        "allowed_tables": list(ALLOWED_TABLES),
        "intent": plan.intent,
        "group_by": plan.group_by,
        "limit": plan.limit,
        "query_constraints": _json_value(plan.filters),
        "page_filter": canonical_filter_payload(active_filter),
        "page_filter_fingerprint": filter_fingerprint(active_filter),
        "base_scope_paper_count": len(set(base_scope_ids)),
        "scope_paper_count": len(set(scope_ids)),
        "scope_paper_set_sha256": paper_set_sha256(scope_ids),
        "scope_paper_set_encoding": PAPER_SET_ENCODING,
        "statement_sha256": sql_fingerprint,
        "parameter_binding": "sqlalchemy-bound-parameters",
        "statement_type": "SELECT",
        "row_count": len(rows),
    }
    return NlSqlResult(
        query=query,
        plan=plan,
        sql=sql,
        parameters=parameters,
        rows=rows,
        summary=_summary(
            plan,
            rows,
            chinese=bool(re.search(r"[\u3400-\u9fff]", query)),
            base_scope_paper_count=len(set(base_scope_ids)),
        ),
        audit=audit,
    )
