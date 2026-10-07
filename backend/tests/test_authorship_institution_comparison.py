from __future__ import annotations

from datetime import UTC, datetime

from app.models import (
    Author,
    Institution,
    MetadataEnrichmentRun,
    Paper,
    PaperAuthorshipMetadata,
)
from app.services.authorship_institution_comparison import (
    InstitutionMetadataFilter,
    build_authorship_institution_comparison,
)


UOFT = {
    "institution_id": "inst_uoft",
    "display_name": "University of Toronto",
    "ror": "https://ror.org/03dbr7087",
    "openalex_id": "https://openalex.org/I185261750",
    "country_code": "CA",
    "lineage": ["https://openalex.org/I185261750"],
    "source": "openalex",
    "confidence": 0.98,
    "resolved": True,
}
OXFORD = {
    "institution_id": "inst_oxford",
    "display_name": "University of Oxford",
    "ror": "https://ror.org/052gg0110",
    "openalex_id": "https://openalex.org/I40120149",
    "country_code": "GB",
    "lineage": ["https://openalex.org/I40120149"],
    "source": "openalex",
    "confidence": 0.98,
    "resolved": True,
}


def _seed(session) -> None:
    session.add_all(
        [
            Institution(
                id="inst_uoft",
                canonical_name="University of Toronto",
                aliases=[],
                normalized_aliases=["university of toronto"],
                country="CA",
                raw_metadata={},
            ),
            Institution(
                id="inst_oxford",
                canonical_name="University of Oxford",
                aliases=[],
                normalized_aliases=["university of oxford"],
                country="GB",
                raw_metadata={},
            ),
            Paper(id="p1", title="Three authors", doi="10.test/p1", year=2024),
            Paper(id="p2", title="Multi affiliation", doi="10.test/p2", year=2025),
        ]
    )
    for index, name in enumerate(["First A", "Middle B", "Last C", "Solo D"]):
        session.add(
            Author(
                id=f"a{index}",
                canonical_name=name,
                aliases=[],
                normalized_name=name.casefold(),
                raw_metadata={},
            )
        )
    session.flush()
    rows = [
        ("p1", "a0", 0, "first", [UOFT]),
        ("p1", "a1", 1, "middle", [OXFORD]),
        ("p1", "a2", 2, "last", [UOFT]),
        ("p2", "a3", 0, "first", [UOFT, OXFORD]),
    ]
    for paper_id, author_id, order, position, affiliations in rows:
        session.add(
            PaperAuthorshipMetadata(
                paper_id=paper_id,
                author_id=author_id,
                author_order=order,
                author_position=position,
                is_corresponding=author_id in {"a1", "a3"},
                affiliations=affiliations,
                sources=["openalex"],
                source_record_ids=[paper_id],
                quality_flags=[],
                provenance_hash=f"hash-{paper_id}-{author_id}",
            )
        )
    session.commit()


def test_lead_balanced_fractional_comparison(session):
    _seed(session)

    result = build_authorship_institution_comparison(
        session,
        InstitutionMetadataFilter(),
        credit_scheme="lead_balanced",
        affiliation_allocation="fractional",
    )

    assert result["available"] is True
    assert result["scope"]["corpus_papers"] == 2
    assert result["scope"]["selected_authorships"] == 4
    assert result["scope"]["affiliation_credit_coverage"] == 1.0
    assert result["focus"]["weighted_credit"] == 1.2
    assert result["focus"]["share_of_resolved_credit"] == 0.6
    assert result["focus"]["rank"] == 1
    assert result["comparison"]["other_institutions_weighted_credit"] == 0.8
    assert result["audit"]["projection"]["credit_scheme"] == "lead_balanced"
    assert result["audit"]["filter_fingerprint"]
    assert result["audit"]["paper_set_sha256"]


def test_last_author_filter_keeps_original_position_credit(session):
    _seed(session)

    result = build_authorship_institution_comparison(
        session,
        InstitutionMetadataFilter(),
        credit_scheme="lead_balanced",
        author_role="last",
        affiliation_allocation="fractional",
    )

    assert result["scope"]["selected_authorships"] == 2
    assert result["scope"]["selected_author_credit"] == 1.35
    assert result["focus"]["weighted_credit"] == 0.85
    assert result["comparison"]["other_institutions_weighted_credit"] == 0.5


