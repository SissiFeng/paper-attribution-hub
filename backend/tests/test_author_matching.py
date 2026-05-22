from sqlalchemy import select

from app.models import Author
from app.services.author_matcher import AuthorMatcher


def test_exact_match(seeded_session):
    authors = list(seeded_session.execute(select(Author)).scalars())
    matcher = AuthorMatcher(authors)
    m = matcher.match("Alan Aspuru-Guzik")
    assert m is not None
    assert m.match_type == "exact_author_match"
    assert m.is_ac_member is True


def test_alias_match_with_diacritics(seeded_session):
    authors = list(seeded_session.execute(select(Author)).scalars())
    matcher = AuthorMatcher(authors)
    m = matcher.match("Alán Aspuru Guzik")
    assert m is not None
    assert m.match_type in {"exact_author_match", "alias_match"}


def test_last_first_form(seeded_session):
    authors = list(seeded_session.execute(select(Author)).scalars())
    matcher = AuthorMatcher(authors)
    m = matcher.match("Aspuru-Guzik, Alan")
    assert m is not None
    assert m.is_ac_member is True


def test_initials_match(seeded_session):
    authors = list(seeded_session.execute(select(Author)).scalars())
    matcher = AuthorMatcher(authors)
    # v0.7: without corroboration, an initials-only match is marked
    # `initials_match_unverified`. Pass coauthors/affiliation to verify.
    m = matcher.match(
        "A. Aspuru-Guzik",
        affiliations=["University of Toronto"],
    )
    assert m is not None
    assert m.match_type in {
        "alias_match",
        "initials_match",
        "fuzzy_match",
        "initials_match_unverified",
        "fuzzy_match_unverified",
    }


def test_no_match_for_unrelated(seeded_session):
    authors = list(seeded_session.execute(select(Author)).scalars())
    matcher = AuthorMatcher(authors)
    assert matcher.match("Henrik Olsson") is None
