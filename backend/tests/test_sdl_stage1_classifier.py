from __future__ import annotations

from sqlalchemy import select

from app.config import settings
from app.models import Author, Institution, Paper, Topic
from app.services.author_matcher import AuthorMatcher
from app.services.graph_service import GraphSignals
from app.services.institution_matcher import InstitutionMatcher
from app.services.relevance_classifier import _classify_paper
from app.services.topic_classifier import TopicClassifier


def test_stage1_classifier_zeros_ac_identity_and_graph_signals(
    seeded_session,
    monkeypatch,
):
    monkeypatch.setattr(settings, "sdl_stage1_only", True)
    paper = seeded_session.get(Paper, "P001")
    result = _classify_paper(
        paper,
        AuthorMatcher(list(seeded_session.scalars(select(Author)))),
        InstitutionMatcher(
            list(seeded_session.scalars(select(Institution)))
        ),
        TopicClassifier(list(seeded_session.scalars(select(Topic)))),
        graph_signals=GraphSignals(
            paper_id=paper.id,
            network_score=1.0,
            citation_score=1.0,
        ),
        use_attribution_evidence=True,
    )

    assert result.author_score == 0.0
    assert result.institution_score == 0.0
    assert result.network_score == 0.0
    assert result.citation_score == 0.0
    assert result.matched_people == []
    assert result.matched_institutions == []
    assert result.graph_signals is None
    assert result.attribution_evidence is None
    assert result.aet_applied is False
