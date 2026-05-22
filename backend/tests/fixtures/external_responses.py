"""Canned external-API responses for tests.

We replicate just enough structure for the v0.5 code paths. Real responses
are massively larger — but our normalizers only touch a handful of fields,
so a thin payload is sufficient and keeps the fixture readable.
"""
from __future__ import annotations


def openalex_work(doi: str, openalex_id: str, *, citing_authors=None, year=2024):
    citing_authors = citing_authors or []
    return {
        "id": f"https://openalex.org/{openalex_id}",
        "doi": f"https://doi.org/{doi}",
        "title": f"Mock paper for {openalex_id}",
        "publication_year": year,
        "primary_location": {"source": {"display_name": "Mock Journal"}},
        "abstract_inverted_index": {
            "Autonomous": [0],
            "closed-loop": [1],
            "Bayesian": [2],
            "optimization.": [3],
        },
        "authorships": [
            {
                "author": {
                    "display_name": a.get("name", "Unknown"),
                    "orcid": a.get("orcid"),
                },
                "institutions": [
                    {"display_name": a.get("institution", "Unknown Inst")}
                ],
            }
            for a in citing_authors
        ],
        "concepts": [{"display_name": "Self-driving lab", "score": 0.9}],
    }


def s2_paper(doi: str, paper_id: str = "abc123"):
    return {
        "paperId": paper_id,
        "externalIds": {"DOI": doi},
        "title": f"S2 paper {paper_id}",
        "abstract": "Abstract from Semantic Scholar.",
        "year": 2024,
        "venue": "Some Venue",
        "authors": [{"name": "Jane Doe"}],
        "referenceCount": 25,
        "citationCount": 12,
    }


def crossref_work(doi: str):
    return {
        "status": "ok",
        "message": {
            "DOI": doi,
            "title": [f"Crossref title for {doi}"],
            "container-title": ["Crossref Journal"],
            "issued": {"date-parts": [[2024]]},
            "author": [
                {
                    "given": "Alan",
                    "family": "Aspuru-Guzik",
                    "affiliation": [{"name": "University of Toronto"}],
                }
            ],
        },
    }
