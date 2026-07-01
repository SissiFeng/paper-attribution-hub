"""Cross-SDL knowledge base: aggregated, evidence-linked entity and lab pages
built on the foundation layer (sdl.py models) and transfer analytics."""
from __future__ import annotations

from collections import Counter, defaultdict

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import (
    Paper,
    PaperChunk,
    PaperClassification,
    PaperEntity,
    PaperLabLink,
    SdlLab,
)
from app.services.sag_lite_service import entity_event_trail
from app.services.transfer_service import adoption_lags

ENTITY_TYPES = ("method", "material", "instrument", "software")

_EVIDENCE_LIMIT = 10
_EVIDENCE_CHARS = 300
_TOP_ENTITIES_PER_TYPE = 10


def entity_index(
    session: Session, entity_type: str | None = None, q: str | None = None
) -> list[dict]:
    """Distinct normalized entities with paper/lab counts and year span,
    sorted by paper_count descending."""
    stmt = (
        select(
            PaperEntity.entity_type,
            PaperEntity.normalized_name,
            func.count(PaperEntity.paper_id.distinct()),
            func.count(PaperLabLink.lab_id.distinct()),
            func.min(Paper.year),
            func.max(Paper.year),
        )
        .join(Paper, Paper.id == PaperEntity.paper_id)
        .outerjoin(PaperLabLink, PaperLabLink.paper_id == PaperEntity.paper_id)
        .group_by(PaperEntity.entity_type, PaperEntity.normalized_name)
    )
    if entity_type is not None:
        stmt = stmt.where(PaperEntity.entity_type == entity_type)
    if q:
        stmt = stmt.where(PaperEntity.normalized_name.ilike(f"%{q}%"))

    entries = [
        {
            "entity_type": etype,
            "name": name,
            "paper_count": paper_count,
            "lab_count": lab_count,
            "first_year": first_year,
            "last_year": last_year,
        }
        for etype, name, paper_count, lab_count, first_year, last_year
        in session.execute(stmt)
    ]
    entries.sort(key=lambda e: (-e["paper_count"], e["name"], e["entity_type"]))
    return entries


def entity_page(
    session: Session, entity_type: str, normalized_name: str
) -> dict | None:
    """Full page for one normalized entity: labs, papers, timeline, evidence
    snippets and its adoption-lag entry. None if the entity is unknown."""
    rows = session.execute(
        select(PaperEntity, Paper)
        .join(Paper, Paper.id == PaperEntity.paper_id)
        .where(
            PaperEntity.entity_type == entity_type,
            PaperEntity.normalized_name == normalized_name,
        )
        .order_by(Paper.year, Paper.id)
    ).all()
    if not rows:
        return None

    paper_ids = [paper.id for _, paper in rows]
    paper_labs: dict[str, list[str]] = defaultdict(list)
    for paper_id, lab_id in session.execute(
        select(PaperLabLink.paper_id, PaperLabLink.lab_id)
        .where(PaperLabLink.paper_id.in_(paper_ids))
        .order_by(PaperLabLink.lab_id)
    ):
        paper_labs[paper_id].append(lab_id)
    lab_names = dict(session.execute(select(SdlLab.id, SdlLab.name)).all())
    labels = dict(
        session.execute(
            select(PaperClassification.paper_id, PaperClassification.label).where(
                PaperClassification.paper_id.in_(paper_ids)
            )
        ).all()
    )

    papers: list[dict] = []
    timeline: Counter[int] = Counter()
    labs: dict[str, dict] = {}
    stages: Counter[str] = Counter()
    for entity, paper in rows:
        lab_ids = paper_labs.get(paper.id, [])
        papers.append(
            {
                "id": paper.id,
                "title": paper.title,
                "year": paper.year,
                "labs": lab_ids,
                "confidence": entity.confidence,
                "label": labels.get(paper.id),
                "stage": entity.stage,
                "usage_snippet": entity.usage_snippet,
            }
        )
        if entity.stage is not None:
            stages[entity.stage] += 1
        if paper.year is not None:
            timeline[paper.year] += 1
        for lab_id in lab_ids:
            agg = labs.setdefault(
                lab_id,
                {
                    "lab_id": lab_id,
                    "lab_name": lab_names.get(lab_id, lab_id),
                    "first_year": None,
                    "paper_count": 0,
                },
            )
            agg["paper_count"] += 1
            if paper.year is not None and (
                agg["first_year"] is None or paper.year < agg["first_year"]
            ):
                agg["first_year"] = paper.year

    evidence = [
        {
            "paper_id": paper_id,
            "paper_title": title,
            "text": text[:_EVIDENCE_CHARS],
            "stage": stage,
            "usage_snippet": usage_snippet,
        }
        for paper_id, title, text, stage, usage_snippet in session.execute(
            select(
                PaperEntity.paper_id,
                Paper.title,
                PaperChunk.chunk_text,
                PaperEntity.stage,
                PaperEntity.usage_snippet,
            )
            .join(Paper, Paper.id == PaperEntity.paper_id)
            .join(PaperChunk, PaperChunk.id == PaperEntity.evidence_chunk_id)
            .where(
                PaperEntity.entity_type == entity_type,
                PaperEntity.normalized_name == normalized_name,
            )
            .limit(_EVIDENCE_LIMIT)
        )
    ]

    adoption = next(
        (
            entry
            for entry in adoption_lags(session, entity_type=entity_type, min_labs=1)
            if entry["entity"] == normalized_name
        ),
        None,
    )

    return {
        "entity": normalized_name,
        "entity_type": entity_type,
        "labs": sorted(
            labs.values(), key=lambda lab: (-lab["paper_count"], lab["lab_id"])
        ),
        "papers": papers,
        "timeline": [
            {"year": year, "paper_count": count}
            for year, count in sorted(timeline.items())
        ],
        "evidence": evidence,
        "adoption": adoption,
        "stages": dict(stages),
        "events": entity_event_trail(session, entity_type, normalized_name),
    }


