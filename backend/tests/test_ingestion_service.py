from __future__ import annotations

from collections.abc import Iterable

from sqlalchemy import select

from app.adapters.base import (
    InstitutionRecord,
    PaperRecord,
    PaperSource,
    PersonRecord,
    TopicRecord,
)
from app.models import PaperAuthor
from app.services.ingestion_service import ingest_all


class DuplicateAuthorSource(PaperSource):
    def papers(self) -> Iterable[PaperRecord]:
        yield PaperRecord(
            paper_id="P_DUP_AUTHOR",
            title="Duplicate author source row",
            authors=["Jane Doe", "Jane Doe"],
            affiliations=["University of Toronto", "University of Toronto"],
        )

    def people(self) -> Iterable[PersonRecord]:
        return []

    def institutions(self) -> Iterable[InstitutionRecord]:
        yield InstitutionRecord(
            canonical_name="University of Toronto",
            aliases=["UofT"],
            is_partner=True,
        )

    def topics(self) -> Iterable[TopicRecord]:
        return []


def test_ingest_all_deduplicates_same_author_on_one_paper(session):
    ingest_all(session, DuplicateAuthorSource())

    links = session.execute(
        select(PaperAuthor).where(PaperAuthor.paper_id == "P_DUP_AUTHOR")
    ).scalars().all()

    assert len(links) == 1
