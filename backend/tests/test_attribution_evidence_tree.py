from __future__ import annotations

from fastapi.testclient import TestClient


def _seed_aet_paper(session) -> None:
    from app.models import Paper, PaperChunk, PaperEvidence, PaperSection

    session.add(Paper(id="AET1", title="Auditable SDL paper"))
    methods = PaperSection(
        id="sec_methods",
        paper_id="AET1",
        section_type="methods",
        section_title="Methods",
        content="A closed-loop platform selects experiments with Bayesian optimization.",
        page_start=4,
        page_end=6,
        order_index=0,
    )
    acknowledgements = PaperSection(
        id="sec_ack",
        paper_id="AET1",
        section_type="acknowledgements",
        section_title="Acknowledgements",
        content="This work was supported by the Acceleration Consortium.",
        page_start=9,
        page_end=9,
        order_index=1,
    )
    session.add_all([methods, acknowledgements])
    session.add_all(
        [
            PaperChunk(
                id="chk_methods",
                paper_id="AET1",
                section_id=methods.id,
                section_type="methods",
                chunk_text=methods.content,
            ),
            PaperChunk(
                id="chk_ack",
                paper_id="AET1",
                section_id=acknowledgements.id,
                section_type="acknowledgements",
                chunk_text=acknowledgements.content,
            ),
        ]
    )
    session.add_all(
        [
            PaperEvidence(
                id="ev_method",
                paper_id="AET1",
                chunk_id="chk_methods",
                evidence_type="sdl_methodology",
                evidence_source="methods",
                evidence_text="closed-loop platform selects experiments",
                score=0.2,
            ),
            PaperEvidence(
                id="ev_funding",
                paper_id="AET1",
                chunk_id="chk_ack",
                evidence_type="funding_acknowledgement",
                evidence_source="acknowledgements",
                evidence_text="supported by the Acceleration Consortium",
                score=0.6,
                extra={
                    "attribution_evidence": {
                        "contract_version": "aet-evidence-meta-v0.1",
                        "centrality": "core_contribution",
                        "confidence": 0.93,
                        "detector_type": "curated_rule",
                    }
                },
            ),
            PaperEvidence(
                id="ev_negative",
                paper_id="AET1",
                chunk_id=None,
                evidence_type="disqualifying",
                evidence_source="llm_judge",
                evidence_text="The SDL phrase is background only.",
                score=-0.4,
                extra={"centrality": "background_only"},
            ),
        ]
    )
    session.flush()


def test_build_tree_returns_traceable_paths(session):
    from app.services.attribution_evidence_tree import build_attribution_evidence_tree

    _seed_aet_paper(session)

    tree = build_attribution_evidence_tree(session, "AET1")

    assert tree.tree_version == "aet-derived-v0.1"
    assert tree.generation_mode == "derived_ephemeral"
    assert len(tree.generation_id) == 24
    assert tree.metadata_contract_version == "aet-evidence-meta-v0.1"
    assert [node.node_type for node in tree.nodes[:3]] == [
        "root",
        "section",
        "section",
    ]
    methods = next(
        node for node in tree.nodes if node.source_section_id == "sec_methods"
    )
    assert methods.path == ["Paper", "Methods"]
    assert methods.page_start == 4
    assert methods.page_end == 6
    assert methods.source_chunk_ids == ["chk_methods"]

    funding = next(
        path
        for path in tree.evidence_paths
        if path.evidence_type == "funding_acknowledgement"
    )
    assert funding.path == [
        "Paper",
        "Acknowledgements",
        "funding_acknowledgement",
    ]
    assert funding.page_start == 9
    assert funding.page_end == 9
    assert funding.polarity == "positive"
    assert funding.centrality == "core_contribution"
    assert funding.confidence == 0.93
    assert funding.detector_type == "curated_rule"
    assert funding.rank == 1
    assert funding.metadata_status == "versioned_validated"
    assert funding.generation_id
    assert funding.raw_score == 0.6

    negative = next(
        path for path in tree.evidence_paths if path.evidence_type == "disqualifying"
    )
    assert negative.path == ["Paper", "Llm Judge", "disqualifying"]
    assert negative.polarity == "negative"
    assert negative.centrality == "background_only"
    assert negative.page_start is None
    assert negative.rank == 3
    assert negative.metadata_status == "legacy_validated"
    assert {path.generation_id for path in tree.evidence_paths} == {
        funding.generation_id
    }
    assert tree.evidence_review_recommended is True
    assert tree.evidence_review_reasons == ["AET_CONFLICTING_EVIDENCE"]


