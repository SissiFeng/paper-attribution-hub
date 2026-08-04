"""Unified paper filter used by /papers, /papers/export.csv, /analytics/*.

Why this exists: figure.md is explicit that analytics charts must come from
structured DB queries, not RAG. That means the same filter has to drive the
table view, the Sankey, the timeline, and the institution network. A single
Pydantic spec + one SQLAlchemy helper guarantees they stay in sync.
"""
from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Annotated
from urllib.parse import urlencode

from fastapi import HTTPException, Query
from pydantic import BaseModel, Field, ValidationError, field_validator, model_validator
from sqlalchemy import Select, String, exists, false, func, or_, select
from sqlalchemy.orm import Session

from app.classification_labels import CLASSIFICATION_LABELS
from app.country_normalization import (
    canonical_country_entries,
    canonical_country_values,
    country_keys_v1,
)
from app.models import (
    Author,
    HumanReview,
    Institution,
    Paper,
    PaperAuthor,
    PaperClassification,
    Topic,
)
from app.review_contract import (
    AC_RELEVANCE_JUDGEMENTS,
    AI_FOR_SCIENCE_JUDGEMENTS,
    CORPUS_SOURCES,
    REVIEW_STATUSES,
    SDL_JUDGEMENTS,
    infer_corpus_sources,
    normalize_corpus_sources,
)


SDL_MODEL_EQUIVALENTS = {
    "CONFIRMED_SDL": ("SDL_RELEVANT",),
    "PROBABLE_SDL": ("SDL_ADJACENT",),
    "SDL_ADJACENT": ("SDL_ADJACENT",),
    "NOT_SDL": ("SDL_NOT_RELEVANT",),
    "INSUFFICIENT_EVIDENCE": (),
}
AC_MODEL_EQUIVALENTS = {
    "AC_RELEVANT": ("CORE_AC", "AC_RELATED"),
    "NOT_AC_RELEVANT": ("NO_AC_EVIDENCE",),
    "INSUFFICIENT_EVIDENCE": ("WEAK_AC_SIGNAL",),
}