def lab_profile(session: Session, lab_id: str) -> dict | None:
    """Aggregated profile for one lab: papers, sdl_tags histogram, top entities
    by type, collaborations and unique-entity count. None if unknown."""
    lab = session.get(SdlLab, lab_id)
    if lab is None:
        return None

    paper_rows = session.execute(
        select(Paper.id, Paper.year, Paper.sdl_tags)
        .join(PaperLabLink, PaperLabLink.paper_id == Paper.id)
        .where(PaperLabLink.lab_id == lab_id)
    ).all()
    paper_ids = [pid for pid, _, _ in paper_rows]
    years = [year for _, year, _ in paper_rows if year is not None]
    tag_counts: Counter[str] = Counter(
        str(tag).strip()
        for _, _, sdl_tags in paper_rows
        for tag in (sdl_tags or [])
        if str(tag).strip()
    )

    top_entities: dict[str, list[dict]] = {etype: [] for etype in ENTITY_TYPES}
    if paper_ids:
        ent_rows = session.execute(
            select(
                PaperEntity.entity_type,
                PaperEntity.normalized_name,
                func.count(PaperEntity.paper_id.distinct()),
            )
            .where(PaperEntity.paper_id.in_(paper_ids))
            .group_by(PaperEntity.entity_type, PaperEntity.normalized_name)
        ).all()
        for etype, name, count in sorted(ent_rows, key=lambda r: (-r[2], r[1])):
            bucket = top_entities.setdefault(etype, [])
            if len(bucket) < _TOP_ENTITIES_PER_TYPE:
                bucket.append({"name": name, "paper_count": count})

    shared: Counter[str] = Counter()
    if paper_ids:
        for other_lab_id in session.execute(
            select(PaperLabLink.lab_id).where(
                PaperLabLink.paper_id.in_(paper_ids),
                PaperLabLink.lab_id != lab_id,
            )
        ).scalars():
            shared[other_lab_id] += 1
    lab_names = dict(session.execute(select(SdlLab.id, SdlLab.name)).all())
    collaborations = [
        {"lab_id": other_id, "name": lab_names.get(other_id, other_id), "shared_papers": count}
        for other_id, count in sorted(shared.items(), key=lambda kv: (-kv[1], kv[0]))
    ]

    lab_entities: dict[str, set[tuple[str, str]]] = defaultdict(set)
    for link_lab_id, etype, name in session.execute(
        select(
            PaperLabLink.lab_id, PaperEntity.entity_type, PaperEntity.normalized_name
        ).join(PaperEntity, PaperEntity.paper_id == PaperLabLink.paper_id)
    ):
        lab_entities[link_lab_id].add((etype, name))
    other_entities: set[tuple[str, str]] = set()
    for other_id, entities in lab_entities.items():
        if other_id != lab_id:
            other_entities |= entities
    entities_unique = len(lab_entities.get(lab_id, set()) - other_entities)

    return {
        "id": lab.id,
        "name": lab.name,
        "institution": lab.institution,
        "pi_names": lab.pi_names or [],
        "domain_focus": lab.domain_focus,
        "platform_stack": lab.platform_stack,
        "automation_level": lab.automation_level,
        "paper_count": len(paper_ids),
        "first_year": min(years) if years else None,
        "last_year": max(years) if years else None,
        "sdl_tag_histogram": [
            {"tag": tag, "count": count} for tag, count in tag_counts.most_common()
        ],
        "top_entities": top_entities,
        "collaborations": collaborations,
        "entities_unique_to_lab": entities_unique,
    }


def lab_classification_profile(session: Session, lab_id: str) -> list[dict]:
    """Classification-label histogram over a lab's linked papers, sorted by
    count descending. Empty when none of the lab's papers are classified."""
    rows = session.execute(
        select(PaperClassification.label, func.count())
        .join(PaperLabLink, PaperLabLink.paper_id == PaperClassification.paper_id)
        .where(PaperLabLink.lab_id == lab_id)
        .group_by(PaperClassification.label)
    ).all()
    return [
        {"label": label, "count": count}
        for label, count in sorted(rows, key=lambda r: (-r[1], r[0]))
    ]


def kb_summary(session: Session) -> dict:
    """Headline totals for the knowledge-base landing page."""
    labs = session.scalar(select(func.count()).select_from(SdlLab)) or 0
    linked_papers = (
        session.scalar(select(func.count(PaperLabLink.paper_id.distinct()))) or 0
    )
    entities_by_type = dict(
        session.execute(
            select(
                PaperEntity.entity_type,
                func.count(PaperEntity.normalized_name.distinct()),
            ).group_by(PaperEntity.entity_type)
        ).all()
    )
    cross_lab_entities = len(
        session.execute(
            select(PaperEntity.entity_type, PaperEntity.normalized_name)
            .join(PaperLabLink, PaperLabLink.paper_id == PaperEntity.paper_id)
            .group_by(PaperEntity.entity_type, PaperEntity.normalized_name)
            .having(func.count(PaperLabLink.lab_id.distinct()) >= 2)
        ).all()
    )
    return {
        "labs": labs,
        "linked_papers": linked_papers,
        "entities_by_type": entities_by_type,
        "cross_lab_entities": cross_lab_entities,
    }
