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
    PaperEntityExtractionState,
    PaperEntityMention,
    PaperEntityRelation,
    PaperLabLink,
    SdlLab,
)
from app.services.entity_extractor import (
    CATALYST_EXTRACTOR_VERSION,
    extraction_config_fingerprint,
)
from app.services.ontology_service import (
    concept,
    concept_ancestors,
    concept_children,
    concept_id_for_name,
    load_ontology,
)
from app.services.sag_lite_service import entity_event_trail
from app.services.transfer_service import adoption_lags

ENTITY_TYPES = ("method", "material", "instrument", "software")

_EVIDENCE_LIMIT = 10
_EVIDENCE_CHARS = 300
_TOP_ENTITIES_PER_TYPE = 10


def _current_state_filters() -> tuple:
    return (
        PaperEntityExtractionState.ontology_version
        == load_ontology()["ontology_version"],
        PaperEntityExtractionState.extractor_version
        == CATALYST_EXTRACTOR_VERSION,
        PaperEntityExtractionState.config_fingerprint
        == extraction_config_fingerprint(),
        Paper.updated_at <= PaperEntityExtractionState.extracted_at,
    )


def _concept_ref(concept_id: str) -> dict:
    spec = concept(concept_id)
    return {
        "concept_id": concept_id,
        "name": spec["name"] if spec is not None else concept_id,
    }


def _descendant_ids(concept_id: str) -> list[str]:
    descendants: list[str] = []
    frontier = list(concept_children(concept_id))
    while frontier:
        child_id = frontier.pop(0)
        if child_id in descendants:
            continue
        descendants.append(child_id)
        frontier.extend(concept_children(child_id))
    return descendants


def _catalyst_concept_id(entity_type: str, name: str) -> str | None:
    if entity_type != "material":
        return None
    concept_id = concept_id_for_name("material", name)
    if concept_id is None:
        return None
    if concept_id == "material:catalyst" or (
        "material:catalyst" in concept_ancestors(concept_id)
    ):
        return concept_id
    return None


