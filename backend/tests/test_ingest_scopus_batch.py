from __future__ import annotations

import pandas as pd

from sqlalchemy import select


def test_author_links_from_scopus_row_aligns_affiliations():
    from app.scripts.ingest_scopus_batch import _author_links_from_row

    row = pd.Series({
        "author_names": "Alice Smith|Bob Jones",
        "author_scopus_ids": "111|222",
        "author_affiliation_names_grouped": "Lab A; University A|Institute B",
        "author_affiliation_profile_names_grouped": "University A|Institute B",
        "author_affiliation_countries_grouped": "Canada|United States",
        "author_affiliation_cities_grouped": "Toronto|Boston",
    })

    links = _author_links_from_row(row, ["Alice Smith"])

    assert [l["name"] for l in links] == ["Alice Smith", "Bob Jones"]
    assert links[0]["institution"] == "University A"
    assert links[0]["country"] == "Canada"
    assert links[0]["is_ac_member"] is True
    assert links[1]["scopus_id"] == "222"


def test_upsert_papers_writes_author_institution_links(session):
    from app.models import Author, Institution, PaperAuthor
    from app.scripts.ingest_scopus_batch import _upsert_papers

    rows = [{
        "id": "p_scopus_1",
        "title": "A robotic closed-loop platform",
        "doi": "10.1234/scopus.1",
        "source": "scopus",
        "provenance": "scopus_batch",
        "author_links": [
            {
                "author_id": "auth_scopus_1",
                "name": "Alice Smith",
                "scopus_id": "111",
                "institution": "University A",
                "country": "Canada",
                "city": "Toronto",
                "affiliation_text": "Lab A; University A",
            }
        ],
    }]

    inserted, updated, authors, institutions, links = _upsert_papers(session, rows)
    session.commit()

    assert (inserted, updated, authors, institutions, links) == (1, 0, 1, 1, 1)
    assert session.get(Author, "auth_scopus_1").institution.canonical_name == "University A"
    inst = session.execute(
        select(Institution).where(Institution.canonical_name == "University A")
    ).scalar_one()
    assert inst.country == "Canada"
    assert session.get(PaperAuthor, ("p_scopus_1", "auth_scopus_1")).match_confidence == 1.0


def test_upsert_papers_reuses_institutions_within_same_flush(session):
    from app.models import Institution
    from app.scripts.ingest_scopus_batch import _upsert_papers

    rows = [
        {
            "id": "p_scopus_2",
            "title": "Paper two",
            "doi": "10.1234/scopus.2",
            "source": "scopus",
            "provenance": "scopus_batch",
            "author_links": [
                {
                    "author_id": "auth_scopus_2",
                    "name": "Alice Smith",
                    "scopus_id": "222",
                    "institution": "Shared Institute",
                    "country": "Canada",
                    "city": "Toronto",
                    "affiliation_text": "Shared Institute",
                }
            ],
        },
        {
            "id": "p_scopus_3",
            "title": "Paper three",
            "doi": "10.1234/scopus.3",
            "source": "scopus",
            "provenance": "scopus_batch",
            "author_links": [
                {
                    "author_id": "auth_scopus_3",
                    "name": "Bob Jones",
                    "scopus_id": "333",
                    "institution": "Shared Institute",
                    "country": "Canada",
                    "city": "Toronto",
                    "affiliation_text": "Shared Institute",
                }
            ],
        },
    ]

    _upsert_papers(session, rows)
    session.commit()

    count = session.execute(
        select(Institution).where(Institution.canonical_name == "Shared Institute")
    ).scalars().all()
    assert len(count) == 1


def test_upsert_papers_deduplicates_same_author_on_one_paper(session):
    from app.models import PaperAuthor
    from app.scripts.ingest_scopus_batch import _upsert_papers

    rows = [{
        "id": "p_scopus_4",
        "title": "Paper four",
        "doi": "10.1234/scopus.4",
        "source": "scopus",
        "provenance": "scopus_batch",
        "author_links": [
            {
                "author_id": "auth_scopus_4",
                "name": "Repeated Author",
                "scopus_id": "444",
                "institution": "Institute C",
                "country": "Canada",
                "city": "Toronto",
                "affiliation_text": "Institute C",
            },
            {
                "author_id": "auth_scopus_4",
                "name": "Repeated Author",
                "scopus_id": "444",
                "institution": "Institute C",
                "country": "Canada",
                "city": "Toronto",
                "affiliation_text": "Institute C",
            },
        ],
    }]

    _upsert_papers(session, rows)
    session.commit()

    links = session.execute(
        select(PaperAuthor).where(PaperAuthor.paper_id == "p_scopus_4")
    ).scalars().all()
    assert len(links) == 1


def test_upsert_papers_reuses_institution_when_stable_id_matches(session):
    from app.models import Institution
    from app.scripts.ingest_scopus_batch import _upsert_papers

    rows = [
        {
            "id": "p_scopus_5",
            "title": "Paper five",
            "doi": "10.1234/scopus.5",
            "source": "scopus",
            "provenance": "scopus_batch",
            "author_links": [
                {
                    "author_id": "auth_scopus_5",
                    "name": "Case One",
                    "scopus_id": "555",
                    "institution": "CNRS",
                    "country": "France",
                    "city": "Paris",
                    "affiliation_text": "CNRS",
                }
            ],
        },
        {
            "id": "p_scopus_6",
            "title": "Paper six",
            "doi": "10.1234/scopus.6",
            "source": "scopus",
            "provenance": "scopus_batch",
            "author_links": [
                {
                    "author_id": "auth_scopus_6",
                    "name": "Case Two",
                    "scopus_id": "666",
                    "institution": "Cnrs",
                    "country": "France",
                    "city": "Paris",
                    "affiliation_text": "Cnrs",
                }
            ],
        },
    ]

    _upsert_papers(session, rows)
    session.commit()

    institutions = session.execute(
        select(Institution).where(Institution.canonical_name.in_(["CNRS", "Cnrs"]))
    ).scalars().all()
    assert len(institutions) == 1