class PaperFilter(BaseModel):
    """Filter parameters accepted by every paper-listing or analytics endpoint."""

    year_from: int | None = None
    year_to: int | None = None
    labels: list[str] = Field(default_factory=list)
    topic_ids: list[str] = Field(default_factory=list)
    fields: list[str] = Field(default_factory=list)
    institution_ids: list[str] = Field(default_factory=list)
    countries: list[str] = Field(default_factory=list)
    # D20 reporting-entity support: match papers whose institution city matches
    # any of these values (case-insensitive). E.g. "Toronto" selects all
    # Toronto-institution papers (U of T + Vector Institute), separate from the
    # University of Toronto institution filter.
    cities: list[str] = Field(default_factory=list)
    corpus_sources: list[str] = Field(default_factory=list)
    sdl_judgements: list[str] = Field(default_factory=list)
    ac_relevance_judgements: list[str] = Field(default_factory=list)
    ai_for_science_judgements: list[str] = Field(default_factory=list)
    review_statuses: list[str] = Field(default_factory=list)
    # D21 report-evidence policy: allow unreviewed papers alongside a
    # review-status restriction (reviewed papers must still match).
    review_statuses_include_unreviewed: bool = False
    # Confidence floor applied only to papers without a human review.
    unreviewed_min_confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    # Model SDL labels permitted for unreviewed papers (human_plus_probable).
    unreviewed_sdl_labels: list[str] = Field(default_factory=list)
    # Unreviewed papers whose corpus_sources intersect this list are excluded.
    exclude_unreviewed_corpus_sources: list[str] = Field(default_factory=list)
    # Only papers with a human review (any status allowed by review_statuses,
    # or any status when review_statuses is empty) may match.
    require_review: bool = False
    partner_only: bool = False
    ac_author_only: bool = False
    has_fulltext: bool | None = None
    has_review: bool | None = None
    min_confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    max_confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    search: str | None = None

    @field_validator("labels", mode="before")
    @classmethod
    def validate_labels(cls, values: object) -> list[str]:
        return _validated_enum_values(values, CLASSIFICATION_LABELS, "label")

    @field_validator("corpus_sources", mode="before")
    @classmethod
    def validate_corpus_sources(cls, values: object) -> list[str]:
        return _validated_enum_values(values, CORPUS_SOURCES, "corpus source")

    @field_validator("sdl_judgements", mode="before")
    @classmethod
    def validate_sdl_judgements(cls, values: object) -> list[str]:
        return _validated_enum_values(values, SDL_JUDGEMENTS, "SDL judgement")

    @field_validator("ac_relevance_judgements", mode="before")
    @classmethod
    def validate_ac_judgements(cls, values: object) -> list[str]:
        return _validated_enum_values(
            values,
            AC_RELEVANCE_JUDGEMENTS,
            "AC relevance judgement",
        )

    @field_validator("ai_for_science_judgements", mode="before")
    @classmethod
    def validate_ai_judgements(cls, values: object) -> list[str]:
        return _validated_enum_values(
            values,
            AI_FOR_SCIENCE_JUDGEMENTS,
            "AI-for-science judgement",
        )

    @field_validator("review_statuses", mode="before")
    @classmethod
    def validate_review_statuses(cls, values: object) -> list[str]:
        return _validated_enum_values(values, REVIEW_STATUSES, "review status")

    @field_validator("exclude_unreviewed_corpus_sources", mode="before")
    @classmethod
    def validate_exclude_unreviewed_corpus_sources(cls, values: object) -> list[str]:
        return _validated_enum_values(values, CORPUS_SOURCES, "corpus source")

    @model_validator(mode="after")
    def validate_ranges(self) -> "PaperFilter":
        if (
            self.year_from is not None
            and self.year_to is not None
            and self.year_from > self.year_to
        ):
            raise ValueError("year_from must be less than or equal to year_to")
        if (
            self.min_confidence is not None
            and self.max_confidence is not None
            and self.min_confidence > self.max_confidence
        ):
            raise ValueError(
                "min_confidence must be less than or equal to max_confidence"
            )
        return self

    def is_empty(self) -> bool:
        return self.model_dump(exclude_defaults=True) == {}


