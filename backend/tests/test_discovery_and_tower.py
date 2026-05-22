"""v0.7 discovery: AND-tower auto-eligibility, noisy-OR confidence."""
from app.adapters.base import PaperRecord
from app.services.discovery_service import (
    CandidateEnvelope,
    DiscoveryTrigger,
    _score_envelope,
)


def _envelope(triggers, raw=None):
    env = CandidateEnvelope(
        external_id="x",
        record=PaperRecord(
            paper_id="p", title="t", abstract=None, authors=[], affiliations=[],
            raw=raw or {},
        ),
        triggers=triggers,
    )
    return env


def test_s2_only_never_auto():
    env = _envelope(
        [DiscoveryTrigger(strategy="s2_recommend", source="s2", detail="x")]
    )
    auto, conf = _score_envelope(env, ac_orcid_map={})
    assert auto is False
    assert conf > 0  # but it still gets a tiny confidence


def test_single_cite_below_threshold_not_auto():
    env = _envelope(
        [DiscoveryTrigger(strategy="cite_of_core", source="oa", detail="x")]
    )
    auto, conf = _score_envelope(env, ac_orcid_map={})
    assert auto is False
    assert 0 < conf < 0.7


def test_orcid_match_alone_is_auto():
    env = _envelope(
        [DiscoveryTrigger(strategy="cite_of_core", source="oa", detail="x")],
        raw={
            "raw": {
                "authorships": [
                    {
                        "author": {
                            "orcid": "https://orcid.org/0000-0003-1024-3325"
                        }
                    }
                ]
            }
        },
    )
    auto, conf = _score_envelope(
        env, ac_orcid_map={"0000-0003-1024-3325": "A001"}
    )
    assert auto is True
    assert conf >= 0.9


def test_coauthor_and_cite_together_auto():
    env = _envelope(
        [
            DiscoveryTrigger(strategy="cite_of_core", source="oa", detail="x"),
            DiscoveryTrigger(strategy="ac_coauthor", source="oa", detail="x"),
        ]
    )
    auto, conf = _score_envelope(env, ac_orcid_map={})
    assert auto is True


def test_noisy_or_above_max():
    """Two weak signals fuse to above either-alone."""
    env = _envelope(
        [
            DiscoveryTrigger(strategy="cite_of_core", source="oa", detail="x"),
            DiscoveryTrigger(strategy="s2_recommend", source="s2", detail="x"),
        ]
    )
    _, conf_both = _score_envelope(env, ac_orcid_map={})

    env_one = _envelope(
        [DiscoveryTrigger(strategy="cite_of_core", source="oa", detail="x")]
    )
    _, conf_cite = _score_envelope(env_one, ac_orcid_map={})

    assert conf_both > conf_cite
