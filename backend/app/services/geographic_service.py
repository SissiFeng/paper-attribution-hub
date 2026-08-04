"""Geographic collaboration aggregation (v0.7).

Given the filtered paper set, computes:

  * `countries`: per-country totals
      - paper_count: papers with at least one author affiliated there
      - institution_count: distinct institutions in that country
      - is_partner: country contains at least one AC partner institution
  * `arcs`: undirected collaboration links weighted by distinct shared papers;
    a selected country/institution center projects only its incident links.
  * `institutions`: top institutions per country (for tooltip drill-down).
  * `growth`: year-resolved distinct center papers, collaboration papers, and
    active/cumulative partner counts.

No coordinates here — the frontend uses ECharts' built-in world map (geo
component) and matches on country name.
"""
from __future__ import annotations

from collections import defaultdict
from itertools import combinations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.country_normalization import canonical_country_entries
from app.models import Institution, Paper, PaperAuthor
from app.services.filter_spec import (
    PaperFilter,
    PAPER_SET_ENCODING,
    apply_filter,
    build_filter_audit,
    paper_set_sha256,
)


class GeographicCenterError(ValueError):
    """Raised when a requested geographic center cannot be resolved."""


def _resolve_center(
    session: Session,
    *,
    center_type: str | None,
    center_id: str | None,
    center_country: str | None,
) -> tuple[dict | None, str | None]:
    if center_country:
        if center_type is not None or center_id is not None:
            raise GeographicCenterError(
                "Legacy center_country cannot be combined with center_type or center_id"
            )
        center_type = "country"
        center_id = center_country
    if center_type is None and center_id is None:
        return None, None
    if center_type not in {"country", "institution"} or not center_id:
        raise GeographicCenterError(
            "center_type and center_id must be provided together"
        )

    if center_type == "country":
        entries = canonical_country_entries(center_id)
        if len(entries) != 1:
            raise GeographicCenterError("center_id must identify exactly one country")
        requested = entries[0]
        available = {
            entry.identity: entry.display
            for raw_country in session.execute(select(Institution.country)).scalars()
            for entry in canonical_country_entries(raw_country)
        }
        if requested.identity not in available:
            raise GeographicCenterError(f"Unknown country center: {center_id}")
        display = available[requested.identity]
        return (
            {
                "type": "country",
                "id": display,
                "name": display,
                "country": display,
            },
            requested.identity,
        )

    institution = session.get(Institution, center_id)
    if institution is None:
        raise GeographicCenterError(f"Unknown institution center: {center_id}")
    country_names = [
        entry.display for entry in canonical_country_entries(institution.country)
    ]
    return (
        {
            "type": "institution",
            "id": institution.id,
            "name": institution.canonical_name,
            "country": "; ".join(country_names) or None,
        },
        institution.id,
    )


def _growth_years(filt: PaperFilter, paper_year: dict[str, int | None]) -> list[int]:
    observed = sorted({year for year in paper_year.values() if year is not None})
    start = filt.year_from if filt.year_from is not None else (observed[0] if observed else None)
    end = filt.year_to if filt.year_to is not None else (observed[-1] if observed else None)
    if start is None and end is None:
        return []
    if start is None:
        start = end
    if end is None:
        end = start
    return list(range(start, end + 1))


