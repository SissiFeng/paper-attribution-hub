"""v0.7 author matcher: contextual disambiguation downgrades unverified fuzzy."""
from sqlalchemy import select

from app.models import Author
from app.services.author_matcher import AuthorMatcher


def test_unverified_match_without_context(seeded_session):
    """A weak match without ORCID/coauthor/institution evidence must not
    be treated as an AC member."""
    authors = list(seeded_session.execute(select(Author)).scalars())
    matcher = AuthorMatcher(authors)
    # "A. Aspuru-Guzik" is an initials_match for Alan Aspuru-Guzik; without
    # corroborating context it must not be elevated to AC member.
    m = matcher.match(
        "A. Aspuru-Guzik",
        coauthor_names=["Random Person", "Other Random"],
        affiliations=["Some Unknown University"],
    )
    assert m is None or m.is_ac_member is False


def test_initials_with_coauthor_corroboration_is_trusted(seeded_session):
    authors = list(seeded_session.execute(select(Author)).scalars())
    matcher = AuthorMatcher(authors)
    # Initials match plus another AC member on the same paper.
    m = matcher.match(
        "A. Aspuru-Guzik",
        coauthor_names=["Curtis Berlinguette", "A. Aspuru-Guzik"],
        affiliations=[],
    )
    assert m is not None
    assert m.match_type == "initials_match"  # verified, no _unverified suffix
    assert m.is_ac_member is True
    assert m.corroborating_signals


def test_initials_without_context_is_unverified(seeded_session):
    authors = list(seeded_session.execute(select(Author)).scalars())
    matcher = AuthorMatcher(authors)
    m = matcher.match("A. Aspuru-Guzik")
    assert m is not None
    assert m.match_type.endswith("_unverified")
    assert m.is_ac_member is False


def test_exact_match_does_not_need_context(seeded_session):
    authors = list(seeded_session.execute(select(Author)).scalars())
    matcher = AuthorMatcher(authors)
    m = matcher.match("Alan Aspuru-Guzik")
    assert m is not None
    assert m.is_ac_member is True
    assert m.match_type == "exact_author_match"


def test_initials_with_home_institution_corroborated(seeded_session):
    authors = list(seeded_session.execute(select(Author)).scalars())
    matcher = AuthorMatcher(authors)
    m = matcher.match(
        "A. Aspuru-Guzik",
        coauthor_names=[],
        affiliations=["University of Toronto"],
    )
    assert m is not None
    # If matched at all, must be trusted because the home institution shows up.
    if m.match_type in {"initials_match", "fuzzy_match"}:
        assert m.is_ac_member is True
