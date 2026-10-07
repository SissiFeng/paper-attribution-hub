"""Provider abstract base classes + concrete implementations.

Each NodeProvider yields a list of GraphNode for entities of one type.
Each EdgeProvider yields GraphEdges between active nodes — it receives the
materialized node set and is responsible for not emitting dangling edges.
Each GroupProvider assigns a group key to every node.

All providers are stateless. They take a SQLAlchemy session + the active
MultiGraphFilter and return lists.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from collections import defaultdict
import hashlib
import re
from typing import Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.config import settings
from app.country_normalization import (
    canonical_country_entries,
    canonical_country_values,
)
from app.models import (
    AcCorePaper,
    Author,
    Institution,
    Paper,
    PaperAuthor,
    PaperEntity,
    PaperProposition,
    PaperReference,
    Topic,
)
from app.services.filter_spec import (
    apply_filter,
    split_semicolon_values,
)
from app.services.multi_graph.types import (
    GraphEdge,
    GraphNode,
    MultiGraphFilter,
)


# ---------------------------------------------------------------------------
# ABCs
# ---------------------------------------------------------------------------


class NodeProvider(ABC):
    type: str

    @abstractmethod
    def nodes(
        self, session: Session, filt: MultiGraphFilter
    ) -> Iterable[GraphNode]: ...


class EdgeProvider(ABC):
    type: str
    requires_node_types: tuple[str, ...] = ()  # both endpoint types must be active

    @abstractmethod
    def edges(
        self,
        session: Session,
        filt: MultiGraphFilter,
        active_node_ids: set[str],
    ) -> Iterable[GraphEdge]: ...


class GroupProvider(ABC):
    key: str

    @abstractmethod
    def assign(
        self,
        nodes: list[GraphNode],
        edges: list[GraphEdge],
    ) -> dict[str, str]:
        """Return node_id -> group_id mapping. Nodes without a group stay None."""


# ---------------------------------------------------------------------------
# Helpers used by multiple providers
# ---------------------------------------------------------------------------


def _norm_semi(value: str | None) -> str | None:
    """Normalize semicolon-concatenated fields without dropping values."""
    normalized = split_semicolon_values(value)
    return "; ".join(normalized) or None


def _norm_country(value: str | None) -> str | None:
    return "; ".join(canonical_country_values(value)) or None


def _filtered_papers(session: Session, filt: MultiGraphFilter) -> list[Paper]:
    if filt._papers_cache is not None:
        return filt._papers_cache  # type: ignore[return-value]
    result = list(
        session.execute(
            apply_filter(
                select(Paper).options(
                    selectinload(Paper.classification),
                    selectinload(Paper.authors)
                    .selectinload(PaperAuthor.author)
                    .selectinload(Author.institution),
                ),
                filt.paper_filter,
            )
        ).scalars()
    )
    filt._papers_cache = result
    return result


def _paper_id_set(session: Session, filt: MultiGraphFilter) -> set[str]:
    return {p.id for p in _filtered_papers(session, filt)}


AUTHOR_GRAPH_MAX_PER_PAPER = 5
AUTHOR_GRAPH_SELECTION_POLICY = (
    "first_four_plus_confirmed_corresponding_else_last_listed_max_five"
)


def _confirmed_corresponding_author_ids(paper: Paper) -> set[str]:
    evidence = (paper.raw_metadata or {}).get(
        "corresponding_author_evidence"
    )
    if not isinstance(evidence, dict):
        return set()
    authors = evidence.get("authors")
    if not isinstance(authors, list):
        return set()
    return {
        str(author.get("author_id"))
        for author in authors
        if isinstance(author, dict) and author.get("author_id")
    }


def _selected_paper_authors(
    paper: Paper,
) -> list[tuple[PaperAuthor, str, bool]]:
    """Return at most five evidence-backed authors for one graph paper.

    Zotero preserves creator order but does not identify a corresponding
    author. For long lists we retain the first four listed creators and the
    last listed creator. The last creator is deliberately labelled
    ``last_listed`` rather than ``corresponding``.
    """
    authors = sorted(
        paper.authors,
        key=lambda paper_author: (
            paper_author.author_order,
            paper_author.author_id,
        ),
    )
    total_authors = len(authors)
    confirmed_corresponding_ids = _confirmed_corresponding_author_ids(paper)
    corresponding_authors = [
        paper_author
        for paper_author in authors
        if paper_author.author_id in confirmed_corresponding_ids
    ]
    if total_authors > AUTHOR_GRAPH_MAX_PER_PAPER:
        prefix = authors[: AUTHOR_GRAPH_MAX_PER_PAPER - 1]
        last_confirmed_corresponding = (
            corresponding_authors[-1] if corresponding_authors else None
        )
        if (
            last_confirmed_corresponding is not None
            and last_confirmed_corresponding not in prefix
        ):
            fifth = last_confirmed_corresponding
        elif last_confirmed_corresponding is not None:
            fifth = authors[AUTHOR_GRAPH_MAX_PER_PAPER - 1]
        else:
            fifth = authors[-1]
        selected = [*prefix, fifth]
    else:
        selected = authors

    positioned: list[tuple[PaperAuthor, str, bool]] = []
    for paper_author in selected:
        original_index = authors.index(paper_author)
        if total_authors == 1:
            position = "sole"
        elif original_index == 0:
            position = "first"
        elif original_index == total_authors - 1:
            position = "last_listed"
        else:
            position = "middle"
        positioned.append(
            (
                paper_author,
                position,
                paper_author.author_id in confirmed_corresponding_ids,
            )
        )
    return positioned


def _author_ids_from_papers(papers: list[Paper]) -> set[str]:
    return {
        paper_author.author_id
        for paper in papers
        for paper_author, _position, _is_corresponding in (
            _selected_paper_authors(paper)
        )
    }


def _institution_ids_from_papers(papers: list[Paper]) -> set[str]:
    out: set[str] = set()
    for p in papers:
        for pa in p.authors:
            inst = pa.author.institution
            if inst is not None:
                out.add(inst.id)
    return out


def _stage1_institution_node_id(name: str) -> str:
    identity = re.sub(r"\s+", " ", name.strip()).casefold()
    digest = hashlib.sha1(identity.encode("utf-8")).hexdigest()[:16]
    return f"institution:stage1:{digest}"


def _paper_entity_node_id(entity_type: str, normalized_name: str) -> str:
    identity = re.sub(r"\s+", " ", normalized_name.strip()).casefold()
    digest = hashlib.sha1(identity.encode("utf-8")).hexdigest()[:16]
    return f"{entity_type}:stage1:{digest}"


def _paper_entities_for_type(
    session: Session,
    papers: list[Paper],
    entity_type: str,
) -> list[PaperEntity]:
    paper_ids = {paper.id for paper in papers}
    if not paper_ids:
        return []
    return list(
        session.execute(
            select(PaperEntity).where(
                PaperEntity.paper_id.in_(paper_ids),
                PaperEntity.entity_type == entity_type,
            )
        ).scalars()
    )


def _stage1_institutions_by_paper(
    session: Session,
    papers: list[Paper],
) -> dict[str, dict[str, tuple[str, float, str]]]:
    """Return paper-level Tier 1 affiliation mentions.

    These entities come from verified Zotero Markdown front matter. They do
    not resolve which author belongs to which institution.
    """
    paper_ids = {paper.id for paper in papers}
    if not paper_ids:
        return {}
    rows = session.execute(
        select(
            PaperEntity.paper_id,
            PaperEntity.normalized_name,
            PaperEntity.confidence,
            PaperEntity.extractor,
        ).where(
            PaperEntity.paper_id.in_(paper_ids),
            PaperEntity.entity_type == "institution",
        )
    ).all()
    by_paper: dict[str, dict[str, tuple[str, float, str]]] = defaultdict(dict)
    for paper_id, normalized_name, confidence, extractor in rows:
        label = str(normalized_name or "").strip()
        if not label:
            continue
        node_id = _stage1_institution_node_id(label)
        previous = by_paper[paper_id].get(node_id)
        if previous is None:
            by_paper[paper_id][node_id] = (
                label,
                float(confidence or 0.0),
                str(extractor or ""),
            )
            continue
        previous_label, previous_confidence, previous_extractor = previous
        by_paper[paper_id][node_id] = (
            min(previous_label, label, key=str.casefold),
            max(previous_confidence, float(confidence or 0.0)),
            min(previous_extractor, str(extractor or "")),
        )
    return dict(by_paper)


_TOPIC_STOPWORDS = {
    "article",
    "study",
    "review",
    "method",
    "methods",
    "system",
    "systems",
}


def _keyword_topic_id(keyword: str) -> str:
    normalized = _norm_keyword(keyword)
    digest = hashlib.sha1(normalized.encode("utf-8")).hexdigest()[:10]
    return f"kw_{digest}"


def _norm_keyword(keyword: str) -> str:
    return re.sub(r"\s+", " ", keyword.strip().lower())


def _keyword_topics_for_paper(paper: Paper) -> list[dict]:
    candidates: list[str] = []
    for values in (
        paper.sdl_tags,
        paper.research_tags,
        paper.keywords,
        paper.indexed_keywords,
    ):
        for value in values or []:
            text = str(value).strip()
            norm = _norm_keyword(text)
            if len(norm) < 3 or norm in _TOPIC_STOPWORDS:
                continue
            candidates.append(text)

    seen: set[str] = set()
    topics: list[dict] = []
    for text in candidates:
        norm = _norm_keyword(text)
        if norm in seen:
            continue
        seen.add(norm)
        topics.append(
            {
                "topic_id": _keyword_topic_id(text),
                "name": text,
                "score": 0.45,
                "source": "paper_keyword",
            }
        )
        if len(topics) >= 4:
            break
    return topics


def _topic_matches_for_paper(paper: Paper) -> list[dict]:
    if paper.classification is not None and paper.classification.matched_topics:
        by_topic: dict[str, dict] = {}
        for match in paper.classification.matched_topics:
            topic_id = match.get("topic_id")
            score = float(match.get("score") or 0)
            if not topic_id or score < 0.3:
                continue
            incumbent = by_topic.get(topic_id)
            if incumbent is None or score > float(incumbent.get("score") or 0):
                by_topic[topic_id] = match
        return list(by_topic.values())
    return _keyword_topics_for_paper(paper)


# ---------------------------------------------------------------------------
# Node providers
# ---------------------------------------------------------------------------


class AuthorNodes(NodeProvider):
    type = "author"

    def nodes(self, session, filt):
        papers = _filtered_papers(session, filt)
        ids = _author_ids_from_papers(papers)
        author_paper_count: dict[str, int] = defaultdict(int)
        first_author_paper_count: dict[str, int] = defaultdict(int)
        last_listed_author_paper_count: dict[str, int] = defaultdict(int)
        sole_author_paper_count: dict[str, int] = defaultdict(int)
        corresponding_author_paper_count: dict[str, int] = defaultdict(int)
        for paper in papers:
            for (
                paper_author,
                position,
                is_corresponding,
            ) in _selected_paper_authors(paper):
                author_id = paper_author.author_id
                author_paper_count[author_id] += 1
                if position == "first":
                    first_author_paper_count[author_id] += 1
                elif position == "last_listed":
                    last_listed_author_paper_count[author_id] += 1
                elif position == "sole":
                    sole_author_paper_count[author_id] += 1
                if is_corresponding:
                    corresponding_author_paper_count[author_id] += 1
        for a in session.execute(select(Author).where(Author.id.in_(ids))).scalars():
            yield GraphNode(
                id=f"author:{a.id}",
                type=self.type,
                label=a.canonical_name,
                metadata={
                    "is_ac_member": bool(a.is_ac_member),
                    "orcid": a.orcid,
                    "institution": a.institution.canonical_name if a.institution else None,
                    "institution_id": a.institution_id,
                    "paper_count": author_paper_count[a.id],
                    "first_author_paper_count": first_author_paper_count[a.id],
                    "last_listed_author_paper_count": (
                        last_listed_author_paper_count[a.id]
                    ),
                    "sole_author_paper_count": sole_author_paper_count[a.id],
                    "corresponding_author_paper_count": (
                        corresponding_author_paper_count[a.id]
                    ),
                    "authorship_selection_policy": (
                        AUTHOR_GRAPH_SELECTION_POLICY
                    ),
                    "corresponding_author_evidence_available": bool(
                        corresponding_author_paper_count[a.id]
                    ),
                },
            )


class InstitutionNodes(NodeProvider):
    type = "institution"

    def nodes(self, session, filt):
        papers = _filtered_papers(session, filt)
        if settings.sdl_stage1_only:
            by_paper = _stage1_institutions_by_paper(session, papers)
            paper_ids_by_node: dict[str, set[str]] = defaultdict(set)
            labels: dict[str, str] = {}
            confidence_by_node: dict[str, list[float]] = defaultdict(list)
            extractors_by_node: dict[str, set[str]] = defaultdict(set)
            for paper_id, institutions in by_paper.items():
                for node_id, (label, confidence, extractor) in institutions.items():
                    paper_ids_by_node[node_id].add(paper_id)
                    labels[node_id] = label
                    confidence_by_node[node_id].append(confidence)
                    extractors_by_node[node_id].add(extractor)
            for node_id in sorted(labels):
                confidences = confidence_by_node[node_id]
                extractors = extractors_by_node[node_id]
                ror_resolved = bool(extractors) and all(
                    extractor.startswith("ror_affiliation_v2:")
                    for extractor in extractors
                )
                yield GraphNode(
                    id=node_id,
                    type=self.type,
                    label=labels[node_id],
                    metadata={
                        "is_partner": False,
                        "country": None,
                        "city": None,
                        "paper_count": len(paper_ids_by_node[node_id]),
                        "mean_extraction_confidence": round(
                            sum(confidences) / len(confidences),
                            4,
                        ),
                        "source": (
                            "zotero_tier1_pdf_affiliation_ror_resolved"
                            if ror_resolved
                            else "zotero_tier1_markdown_frontmatter_candidate"
                        ),
                        "resolution_status": (
                            "ror_resolved" if ror_resolved else "candidate"
                        ),
                        "extractors": sorted(extractors),
                        "relationship_scope": (
                            "paper_level_affiliation_mention"
                        ),
                        "author_affiliation_resolved": False,
                    },
                )
            return
        ids = _institution_ids_from_papers(papers)
        paper_count: dict[str, int] = defaultdict(int)
        for p in papers:
            seen: set[str] = set()
            for pa in p.authors:
                inst = pa.author.institution
                if inst is not None and inst.id not in seen:
                    seen.add(inst.id)
                    paper_count[inst.id] += 1
        for inst in session.execute(select(Institution).where(Institution.id.in_(ids))).scalars():
            yield GraphNode(
                id=f"institution:{inst.id}",
                type=self.type,
                label=inst.canonical_name,
                metadata={
                    "is_partner": bool(inst.is_partner),
                    "country": _norm_country(inst.country),
                    "city": _norm_semi(inst.city),
                    "paper_count": paper_count[inst.id],
                },
            )


class CountryNodes(NodeProvider):
    type = "country"

    def nodes(self, session, filt):
        papers = _filtered_papers(session, filt)
        paper_count: dict[str, int] = defaultdict(int)
        institution_ids: dict[str, set[str]] = defaultdict(set)
        partner_countries: set[str] = set()
        country_display: dict[str, str] = {}
        for paper in papers:
            seen: set[str] = set()
            for paper_author in paper.authors:
                institution = paper_author.author.institution
                countries = canonical_country_entries(
                    institution.country if institution is not None else None
                )
                if not countries:
                    continue
                if institution is not None:
                    for country in countries:
                        country_display[country.identity] = country.display
                        institution_ids[country.identity].add(institution.id)
                        if institution.is_partner:
                            partner_countries.add(country.identity)
                seen.update(country.identity for country in countries)
            for country in seen:
                paper_count[country] += 1
        for identity in sorted(paper_count):
            country = country_display[identity]
            yield GraphNode(
                id=f"country:{country}",
                type=self.type,
                label=country,
                metadata={
                    "paper_count": paper_count[identity],
                    "institution_count": len(institution_ids[identity]),
                    "has_partner_institution": identity in partner_countries,
                },
            )


class PaperNodes(NodeProvider):
    type = "paper"

    def nodes(self, session, filt):
        for p in _filtered_papers(session, filt):
            cls = p.classification
            yield GraphNode(
                id=f"paper:{p.id}",
                type=self.type,
                label=p.title,
                metadata={
                    "year": p.year,
                    "venue": p.venue,
                    "doi": p.doi,
                    "label_class": cls.label if cls else None,
                    "confidence": cls.confidence if cls else None,
                    "provenance": getattr(p, "provenance", "csv"),
                },
            )


class TopicNodes(NodeProvider):
    type = "topic"

    def nodes(self, session, filt):
        # Only emit topics that actually attach to a filtered paper.
        papers = _filtered_papers(session, filt)
        topic_ids: dict[str, str] = {}  # topic_id -> display name
        topic_paper_count: dict[str, int] = defaultdict(int)
        for p in papers:
            for tm in _topic_matches_for_paper(p):
                tid = tm.get("topic_id")
                topic_ids[tid] = tm.get("name") or tid
                topic_paper_count[tid] += 1
        for tid, name in topic_ids.items():
            topic_row = session.get(Topic, tid)
            yield GraphNode(
                id=f"topic:{tid}",
                type=self.type,
                label=name,
                metadata={
                    "is_core": bool(topic_row.is_core) if topic_row else None,
                    "paper_count": topic_paper_count[tid],
                },
            )


class MethodNodes(NodeProvider):
    """One node per distinct `uses_method` proposition object_key (e.g. one
    node per method like 'Bayesian optimization'). Methods aggregate evidence
    across all papers that use them."""

    type = "method"

    def nodes(self, session, filt):
        if settings.sdl_stage1_only:
            yield from ExtractedEntityNodes(self.type).nodes(session, filt)
            return
        paper_ids = _paper_id_set(session, filt)
        if not paper_ids:
            return
        seen: dict[str, str] = {}
        method_papers: dict[str, set[str]] = defaultdict(set)
        for prop in session.execute(
            select(PaperProposition).where(
                PaperProposition.predicate == "uses_method",
                PaperProposition.paper_id.in_(paper_ids),
            )
        ).scalars():
            key = prop.object_key or prop.object_value
            if not key:
                continue
            seen[key] = prop.object_value
            method_papers[key].add(prop.paper_id)
        for key, label in seen.items():
            yield GraphNode(
                id=f"method:{key}",
                type=self.type,
                label=label,
                metadata={"paper_count": len(method_papers[key])},
            )


class ExtractedEntityNodes(NodeProvider):
    """Entities extracted from the verified Tier 1 Markdown corpus."""

    def __init__(self, entity_type: str):
        self.type = entity_type

    def nodes(self, session, filt):
        rows = _paper_entities_for_type(
            session,
            _filtered_papers(session, filt),
            self.type,
        )
        labels: dict[str, str] = {}
        paper_ids: dict[str, set[str]] = defaultdict(set)
        confidences: dict[str, list[float]] = defaultdict(list)
        stages: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
        extractors: dict[str, set[str]] = defaultdict(set)
        for entity in rows:
            label = str(entity.normalized_name or entity.name or "").strip()
            if not label:
                continue
            node_id = _paper_entity_node_id(self.type, label)
            labels[node_id] = min(labels.get(node_id, label), label, key=str.casefold)
            paper_ids[node_id].add(entity.paper_id)
            confidences[node_id].append(float(entity.confidence or 0.0))
            if entity.stage:
                stages[node_id][entity.stage] += 1
            if entity.extractor:
                extractors[node_id].add(entity.extractor)
        for node_id in sorted(labels):
            entity_confidences = confidences[node_id]
            yield GraphNode(
                id=node_id,
                type=self.type,
                label=labels[node_id],
                metadata={
                    "paper_count": len(paper_ids[node_id]),
                    "mean_extraction_confidence": round(
                        sum(entity_confidences) / len(entity_confidences),
                        4,
                    ),
                    "stage_counts": dict(sorted(stages[node_id].items())),
                    "extractors": sorted(extractors[node_id]),
                    "source": "verified_zotero_tier1_markdown_fulltext",
                    "relationship_scope": "paper_level_fulltext_entity_mention",
                },
            )


class FunderNodes(NodeProvider):
    """One node per funder mentioned in any `funded_by` proposition."""

    type = "funder"

    def nodes(self, session, filt):
        paper_ids = _paper_id_set(session, filt)
        if not paper_ids:
            return
        seen: dict[str, str] = {}
        funded_papers: dict[str, set[str]] = defaultdict(set)
        for prop in session.execute(
            select(PaperProposition).where(
                PaperProposition.predicate == "funded_by",
                PaperProposition.paper_id.in_(paper_ids),
            )
        ).scalars():
            key = prop.object_key or prop.object_value
            if not key:
                continue
            seen[key] = prop.object_value
            funded_papers[key].add(prop.paper_id)
        for key, label in seen.items():
            yield GraphNode(
                id=f"funder:{key}",
                type=self.type,
                label=label,
                metadata={"paper_count": len(funded_papers[key])},
            )


class AcCoreNodes(NodeProvider):
    type = "ac_core"

    def nodes(self, session, filt):
        paper_ids = _paper_id_set(session, filt)
        support: dict[str, set[str]] = defaultdict(set)
        if paper_ids:
            for citing_paper_id, cited_ac_core_id in session.execute(
                select(
                    PaperReference.citing_paper_id,
                    PaperReference.cited_ac_core_id,
                ).where(
                    PaperReference.citing_paper_id.in_(paper_ids),
                    PaperReference.cited_ac_core_id.is_not(None),
                )
            ):
                support[cited_ac_core_id].add(citing_paper_id)
        for c in session.execute(select(AcCorePaper)).scalars():
            if not support[c.id]:
                continue
            yield GraphNode(
                id=f"ac_core:{c.id}",
                type=self.type,
                label=c.title,
                metadata={
                    "year": c.year,
                    "doi": c.doi,
                    "why_core": c.why_core,
                    "paper_count": len(support[c.id]),
                },
            )


NODE_PROVIDERS: dict[str, NodeProvider] = {
    p.type: p
    for p in (
        AuthorNodes(),
        InstitutionNodes(),
        CountryNodes(),
        PaperNodes(),
        TopicNodes(),
        MethodNodes(),
        ExtractedEntityNodes("material"),
        ExtractedEntityNodes("instrument"),
        ExtractedEntityNodes("software"),
        FunderNodes(),
        AcCoreNodes(),
    )
}


def available_node_types() -> list[str]:
    return list(NODE_PROVIDERS.keys())


# ---------------------------------------------------------------------------
# Edge providers
# ---------------------------------------------------------------------------


class AuthoredEdges(EdgeProvider):
    type = "authored"
    requires_node_types = ("author", "paper")

    def edges(self, session, filt, active_node_ids):
        papers = _filtered_papers(session, filt)
        for p in papers:
            paper_node = f"paper:{p.id}"
            if paper_node not in active_node_ids:
                continue
            total_authors = len(p.authors)
            corresponding_evidence_available = bool(
                _confirmed_corresponding_author_ids(p)
            )
            for (
                pa,
                position,
                is_corresponding,
            ) in _selected_paper_authors(p):
                author_node = f"author:{pa.author_id}"
                if author_node in active_node_ids:
                    yield GraphEdge(
                        source=author_node,
                        target=paper_node,
                        type=self.type,
                        weight=1.0,
                        metadata={
                            "paper_id": p.id,
                            "author_order": pa.author_order,
                            "author_position": position,
                            "total_listed_authors": total_authors,
                            "authorship_selection_policy": (
                                AUTHOR_GRAPH_SELECTION_POLICY
                            ),
                            "corresponding_author_confirmed": is_corresponding,
                            "corresponding_author_evidence_available": (
                                corresponding_evidence_available
                            ),
                            "corresponding_author_evidence_source": (
                                "pdf_frontmatter_corresponding_author_v1"
                                if corresponding_evidence_available
                                else None
                            ),
                        },
                    )


class AffiliatedWithEdges(EdgeProvider):
    type = "affiliated_with"
    requires_node_types = ("author", "institution")

    def edges(self, session, filt, active_node_ids):
        if settings.sdl_stage1_only:
            # Stage 1 entities are paper-level affiliation mentions. There is
            # no evidence to resolve an individual author to an institution.
            return
        seen: set[tuple[str, str]] = set()
        author_ids = {
            n.split(":", 1)[1] for n in active_node_ids if n.startswith("author:")
        }
        if not author_ids:
            return
        for a in session.execute(select(Author).where(Author.id.in_(author_ids))).scalars():
            if a.institution is None:
                continue
            source = f"author:{a.id}"
            target = f"institution:{a.institution.id}"
            if target not in active_node_ids:
                continue
            key = (source, target)
            if key in seen:
                continue
            seen.add(key)
            yield GraphEdge(source=source, target=target, type=self.type, weight=1.0)


class CoauthoredEdges(EdgeProvider):
    type = "coauthored"
    requires_node_types = ("author",)

    def edges(self, session, filt, active_node_ids):
        papers = _filtered_papers(session, filt)
        weights: dict[tuple[str, str], int] = defaultdict(int)
        shared: dict[tuple[str, str], list[str]] = defaultdict(list)
        for p in papers:
            ids = sorted(
                f"author:{pa.author_id}"
                for pa, _position, _is_corresponding in (
                    _selected_paper_authors(p)
                )
                if f"author:{pa.author_id}" in active_node_ids
            )
            for i, a in enumerate(ids):
                for b in ids[i + 1 :]:
                    key = (a, b)
                    weights[key] += 1
                    shared[key].append(p.id)
        for (a, b), w in weights.items():
            yield GraphEdge(
                source=a, target=b, type=self.type, weight=float(w),
                metadata={"papers": shared[(a, b)]},
            )


class InstitutionCollabEdges(EdgeProvider):
    type = "institution_collaboration"
    requires_node_types = ("institution",)

    def edges(self, session, filt, active_node_ids):
        papers = _filtered_papers(session, filt)
        if settings.sdl_stage1_only:
            by_paper = _stage1_institutions_by_paper(session, papers)
            weights: dict[tuple[str, str], int] = defaultdict(int)
            shared: dict[tuple[str, str], list[str]] = defaultdict(list)
            for paper in papers:
                inst_ids = sorted(
                    node_id
                    for node_id in by_paper.get(paper.id, {})
                    if node_id in active_node_ids
                )
                for index, source in enumerate(inst_ids):
                    for target in inst_ids[index + 1 :]:
                        key = (source, target)
                        weights[key] += 1
                        shared[key].append(paper.id)
            for (source, target), weight in weights.items():
                yield GraphEdge(
                    source=source,
                    target=target,
                    type=self.type,
                    weight=float(weight),
                    metadata={
                        "papers": shared[(source, target)],
                        "relationship_scope": (
                            "paper_level_affiliation_cooccurrence"
                        ),
                        "author_affiliation_resolved": False,
                    },
                )
            return
        weights: dict[tuple[str, str], int] = defaultdict(int)
        for p in papers:
            inst_ids = sorted({
                f"institution:{pa.author.institution.id}"
                for pa in p.authors
                if pa.author.institution is not None
                and f"institution:{pa.author.institution.id}" in active_node_ids
            })
            for i, a in enumerate(inst_ids):
                for b in inst_ids[i + 1 :]:
                    weights[(a, b)] += 1
        for (a, b), w in weights.items():
            yield GraphEdge(source=a, target=b, type=self.type, weight=float(w))


class PublishedByEdges(EdgeProvider):
    """Direct paper-to-institution projection."""

    type = "published_by"
    requires_node_types = ("paper", "institution")

    def edges(self, session, filt, active_node_ids):
        papers = _filtered_papers(session, filt)
        if settings.sdl_stage1_only:
            by_paper = _stage1_institutions_by_paper(session, papers)
            for paper in papers:
                paper_node = f"paper:{paper.id}"
                if paper_node not in active_node_ids:
                    continue
                for institution_node, (
                    _label,
                    confidence,
                    extractor,
                ) in sorted(
                    by_paper.get(paper.id, {}).items()
                ):
                    if institution_node not in active_node_ids:
                        continue
                    yield GraphEdge(
                        source=paper_node,
                        target=institution_node,
                        type=self.type,
                        weight=1.0,
                        metadata={
                            "paper_id": paper.id,
                            "extraction_confidence": confidence,
                            "source": (
                                "zotero_tier1_pdf_affiliation_ror_resolved"
                                if extractor.startswith(
                                    "ror_affiliation_v2:"
                                )
                                else (
                                    "zotero_tier1_markdown_"
                                    "frontmatter_candidate"
                                )
                            ),
                            "resolution_status": (
                                "ror_resolved"
                                if extractor.startswith(
                                    "ror_affiliation_v2:"
                                )
                                else "candidate"
                            ),
                            "relationship_scope": (
                                "paper_level_affiliation_mention"
                            ),
                            "author_affiliation_resolved": False,
                        },
                    )
            return
        for paper in papers:
            paper_node = f"paper:{paper.id}"
            if paper_node not in active_node_ids:
                continue
            seen: set[str] = set()
            for paper_author in paper.authors:
                institution = paper_author.author.institution
                if institution is None:
                    continue
                institution_node = f"institution:{institution.id}"
                if institution_node in active_node_ids and institution_node not in seen:
                    seen.add(institution_node)
                    yield GraphEdge(
                        source=paper_node,
                        target=institution_node,
                        type=self.type,
                        weight=1.0,
                        metadata={"paper_id": paper.id},
                    )


class CountryCollaborationEdges(EdgeProvider):
    """Country edge weight is the count of distinct jointly authored papers."""

    type = "country_collaboration"
    requires_node_types = ("country",)

    def edges(self, session, filt, active_node_ids):
        weights: dict[tuple[str, str], int] = defaultdict(int)
        shared: dict[tuple[str, str], list[str]] = defaultdict(list)
        for paper in _filtered_papers(session, filt):
            countries = {
                country.identity: country.display
                for paper_author in paper.authors
                if paper_author.author.institution is not None
                for country in canonical_country_entries(
                    paper_author.author.institution.country
                )
            }
            country_nodes = [
                f"country:{countries[identity]}"
                for identity in sorted(countries)
                if f"country:{countries[identity]}" in active_node_ids
            ]
            for index, source in enumerate(country_nodes):
                for target in country_nodes[index + 1 :]:
                    key = (source, target)
                    weights[key] += 1
                    shared[key].append(paper.id)
        for (source, target), weight in weights.items():
            yield GraphEdge(
                source=source,
                target=target,
                type=self.type,
                weight=float(weight),
                metadata={"papers": shared[(source, target)]},
            )


class CitesEdges(EdgeProvider):
    type = "cites"
    requires_node_types = ("paper",)

    def edges(self, session, filt, active_node_ids):
        for ref in session.execute(
            select(PaperReference).where(PaperReference.cited_paper_id.is_not(None))
        ).scalars():
            src = f"paper:{ref.citing_paper_id}"
            dst = f"paper:{ref.cited_paper_id}"
            if src in active_node_ids and dst in active_node_ids:
                yield GraphEdge(source=src, target=dst, type=self.type, weight=1.0)


class CitesAcCoreEdges(EdgeProvider):
    type = "cites_ac_core"
    requires_node_types = ("paper", "ac_core")

    def edges(self, session, filt, active_node_ids):
        seen: set[tuple[str, str]] = set()
        for ref in session.execute(
            select(PaperReference).where(PaperReference.cited_ac_core_id.is_not(None))
        ).scalars():
            src = f"paper:{ref.citing_paper_id}"
            dst = f"ac_core:{ref.cited_ac_core_id}"
            pair = (src, dst)
            if (
                src in active_node_ids
                and dst in active_node_ids
                and pair not in seen
            ):
                seen.add(pair)
                yield GraphEdge(source=src, target=dst, type=self.type, weight=1.0)


class BelongsToTopicEdges(EdgeProvider):
    type = "belongs_to_topic"
    requires_node_types = ("paper", "topic")

    def edges(self, session, filt, active_node_ids):
        papers = _filtered_papers(session, filt)
        for p in papers:
            paper_node = f"paper:{p.id}"
            if paper_node not in active_node_ids:
                continue
            for tm in _topic_matches_for_paper(p):
                tid = tm.get("topic_id")
                topic_node = f"topic:{tid}"
                if topic_node not in active_node_ids:
                    continue
                yield GraphEdge(
                    source=paper_node,
                    target=topic_node,
                    type=self.type,
                    weight=float(tm.get("score") or 0.0),
                )


class UsesMethodEdges(EdgeProvider):
    type = "uses_method"
    requires_node_types = ("paper", "method")

    def edges(self, session, filt, active_node_ids):
        if settings.sdl_stage1_only:
            yield from PaperEntityMentionEdges(
                "uses_method",
                "method",
                "paper_level_method_usage_evidence",
            ).edges(session, filt, active_node_ids)
            return
        best: dict[tuple[str, str], float] = {}
        for prop in session.execute(
            select(PaperProposition).where(PaperProposition.predicate == "uses_method")
        ).scalars():
            src = f"paper:{prop.paper_id}"
            dst = f"method:{prop.object_key or prop.object_value}"
            if src in active_node_ids and dst in active_node_ids:
                best[(src, dst)] = max(
                    best.get((src, dst), 0.0),
                    float(prop.confidence),
                )
        for (source, target), weight in best.items():
            yield GraphEdge(
                source=source,
                target=target,
                type=self.type,
                weight=weight,
            )


class PaperEntityMentionEdges(EdgeProvider):
    """Paper-to-entity evidence links extracted from Tier 1 Markdown."""

    def __init__(
        self,
        edge_type: str,
        entity_type: str,
        relationship_scope: str = "paper_level_fulltext_entity_mention",
    ):
        self.type = edge_type
        self.entity_type = entity_type
        self.requires_node_types = ("paper", entity_type)
        self.relationship_scope = relationship_scope

    def edges(self, session, filt, active_node_ids):
        rows = _paper_entities_for_type(
            session,
            _filtered_papers(session, filt),
            self.entity_type,
        )
        for entity in rows:
            label = str(entity.normalized_name or entity.name or "").strip()
            if not label:
                continue
            source = f"paper:{entity.paper_id}"
            target = _paper_entity_node_id(self.entity_type, label)
            if source not in active_node_ids or target not in active_node_ids:
                continue
            yield GraphEdge(
                source=source,
                target=target,
                type=self.type,
                weight=float(entity.confidence or 0.0),
                metadata={
                    "paper_id": entity.paper_id,
                    "entity_type": self.entity_type,
                    "normalized_name": label,
                    "extraction_confidence": float(entity.confidence or 0.0),
                    "evidence_chunk_id": entity.evidence_chunk_id,
                    "section": entity.section,
                    "extractor": entity.extractor,
                    "stage": entity.stage,
                    "usage_snippet": entity.usage_snippet,
                    "source": "verified_zotero_tier1_markdown_fulltext",
                    "relationship_scope": self.relationship_scope,
                },
            )


class FundedByEdges(EdgeProvider):
    type = "funded_by"
    requires_node_types = ("paper", "funder")

    def edges(self, session, filt, active_node_ids):
        best: dict[tuple[str, str], float] = {}
        for prop in session.execute(
            select(PaperProposition).where(PaperProposition.predicate == "funded_by")
        ).scalars():
            src = f"paper:{prop.paper_id}"
            dst = f"funder:{prop.object_key or prop.object_value}"
            if src in active_node_ids and dst in active_node_ids:
                best[(src, dst)] = max(
                    best.get((src, dst), 0.0),
                    float(prop.confidence),
                )
        for (source, target), weight in best.items():
            yield GraphEdge(
                source=source,
                target=target,
                type=self.type,
                weight=weight,
            )


class TopicCooccurrenceEdges(EdgeProvider):
    """Topics that appear together on the same paper. Weight = number of
    papers they co-occur on."""

    type = "topic_cooccurrence"
    requires_node_types = ("topic",)

    def edges(self, session, filt, active_node_ids):
        papers = _filtered_papers(session, filt)
        weights: dict[tuple[str, str], int] = defaultdict(int)
        for p in papers:
            if p.classification is None:
                continue
            topic_ids = sorted({
                f"topic:{tm.get('topic_id')}"
                for tm in p.classification.matched_topics or []
                if tm.get("topic_id") and (tm.get("score") or 0) >= 0.3
            })
            topic_ids = [t for t in topic_ids if t in active_node_ids]
            for i, a in enumerate(topic_ids):
                for b in topic_ids[i + 1 :]:
                    weights[(a, b)] += 1
        for (a, b), w in weights.items():
            yield GraphEdge(source=a, target=b, type=self.type, weight=float(w))


class SimilarityEdges(EdgeProvider):
    """Paper-to-paper similarity computed on demand from chunk embeddings."""

    type = "similarity"
    requires_node_types = ("paper",)

    def edges(self, session, filt, active_node_ids):
        import numpy as np

        from app.models import PaperChunk

        paper_node_ids = [n for n in active_node_ids if n.startswith("paper:")]
        if len(paper_node_ids) < 2:
            return
        paper_ids = [n.split(":", 1)[1] for n in paper_node_ids]

        # Aggregate chunk embeddings into a paper-level mean (L2-renormalized).
        chunks_by_paper: dict[str, list[list[float]]] = defaultdict(list)
        for c in session.execute(
            select(PaperChunk).where(PaperChunk.paper_id.in_(paper_ids))
        ).scalars():
            if c.embedding:
                chunks_by_paper[c.paper_id].append(c.embedding)
        if not chunks_by_paper:
            return

        ordered_ids: list[str] = []
        vecs: list[np.ndarray] = []
        dim = None
        for pid in paper_ids:
            chunks = chunks_by_paper.get(pid)
            if not chunks:
                continue
            arr = np.asarray(chunks, dtype=np.float32)
            if dim is None:
                dim = arr.shape[1]
            elif arr.shape[1] != dim:
                # Skip papers whose embedding dimension differs (model swap mid-corpus).
                continue
            mean = arr.mean(axis=0)
            norm = float(np.linalg.norm(mean))
            if norm == 0.0:
                continue
            mean /= norm
            ordered_ids.append(pid)
            vecs.append(mean)
        if len(vecs) < 2:
            return

        matrix = np.vstack(vecs)
        sim = matrix @ matrix.T

        # For each paper, keep top-K most similar others above threshold.
        emitted: set[tuple[str, str]] = set()
        for i, pid in enumerate(ordered_ids):
            scores = sim[i].copy()
            scores[i] = -1.0
            top = np.argsort(-scores)[: filt.similarity_top_k]
            for j in top:
                score = float(scores[j])
                if score < filt.similarity_min:
                    continue
                other = ordered_ids[int(j)]
                a, b = sorted([pid, other])
                key = (a, b)
                if key in emitted:
                    continue
                emitted.add(key)
                yield GraphEdge(
                    source=f"paper:{a}",
                    target=f"paper:{b}",
                    type=self.type,
                    weight=round(score, 4),
                )


EDGE_PROVIDERS: dict[str, EdgeProvider] = {
    p.type: p
    for p in (
        AuthoredEdges(),
        AffiliatedWithEdges(),
        CoauthoredEdges(),
        InstitutionCollabEdges(),
        PublishedByEdges(),
        CountryCollaborationEdges(),
        CitesEdges(),
        CitesAcCoreEdges(),
        BelongsToTopicEdges(),
        UsesMethodEdges(),
        PaperEntityMentionEdges("mentions_material", "material"),
        PaperEntityMentionEdges("mentions_instrument", "instrument"),
        PaperEntityMentionEdges("mentions_software", "software"),
        FundedByEdges(),
        TopicCooccurrenceEdges(),
        SimilarityEdges(),
    )
}


def available_edge_types() -> list[str]:
    return list(EDGE_PROVIDERS.keys())


# ---------------------------------------------------------------------------
# Group providers
# ---------------------------------------------------------------------------


class ByInstitutionGroup(GroupProvider):
    key = "by_institution"

    def assign(self, nodes, edges):
        out: dict[str, str] = {}
        for n in nodes:
            if n.type == "institution":
                out[n.id] = n.id
            elif n.type == "author":
                inst_id = n.metadata.get("institution_id")
                if inst_id:
                    out[n.id] = f"institution:{inst_id}"
        # Papers inherit one deterministic institution group for coloring.
        published_by: dict[str, list[str]] = defaultdict(list)
        for edge in edges:
            if edge.type == "published_by":
                published_by[edge.source].append(edge.target)
        for paper_id, institution_ids in published_by.items():
            out[paper_id] = sorted(institution_ids)[0]

        # Legacy papers without published_by edges inherit from an author.
        author_to_inst = {n.id: out.get(n.id) for n in nodes if n.type == "author"}
        for e in edges:
            if e.type != "authored":
                continue
            inst = author_to_inst.get(e.source)
            if inst and e.target not in out:
                out[e.target] = inst
        return out


class ByTopicGroup(GroupProvider):
    key = "by_topic"

    def assign(self, nodes, edges):
        out: dict[str, str] = {}
        for n in nodes:
            if n.type == "topic":
                out[n.id] = n.id
        # Papers inherit from highest-weight topic edge they participate in.
        best_for_paper: dict[str, tuple[float, str]] = {}
        for e in edges:
            if e.type != "belongs_to_topic":
                continue
            cur = best_for_paper.get(e.source)
            if cur is None or e.weight > cur[0]:
                best_for_paper[e.source] = (e.weight, e.target)
        for paper_id, (_, topic_id) in best_for_paper.items():
            out[paper_id] = topic_id
        return out


class ByCountryGroup(GroupProvider):
    key = "by_country"

    def assign(self, nodes, edges):
        out: dict[str, str] = {}
        country_for_inst: dict[str, str] = {}
        for n in nodes:
            if n.type == "country":
                out[n.id] = n.id
            if n.type == "institution":
                countries = canonical_country_values(
                    str(n.metadata.get("country") or "")
                )
                c = countries[0] if countries else "Unknown"
                country_for_inst[n.id] = c
                out[n.id] = f"country:{c}"
        for n in nodes:
            if n.type == "author":
                inst_id = n.metadata.get("institution_id")
                if inst_id:
                    c = country_for_inst.get(f"institution:{inst_id}")
                    if c:
                        out[n.id] = f"country:{c}"
        return out


class ByYearBucketGroup(GroupProvider):
    key = "by_year_bucket"

    def assign(self, nodes, edges):
        out: dict[str, str] = {}
        for n in nodes:
            year = n.metadata.get("year")
            if year is None:
                continue
            bucket = (year // 2) * 2
            out[n.id] = f"era:{bucket}-{bucket+1}"
        return out


class ByLabelGroup(GroupProvider):
    key = "by_classification_label"

    def assign(self, nodes, edges):
        out: dict[str, str] = {}
        for n in nodes:
            label = n.metadata.get("label_class")
            if label:
                out[n.id] = f"label:{label}"
        return out


class ByCommunityGroup(GroupProvider):
    """Louvain community detection on the active subgraph."""

    key = "by_community"

    def assign(self, nodes, edges):
        if not nodes or not edges:
            return {}
        import networkx as nx

        g = nx.Graph()
        for n in nodes:
            g.add_node(n.id)
        for e in edges:
            if e.source in g and e.target in g:
                # networkx 3.x: combine repeated edges via additive weight.
                if g.has_edge(e.source, e.target):
                    g[e.source][e.target]["weight"] += e.weight
                else:
                    g.add_edge(e.source, e.target, weight=e.weight)

        try:
            communities = nx.community.louvain_communities(g, seed=42)
        except Exception:
            return {}

        out: dict[str, str] = {}
        for i, community in enumerate(communities):
            for node_id in community:
                out[node_id] = f"community:{i}"
        return out


class ByEntityTypeGroup(GroupProvider):
    key = "by_entity_type"

    def assign(self, nodes, edges):
        return {node.id: f"entity-type:{node.type}" for node in nodes}


class NoGroup(GroupProvider):
    key = "none"

    def assign(self, nodes, edges):
        return {}


GROUP_PROVIDERS: dict[str, GroupProvider] = {
    p.key: p
    for p in (
        ByInstitutionGroup(),
        ByTopicGroup(),
        ByCountryGroup(),
        ByYearBucketGroup(),
        ByLabelGroup(),
        ByCommunityGroup(),
        ByEntityTypeGroup(),
        NoGroup(),
    )
}


def available_group_keys() -> list[str]:
    return list(GROUP_PROVIDERS.keys())