def paper_filter_query(
    year_from: Annotated[int | None, Query()] = None,
    year_to: Annotated[int | None, Query()] = None,
    labels: Annotated[list[str] | None, Query()] = None,
    topic_ids: Annotated[list[str] | None, Query()] = None,
    fields: Annotated[list[str] | None, Query()] = None,
    institution_ids: Annotated[list[str] | None, Query()] = None,
    countries: Annotated[list[str] | None, Query()] = None,
    cities: Annotated[list[str] | None, Query()] = None,
    corpus_sources: Annotated[list[str] | None, Query()] = None,
    sdl_judgements: Annotated[list[str] | None, Query()] = None,
    ac_relevance_judgements: Annotated[list[str] | None, Query()] = None,
    ai_for_science_judgements: Annotated[list[str] | None, Query()] = None,
    review_statuses: Annotated[list[str] | None, Query()] = None,
    review_statuses_include_unreviewed: Annotated[bool, Query()] = False,
    unreviewed_min_confidence: Annotated[float | None, Query(ge=0.0, le=1.0)] = None,
    unreviewed_sdl_labels: Annotated[list[str] | None, Query()] = None,
    exclude_unreviewed_corpus_sources: Annotated[list[str] | None, Query()] = None,
    require_review: Annotated[bool, Query()] = False,
    partner_only: Annotated[bool, Query()] = False,
    ac_author_only: Annotated[bool, Query()] = False,
    has_fulltext: Annotated[bool | None, Query()] = None,
    has_review: Annotated[bool | None, Query()] = None,
    min_confidence: Annotated[float | None, Query(ge=0.0, le=1.0)] = None,
    max_confidence: Annotated[float | None, Query(ge=0.0, le=1.0)] = None,
    search: Annotated[str | None, Query()] = None,
) -> PaperFilter:
    """FastAPI dependency that turns query params into a PaperFilter."""
    if year_from is not None and year_to is not None and year_from > year_to:
        raise HTTPException(
            status_code=422,
            detail="year_from must be less than or equal to year_to",
        )
    if (
        min_confidence is not None
        and max_confidence is not None
        and min_confidence > max_confidence
    ):
        raise HTTPException(
            status_code=422,
            detail="min_confidence must be less than or equal to max_confidence",
        )
    try:
        return PaperFilter(
            year_from=year_from,
            year_to=year_to,
            labels=labels or [],
            topic_ids=topic_ids or [],
            fields=fields or [],
            institution_ids=institution_ids or [],
            countries=countries or [],
            cities=cities or [],
            corpus_sources=corpus_sources or [],
            sdl_judgements=sdl_judgements or [],
            ac_relevance_judgements=ac_relevance_judgements or [],
            ai_for_science_judgements=ai_for_science_judgements or [],
            review_statuses=review_statuses or [],
            review_statuses_include_unreviewed=review_statuses_include_unreviewed,
            unreviewed_min_confidence=unreviewed_min_confidence,
            unreviewed_sdl_labels=unreviewed_sdl_labels or [],
            exclude_unreviewed_corpus_sources=exclude_unreviewed_corpus_sources or [],
            require_review=require_review,
            partner_only=partner_only,
            ac_author_only=ac_author_only,
            has_fulltext=has_fulltext,
            has_review=has_review,
            min_confidence=min_confidence,
            max_confidence=max_confidence,
            search=search,
        )
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