def test_build_tree_flags_missing_evidence(session):
    from app.models import Paper
    from app.services.attribution_evidence_tree import build_attribution_evidence_tree

    session.add(Paper(id="AET_EMPTY", title="No full text evidence"))
    session.flush()

    tree = build_attribution_evidence_tree(session, "AET_EMPTY")

    assert [node.node_type for node in tree.nodes] == ["root"]
    assert tree.evidence_paths == []
    assert tree.evidence_review_recommended is True
    assert tree.evidence_review_reasons == ["AET_NO_EVIDENCE"]


def test_build_tree_does_not_defer_positive_only_evidence(session):
    from app.models import PaperEvidence
    from app.services.attribution_evidence_tree import build_attribution_evidence_tree

    _seed_aet_paper(session)
    session.delete(session.get(PaperEvidence, "ev_negative"))
    session.flush()

    tree = build_attribution_evidence_tree(session, "AET1")

    assert {path.polarity for path in tree.evidence_paths} == {"positive"}
    assert tree.evidence_review_recommended is False
    assert tree.evidence_review_reasons == []


def test_generation_and_metadata_fallbacks_are_explicit(session):
    from app.models import PaperEvidence
    from app.services.attribution_evidence_tree import build_attribution_evidence_tree

    _seed_aet_paper(session)
    initial_tree = build_attribution_evidence_tree(session, "AET1")
    evidence = session.get(PaperEvidence, "ev_method")
    evidence.extra = {
        "attribution_evidence": {
            "confidence": 0.8,
            "confidnce": 0.8,
        }
    }
    evidence.score = 0.25
    session.flush()

    updated_tree = build_attribution_evidence_tree(session, "AET1")
    method = next(
        path
        for path in updated_tree.evidence_paths
        if path.evidence_type == "sdl_methodology"
    )

    assert updated_tree.generation_id != initial_tree.generation_id
    assert {path.path_id for path in updated_tree.evidence_paths}.isdisjoint(
        path.path_id for path in initial_tree.evidence_paths
    )
    assert method.confidence is None
    assert method.metadata_status == "invalid_fallback"


def test_tree_generation_changes_when_classifier_signals_change(session):
    from app.models import PaperClassification
    from app.services.attribution_evidence_tree import build_attribution_evidence_tree

    _seed_aet_paper(session)
    session.add(
        PaperClassification(
            id="cls_aet1",
            paper_id="AET1",
            label="RELATED_RELEVANT",
            confidence=0.7,
            topic_score=0.4,
        )
    )
    session.flush()
    initial_tree = build_attribution_evidence_tree(session, "AET1")

    session.get(PaperClassification, "cls_aet1").topic_score = 0.9
    session.flush()
    updated_tree = build_attribution_evidence_tree(session, "AET1")

    assert updated_tree.generation_id != initial_tree.generation_id


def test_aet_endpoint_is_default_off(session, monkeypatch):
    from app.config import settings
    from app.main import app

    _seed_aet_paper(session)
    session.commit()
    monkeypatch.setattr(settings, "attribution_evidence_tree_enabled", False)

    response = TestClient(app).get("/papers/AET1/attribution-evidence-tree")

    assert response.status_code == 404
    assert response.json()["detail"] == "Attribution evidence tree is disabled"


def test_aet_endpoint_returns_tree_when_enabled(session, monkeypatch):
    from app.config import settings
    from app.main import app

    _seed_aet_paper(session)
    session.commit()
    monkeypatch.setattr(settings, "attribution_evidence_tree_enabled", True)
    client = TestClient(app)

    response = client.get("/papers/AET1/attribution-evidence-tree")

    assert response.status_code == 200, response.text
    assert response.json()["paper_id"] == "AET1"
    assert len(response.json()["evidence_paths"]) == 3
    assert client.get("/papers/NOPE/attribution-evidence-tree").status_code == 404
