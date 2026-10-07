from __future__ import annotations

import httpx
from sqlalchemy import select

from app.models import Paper, PaperEntity
from app.services.external.ror_client import RorClient
from app.services.institution_resolution_service import (
    resolve_institution_entities_with_ror,
)


def _ror_item(
    *,
    canonical_name: str,
    ror_id: str,
) -> dict:
    return {
        "chosen": True,
        "score": 1.0,
        "matching_type": "SINGLE SEARCH",
        "organization": {
            "id": f"https://ror.org/{ror_id}",
            "names": [
                {
                    "lang": "en",
                    "types": ["ror_display", "label"],
                    "value": canonical_name,
                }
            ],
        },
    }


def test_ror_resolution_canonicalizes_merges_and_rejects_incompatible_matches(
    session,
):
    paper = Paper(id="ror-paper", title="ROR resolution")
    session.add(paper)
    session.flush()
    session.add_all(
        [
            PaperEntity(
                id="ror-candidate-prefixed",
                paper_id=paper.id,
                entity_type="institution",
                name="Davis Colorado State University",
                normalized_name="Davis Colorado State University",
                confidence=0.8,
                extractor="frontmatter_affiliation_v2",
            ),
            PaperEntity(
                id="ror-candidate-canonical",
                paper_id=paper.id,
                entity_type="institution",
                name="Colorado State University",
                normalized_name="Colorado State University",
                confidence=0.8,
                extractor="frontmatter_affiliation_v2",
            ),
            PaperEntity(
                id="ror-candidate-wrong",
                paper_id=paper.id,
                entity_type="institution",
                name="Chinese Academy of Sci",
                normalized_name="Chinese Academy of Sci",
                confidence=0.8,
                extractor="frontmatter_affiliation_v2",
            ),
        ]
    )
    session.commit()

    def handler(request: httpx.Request) -> httpx.Response:
        candidate = request.url.params["affiliation"]
        if candidate == "Chinese Academy of Sci":
            item = _ror_item(
                canonical_name="Academia Sinica",
                ror_id="05bxb3784",
            )
        else:
            item = _ror_item(
                canonical_name="Colorado State University",
                ror_id="03k1gpj17",
            )
        return httpx.Response(200, json={"items": [item]})

    client = RorClient(transport=httpx.MockTransport(handler))
    try:
        summary = resolve_institution_entities_with_ror(
            session,
            client=client,
        )
        session.commit()
    finally:
        client.close()

    assert summary == {
        "candidates": 3,
        "matched": 1,
        "rejected": 1,
        "duplicates_merged": 1,
        "papers_with_resolved_institutions": 1,
        "unique_institutions": 1,
    }
    rows = list(
        session.execute(
            select(PaperEntity).where(
                PaperEntity.entity_type == "institution"
            )
        ).scalars()
    )
    assert len(rows) == 1
    assert rows[0].normalized_name == "Colorado State University"
    assert rows[0].extractor == "ror_affiliation_v2:03k1gpj17"
    assert rows[0].confidence == 0.98
