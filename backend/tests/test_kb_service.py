"""Cross-SDL knowledge base: entity index/pages, lab profiles, summary."""
from __future__ import annotations

from tests.admin_client import AdminTestClient as TestClient

from app.models import Paper, PaperChunk, PaperEntity, PaperLabLink, SdlLab
from app.services.kb_service import entity_index, entity_page, kb_summary, lab_profile

CHUNK_TEXT = "We used bayesian optimization to drive the closed-loop campaign. " * 8


def _lab(lab_id: str) -> SdlLab:
    return SdlLab(
        id=lab_id,
        name=f"Lab {lab_id[-1].upper()}",
        institution="Test U",
        domain_focus="testing",
    )


def _entity(
    paper_id: str,
    entity_type: str,
    name: str,
    chunk_id: str | None = None,
    stage: str | None = None,
    usage_snippet: str | None = None,
) -> PaperEntity:
    return PaperEntity(
        id=f"ent_{paper_id}_{name.replace(' ', '_')}",
        paper_id=paper_id,
        entity_type=entity_type,
        name=name,
        normalized_name=name,
        evidence_chunk_id=chunk_id,
        stage=stage,
        usage_snippet=usage_snippet,
    )


def _seed(session) -> None:
    session.add_all([_lab("lab-a"), _lab("lab-b"), _lab("lab-c")])
    papers = {
        "PA1": (2020, "lab-a", ["SDL 1"]),
        "PA2": (2022, "lab-a", ["SDL 1", "SDL 2"]),
        "PB1": (2021, "lab-b", ["SDL 2"]),
        "PC1": (2023, "lab-c", None),
        "PX": (2022, None, None),  # not linked to any lab
    }
    for pid, (year, lab_id, tags) in papers.items():
        session.add(Paper(id=pid, title=f"Paper {pid}", year=year, sdl_tags=tags))
        if lab_id:
            session.add(PaperLabLink(paper_id=pid, lab_id=lab_id))
    # PA2 is shared between lab-a and lab-b (collaboration).
    session.add(PaperLabLink(paper_id="PA2", lab_id="lab-b"))
    session.add(
        PaperChunk(
            id="CH1", paper_id="PA1", section_type="methods", chunk_text=CHUNK_TEXT
        )
    )
    session.add_all(
        [
            _entity(
                "PA1",
                "method",
                "bayesian optimization",
                chunk_id="CH1",
                stage="optimization",
                usage_snippet="Bayesian optimization drove the campaign.",
            ),
            _entity("PB1", "method", "bayesian optimization"),
            _entity("PC1", "method", "bayesian optimization"),
            _entity("PA1", "software", "python"),  # unique to lab-a
            _entity("PA2", "material", "perovskite"),  # PA2 → lab-a and lab-b
            _entity("PX", "instrument", "opentrons"),  # paper without a lab
        ]
    )
    session.flush()


def test_entity_index_counts_and_sort(session):
    _seed(session)
    entries = entity_index(session)
    assert [e["name"] for e in entries] == [
        "bayesian optimization",
        "opentrons",
        "perovskite",
        "python",
    ]
    bayes = entries[0]
    assert bayes == {
        "entity_type": "method",
        "name": "bayesian optimization",
        "paper_count": 3,
        "lab_count": 3,
        "first_year": 2020,
        "last_year": 2023,
    }
    # perovskite: one paper linked to two labs
    perov = entries[2]
    assert perov["paper_count"] == 1
    assert perov["lab_count"] == 2
    # entity on a lab-less paper still appears, with lab_count 0
    assert entries[1]["lab_count"] == 0


def test_entity_index_filters(session):
    _seed(session)
    assert [e["name"] for e in entity_index(session, entity_type="software")] == [
        "python"
    ]
    assert [e["name"] for e in entity_index(session, q="OPTIM")] == [
        "bayesian optimization"
    ]
    assert entity_index(session, entity_type="method", q="zzz") == []


