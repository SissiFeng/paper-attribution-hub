"""Cross-SDL knowledge-transfer analytics.

Built on the foundation layer (sdl.py models): lab×lab citation flows via
PaperReference + PaperLabLink, entity adoption lags via PaperEntity joined on
normalized_name, and a headline summary.
"""
from __future__ import annotations

from collections import defaultdict
from statistics import median

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Paper, PaperEntity, PaperLabLink, PaperReference, SdlLab


def lab_flow_matrix(
    session: Session, year_from: int | None = None, year_to: int | None = None
) -> dict:
    """Lab×lab citation-flow matrix.

    Cell [i][j] counts references where the citing paper belongs to lab i and
    the cited paper to lab j. Self-flows (same lab on both sides) are excluded
    from the matrix and reported per lab in `intra_lab`. The optional year
    window filters on the citing paper's year.
    """
    labs = list(session.execute(select(SdlLab).order_by(SdlLab.id)).scalars())
    lab_index = {lab.id: i for i, lab in enumerate(labs)}

    paper_labs: dict[str, set[str]] = defaultdict(set)
    for paper_id, lab_id in session.execute(
        select(PaperLabLink.paper_id, PaperLabLink.lab_id)
    ):
        paper_labs[paper_id].add(lab_id)

    stmt = select(
        PaperReference.citing_paper_id, PaperReference.cited_paper_id
    ).where(PaperReference.cited_paper_id.is_not(None))
    if year_from is not None or year_to is not None:
        stmt = stmt.join(Paper, Paper.id == PaperReference.citing_paper_id)
        if year_from is not None:
            stmt = stmt.where(Paper.year >= year_from)
        if year_to is not None:
            stmt = stmt.where(Paper.year <= year_to)

    n = len(labs)
    matrix = [[0] * n for _ in range(n)]
    intra_lab = {lab.id: 0 for lab in labs}
    total_cross = 0
    for citing_id, cited_id in session.execute(stmt):
        for citing_lab in paper_labs.get(citing_id, ()):
            for cited_lab in paper_labs.get(cited_id, ()):
                if citing_lab == cited_lab:
                    intra_lab[citing_lab] += 1
                else:
                    matrix[lab_index[citing_lab]][lab_index[cited_lab]] += 1
                    total_cross += 1

    return {
        "labs": [{"id": lab.id, "name": lab.name} for lab in labs],
        "matrix": matrix,
        "intra_lab": intra_lab,
        "total_cross_flows": total_cross,
    }


def adoption_lags(
    session: Session, entity_type: str | None = None, min_labs: int = 2
) -> list[dict]:
    """Per-entity adoption lags across labs.

    For each normalized entity, the origin is the lab with the earliest
    mention year (ties: all earliest labs count as origins; the alphabetically
    first is reported as `origin_lab`, and tied origins do not appear as
    adoptions). Every later lab is an adoption with
    lag_years = its first year − origin year. Papers without a year are
    skipped. Only entities seen in >= min_labs labs are returned, sorted by
    number of adopting labs descending.
    """
    stmt = (
        select(
            PaperEntity.entity_type,
            PaperEntity.normalized_name,
            PaperLabLink.lab_id,
            Paper.year,
        )
        .join(PaperLabLink, PaperLabLink.paper_id == PaperEntity.paper_id)
        .join(Paper, Paper.id == PaperEntity.paper_id)
        .where(Paper.year.is_not(None))
    )
    if entity_type is not None:
        stmt = stmt.where(PaperEntity.entity_type == entity_type)

    # (entity_type, normalized_name) -> {lab_id: first mention year}
    first_years: dict[tuple[str, str], dict[str, int]] = defaultdict(dict)
    for etype, norm, lab_id, year in session.execute(stmt):
        key = (etype, norm)
        prev = first_years[key].get(lab_id)
        if prev is None or year < prev:
            first_years[key][lab_id] = year

    entries: list[dict] = []
    for (etype, norm), lab_years in first_years.items():
        if len(lab_years) < min_labs:
            continue
        origin_year = min(lab_years.values())
        origin_labs = sorted(
            lab_id for lab_id, year in lab_years.items() if year == origin_year
        )
        adoptions = [
            {"lab": lab, "first_year": year, "lag_years": year - origin_year}
            for lab, year in sorted(lab_years.items(), key=lambda kv: (kv[1], kv[0]))
            if year > origin_year
        ]
        entries.append(
            {
                "entity": norm,
                "entity_type": etype,
                "origin_lab": origin_labs[0],
                "origin_year": origin_year,
                "adoptions": adoptions,
            }
        )
    entries.sort(key=lambda e: (-len(e["adoptions"]), e["entity"], e["entity_type"]))
    return entries


def fastest_spreading(session: Session, limit: int = 5) -> list[dict]:
    """Cross-lab entities with the lowest average adoption lag, including the
    origin lab/year. Sorted by avg lag ascending, then adopter count desc."""
    return _fastest_entries(adoption_lags(session, min_labs=2), limit)


def _fastest_entries(lags: list[dict], limit: int) -> list[dict]:
    entries = sorted(
        (e for e in lags if e["adoptions"]),
        key=lambda e: (
            sum(a["lag_years"] for a in e["adoptions"]) / len(e["adoptions"]),
            -len(e["adoptions"]),
            e["entity"],
        ),
    )[:limit]
    return [
        {
            "entity": e["entity"],
            "entity_type": e["entity_type"],
            "origin_lab": e["origin_lab"],
            "origin_year": e["origin_year"],
            "adopter_count": len(e["adoptions"]),
            "avg_lag_years": round(
                sum(a["lag_years"] for a in e["adoptions"]) / len(e["adoptions"]),
                2,
            ),
        }
        for e in entries
    ]


def transfer_summary(session: Session) -> dict:
    """Headline numbers for the knowledge-transfer page."""
    labs = session.scalar(select(func.count()).select_from(SdlLab)) or 0
    linked_papers = (
        session.scalar(select(func.count(PaperLabLink.paper_id.distinct()))) or 0
    )
    entities_tracked = (
        session.scalar(
            select(func.count()).select_from(
                select(PaperEntity.entity_type, PaperEntity.normalized_name)
                .distinct()
                .subquery()
            )
        )
        or 0
    )

    lags = adoption_lags(session, min_labs=2)
    all_lags = [a["lag_years"] for e in lags for a in e["adoptions"]]
    return {
        "labs": labs,
        "linked_papers": linked_papers,
        "entities_tracked": entities_tracked,
        "cross_lab_entities": len(lags),
        "median_adoption_lag_years": (
            float(median(all_lags)) if all_lags else None
        ),
        "fastest_spreading": [
            {
                k: e[k]
                for k in ("entity", "entity_type", "adopter_count", "avg_lag_years")
            }
            for e in _fastest_entries(lags, limit=5)
        ],
    }