def test_first_and_corresponding_author_filters_are_independent(session):
    _seed(session)

    first = build_authorship_institution_comparison(
        session,
        InstitutionMetadataFilter(search="Three authors"),
        credit_scheme="full_counting",
        author_role="first",
        affiliation_allocation="fractional",
    )
    corresponding = build_authorship_institution_comparison(
        session,
        InstitutionMetadataFilter(search="Three authors"),
        credit_scheme="full_counting",
        author_role="corresponding",
        affiliation_allocation="fractional",
    )

    assert first["scope"]["selected_authorships"] == 1
    assert first["focus"]["weighted_credit"] == 1.0
    assert first["comparison"]["other_institutions_weighted_credit"] == 0.0
    assert first["configuration"]["author_role_label"] == "First author only"

    assert corresponding["scope"]["selected_authorships"] == 1
    assert corresponding["focus"]["weighted_credit"] == 0.0
    assert corresponding["comparison"]["other_institutions_weighted_credit"] == 1.0
    assert (
        corresponding["configuration"]["author_role_label"]
        == "Corresponding author only"
    )


def test_paper_counts_use_any_affiliated_author_not_selected_credit_role(session):
    _seed(session)

    result = build_authorship_institution_comparison(
        session,
        InstitutionMetadataFilter(),
        credit_scheme="lead_heavy",
        author_role="last",
        affiliation_allocation="full",
    )

    oxford = next(row for row in result["institutions"] if row["id"] == "inst_oxford")
    assert result["focus"]["paper_count"] == 2
    assert result["comparison"]["other_institutions_paper_count"] == 2
    assert oxford["paper_count"] == 2
    assert result["yearly"] == [
        {
            "year": 2024,
            "corpus_papers": 1,
            "focus_papers": 1,
            "other_institution_papers": 1,
            "focus_weighted_credit": 0.4,
            "other_weighted_credit": 0.0,
        },
        {
            "year": 2025,
            "corpus_papers": 1,
            "focus_papers": 1,
            "other_institution_papers": 1,
            "focus_weighted_credit": 1.0,
            "other_weighted_credit": 1.0,
        },
    ]


def test_report_exposes_paper_level_institution_membership_gaps(session):
    _seed(session)
    run_sha = "paper-gap-test"
    session.add(
        MetadataEnrichmentRun(
            id="meta-paper-gap-test",
            agent_version="test",
            status="succeeded",
            input_path="test.csv",
            input_sha256=run_sha,
            configuration={},
            summary={},
            errors=[],
            started_at=datetime(2025, 1, 1, tzinfo=UTC),
            completed_at=datetime(2025, 1, 1, tzinfo=UTC),
        )
    )
    for paper_id in ("p1", "p2"):
        paper = session.get(Paper, paper_id)
        assert paper is not None
        paper.raw_metadata = {"tier1_metadata_agent": {"input_sha256": run_sha}}
    middle = session.get(
        PaperAuthorshipMetadata,
        {"paper_id": "p1", "author_id": "a1"},
    )
    assert middle is not None
    middle.affiliations = []
    session.add(
        Paper(
            id="p3",
            title="No authorship metadata",
            year=2025,
            raw_metadata={"tier1_metadata_agent": {"input_sha256": run_sha}},
        )
    )
    session.commit()

    result = build_authorship_institution_comparison(
        session,
        InstitutionMetadataFilter(),
    )

    assert result["scope"]["corpus_papers"] == 3
    assert result["scope"]["papers_with_complete_institution_membership"] == 1
    assert result["scope"]["papers_with_incomplete_institution_membership"] == 1
    assert result["scope"]["papers_without_authorship_metadata"] == 1
    assert result["scope"]["paper_institution_membership_coverage"] == 0.333333


def test_fulltext_state_cannot_change_metadata_comparison(session):
    _seed(session)

    before = build_authorship_institution_comparison(
        session,
        InstitutionMetadataFilter(),
    )
    paper = session.get(Paper, "p1")
    assert paper is not None
    paper.full_text_available = True
    paper.pdf_path = "s3://fulltext-raw/p1.md"
    session.commit()

    after = build_authorship_institution_comparison(
        session,
        InstitutionMetadataFilter(),
    )

    assert after["scope"] == before["scope"]
    assert after["focus"] == before["focus"]
    assert after["comparison"] == before["comparison"]
    assert after["institutions"] == before["institutions"]
    assert after["audit"]["paper_set_sha256"] == before["audit"]["paper_set_sha256"]
    assert after["audit"]["data_boundary"]["mode"] == "metadata_only"
    assert "fulltext_papers" not in after["audit"]
    assert "classified_papers" not in after["audit"]
    assert "reviewed_papers" not in after["audit"]
    assert "corpus_source_breakdown" not in after["audit"]