def build_geographic_payload(
    session: Session,
    filt: PaperFilter,
    *,
    center_type: str | None = None,
    center_id: str | None = None,
    center_country: str | None = None,
) -> dict:
    center, center_key = _resolve_center(
        session,
        center_type=center_type,
        center_id=center_id,
        center_country=center_country,
    )
    filtered_papers = session.execute(
        apply_filter(select(Paper.id, Paper.year), filt)
    ).all()
    paper_year = {paper_id: year for paper_id, year in filtered_papers}
    paper_ids = list(paper_year)

    # Join paper_authors → author → institution to get (paper_id, country, institution_id)
    from app.models import Author

    rows = (
        session.execute(
            select(
                Paper.id,
                Institution.id,
                Institution.canonical_name,
                Institution.country,
                Institution.is_partner,
            )
            .join(PaperAuthor, PaperAuthor.paper_id == Paper.id)
            .join(Author, Author.id == PaperAuthor.author_id)
            .join(Institution, Institution.id == Author.institution_id)
            .where(Paper.id.in_(paper_ids))
        ).all()
        if paper_ids
        else []
    )

    # Per-paper country set (don't double-count papers with multiple authors in same country)
    paper_country_pairs: set[tuple[str, str]] = set()
    paper_institution_pairs: set[tuple[str, str, str]] = set()
    country_institutions: dict[str, set[str]] = defaultdict(set)
    institution_label: dict[str, str] = {}
    institution_is_partner: dict[str, bool] = {}
    institution_countries: dict[str, set[str]] = defaultdict(set)
    country_is_partner: dict[str, bool] = defaultdict(bool)
    country_display: dict[str, str] = {}

    for paper_id, inst_id, inst_name, country, is_partner in rows:
        institution_label[inst_id] = inst_name
        institution_is_partner[inst_id] = bool(is_partner)
        for normalized_country in canonical_country_entries(country):
            identity = normalized_country.identity
            country_display[identity] = normalized_country.display
            paper_country_pairs.add((paper_id, identity))
            paper_institution_pairs.add((paper_id, inst_id, identity))
            institution_countries[inst_id].add(identity)
            country_institutions[identity].add(inst_id)
            if is_partner:
                country_is_partner[identity] = True

    country_papers: dict[str, set[str]] = defaultdict(set)
    for paper_id, country in paper_country_pairs:
        country_papers[country].add(paper_id)
    institution_papers: dict[tuple[str, str], set[str]] = defaultdict(set)
    for paper_id, inst_id, country in paper_institution_pairs:
        institution_papers[(inst_id, country)].add(paper_id)

    countries_out = [
        {
            "country": country_display[country],
            "paper_count": len(papers),
            "institution_count": len(country_institutions[country]),
            "is_partner": bool(country_is_partner[country]),
        }
        for country, papers in sorted(
            country_papers.items(),
            key=lambda item: (-len(item[1]), country_display[item[0]]),
        )
    ]

    # Top institutions per country (for tooltip)
    institutions_out = [
        {
            "id": f"{inst_id}:{country_display[country]}",
            "institution_id": inst_id,
            "name": institution_label[inst_id],
            "country": country_display[country],
            "is_partner": institution_is_partner[inst_id],
            "paper_count": len(papers),
        }
        for (inst_id, country), papers in sorted(
            institution_papers.items(),
            key=lambda item: (
                -len(item[1]),
                institution_label[item[0][0]],
                item[0][0],
                country_display[item[0][1]],
            ),
        )
    ]

    paper_countries: dict[str, set[str]] = defaultdict(set)
    for paper_id, country in paper_country_pairs:
        paper_countries[paper_id].add(country)
    paper_institutions: dict[str, set[str]] = defaultdict(set)
    for paper_id, inst_id, _country in paper_institution_pairs:
        paper_institutions[paper_id].add(inst_id)

    center_paper_ids: set[str] = set()
    collaboration_paper_ids: set[str] = set()
    partner_papers: dict[str, set[str]] = defaultdict(set)
    arc_papers: dict[tuple[str, str], set[str]] = defaultdict(set)

    if center and center["type"] == "country":
        center_paper_ids = {
            paper_id
            for paper_id, countries in paper_countries.items()
            if center_key in countries
        }
        for paper_id in center_paper_ids:
            for partner in paper_countries[paper_id] - {center_key}:
                partner_papers[partner].add(paper_id)
                collaboration_paper_ids.add(paper_id)
                arc_papers[(center_key, partner)].add(paper_id)
    elif center and center["type"] == "institution":
        center_paper_ids = {
            paper_id
            for paper_id, institutions in paper_institutions.items()
            if center_key in institutions
        }
        center_countries = institution_countries.get(center_key, set())
        for paper_id in center_paper_ids:
            for partner in paper_institutions[paper_id] - {center_key}:
                partner_papers[partner].add(paper_id)
                collaboration_paper_ids.add(paper_id)
                for source in center_countries:
                    for target in institution_countries.get(partner, set()):
                        if source != target:
                            arc_papers[(source, target)].add(paper_id)
    else:
        for paper_id, countries in paper_countries.items():
            for source, target in combinations(sorted(countries), 2):
                if country_is_partner.get(source) or country_is_partner.get(target):
                    arc_papers[(source, target)].add(paper_id)

    arcs_out = [
        {
            "from": country_display[src],
            "to": country_display[dst],
            "weight": len(papers),
        }
        for (src, dst), papers in sorted(
            arc_papers.items(),
            key=lambda item: (
                -len(item[1]),
                country_display[item[0][0]],
                country_display[item[0][1]],
            ),
        )
    ]

    years = _growth_years(filt, paper_year)
    partner_rows: list[dict] = []
    for partner_id, papers in partner_papers.items():
        partner_year_counts = {
            year: len({paper_id for paper_id in papers if paper_year[paper_id] == year})
            for year in years
        }
        observed_years = sorted(
            {paper_year[paper_id] for paper_id in papers if paper_year[paper_id] is not None}
        )
        if center and center["type"] == "country":
            partner_name = country_display[partner_id]
            partner_country = partner_name
        else:
            partner_name = institution_label[partner_id]
            partner_country = "; ".join(
                sorted(country_display[country] for country in institution_countries[partner_id])
            ) or None
        partner_rows.append(
            {
                "id": partner_name if center and center["type"] == "country" else partner_id,
                "name": partner_name,
                "country": partner_country,
                "paper_count": len(papers),
                "first_year": observed_years[0] if observed_years else None,
                "last_year": observed_years[-1] if observed_years else None,
                "yearly": [
                    {"year": year, "paper_count": partner_year_counts[year]}
                    for year in years
                ],
            }
        )
    partner_rows.sort(key=lambda item: (-item["paper_count"], item["name"], item["id"]))

    cumulative_partners: set[str] = set()
    cumulative_collaboration_papers: set[str] = set()
    growth = []
    for year in years:
        year_center_papers = {
            paper_id for paper_id in center_paper_ids if paper_year[paper_id] == year
        }
        year_collaboration_papers = {
            paper_id
            for paper_id in collaboration_paper_ids
            if paper_year[paper_id] == year
        }
        year_partners = {
            partner_id
            for partner_id, papers in partner_papers.items()
            if any(paper_year[paper_id] == year for paper_id in papers)
        }
        cumulative_partners.update(year_partners)
        cumulative_collaboration_papers.update(year_collaboration_papers)
        growth.append(
            {
                "year": year,
                "center_papers": len(year_center_papers),
                "collaboration_papers": len(year_collaboration_papers),
                "active_partners": len(year_partners),
                "cumulative_partners": len(cumulative_partners),
                "cumulative_collaboration_papers": len(
                    cumulative_collaboration_papers
                ),
            }
        )

    center_years = sorted(
        {
            paper_year[paper_id]
            for paper_id in center_paper_ids
            if paper_year[paper_id] is not None
        }
    )
    center_summary = None
    if center:
        center_summary = {
            **center,
            "paper_count": len(center_paper_ids),
            "collaboration_paper_count": len(collaboration_paper_ids),
            "partner_count": len(partner_papers),
            "first_year": center_years[0] if center_years else None,
            "last_year": center_years[-1] if center_years else None,
            "missing_year_paper_count": sum(
                paper_year[paper_id] is None for paper_id in center_paper_ids
            ),
        }

    audit = build_filter_audit(
        session,
        filt,
        algorithm="geographic_collaboration_growth.v2",
        metric_definitions={
            "country_paper_count": "Distinct filtered papers with at least one author affiliation in the country.",
            "institution_count": "Distinct institutions attached to filtered papers in the country.",
            "arc_weight": "Distinct filtered papers connecting the selected center to the mapped partner country; without a center, only country pairs involving an AC-partner country are shown.",
            "center_papers": "Distinct filtered papers involving the selected country or institution.",
            "collaboration_papers": "Distinct center papers containing at least one other country or institution; a paper counts once even when it has multiple partners.",
            "active_partners": "Distinct partner countries or institutions connected to the center in the year.",
            "cumulative_partners": "Distinct partners observed from the selected window start through the year.",
            "growth_semantics": "Yearly collaboration growth, not causal influence or citation impact. Papers without a year are excluded from yearly series and reported separately.",
        },
        projection={
            "center_type": center["type"] if center else None,
            "center_id": center["id"] if center else None,
            "center_name": center["name"] if center else None,
            "partner_type": (
                "country"
                if center and center["type"] == "country"
                else "institution" if center else None
            ),
            "yearly_zero_fill": years,
            "arc_scope": (
                "all_center_incident_collaborations"
                if center
                else "pairs_involving_ac_partner_country"
            ),
        },
    )
    if center:
        audit["evidence_subsets"] = {
            "center_papers": {
                "count": len(center_paper_ids),
                "paper_set_sha256": paper_set_sha256(sorted(center_paper_ids)),
                "paper_set_encoding": PAPER_SET_ENCODING,
                "purpose": "Papers supporting the selected center's activity series.",
            },
            "collaboration_papers": {
                "count": len(collaboration_paper_ids),
                "paper_set_sha256": paper_set_sha256(
                    sorted(collaboration_paper_ids)
                ),
                "paper_set_encoding": PAPER_SET_ENCODING,
                "purpose": "Center papers with at least one distinct partner entity.",
            },
        }

    return {
        "countries": countries_out,
        "arcs": arcs_out,
        "institutions": institutions_out,
        "total_papers": len(paper_ids),
        "center_country": center["name"] if center and center["type"] == "country" else None,
        "center": center_summary,
        "growth": growth,
        "partners": partner_rows,
        "audit": audit,
    }
