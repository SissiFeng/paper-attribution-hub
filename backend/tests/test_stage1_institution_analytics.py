from __future__ import annotations

from tests.admin_client import AdminTestClient as TestClient

from app.config import settings
from app.main import app
from app.models import Paper, PaperEntity
from app.services.filter_spec import PaperFilter
from app.services.stage1_institution_analytics import (
    build_institution_comparison,
)


def _institution(
    paper_id: str,
    name: str,
    *,
    suffix: str,
) -> PaperEntity:
    return PaperEntity(
        id=f"inst_{suffix}",
        paper_id=paper_id,
        entity_type="institution",
        name=name,
        normalized_name=name,
        confidence=0.95,
        extractor="frontmatter_affiliation_v1",
        section="unknown",
    )


def test_institution_comparison_counts_distinct_papers_and_cooccurrence(session):
    papers = [
        Paper(
            id="P_INST_1",
            title="One",
            year=2024,
            full_text_available=True,
        ),
        Paper(
            id="P_INST_2",
            title="Two",
            year=2024,
            full_text_available=True,
        ),
        Paper(
            id="P_INST_3",
            title="Three",
            year=2025,
            full_text_available=True,
        ),
    ]
    session.add_all(papers)
    session.flush()
    session.add_all(
        [
            _institution(
                "P_INST_1",
                "University of Toronto",
                suffix="uoft_1",
            ),
            _institution(
                "P_INST_1",
                "University of Oxford",
                suffix="oxford_1",
            ),
            _institution(
                "P_INST_2",
                "University of Toronto",
                suffix="uoft_2",
            ),
            _institution(
                "P_INST_3",
                "Stanford University",
                suffix="stanford_3",
            ),
        ]
    )
    session.commit()

    result = build_institution_comparison(
        session,
        PaperFilter(),
        focus="uoft",
    )

    assert result["scope"]["corpus_papers"] == 3
    assert result["scope"]["fulltext_papers"] == 3
    assert result["scope"]["papers_with_affiliations"] == 3
    assert result["focus"]["name"] == "University of Toronto"
    assert result["focus"]["paper_count"] == 2
    assert result["focus"]["coaffiliated_papers"] == 1
    oxford = next(
        row
        for row in result["institutions"]
        if row["name"] == "University of Oxford"
    )
    assert oxford["paper_count"] == 1
    assert oxford["shared_papers_with_focus"] == 1
    assert result["audit"]["classification_used"] is False
    assert result["audit"]["ac_member_seed_used"] is False


def test_stage1_institution_api_requires_complete_explicit_preview(
    seeded_session,
    monkeypatch,
):
    monkeypatch.setattr(settings, "sdl_stage1_only", True)
    monkeypatch.setattr(
        settings,
        "sdl_stage1_descriptive_analytics_enabled",
        True,
    )
    monkeypatch.setattr(
        settings,
        "sdl_stage1_derived_views_enabled",
        False,
    )
    client = TestClient(app)

    assert client.get("/analytics/institution-comparison").status_code == 409

    for paper in seeded_session.query(Paper).all():
        paper.full_text_available = True
    seeded_session.commit()

    readiness = client.get("/stage1/readiness").json()
    response = client.get("/analytics/institution-comparison")

    assert readiness["phase"] == "analysis_preview"
    assert readiness["descriptive_analytics_enabled"] is True
    assert readiness["derived_views_enabled"] is False
    assert response.status_code == 200
    assert response.json()["scope"]["corpus_papers"] > 0
    growth = client.get("/analytics/network-growth").json()
    assert growth["yearly"]
    assert growth["cumulative"][-1]["papers"] > 0
