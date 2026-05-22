from app.services.external.author_disambiguator import disambiguate


def test_orcid_match_wins(seeded_session):
    match = disambiguate(
        seeded_session,
        name="Some other surface form",
        orcid="0000-0003-1024-3325",
    )
    assert match is not None
    assert match.method == "orcid"
    assert match.canonical_name == "Alan Aspuru-Guzik"
    assert match.confidence == 1.0


def test_name_institution_match(seeded_session):
    match = disambiguate(
        seeded_session,
        name="Alan Aspuru-Guzik",
        institution="University of Toronto",
    )
    assert match is not None
    # ORCID isn't passed in, so we expect the institution-based path.
    assert match.method == "name_institution"


def test_no_match_for_unrelated_author(seeded_session):
    match = disambiguate(seeded_session, name="Henrik Olsson")
    assert match is None
