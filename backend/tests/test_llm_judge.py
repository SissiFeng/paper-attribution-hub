"""v0.7 LLM judge: parse_judge_response + StubJudge behavior."""
from app.services.llm_judge import (
    AnthropicJudge,
    JudgeVerdict,
    StubJudge,
    get_judge,
    parse_judge_response,
)


def test_parse_judge_response_strict_json():
    text = '{"label":"EXCLUDE","confidence":0.92,"reasons":["A"],"disqualifying_evidence":["B"]}'
    v = parse_judge_response(text)
    assert v is not None
    assert v.label == "EXCLUDE"
    assert v.confidence == 0.92
    assert v.reasons == ["A"]
    assert v.disqualifying_evidence == ["B"]


def test_parse_judge_response_fenced_json():
    text = "Sure!\n```json\n{\"label\":\"CORE_RELEVANT\",\"confidence\":0.8,\"reasons\":[\"r\"],\"disqualifying_evidence\":[]}\n```"
    v = parse_judge_response(text)
    assert v is not None
    assert v.label == "CORE_RELEVANT"


def test_parse_judge_invalid_label_returns_none():
    text = '{"label":"NOT_A_LABEL","confidence":0.5}'
    assert parse_judge_response(text) is None


def test_stub_excludes_on_explicit_negation():
    judge = StubJudge()
    v = judge.adjudicate(
        title="Surrogate models",
        abstract="No autonomous platform is described in this work.",
        matched_topics=[],
        evidence=[],
        current_label="UNCERTAIN",
        current_confidence=0.5,
    )
    assert v.label == "EXCLUDE"
    assert v.disqualifying_evidence


def test_stub_promotes_when_funding_evidence_present():
    judge = StubJudge()
    v = judge.adjudicate(
        title="x",
        abstract="An ML paper.",
        matched_topics=[],
        evidence=[{"type": "funding_acknowledgement", "snippet": "AC funded"}],
        current_label="UNCERTAIN",
        current_confidence=0.4,
    )
    assert v.label == "RELATED_RELEVANT"
    assert v.confidence >= 0.6


def test_stub_demotes_when_no_strong_signal():
    judge = StubJudge()
    v = judge.adjudicate(
        title="x",
        abstract="A general ML method paper.",
        matched_topics=[],
        evidence=[],
        current_label="UNCERTAIN",
        current_confidence=0.5,
    )
    assert v.label == "ADJACENT"


def test_get_judge_default_is_stub(monkeypatch):
    monkeypatch.delenv("PAS_LLM_JUDGE_BACKEND", raising=False)
    judge = get_judge()
    assert isinstance(judge, StubJudge)


def test_get_judge_anthropic_without_key_falls_back(monkeypatch):
    monkeypatch.setenv("PAS_LLM_JUDGE_BACKEND", "anthropic")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    judge = get_judge()
    # Without an API key, factory falls back to the stub.
    assert isinstance(judge, StubJudge)
