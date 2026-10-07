"""SDL lab registry, paper→lab mapping, and labs/entities API."""
from __future__ import annotations

from tests.admin_client import AdminTestClient as TestClient
from sqlalchemy import select

from app.models import Author, Paper, PaperAuthor, PaperLabLink, SdlLab
from app.services.lab_service import load_labs_from_yaml, map_papers_to_labs
from app.services.normalization_service import normalize_name


def _add_paper_with_author(session, paper_id: str, author_name: str) -> None:
    author = Author(
        id=f"A_{paper_id}",
        canonical_name=author_name,
        normalized_name=normalize_name(author_name),
    )
    paper = Paper(id=paper_id, title=f"Paper {paper_id}", year=2024)
    session.add_all([author, paper])
    session.add(PaperAuthor(paper_id=paper_id, author_id=author.id, author_order=0))
    session.flush()


def test_load_labs_from_yaml_upserts(session):
    summary = load_labs_from_yaml(session)
    assert summary == {"created": 77, "updated": 0}
    lab = session.get(SdlLab, "aspuru-guzik-lab")
    assert lab is not None
    assert lab.institution == "University of Toronto"
    assert lab.pi_names == ["Alán Aspuru-Guzik"]
    # Curated aliases land in the roster alongside the canonical name.
    assert "A. Aspuru-Guzik" in lab.member_author_names

    # Re-running updates in place, no duplicates.
    summary = load_labs_from_yaml(session)
    assert summary == {"created": 0, "updated": 77}
    labs = list(session.execute(select(SdlLab)).scalars())
    assert len(labs) == 77


def test_map_papers_to_labs_via_roster(session):
    load_labs_from_yaml(session)
    # An alias spelling of the PI should still fold onto the roster.
    _add_paper_with_author(session, "P_LAB1", "Alan Aspuru-Guzik")
    _add_paper_with_author(session, "P_LAB2", "Unrelated Person")

    summary = map_papers_to_labs(session)
    assert summary["links_created"] == 1
    assert summary["links_ac_members"] == 0
    assert summary["papers_linked"] == 1

    links = list(session.execute(select(PaperLabLink)).scalars())
    assert len(links) == 1
    link = links[0]
    assert link.paper_id == "P_LAB1"
    assert link.lab_id == "aspuru-guzik-lab"
    assert link.source == "author_roster"
    assert link.confidence == 0.9

    # Idempotent re-run.
    summary = map_papers_to_labs(session)
    assert summary["links_created"] == 0
    assert len(list(session.execute(select(PaperLabLink)).scalars())) == 1


def test_map_papers_to_labs_via_ac_members(session):
    load_labs_from_yaml(session)
    _add_paper_with_author(session, "P_LAB4", "Unrelated Person")
    paper = session.get(Paper, "P_LAB4")
    # Raw "AC Members" string: comma-separated, with "(Deactivated)" noise.
    paper.ac_members_matched = ["Christine Allen,Kourosh Darvish (Deactivated)"]
    session.flush()

    summary = map_papers_to_labs(session)
    assert summary["links_created"] == 0
    assert summary["links_ac_members"] == 2
    assert summary["papers_linked"] == 1

    links = {
        link.lab_id: link for link in session.execute(select(PaperLabLink)).scalars()
    }
    assert set(links) == {"allen-lab", "darvish-lab"}
    for link in links.values():
        assert link.paper_id == "P_LAB4"
        assert link.source == "ac_members"
        assert link.confidence == 1.0

    # Idempotent re-run.
    summary = map_papers_to_labs(session)
    assert summary["links_ac_members"] == 0
    assert summary["links_upgraded"] == 0
    assert len(list(session.execute(select(PaperLabLink)).scalars())) == 2


def test_ac_members_upgrades_existing_roster_link(session):
    load_labs_from_yaml(session)
    _add_paper_with_author(session, "P_LAB5", "Alán Aspuru-Guzik")
    summary = map_papers_to_labs(session)
    assert summary["links_created"] == 1

    paper = session.get(Paper, "P_LAB5")
    paper.ac_members_matched = ["Alán Aspuru-Guzik"]
    session.flush()

    summary = map_papers_to_labs(session)
    assert summary["links_created"] == 0
    assert summary["links_ac_members"] == 0
    assert summary["links_upgraded"] == 1

    links = list(session.execute(select(PaperLabLink)).scalars())
    assert len(links) == 1
    assert links[0].lab_id == "aspuru-guzik-lab"
    assert links[0].source == "ac_members"
    assert links[0].confidence == 1.0


def test_labs_api_happy_path(session):
    from app.main import app
    from app.services.entity_extractor import extract_entities_for_paper

    load_labs_from_yaml(session)
    _add_paper_with_author(session, "P_LAB3", "Alan Aspuru-Guzik")
    paper = session.get(Paper, "P_LAB3")
    paper.title = "Bayesian optimization of perovskites"
    map_papers_to_labs(session)
    extract_entities_for_paper(session, paper)
    session.commit()

    client = TestClient(app)

    r = client.get("/labs")
    assert r.status_code == 200
    labs = {lab["id"]: lab for lab in r.json()}
    assert len(labs) == 77
    assert labs["aspuru-guzik-lab"]["paper_count"] == 1
    assert labs["allen-lab"]["paper_count"] == 0

    r = client.get("/labs/aspuru-guzik-lab/papers")
    assert r.status_code == 200
    papers = r.json()
    assert len(papers) == 1
    assert papers[0]["id"] == "P_LAB3"
    assert papers[0]["year"] == 2024
    assert papers[0]["label"] is None  # not classified

    assert client.get("/labs/nope/papers").status_code == 404

    r = client.get("/papers/P_LAB3/entities")
    assert r.status_code == 200
    entities = {(e["entity_type"], e["normalized_name"]) for e in r.json()}
    assert ("method", "bayesian optimization") in entities
    assert ("material", "perovskite") in entities
