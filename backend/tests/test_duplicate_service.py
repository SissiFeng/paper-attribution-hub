from __future__ import annotations

from app.models import Paper, PaperClassification
from app.services.duplicate_service import build_duplicate_groups


def test_duplicate_group_suggests_published_record_over_preprint(session):
    preprint = Paper(
        id="p_preprint",
        title="Shared title",
        doi="10.48550/arxiv.1234",
        year=2024,
        provenance="ac_gold",
        ac_known_publication=True,
    )
    published = Paper(
        id="p_published",
        title="Shared title",
        doi="10.1038/example",
        year=2025,
        provenance="ac_gold",
        ac_known_publication=True,
    )
    preprint.classification = PaperClassification(
        id="cls_preprint", paper_id="p_preprint", label="RELATED_RELEVANT", confidence=0.7
    )
    published.classification = PaperClassification(
        id="cls_published", paper_id="p_published", label="RELATED_RELEVANT", confidence=0.8
    )
    session.add_all([preprint, published])
    session.commit()

    groups = build_duplicate_groups(session)

    assert len(groups) == 1
    assert groups[0].group_type == "preprint_published_version"
    assert groups[0].severity == "warning"
    assert groups[0].canonical_paper_id == "p_published"


def test_duplicate_group_blocks_unclear_conflicting_metadata(session):
    a = Paper(id="p_a", title="Same title", doi="10.1000/a", provenance="scopus_batch")
    b = Paper(id="p_b", title="Same title", doi="10.1000/b", provenance="scopus_batch")
    session.add_all([a, b])
    session.commit()

    groups = build_duplicate_groups(session)

    assert len(groups) == 1
    assert groups[0].group_type == "conflicting_metadata"
    assert groups[0].severity == "blocker"