def apply_filter(stmt: Select, filt: PaperFilter) -> Select:
    """Apply a PaperFilter to a Select that returns Paper rows."""
    if filt.year_from is not None:
        stmt = stmt.where(Paper.year >= filt.year_from)
    if filt.year_to is not None:
        stmt = stmt.where(Paper.year <= filt.year_to)
    if filt.has_fulltext is not None:
        stmt = stmt.where(Paper.full_text_available.is_(filt.has_fulltext))
    if filt.search:
        escaped = _escape_like(filt.search.lower())
        like = f"%{escaped}%"
        stmt = stmt.where(
            or_(
                func.lower(Paper.title).like(like, escape="\\"),
                func.lower(Paper.abstract).like(like, escape="\\"),
            )
        )

    if filt.fields:
        stmt = stmt.where(
            or_(
                *[
                    or_(
                        func.cast(Paper.sdl_tags, String).like(
                            _quoted_json_value_pattern(field),
                            escape="\\",
                        ),
                        func.cast(Paper.research_tags, String).like(
                            _quoted_json_value_pattern(field),
                            escape="\\",
                        ),
                    )
                    for field in filt.fields
                ]
            )
        )

    if filt.corpus_sources:
        explicit_conditions = []
        legacy_conditions = []
        for source in filt.corpus_sources:
            normalized = source.upper()
            explicit_conditions.append(
                func.cast(Paper.corpus_sources, String).like(
                    _quoted_json_value_pattern(normalized),
                    escape="\\",
                )
            )
            legacy_conditions.extend(_legacy_corpus_source_conditions(normalized))
        has_explicit_sources = (
            func.coalesce(func.json_array_length(Paper.corpus_sources), 0) > 0
        )
        stmt = stmt.where(
            or_(
                has_explicit_sources & or_(*explicit_conditions),
                ~has_explicit_sources & or_(*legacy_conditions),
            )
        )

    if (
        filt.labels
        or filt.min_confidence is not None
        or filt.max_confidence is not None
        or filt.topic_ids
    ):
        # Use EXISTS subquery instead of JOIN so we never produce duplicate rows
        # (JOIN on a 1:1 relationship is safe, but DISTINCT on JSON columns fails
        # in PostgreSQL because json has no equality operator).
        cls_conds = [PaperClassification.paper_id == Paper.id]
        if filt.labels:
            cls_conds.append(
                PaperClassification.label.in_(
                    [label.upper() for label in filt.labels]
                )
            )
        if filt.min_confidence is not None:
            cls_conds.append(PaperClassification.confidence >= filt.min_confidence)
        if filt.max_confidence is not None:
            cls_conds.append(PaperClassification.confidence <= filt.max_confidence)
        if filt.topic_ids:
            cls_conds.append(
                or_(
                    *[
                    func.cast(PaperClassification.matched_topics, String).like(
                        like_pattern,
                        escape="\\",
                    )
                        for tid in filt.topic_ids
                        for like_pattern in [_topic_id_pattern(tid)]
                    ]
                )
            )
        stmt = stmt.where(
            exists(select(1).select_from(PaperClassification).where(*cls_conds))
        )

    if filt.has_review is True or filt.require_review:
        stmt = stmt.where(exists().where(HumanReview.paper_id == Paper.id))
    elif filt.has_review is False:
        stmt = stmt.where(~exists().where(HumanReview.paper_id == Paper.id))

    if filt.review_statuses:
        review_cond = exists().where(
            HumanReview.paper_id == Paper.id,
            HumanReview.review_status.in_(filt.review_statuses),
        )
        if filt.review_statuses_include_unreviewed:
            review_cond = or_(
                ~exists().where(HumanReview.paper_id == Paper.id),
                review_cond,
            )
        stmt = stmt.where(review_cond)

    if filt.unreviewed_min_confidence is not None:
        # Confidence floor applies only to papers without a human review;
        # human-judged papers are not re-gated by classifier confidence.
        stmt = stmt.where(
            or_(
                exists().where(HumanReview.paper_id == Paper.id),
                exists().where(
                    PaperClassification.paper_id == Paper.id,
                    PaperClassification.confidence >= filt.unreviewed_min_confidence,
                ),
            )
        )

    if filt.unreviewed_sdl_labels:
        # Only unreviewed papers may match these model SDL labels; reviewed
        # papers must pass the human judgement scope above.
        stmt = stmt.where(
            or_(
                exists().where(HumanReview.paper_id == Paper.id),
                exists().where(
                    PaperClassification.paper_id == Paper.id,
                    PaperClassification.sdl_relevance_label.in_(
                        filt.unreviewed_sdl_labels
                    ),
                ),
            )
        )

    if filt.exclude_unreviewed_corpus_sources:
        excluded_conds = [
            func.cast(Paper.corpus_sources, String).like(
                _quoted_json_value_pattern(source),
                escape="\\",
            )
            for source in filt.exclude_unreviewed_corpus_sources
        ]
        stmt = stmt.where(
            or_(
                exists().where(HumanReview.paper_id == Paper.id),
                ~exists().where(HumanReview.paper_id == Paper.id)
                & ~or_(*excluded_conds),
            )
        )

    if filt.sdl_judgements:
        stmt = stmt.where(
            _effective_judgement_condition(
                human_column=HumanReview.sdl_judgement,
                model_column=PaperClassification.sdl_relevance_label,
                values=filt.sdl_judgements,
                model_equivalents=SDL_MODEL_EQUIVALENTS,
            )
        )
    if filt.ac_relevance_judgements:
        stmt = stmt.where(
            _effective_judgement_condition(
                human_column=HumanReview.ac_relevance_judgement,
                model_column=PaperClassification.ac_attribution_label,
                values=filt.ac_relevance_judgements,
                model_equivalents=AC_MODEL_EQUIVALENTS,
            )
        )
    if filt.ai_for_science_judgements:
        stmt = stmt.where(
            exists().where(
                HumanReview.paper_id == Paper.id,
                HumanReview.ai_for_science_judgement.in_(
                    filt.ai_for_science_judgements
                ),
            )
        )

    if (
        filt.ac_author_only
        or filt.institution_ids
        or filt.partner_only
        or filt.countries
        or filt.cities
    ):
        # Join through paper_authors → authors → institutions for these filters.
        pa = PaperAuthor.__table__
        au = Author.__table__
        inst = Institution.__table__
        stmt = stmt.where(
            exists().select_from(pa.join(au, au.c.id == pa.c.author_id))
            .where(pa.c.paper_id == Paper.id)
            .where(
                (au.c.is_ac_member.is_(True))
                if filt.ac_author_only
                else True
            )
        )
        if (
            filt.institution_ids
            or filt.partner_only
            or filt.countries
            or filt.cities
        ):
            institution_conditions = []
            if filt.institution_ids:
                institution_conditions.append(inst.c.id.in_(filt.institution_ids))
            if filt.partner_only:
                institution_conditions.append(inst.c.is_partner.is_(True))
            if filt.countries:
                institution_conditions.append(
                    or_(
                        *[
                            _country_key_condition(inst.c.country_keys, country)
                            for country in filt.countries
                        ]
                    )
                )
            if filt.cities:
                institution_conditions.append(
                    or_(
                        *[
                            func.lower(inst.c.city).like(
                                _escape_like(city.lower()), escape="\\"
                            )
                            for city in filt.cities
                        ]
                    )
                )
            stmt = stmt.where(
                exists()
                .select_from(
                    pa.join(au, au.c.id == pa.c.author_id).join(
                        inst, inst.c.id == au.c.institution_id
                    )
                )
                .where(pa.c.paper_id == Paper.id)
                .where(*institution_conditions)
            )

    return stmt


