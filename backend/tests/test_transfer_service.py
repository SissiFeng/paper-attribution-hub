"""Cross-SDL knowledge-transfer analytics: flows, adoption lags, summary."""
from __future__ import annotations

from tests.admin_client import AdminTestClient as TestClient

from app.models import Paper, PaperEntity, PaperLabLink, PaperReference, SdlLab
from app.services.transfer_service import (
    adoption_lags,
    lab_flow_matrix,
    transfer_summary,
)


def _lab(lab_id: str) -> SdlLab:
    return SdlLab(
        id=lab_id,
        name=f"Lab {lab_id[-1].upper()}",
        institution="Test U",
        domain_focus="testing",
    )


def _entity(paper_id: str, entity_type: str, name: str) -> PaperEntity:
    return PaperEntity(
        id=f"ent_{paper_id}_{name.replace(' ', '_')}",
        paper_id=paper_id,
        entity_type=entity_type,
        name=name,
        normalized_name=name,
    )


def _ref(ref_id: str, citing: str, cited: str | None) -> PaperReference:
    return PaperReference(
        id=ref_id, citing_paper_id=citing, cited_paper_id=cited, raw_text="ref"
    )


def _seed(session) -> None:
    session.add_all([_lab("lab-a"), _lab("lab-b"), _lab("lab-c")])
    papers = {
        "PA1": (2020, "lab-a"),
        "PA2": (2022, "lab-a"),
        "PB1": (2021, "lab-b"),
        "PB2": (2022, "lab-b"),
        "PC0": (2021, "lab-c"),
        "PC1": (2023, "lab-c"),
        "PN": (None, "lab-a"),  # no year — skipped by adoption lags
        "PX": (2022, None),  # not linked to any lab
    }
    for pid, (year, lab_id) in papers.items():
        session.add(Paper(id=pid, title=f"Paper {pid}", year=year))
        if lab_id:
            session.add(PaperLabLink(paper_id=pid, lab_id=lab_id))
    session.add_all(
        [
            _ref("R1", "PB1", "PA1"),  # lab-b -> lab-a (citing year 2021)
            _ref("R2", "PC1", "PA1"),  # lab-c -> lab-a (2023)
            _ref("R3", "PC1", "PB1"),  # lab-c -> lab-b (2023)
            _ref("R4", "PB2", "PB1"),  # intra lab-b
            _ref("R5", "PB1", "PX"),  # cited paper has no lab — ignored
            _ref("R6", "PB1", None),  # unresolved — ignored
        ]
    )
    session.add_all(
        [
            _entity("PA1", "method", "bayesian optimization"),
            _entity("PB1", "method", "bayesian optimization"),
            _entity("PC1", "method", "bayesian optimization"),
            _entity("PN", "method", "bayesian optimization"),  # null year
            # tie origin: lab-b and lab-c both first mention in 2021
            _entity("PB1", "instrument", "opentrons"),
            _entity("PC0", "instrument", "opentrons"),
            # single lab — filtered out by min_labs=2
            _entity("PA1", "software", "python"),
        ]
    )
    session.flush()


def test_lab_flow_matrix_counts_and_self_flow_exclusion(session):
    _seed(session)
    flows = lab_flow_matrix(session)
    assert [lab["id"] for lab in flows["labs"]] == ["lab-a", "lab-b", "lab-c"]
    # rows = citing lab, cols = cited lab
    assert flows["matrix"] == [
        [0, 0, 0],
        [1, 0, 0],
        [1, 1, 0],
    ]
    assert flows["intra_lab"] == {"lab-a": 0, "lab-b": 1, "lab-c": 0}
    assert flows["total_cross_flows"] == 3


def test_lab_flow_matrix_year_filter_on_citing_paper(session):
    _seed(session)
    flows = lab_flow_matrix(session, year_from=2022)
    # PB1 (2021) citations drop out; PC1 (2023) and PB2 (2022) remain.
    assert flows["matrix"] == [
        [0, 0, 0],
        [0, 0, 0],
        [1, 1, 0],
    ]
    assert flows["intra_lab"]["lab-b"] == 1
    assert flows["total_cross_flows"] == 2
    assert lab_flow_matrix(session, year_to=2021)["total_cross_flows"] == 1


def test_adoption_lags_math_and_ordering(session):
    _seed(session)
    entries = adoption_lags(session)
    # Sorted by adopting-lab count desc: bayes (2 adopters) before opentrons (0).
    assert [e["entity"] for e in entries] == ["bayesian optimization", "opentrons"]

    bayes = entries[0]
    assert bayes["origin_lab"] == "lab-a"
    assert bayes["origin_year"] == 2020
    assert bayes["adoptions"] == [
        {"lab": "lab-b", "first_year": 2021, "lag_years": 1},
        {"lab": "lab-c", "first_year": 2023, "lag_years": 3},
    ]

    # Tie origin: lab-b and lab-c both 2021 — deterministic first, no adoptions.
    tie = entries[1]
    assert tie["origin_lab"] == "lab-b"
    assert tie["origin_year"] == 2021
    assert tie["adoptions"] == []


def test_adoption_lags_filters(session):
    _seed(session)
    # min_labs=3 keeps only the entity seen in all three labs.
    entries = adoption_lags(session, min_labs=3)
    assert [e["entity"] for e in entries] == ["bayesian optimization"]
    # entity_type filter
    entries = adoption_lags(session, entity_type="instrument")
    assert [e["entity"] for e in entries] == ["opentrons"]
    assert adoption_lags(session, entity_type="software") == []


def test_transfer_summary(session):
    _seed(session)
    summary = transfer_summary(session)
    assert summary["labs"] == 3
    assert summary["linked_papers"] == 7  # all seeded papers except PX
    assert summary["entities_tracked"] == 3
    assert summary["cross_lab_entities"] == 2
    assert summary["median_adoption_lag_years"] == 2.0  # median of [1, 3]
    fastest = summary["fastest_spreading"]
    assert fastest == [
        {
            "entity": "bayesian optimization",
            "entity_type": "method",
            "adopter_count": 2,
            "avg_lag_years": 2.0,
        }
    ]


def test_transfer_endpoints_happy_path(session):
    from app.main import app

    _seed(session)
    session.commit()
    client = TestClient(app)

    r = client.get("/analytics/transfer/flows")
    assert r.status_code == 200
    body = r.json()
    assert body["total_cross_flows"] == 3
    assert body["matrix"][1][0] == 1

    r = client.get("/analytics/transfer/flows", params={"year_from": 2022})
    assert r.status_code == 200
    assert r.json()["total_cross_flows"] == 2

    r = client.get("/analytics/transfer/adoption")
    assert r.status_code == 200
    entries = r.json()
    assert entries[0]["entity"] == "bayesian optimization"
    assert entries[0]["adoptions"][0]["lag_years"] == 1

    r = client.get(
        "/analytics/transfer/adoption", params={"entity_type": "instrument"}
    )
    assert r.status_code == 200
    assert [e["entity"] for e in r.json()] == ["opentrons"]

    r = client.get("/analytics/transfer/summary")
    assert r.status_code == 200
    assert r.json()["cross_lab_entities"] == 2
