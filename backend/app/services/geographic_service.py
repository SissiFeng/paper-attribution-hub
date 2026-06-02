"""Geographic collaboration aggregation (v0.7).

Given the filtered paper set, computes:

  * `countries`: per-country totals
      - paper_count: papers with at least one author affiliated there
      - institution_count: distinct institutions in that country
      - is_partner: country contains at least one AC partner institution
  * `arcs`: directional collaboration links from AC-partner countries to
    other countries, weighted by shared papers.
  * `institutions`: top institutions per country (for tooltip drill-down).

No coordinates here — the frontend uses ECharts' built-in world map (geo
component) and matches on country name.
"""
from __future__ import annotations

from collections import defaultdict

from sqlalchemy.orm import Session

from app.models import Institution, Paper, PaperAuthor
from app.services.filter_spec import PaperFilter, apply_filter
from sqlalchemy import select


def build_geographic_payload(session: Session, filt: PaperFilter) -> dict:
    # Filtered papers
    paper_ids = [
        pid for (pid,) in session.execute(apply_filter(select(Paper.id), filt)).all()
    ]
    if not paper_ids:
        return {"countries": [], "arcs": [], "institutions": [], "total_papers": 0}

    # Join paper_authors → author → institution to get (paper_id, country, institution_id)
    from app.models import Author

    rows = session.execute(
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

    # Per-paper country set (don't double-count papers with multiple authors in same country)
    paper_country_pairs: set[tuple[str, str]] = set()
    paper_institution_pairs: set[tuple[str, str]] = set()
    country_institutions: dict[str, set[str]] = defaultdict(set)
    institution_country: dict[str, str] = {}
    institution_label: dict[str, str] = {}
    institution_is_partner: dict[str, bool] = {}
    country_is_partner: dict[str, bool] = defaultdict(bool)

    for paper_id, inst_id, inst_name, country, is_partner in rows:
        if not country:
            continue
        # Normalize semicolon-concatenated values (e.g. "China;China" → "China")
        country = next(
            (c.strip() for c in country.split(";") if c.strip()),
            None,
        )
        if not country:
            continue
        paper_country_pairs.add((paper_id, country))
        paper_institution_pairs.add((paper_id, inst_id))
        country_institutions[country].add(inst_id)
        institution_country[inst_id] = country
        institution_label[inst_id] = inst_name
        institution_is_partner[inst_id] = bool(is_partner)
        if is_partner:
            country_is_partner[country] = True

    country_papers: dict[str, set[str]] = defaultdict(set)
    for paper_id, country in paper_country_pairs:
        country_papers[country].add(paper_id)
    institution_papers: dict[str, set[str]] = defaultdict(set)
    for paper_id, inst_id in paper_institution_pairs:
        institution_papers[inst_id].add(paper_id)

    countries_out = [
        {
            "country": country,
            "paper_count": len(papers),
            "institution_count": len(country_institutions[country]),
            "is_partner": bool(country_is_partner[country]),
        }
        for country, papers in sorted(
            country_papers.items(), key=lambda kv: -len(kv[1])
        )
    ]

    # Top institutions per country (for tooltip)
    institutions_out = [
        {
            "id": inst_id,
            "name": institution_label[inst_id],
            "country": institution_country[inst_id],
            "is_partner": institution_is_partner[inst_id],
            "paper_count": len(papers),
        }
        for inst_id, papers in sorted(
            institution_papers.items(), key=lambda kv: -len(kv[1])
        )
    ]

    # Arcs: per-paper, every country pair that involves an AC-partner country.
    arc_weights: dict[tuple[str, str], int] = defaultdict(int)
    paper_countries: dict[str, set[str]] = defaultdict(set)
    for paper_id, country in paper_country_pairs:
        paper_countries[paper_id].add(country)
    for paper_id, countries in paper_countries.items():
        if len(countries) < 2:
            continue
        partner_countries = [c for c in countries if country_is_partner.get(c)]
        if not partner_countries:
            continue
        for src in partner_countries:
            for dst in countries:
                if dst == src:
                    continue
                key = (src, dst)
                arc_weights[key] += 1

    arcs_out = [
        {"from": src, "to": dst, "weight": w}
        for (src, dst), w in sorted(arc_weights.items(), key=lambda kv: -kv[1])
    ]

    return {
        "countries": countries_out,
        "arcs": arcs_out,
        "institutions": institutions_out,
        "total_papers": len(paper_ids),
    }