def filtered_paper_ids(session: Session, filt: PaperFilter) -> list[str]:
    """Helper that returns the paper-id list matching the filter."""
    stmt = apply_filter(select(Paper.id), filt)
    return [pid for (pid,) in session.execute(stmt).all()]


def canonical_filter_payload(filt: PaperFilter) -> dict:
    """Stable, explicit filter representation for audit and replay."""
    payload = filt.model_dump()
    for key, value in payload.items():
        if isinstance(value, list):
            payload[key] = sorted(set(value))
    # Drop the D21 policy fields when at defaults so ordinary filter URLs and
    # audit payloads stay stable and don't leak report-scoped knobs.
    for key in (
        "review_statuses_include_unreviewed",
        "unreviewed_min_confidence",
        "unreviewed_sdl_labels",
        "exclude_unreviewed_corpus_sources",
        "require_review",
    ):
        if key in payload and payload[key] in (False, None, []):
            del payload[key]
    return payload


def filter_fingerprint(filt: PaperFilter) -> str:
    encoded = json.dumps(
        canonical_filter_payload(filt),
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def canonical_filter_query_string(
    filt: PaperFilter,
    **overrides: object,
) -> str:
    """Encode the complete filter deterministically for replayable URLs."""
    payload = canonical_filter_payload(filt)
    payload.update(overrides)
    pairs: list[tuple[str, str]] = []
    for key in sorted(payload):
        value = payload[key]
        if value is None:
            continue
        values = value if isinstance(value, list) else [value]
        for item in values:
            if isinstance(item, bool):
                encoded = "true" if item else "false"
            else:
                encoded = str(item)
            pairs.append((key, encoded))
    return urlencode(pairs, doseq=True)


PAPER_SET_ENCODING = "paper-id-set-json.v1"


def paper_set_sha256(paper_ids: list[str]) -> str:
    """Hash a paper-id set with a versioned, collation-independent encoding."""
    encoded = json.dumps(
        {
            "encoding": PAPER_SET_ENCODING,
            "paper_ids": sorted(set(paper_ids)),
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def build_filter_audit(
    session: Session,
    filt: PaperFilter,
    *,
    algorithm: str,
    metric_definitions: dict[str, str],
    projection: dict | None = None,
) -> dict:
    """Describe exactly which persisted paper set supports an analysis."""
    papers = list(
        session.execute(
            apply_filter(select(Paper), filt)
        ).scalars()
    )
    papers.sort(key=lambda paper: paper.id)
    paper_ids = [paper.id for paper in papers]
    classified = sum(paper.classification is not None for paper in papers)
    reviewed = sum(paper.review is not None for paper in papers)
    fulltext = sum(bool(paper.full_text_available) for paper in papers)
    corpus_breakdown: dict[str, int] = {}
    for paper in papers:
        sources = normalize_corpus_sources(paper.corpus_sources or []) or infer_corpus_sources(
            provenance=paper.provenance,
            source=paper.source,
            retrieval_tier=paper.retrieval_tier,
            ac_known_publication=paper.ac_known_publication,
        )
        for source in sources:
            corpus_breakdown[source] = corpus_breakdown.get(source, 0) + 1
    audit = {
        "filter": canonical_filter_payload(filt),
        "filter_fingerprint": filter_fingerprint(filt),
        "paper_set_sha256": paper_set_sha256(paper_ids),
        "paper_set_encoding": PAPER_SET_ENCODING,
        "included_papers": len(papers),
        "classified_papers": classified,
        "reviewed_papers": reviewed,
        "fulltext_papers": fulltext,
        "corpus_source_breakdown": dict(sorted(corpus_breakdown.items())),
        "algorithm": algorithm,
        "metric_definitions": metric_definitions,
        "filter_semantics": {
            "within_dimension": "OR",
            "between_dimensions": "AND",
            "human_judgement_precedence": "A non-null human judgement overrides the corresponding model-derived scope label.",
            "corpus_source_counting": "A paper may contribute to more than one corpus-source bucket.",
        },
        "generated_at": datetime.now(UTC).isoformat(),
    }
    if projection is not None:
        canonical_projection = _canonical_json_value(projection)
        encoded = json.dumps(
            canonical_projection,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
        audit["projection"] = canonical_projection
        audit["projection_fingerprint"] = hashlib.sha256(encoded).hexdigest()
    return audit


def _canonical_json_value(value):
    if isinstance(value, dict):
        return {
            key: _canonical_json_value(value[key])
            for key in sorted(value)
        }
    if isinstance(value, (list, tuple, set)):
        normalized = [_canonical_json_value(item) for item in value]
        return sorted(normalized, key=lambda item: json.dumps(item, sort_keys=True))
    return value


def available_filter_options(session: Session) -> dict:
    """Return persisted filter facets without inventing unavailable values."""
    papers = list(session.execute(select(Paper)).scalars())
    institutions = list(
        session.execute(
            select(Institution).order_by(Institution.canonical_name.asc())
        ).scalars()
    )
    topics = list(
        session.execute(select(Topic).order_by(Topic.name.asc())).scalars()
    )
    fields = sorted(
        {
            str(value).strip()
            for paper in papers
            for values in (paper.sdl_tags or [], paper.research_tags or [])
            for value in values
            if str(value).strip()
        }
    )
    corpus_sources = set()
    for paper in papers:
        corpus_sources.update(
            normalize_corpus_sources(paper.corpus_sources or [])
            or infer_corpus_sources(
                provenance=paper.provenance,
                source=paper.source,
                retrieval_tier=paper.retrieval_tier,
                ac_known_publication=paper.ac_known_publication,
            )
        )
    return {
        "years": sorted({paper.year for paper in papers if paper.year is not None}),
        "countries": sorted(
            {
                country.display
                for institution in institutions
                for country in canonical_country_entries(institution.country)
            }
        ),
        "institutions": [
            {
                "id": institution.id,
                "name": institution.canonical_name,
                "country": "; ".join(canonical_country_values(institution.country))
                or None,
                "is_partner": bool(institution.is_partner),
            }
            for institution in institutions
        ],
        "topics": [{"id": topic.id, "name": topic.name} for topic in topics],
        "fields": fields,
        "corpus_sources": sorted(corpus_sources),
    }


def _escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _quoted_json_value_pattern(value: str) -> str:
    encoded = json.dumps(str(value), ensure_ascii=False)[1:-1]
    return f'%"{_escape_like(encoded)}"%'


def _topic_id_pattern(value: str) -> str:
    encoded = json.dumps(str(value), ensure_ascii=False)[1:-1]
    return f'%"topic_id": "{_escape_like(encoded)}"%'


def _first_semicolon_value(value: str | None) -> str | None:
    values = split_semicolon_values(value)
    return values[0] if values else None


def split_semicolon_values(value: str | None) -> list[str]:
    """Split, trim, and case-insensitively deduplicate multi-value fields."""
    output: list[str] = []
    seen: set[str] = set()
    for part in (value or "").split(";"):
        normalized = part.strip()
        key = normalized.casefold()
        if normalized and key not in seen:
            output.append(normalized)
            seen.add(key)
    return output


def _effective_judgement_condition(
    *,
    human_column,
    model_column,
    values: list[str],
    model_equivalents: dict[str, tuple[str, ...]],
):
    human_present = exists().where(
        HumanReview.paper_id == Paper.id,
        human_column.is_not(None),
    )
    model_values = sorted(
        {
            model_value
            for value in values
            for model_value in model_equivalents.get(value, ())
        }
    )
    model_match = exists().where(
        PaperClassification.paper_id == Paper.id,
        model_column.in_(model_values),
    )
    return or_(
        exists().where(
            HumanReview.paper_id == Paper.id,
            human_column.in_(values),
        ),
        ~human_present & model_match,
    )


def _validated_enum_values(
    values: object,
    allowed: frozenset[str],
    field_name: str,
) -> list[str]:
    if values is None:
        return []
    raw_values = values if isinstance(values, (list, tuple, set)) else [values]
    normalized = [str(value).strip().upper() for value in raw_values if str(value).strip()]
    invalid = sorted(set(normalized) - allowed)
    if invalid:
        raise ValueError(f"unsupported {field_name}: {', '.join(invalid)}")
    return list(dict.fromkeys(normalized))


def _country_key_condition(column, value: str):
    keys = country_keys_v1(value)
    if not keys:
        return false()
    return or_(
        *[
            func.cast(column, String).like(
                _quoted_json_value_pattern(key),
                escape="\\",
            )
            for key in keys
        ]
    )


def _legacy_corpus_source_conditions(source: str) -> list:
    provenance = func.coalesce(func.lower(Paper.provenance), "")
    paper_source = func.coalesce(func.lower(Paper.source), "")
    retrieval_tier = func.coalesce(func.lower(Paper.retrieval_tier), "")
    if source == "AC_MEMBER_CORPUS":
        return [
            provenance == "ac_gold",
            Paper.ac_known_publication.is_(True),
        ]
    if source == "STRICT_SDL_KEYWORD":
        return [retrieval_tier.like("%tier1%")]
    if source == "ARCHITECTURE_BROAD_RETRIEVAL":
        return [retrieval_tier.like("%tier2%")]
    if source == "MANUALLY_ADDED":
        return [
            provenance.in_(("manual", "manual_upload")),
            paper_source == "manual",
        ]
    if source == "LEGACY_IMPORT":
        return [
            provenance.in_(("", "csv")),
            paper_source == "csv",
        ]
    if source == "OTHER":
        recognized = or_(
            provenance == "ac_gold",
            Paper.ac_known_publication.is_(True),
            provenance.in_(("manual", "manual_upload")),
            paper_source == "manual",
            retrieval_tier.like("%tier1%"),
            retrieval_tier.like("%tier2%"),
            provenance.in_(("", "csv")),
            paper_source == "csv",
        )
        return [~recognized]
    return [false()]