def test_entity_page_labs_timeline_evidence_adoption(session):
    _seed(session)
    page = entity_page(session, "method", "bayesian optimization")
    assert page is not None
    assert page["entity"] == "bayesian optimization"
    assert page["labs"] == [
        {"lab_id": "lab-a", "lab_name": "Lab A", "first_year": 2020, "paper_count": 1},
        {"lab_id": "lab-b", "lab_name": "Lab B", "first_year": 2021, "paper_count": 1},
        {"lab_id": "lab-c", "lab_name": "Lab C", "first_year": 2023, "paper_count": 1},
    ]
    assert [p["id"] for p in page["papers"]] == ["PA1", "PB1", "PC1"]
    assert page["papers"][0]["labs"] == ["lab-a"]
    assert page["timeline"] == [
        {"year": 2020, "paper_count": 1},
        {"year": 2021, "paper_count": 1},
        {"year": 2023, "paper_count": 1},
    ]
    # evidence joined via evidence_chunk_id, truncated to ~300 chars
    assert len(page["evidence"]) == 1
    ev = page["evidence"][0]
    assert ev["paper_id"] == "PA1"
    assert ev["paper_title"] == "Paper PA1"
    assert ev["text"].startswith("We used bayesian optimization")
    assert len(ev["text"]) == 300 < len(CHUNK_TEXT)
    # adoption reused from transfer_service
    assert page["adoption"]["origin_lab"] == "lab-a"
    assert page["adoption"]["origin_year"] == 2020
    assert [a["lag_years"] for a in page["adoption"]["adoptions"]] == [1, 3]
    assert page["events"][0]["event_type"] == "stage:optimization"
    assert page["events"][0]["source_chunk_id"] == "CH1"
    assert page["events"][0]["snippet"] == "Bayesian optimization drove the campaign."
    assert page["events"][0]["related_entities"] == [
        {"entity_type": "software", "name": "python"}
    ]


def test_entity_page_without_labs_and_unknown(session):
    _seed(session)
    page = entity_page(session, "instrument", "opentrons")
    assert page is not None
    assert page["labs"] == []
    assert page["adoption"] is None
    assert [p["id"] for p in page["papers"]] == ["PX"]
    assert entity_page(session, "method", "nope") is None


def test_lab_profile(session):
    _seed(session)
    profile = lab_profile(session, "lab-a")
    assert profile is not None
    assert profile["name"] == "Lab A"
    assert profile["paper_count"] == 2
    assert profile["first_year"] == 2020
    assert profile["last_year"] == 2022
    assert profile["sdl_tag_histogram"] == [
        {"tag": "SDL 1", "count": 2},
        {"tag": "SDL 2", "count": 1},
    ]
    assert profile["top_entities"]["method"] == [
        {"name": "bayesian optimization", "paper_count": 1}
    ]
    assert profile["top_entities"]["material"] == [
        {"name": "perovskite", "paper_count": 1}
    ]
    assert profile["top_entities"]["software"] == [
        {"name": "python", "paper_count": 1}
    ]
    assert profile["top_entities"]["instrument"] == []
    assert profile["collaborations"] == [
        {"lab_id": "lab-b", "name": "Lab B", "shared_papers": 1}
    ]
    # python is the only entity no other lab has (perovskite is shared via PA2)
    assert profile["entities_unique_to_lab"] == 1
    assert lab_profile(session, "lab-nope") is None


def test_kb_summary(session):
    _seed(session)
    summary = kb_summary(session)
    assert summary["labs"] == 3
    assert summary["linked_papers"] == 4  # all seeded papers except PX
    assert summary["entities_by_type"] == {
        "method": 1,
        "software": 1,
        "material": 1,
        "instrument": 1,
    }
    # bayes (3 labs) + perovskite (2 labs via PA2)
    assert summary["cross_lab_entities"] == 2


def test_kb_endpoints(session):
    from app.main import app

    _seed(session)
    session.commit()
    client = TestClient(app)

    r = client.get("/kb/summary")
    assert r.status_code == 200
    assert r.json()["cross_lab_entities"] == 2

    r = client.get("/kb/entities", params={"entity_type": "method"})
    assert r.status_code == 200
    assert [e["name"] for e in r.json()] == ["bayesian optimization"]

    r = client.get("/kb/entities/method/bayesian optimization")
    assert r.status_code == 200
    body = r.json()
    assert body["adoption"]["origin_lab"] == "lab-a"
    assert len(body["evidence"]) == 1
    assert body["events"][0]["event_type"] == "stage:optimization"
    assert client.get("/kb/entities/method/nope").status_code == 404

    r = client.get("/kb/labs/lab-a/profile")
    assert r.status_code == 200
    assert r.json()["paper_count"] == 2
    assert client.get("/kb/labs/lab-nope/profile").status_code == 404
