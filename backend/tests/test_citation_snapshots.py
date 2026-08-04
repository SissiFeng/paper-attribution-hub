from __future__ import annotations

from datetime import UTC, datetime

from app.models import Paper
from app.services.citation_snapshot_service import (
    citation_snapshot_from_raw,
    refresh_openalex_citation_snapshots,
)


def test_extracts_supported_external_citation_counts():
    updated = datetime(2026, 8, 2, tzinfo=UTC)

    openalex = citation_snapshot_from_raw(
        {"raw": {"cited_by_count": 17}},
        source="openalex",
        updated_at=updated,
    )
    semantic_scholar = citation_snapshot_from_raw(
        {"raw": {"citationCount": "9"}},
        source="semantic_scholar",
        updated_at=updated,
    )

    assert openalex is not None and openalex.count == 17
    assert semantic_scholar is not None and semantic_scholar.count == 9
    assert openalex.updated_at == updated
    assert citation_snapshot_from_raw(
        {"raw": {"cited_by_count": -1}}, source="openalex"
    ) is None


def test_refresh_openalex_snapshots_persists_source_and_time(session):
    paper = Paper(
        id="citation-refresh",
        title="Citation refresh",
        doi="10.1000/citation-refresh",
    )
    session.add(paper)
    session.commit()

    class FakeOpenAlex:
        def work_by_doi(self, _session, doi):
            assert doi == paper.doi
            return {"id": "https://openalex.org/W1", "cited_by_count": 23}

        def work_by_id(self, _session, _work_id):
            raise AssertionError("DOI should take precedence")

    result = refresh_openalex_citation_snapshots(
        session,
        client=FakeOpenAlex(),
    )
    refreshed = session.get(Paper, paper.id)

    assert result["snapshots_updated"] == 1
    assert refreshed.citation_count == 23
    assert refreshed.citation_count_source == "openalex"
    assert refreshed.citation_count_updated_at is not None