def _rollup_counts(session: Session, requested_ids: list[str]) -> dict[str, dict]:
    families = {
        concept_id: {concept_id, *_descendant_ids(concept_id)}
        for concept_id in requested_ids
    }
    names = {
        concept(member_id)["name"]
        for family in families.values()
        for member_id in family
        if concept(member_id) is not None
    }
    rows = session.execute(
        select(
            PaperEntity.normalized_name,
            PaperEntity.paper_id,
            PaperLabLink.lab_id,
            Paper.year,
        )
        .join(
            PaperEntityExtractionState,
            PaperEntityExtractionState.paper_id == PaperEntity.paper_id,
        )
        .join(Paper, Paper.id == PaperEntity.paper_id)
        .outerjoin(PaperLabLink, PaperLabLink.paper_id == PaperEntity.paper_id)
        .where(
            PaperEntity.entity_type == "material",
            PaperEntity.normalized_name.in_(names),
            *_current_state_filters(),
        )
    ).all()
    aggregates = {
        concept_id: {"papers": set(), "labs": set(), "years": []}
        for concept_id in requested_ids
    }
    memberships: dict[str, set[str]] = defaultdict(set)
    for concept_id, family in families.items():
        for member_id in family:
            memberships[member_id].add(concept_id)
    for name, paper_id, lab_id, year in rows:
        member_id = concept_id_for_name("material", name)
        if member_id is None:
            continue
        for concept_id in memberships.get(member_id, ()):
            aggregates[concept_id]["papers"].add(paper_id)
            if lab_id is not None:
                aggregates[concept_id]["labs"].add(lab_id)
            if year is not None:
                aggregates[concept_id]["years"].append(year)
    return {
        concept_id: {
            "paper_count": len(values["papers"]),
            "lab_count": len(values["labs"]),
            "first_year": min(values["years"]) if values["years"] else None,
            "last_year": max(values["years"]) if values["years"] else None,
        }
        for concept_id, values in aggregates.items()
    }


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
        .join(
            PaperEntityExtractionState,
            PaperEntityExtractionState.paper_id == PaperEntity.paper_id,
        )
        .join(Paper, Paper.id == PaperEntity.paper_id)
        .outerjoin(PaperLabLink, PaperLabLink.paper_id == PaperEntity.paper_id)
        .where(*_current_state_filters())
        .group_by(PaperEntity.entity_type, PaperEntity.normalized_name)
    )
    if entity_type is not None:
        stmt = stmt.where(PaperEntity.entity_type == entity_type)
    if q:
        stmt = stmt.where(PaperEntity.normalized_name.ilike(f"%{q}%"))

    entries: list[dict] = [
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

    root_name = concept("material:catalyst")["name"]
    material_entries = {
        entry["name"]: entry
        for entry in entries
        if entry["entity_type"] == "material"
    }
    has_catalyst_child = any(
        _catalyst_concept_id("material", name) not in {None, "material:catalyst"}
        for name in material_entries
    )
    root_matches_filter = (
        entity_type in {None, "material"}
        and (not q or q.lower() in root_name.lower())
    )
    if has_catalyst_child and root_name not in material_entries and root_matches_filter:
        entries.append(
            {
                "entity_type": "material",
                "name": root_name,
                "paper_count": 0,
                "lab_count": 0,
                "first_year": None,
                "last_year": None,
            }
        )

    entry_concept_ids = {
        entry["name"]: concept_id
        for entry in entries
        if (
            concept_id := _catalyst_concept_id(
                entry["entity_type"],
                entry["name"],
            )
        )
        is not None
    }
    rollups = _rollup_counts(session, list(entry_concept_ids.values()))
    for entry in entries:
        concept_id = entry_concept_ids.get(entry["name"])
        if concept_id is None:
            continue
        rollup = rollups[concept_id]
        entry.update(
            {
                "concept_id": concept_id,
                "parent_concept_ids": concept_ancestors(concept_id),
                "children": [
                    _concept_ref(child_id)
                    for child_id in concept_children(concept_id)
                ],
                "direct_paper_count": entry["paper_count"],
                "direct_lab_count": entry["lab_count"],
                "rolled_up_paper_count": rollup["paper_count"],
                "rolled_up_lab_count": rollup["lab_count"],
            }
        )
        if entry["paper_count"] == 0:
            entry["first_year"] = rollup["first_year"]
            entry["last_year"] = rollup["last_year"]
    entries.sort(
        key=lambda e: (
            -e.get("rolled_up_paper_count", e["paper_count"]),
            len(e.get("parent_concept_ids", [])),
            e["name"],
            e["entity_type"],
        )
    )
    return entries


def entity_page(
    session: Session, entity_type: str, normalized_name: str
) -> dict | None:
    """Full page for one normalized entity: labs, papers, timeline, evidence
    snippets and its adoption-lag entry. None if the entity is unknown."""
    ontology_version = load_ontology()["ontology_version"]
    concept_id = _catalyst_concept_id(entity_type, normalized_name)
    family_ids = (
        [concept_id, *_descendant_ids(concept_id)]
        if concept_id is not None
        else []
    )
    family_names = [
        concept(cid)["name"] for cid in family_ids if concept(cid) is not None
    ]
    selected_names = family_names or [normalized_name]
    all_rows = session.execute(
        select(PaperEntity, Paper)
        .join(
            PaperEntityExtractionState,
            PaperEntityExtractionState.paper_id == PaperEntity.paper_id,
        )
        .join(Paper, Paper.id == PaperEntity.paper_id)
        .where(
            PaperEntity.entity_type == entity_type,
            PaperEntity.normalized_name.in_(selected_names),
            *_current_state_filters(),
        )
        .order_by(Paper.year, Paper.id)
    ).all()
    if not all_rows:
        return None

    matched_by_paper: dict[str, set[str]] = defaultdict(set)
    rows_by_paper: dict[str, tuple[PaperEntity, Paper]] = {}
    for entity, paper in all_rows:
        matched_by_paper[paper.id].add(entity.normalized_name)
        current = rows_by_paper.get(paper.id)
        if current is None or (
            entity.normalized_name == normalized_name
            and current[0].normalized_name != normalized_name
        ):
            rows_by_paper[paper.id] = (entity, paper)
    rows = list(rows_by_paper.values())
    rows.sort(key=lambda row: (row[1].year or 9999, row[1].id))
    paper_ids = [paper.id for _, paper in rows]
    direct_paper_ids = {
        paper.id
        for entity, paper in all_rows
        if entity.normalized_name == normalized_name
    }
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
                "matched_entities": sorted(matched_by_paper[paper.id]),
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

    evidence: list[dict] = []
    evidence_paper_ids: set[str] = set()
    if family_ids:
        for (
            paper_id,
            title,
            evidence_text,
            mention_name,
        ) in session.execute(
            select(
                PaperEntityMention.paper_id,
                Paper.title,
                PaperEntityMention.evidence_text,
                PaperEntityMention.normalized_name,
            )
            .join(Paper, Paper.id == PaperEntityMention.paper_id)
            .join(
                PaperEntityExtractionState,
                PaperEntityExtractionState.paper_id
                == PaperEntityMention.paper_id,
            )
            .where(
                PaperEntityMention.concept_id.in_(family_ids),
                PaperEntityMention.ontology_version == ontology_version,
                *_current_state_filters(),
            )
            .order_by(PaperEntityMention.paper_id, PaperEntityMention.start_char)
            .limit(_EVIDENCE_LIMIT)
        ):
            evidence.append(
                {
                    "paper_id": paper_id,
                    "paper_title": title,
                    "text": evidence_text[:_EVIDENCE_CHARS],
                    "stage": None,
                    "usage_snippet": None,
                    "matched_entity": mention_name,
                    "knowledge_state": "observed_mention",
                }
            )
            evidence_paper_ids.add(paper_id)

    fallback_limit = _EVIDENCE_LIMIT - len(evidence)
    fallback_evidence = [
        {
            "paper_id": paper_id,
            "paper_title": title,
            "text": text[:_EVIDENCE_CHARS],
            "stage": stage,
            "usage_snippet": usage_snippet,
            "matched_entity": matched_name,
            "knowledge_state": "observed_mention",
        }
        for paper_id, title, text, stage, usage_snippet, matched_name
        in session.execute(
            select(
                PaperEntity.paper_id,
                Paper.title,
                PaperChunk.chunk_text,
                PaperEntity.stage,
                PaperEntity.usage_snippet,
                PaperEntity.normalized_name,
            )
            .join(
                PaperEntityExtractionState,
                PaperEntityExtractionState.paper_id == PaperEntity.paper_id,
            )
            .join(Paper, Paper.id == PaperEntity.paper_id)
            .join(PaperChunk, PaperChunk.id == PaperEntity.evidence_chunk_id)
            .where(
                PaperEntity.entity_type == entity_type,
                PaperEntity.normalized_name.in_(selected_names),
                PaperEntity.paper_id.not_in(evidence_paper_ids),
                *_current_state_filters(),
            )
            .limit(fallback_limit)
        )
    ]
    evidence.extend(fallback_evidence)

    adoption_granularity = (
        "parent" if concept_id == "material:catalyst" else "entity"
    )
    adoption = next(
        (
            entry
            for entry in adoption_lags(
                session,
                entity_type=entity_type,
                min_labs=1,
                granularity=adoption_granularity,
            )
            if entry["entity"] == normalized_name
        ),
        None,
    )

    reaction_papers: dict[str, set[str]] = defaultdict(set)
    reaction_states: dict[str, set[str]] = defaultdict(set)
    composition_papers: dict[str, set[str]] = defaultdict(set)
    composition_states: dict[str, set[str]] = defaultdict(set)
    if family_ids:
        relation_rows = session.execute(
            select(
                PaperEntityRelation.predicate,
                PaperEntityRelation.object_concept_id,
                PaperEntityRelation.object_value,
                PaperEntityMention.paper_id,
                PaperEntityRelation.status,
            )
            .join(
                PaperEntityMention,
                PaperEntityMention.id == PaperEntityRelation.subject_mention_id,
            )
            .join(
                PaperEntityExtractionState,
                PaperEntityExtractionState.paper_id
                == PaperEntityMention.paper_id,
            )
            .join(Paper, Paper.id == PaperEntityMention.paper_id)
            .where(
                PaperEntityMention.concept_id.in_(family_ids),
                PaperEntityMention.ontology_version == ontology_version,
                PaperEntityRelation.ontology_version == ontology_version,
                *_current_state_filters(),
            )
        )
        for predicate, object_concept_id, object_value, paper_id, status in relation_rows:
            if predicate == "catalyzes" and object_concept_id:
                reaction_papers[object_concept_id].add(paper_id)
                reaction_states[object_concept_id].add(status)
            elif predicate == "has_composition" and object_value:
                composition_papers[object_value].add(paper_id)
                composition_states[object_value].add(status)

    reactions = [
        {
            "name": _concept_ref(reaction_id)["name"],
            "concept_id": reaction_id,
            "paper_count": len(papers),
            "knowledge_state": (
                next(iter(reaction_states[reaction_id]))
                if len(reaction_states[reaction_id]) == 1
                else "mixed"
            ),
        }
        for reaction_id, papers in sorted(
            reaction_papers.items(), key=lambda item: (-len(item[1]), item[0])
        )
    ]
    compositions = [
        {
            "name": raw,
            "concept_id": None,
            "paper_count": len(papers),
            "knowledge_state": (
                next(iter(composition_states[raw]))
                if len(composition_states[raw]) == 1
                else "mixed"
            ),
        }
        for raw, papers in sorted(
            composition_papers.items(), key=lambda item: (-len(item[1]), item[0])
        )
    ]
    direct_lab_ids = {
        lab_id
        for paper_id in direct_paper_ids
        for lab_id in paper_labs.get(paper_id, [])
    }
    rollup_lab_ids = {
        lab_id for lab_ids in paper_labs.values() for lab_id in lab_ids
    }

    return {
        "entity": normalized_name,
        "entity_type": entity_type,
        "concept_id": concept_id,
        "ancestors": (
            [_concept_ref(parent_id) for parent_id in concept_ancestors(concept_id)]
            if concept_id is not None
            else []
        ),
        "children": (
            [_concept_ref(child_id) for child_id in concept_children(concept_id)]
            if concept_id is not None
            else []
        ),
        "direct_paper_count": len(direct_paper_ids),
        "direct_lab_count": len(direct_lab_ids),
        "rolled_up_paper_count": len(paper_ids),
        "rolled_up_lab_count": len(rollup_lab_ids),
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
        "reactions": reactions,
        "compositions": compositions,
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
            .join(
                PaperEntityExtractionState,
                PaperEntityExtractionState.paper_id == PaperEntity.paper_id,
            )
            .join(Paper, Paper.id == PaperEntity.paper_id)
            .where(
                PaperEntity.paper_id.in_(paper_ids),
                *_current_state_filters(),
            )
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
        )
        .join(PaperEntity, PaperEntity.paper_id == PaperLabLink.paper_id)
        .join(
            PaperEntityExtractionState,
            PaperEntityExtractionState.paper_id == PaperEntity.paper_id,
        )
        .join(Paper, Paper.id == PaperEntity.paper_id)
        .where(*_current_state_filters())
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
            )
            .join(
                PaperEntityExtractionState,
                PaperEntityExtractionState.paper_id == PaperEntity.paper_id,
            )
            .join(Paper, Paper.id == PaperEntity.paper_id)
            .where(*_current_state_filters())
            .group_by(PaperEntity.entity_type)
        ).all()
    )
    cross_lab_entities = len(
        session.execute(
            select(PaperEntity.entity_type, PaperEntity.normalized_name)
            .join(
                PaperEntityExtractionState,
                PaperEntityExtractionState.paper_id == PaperEntity.paper_id,
            )
            .join(Paper, Paper.id == PaperEntity.paper_id)
            .join(PaperLabLink, PaperLabLink.paper_id == PaperEntity.paper_id)
            .where(*_current_state_filters())
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
