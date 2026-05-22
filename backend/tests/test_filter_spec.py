from sqlalchemy import select

from app.models import Paper
from app.services.filter_spec import PaperFilter, apply_filter


def _ids(session, filt: PaperFilter) -> list[str]:
    stmt = apply_filter(select(Paper.id), filt)
    return [pid for (pid,) in session.execute(stmt).all()]


def test_empty_filter_returns_all(fulltext_seeded_session):
    from app.services.relevance_classifier import classify_all

    classify_all(fulltext_seeded_session)
    ids = _ids(fulltext_seeded_session, PaperFilter())
    assert set(ids) >= {"P001", "P003", "P011"}


def test_year_range_filter(fulltext_seeded_session):
    from app.services.relevance_classifier import classify_all

    classify_all(fulltext_seeded_session)
    ids = _ids(fulltext_seeded_session, PaperFilter(year_from=2024, year_to=2024))
    # P002, P003, P004, P006, P008, P009 are 2024 in our sample data.
    assert ids and all(pid not in {"P010", "P001"} for pid in ids)


def test_label_filter(fulltext_seeded_session):
    from app.services.relevance_classifier import classify_all

    classify_all(fulltext_seeded_session)
    ids = _ids(fulltext_seeded_session, PaperFilter(labels=["CORE_RELEVANT"]))
    assert ids
    assert all(pid in {"P001", "P002", "P004", "P006", "P009"} for pid in ids)


def test_partner_only_filter(fulltext_seeded_session):
    from app.services.relevance_classifier import classify_all

    classify_all(fulltext_seeded_session)
    ids = _ids(fulltext_seeded_session, PaperFilter(partner_only=True))
    # Climate paper P010 (Univ of Oslo) should be excluded; P007 (Tokyo/KAIST) too.
    assert "P010" not in ids
    assert "P007" not in ids


def test_ac_author_only_filter(fulltext_seeded_session):
    from app.services.relevance_classifier import classify_all

    classify_all(fulltext_seeded_session)
    ids = _ids(fulltext_seeded_session, PaperFilter(ac_author_only=True))
    assert "P011" not in ids  # no direct AC author
    assert "P001" in ids


def test_min_confidence_filter(fulltext_seeded_session):
    from app.services.relevance_classifier import classify_all

    classify_all(fulltext_seeded_session)
    ids = _ids(fulltext_seeded_session, PaperFilter(min_confidence=0.8))
    assert "P010" not in ids


def test_search_filter(fulltext_seeded_session):
    from app.services.relevance_classifier import classify_all

    classify_all(fulltext_seeded_session)
    ids = _ids(fulltext_seeded_session, PaperFilter(search="self-driving"))
    assert "P001" in ids or "P006" in ids


def test_combined_filter(fulltext_seeded_session):
    from app.services.relevance_classifier import classify_all

    classify_all(fulltext_seeded_session)
    ids = _ids(
        fulltext_seeded_session,
        PaperFilter(
            labels=["CORE_RELEVANT", "RELATED_RELEVANT"],
            partner_only=True,
            year_from=2023,
        ),
    )
    assert ids
    assert "P010" not in ids
