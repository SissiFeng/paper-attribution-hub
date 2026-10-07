from __future__ import annotations

import json
from pathlib import Path

import pytest
from tests.admin_client import AdminTestClient as TestClient
from sqlalchemy import func, select


def _seed_paper(
    session,
    *,
    paper_id: str = "SKILL-P1",
    ac_known_publication: bool = False,
    ac_acknowledged: bool | None = None,
    member_match_confidence: float | None = 1.0,
    conflicting_evidence: bool = False,
    agreement_status: str = "single_model",
    include_funding: bool = True,
):
    from app.models import (
        Author,
        Paper,
        PaperAuthor,
        PaperClassification,
        PaperEvidence,
    )

    paper = Paper(
        id=paper_id,
        title="Closed-loop materials discovery",
        abstract="A robotic platform selects experiments with Bayesian optimization.",
        year=2024,
        ac_known_publication=ac_known_publication,
        ac_acknowledged=ac_acknowledged,
        ac_members_matched=["Ada Lovelace"],
    )
    author = Author(
        id=f"author-{paper_id}",
        canonical_name="Ada Lovelace",
        normalized_name="ada lovelace",
        orcid="0000-0001-0000-0001",
        is_ac_member=True,
    )
    paper.authors.append(
        PaperAuthor(
            author=author,
            author_order=0,
            affiliation_text="Acceleration Consortium",
            match_confidence=member_match_confidence,
        )
    )
    paper.classification = PaperClassification(
        id=f"classification-{paper_id}",
        paper_id=paper_id,
        label="CORE_RELEVANT",
        confidence=0.88,
        author_score=0.95,
        institution_score=0.8,
        topic_score=0.9,
        model_agreement_status=agreement_status,
        ac_attribution_label="CORE_AC",
    )
    session.add(paper)
    if include_funding:
        session.add(
            PaperEvidence(
                id=f"funding-{paper_id}",
                paper_id=paper_id,
                evidence_type="funding_acknowledgement",
                evidence_source="acknowledgements",
                evidence_text="Supported by the Acceleration Consortium.",
                score=0.9,
                extra={
                    "attribution_evidence": {
                        "contract_version": "aet-evidence-meta-v0.1",
                        "centrality": "core_contribution",
                        "confidence": 0.95,
                        "detector_type": "curated_rule",
                    }
                },
            )
        )
    if conflicting_evidence:
        session.add(
            PaperEvidence(
                id=f"negative-{paper_id}",
                paper_id=paper_id,
                evidence_type="disqualifying",
                evidence_source="human_screen",
                evidence_text="The apparent AC relationship is a name collision.",
                score=-0.9,
                extra={"centrality": "core_contribution"},
            )
        )
    session.commit()
    return paper


def _client() -> TestClient:
    from app.main import app

    return TestClient(app)


def _payload(
    skill_name: str,
    *,
    invocation_id: str,
    paper_id: str = "SKILL-P1",
    reason: str = "Run the auditable attribution workflow.",
) -> dict:
    return {
        "invocation_id": invocation_id,
        "skill_name": skill_name,
        "paper_id": paper_id,
        "invocation_reason": reason,
    }


def test_catalog_exposes_only_the_five_read_skills(session):
    response = _client().get("/api/v1/attribution-skills")

    assert response.status_code == 200
    assert response.json()["read_skills"] == [
        "determine_ac_paper_attribution",
        "resolve_ambiguous_author_identity",
        "verify_membership_at_publication_time",
        "collect_auditable_attribution_evidence",
        "adjudicate_classifier_disagreement",
    ]
    assert response.json()["network_update_skill_included"] is False


@pytest.mark.parametrize(
    ("skill_name", "expected_status"),
    [
        ("determine_ac_paper_attribution", "succeeded"),
        ("resolve_ambiguous_author_identity", "succeeded"),
        ("verify_membership_at_publication_time", "review_required"),
        ("collect_auditable_attribution_evidence", "succeeded"),
        ("adjudicate_classifier_disagreement", "succeeded"),
    ],
)
def test_dispatcher_invokes_every_read_skill(
    session, skill_name: str, expected_status: str
):
    _seed_paper(session, ac_known_publication=True)

    response = _client().post(
        "/api/v1/attribution-skills/invoke",
        json=_payload(skill_name, invocation_id=f"invoke-{skill_name}"),
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["skill_name"] == skill_name
    assert body["status"] == expected_status
    assert (
        body["skill_outcome"]["outcome_type"]
        == {
            "determine_ac_paper_attribution": "attribution_determination",
            "resolve_ambiguous_author_identity": "author_identity_resolution",
            "verify_membership_at_publication_time": "membership_verification",
            "collect_auditable_attribution_evidence": "evidence_collection",
            "adjudicate_classifier_disagreement": "classifier_disagreement",
        }[skill_name]
    )
    assert body["input_snapshot_id"] == body["output_packet"]["paper_snapshot_id"]
    assert len(body["input_content_hash"]) == 64
    assert body["cost"]["retrieval_api_calls"] == 0
    assert body["cost"]["model_calls"] == 0


def test_determine_uses_gold_attribution_as_human_confirmed_authority(session):
    _seed_paper(session, ac_known_publication=True, conflicting_evidence=True)

    response = _client().post(
        "/api/v1/attribution-skills/invoke",
        json=_payload(
            "determine_ac_paper_attribution",
            invocation_id="invoke-gold",
        ),
    )

    assert response.status_code == 200, response.text
    decision = response.json()["output_packet"]["decision"]
    assert decision["decision"] == "ATTRIBUTED"
    assert decision["authority"] == "human_confirmed"
    assert decision["relevance_label"] == "CORE_RELEVANT"
    assert decision["supporting_evidence_ids"]
    assert decision["contradicting_evidence_ids"]
    assert decision["unresolved_ambiguities"]


def test_attribution_and_relevance_remain_independent_at_runtime(session):
    paper = _seed_paper(
        session,
        ac_acknowledged=True,
        include_funding=False,
    )
    paper.classification.label = "EXCLUDE"
    paper.classification.confidence = 0.99
    session.commit()

    response = _client().post(
        "/api/v1/attribution-skills/invoke",
        json=_payload(
            "determine_ac_paper_attribution",
            invocation_id="invoke-independent-axes",
        ),
    )

    assert response.status_code == 200, response.text
    decision = response.json()["output_packet"]["decision"]
    assert decision["decision"] == "ATTRIBUTED"
    assert decision["relevance_label"] == "EXCLUDE"
    assert decision["contradicting_evidence_ids"] == []


def test_current_membership_without_dates_fails_closed_to_review(session):
    _seed_paper(session)

    response = _client().post(
        "/api/v1/attribution-skills/invoke",
        json=_payload(
            "verify_membership_at_publication_time",
            invocation_id="invoke-membership-unknown",
        ),
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "review_required"
    assert body["output_packet"]["decision"]["decision"] == "REVIEW_REQUIRED"
    membership = [
        item
        for item in body["output_packet"]["evidence"]
        if item["evidence_type"] in {"ac_member_match", "ac_author"}
    ]
    assert membership
    assert all(item["temporal_validity"]["status"] == "unknown" for item in membership)


def test_dated_membership_can_be_verified_for_publication_year(session):
    from app.models import PaperEvidence

    _seed_paper(session)
    session.add(
        PaperEvidence(
            id="membership-valid",
            paper_id="SKILL-P1",
            evidence_type="membership",
            evidence_source="membership_registry",
            evidence_text="Ada Lovelace was an AC member.",
            score=1.0,
            extra={
                "temporal_validity": {
                    "status": "valid",
                    "valid_from": "2023-01-01",
                    "valid_to": "2025-12-31",
                    "basis": "Curated membership registry interval",
                }
            },
        )
    )
    session.commit()

    response = _client().post(
        "/api/v1/attribution-skills/invoke",
        json=_payload(
            "verify_membership_at_publication_time",
            invocation_id="invoke-membership-valid",
        ),
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "succeeded"
    assert body["output_packet"]["decision"]["decision"] == "ATTRIBUTED"
    assert body["output_packet"]["decision"]["authority"] == "machine_provisional"


def test_low_confidence_ac_author_match_routes_identity_to_review(session):
    _seed_paper(session, member_match_confidence=0.55)

    response = _client().post(
        "/api/v1/attribution-skills/invoke",
        json=_payload(
            "resolve_ambiguous_author_identity",
            invocation_id="invoke-ambiguous-author",
        ),
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "review_required"
    assert any(
        "match confidence" in ambiguity
        for ambiguity in body["output_packet"]["decision"]["unresolved_ambiguities"]
    )


def test_disagreement_preserves_both_polarities_and_routes_review(session):
    _seed_paper(
        session,
        conflicting_evidence=True,
        agreement_status="needs_ac_evidence_review",
    )

    response = _client().post(
        "/api/v1/attribution-skills/invoke",
        json=_payload(
            "adjudicate_classifier_disagreement",
            invocation_id="invoke-disagreement",
        ),
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "review_required"
    evidence = body["output_packet"]["evidence"]
    assert {item["polarity"] for item in evidence} == {
        "supporting",
        "contradicting",
    }
    decision = body["output_packet"]["decision"]
    assert decision["supporting_evidence_ids"]
    assert decision["contradicting_evidence_ids"]


def test_invocation_nonce_replays_same_request_and_rejects_changed_request(session):
    from app.models import AttributionSkillInvocationRecord

    _seed_paper(session, ac_known_publication=True)
    client = _client()
    payload = _payload(
        "collect_auditable_attribution_evidence",
        invocation_id="stable-nonce",
    )

    first = client.post("/api/v1/attribution-skills/invoke", json=payload)
    replay = client.post("/api/v1/attribution-skills/invoke", json=payload)
    conflict = client.post(
        "/api/v1/attribution-skills/invoke",
        json={**payload, "invocation_reason": "A different operation."},
    )
    fetched = client.get("/api/v1/attribution-skills/invocations/stable-nonce")

    assert first.status_code == replay.status_code == fetched.status_code == 200
    assert replay.json() == first.json() == fetched.json()
    assert conflict.status_code == 409
    assert (
        session.scalar(
            select(func.count()).select_from(AttributionSkillInvocationRecord)
        )
        == 1
    )
    record = session.get(AttributionSkillInvocationRecord, "stable-nonce")
    assert record is not None
    assert record.input_snapshot["paper"]["id"] == "SKILL-P1"
    assert record.input_snapshot["evidence_tree"]["evidence_paths"]
    assert record.retrieval_api_calls == record.model_calls == 0
    assert record.fulltext_retrieval_status == "not_requested"
    assert record.failure_category is None
    assert record.resolution_path[-1] == "persist_replay_record"


def test_wall_budget_exhaustion_persists_no_decision(session):
    from app.attribution_skill_contract import AttributionInvocationBudget
    from app.services.attribution_skill_service import (
        AttributionSkillInvokeRequest,
        invoke_attribution_skill,
    )

    _seed_paper(session, ac_known_publication=True)
    times = iter([10.0, 11.0])
    result = invoke_attribution_skill(
        session,
        AttributionSkillInvokeRequest(
            invocation_id="invoke-budget",
            skill_name="determine_ac_paper_attribution",
            paper_id="SKILL-P1",
            invocation_reason="Verify the wall-clock budget guard.",
            budget=AttributionInvocationBudget(max_wall_seconds=0.1),
        ),
        monotonic=lambda: next(times),
    )

    assert result.status == "budget_exhausted"
    assert result.failure is not None
    assert result.failure.category == "budget_exhausted"
    assert result.output_packet is None


def test_missing_paper_is_404_and_does_not_create_invocation(session):
    from app.models import AttributionSkillInvocationRecord

    response = _client().post(
        "/api/v1/attribution-skills/invoke",
        json=_payload(
            "collect_auditable_attribution_evidence",
            invocation_id="invoke-missing",
            paper_id="DOES-NOT-EXIST",
        ),
    )

    assert response.status_code == 404
    assert session.get(AttributionSkillInvocationRecord, "invoke-missing") is None


def test_invoke_requires_api_key_when_configured(session, monkeypatch):
    from app.config import settings

    _seed_paper(session)
    monkeypatch.setattr(settings, "api_key", "secret")
    payload = _payload(
        "collect_auditable_attribution_evidence",
        invocation_id="invoke-auth",
    )

    rejected = _client().post("/api/v1/attribution-skills/invoke", json=payload)
    accepted = _client().post(
        "/api/v1/attribution-skills/invoke",
        json=payload,
        headers={"X-API-Key": "secret"},
    )
    replay_rejected = _client().get(
        "/api/v1/attribution-skills/invocations/invoke-auth"
    )
    replay_accepted = _client().get(
        "/api/v1/attribution-skills/invocations/invoke-auth",
        headers={"X-API-Key": "secret"},
    )

    assert rejected.status_code == 401
    assert accepted.status_code == 200
    assert replay_rejected.status_code == 401
    assert replay_accepted.status_code == 200


def test_invoke_rejects_caller_supplied_unknown_policy_version(session):
    _seed_paper(session)
    payload = _payload(
        "collect_auditable_attribution_evidence",
        invocation_id="invoke-unknown-policy",
    )
    payload["policy_version"] = "caller-invented-policy"

    response = _client().post(
        "/api/v1/attribution-skills/invoke",
        json=payload,
    )

    assert response.status_code == 422


def test_invoke_rejects_nonce_that_cannot_be_replayed_in_url(session):
    _seed_paper(session)

    response = _client().post(
        "/api/v1/attribution-skills/invoke",
        json=_payload(
            "collect_auditable_attribution_evidence",
            invocation_id="not/replayable",
        ),
    )

    assert response.status_code == 422


def test_evidence_packet_binds_source_record_chunk_pages_and_hash(session):
    from app.models import PaperChunk, PaperEvidence, PaperSection

    _seed_paper(session, include_funding=False)
    section = PaperSection(
        id="skill-ack-section",
        paper_id="SKILL-P1",
        section_type="acknowledgements",
        section_title="Acknowledgements",
        content="Supported by the Acceleration Consortium.",
        page_start=11,
        page_end=11,
        order_index=0,
    )
    session.add(section)
    session.add(
        PaperChunk(
            id="skill-ack-chunk",
            paper_id="SKILL-P1",
            section_id=section.id,
            section_type=section.section_type,
            chunk_text=section.content,
        )
    )
    session.add(
        PaperEvidence(
            id="skill-span-evidence",
            paper_id="SKILL-P1",
            chunk_id="skill-ack-chunk",
            evidence_type="funding_acknowledgement",
            evidence_source="grobid_acknowledgements",
            evidence_text=section.content,
            score=0.9,
        )
    )
    session.commit()

    response = _client().post(
        "/api/v1/attribution-skills/invoke",
        json=_payload(
            "collect_auditable_attribution_evidence",
            invocation_id="invoke-span-lineage",
        ),
    )

    assert response.status_code == 200, response.text
    item = next(
        evidence
        for evidence in response.json()["output_packet"]["evidence"]
        if evidence["provenance"]["source_record_id"] == "skill-span-evidence"
    )
    assert item["source_chunk_id"] == "skill-ack-chunk"
    assert item["page_start"] == item["page_end"] == 11
    assert item["quote"] == section.content
    assert len(item["provenance"]["content_hash"]) == 64


def test_runtime_error_is_persisted_and_replayed_as_failed(session, monkeypatch):
    import app.services.attribution_skill_service as skill_service

    _seed_paper(session)

    def fail_handler(_context):
        raise RuntimeError("synthetic handler failure")

    monkeypatch.setitem(
        skill_service._HANDLERS,
        "collect_auditable_attribution_evidence",
        fail_handler,
    )
    request = skill_service.AttributionSkillInvokeRequest(
        invocation_id="invoke-runtime-failure",
        skill_name="collect_auditable_attribution_evidence",
        paper_id="SKILL-P1",
        invocation_reason="Exercise fail-closed runtime persistence.",
    )

    failed = skill_service.invoke_attribution_skill(session, request)
    session.commit()
    replay = skill_service.get_recorded_attribution_invocation(
        session, request.invocation_id
    )

    assert failed.status == replay.status == "failed"
    assert failed.failure is not None
    assert failed.failure.stage == "system"
    assert failed.failure.category == "internal_error"
    assert "synthetic handler failure" not in (failed.failure.detail or "")
    assert failed.output_packet is None
    record = session.get(
        skill_service.AttributionSkillInvocationRecord,
        request.invocation_id,
    )
    assert record is not None
    assert record.failure_category == "internal_error"
    assert record.input_snapshot["paper"]["id"] == "SKILL-P1"
    assert record.input_snapshot["evidence_tree"]["evidence_paths"]


def test_service_leaves_commit_to_unit_of_work(session):
    from app.db import SessionLocal
    from app.models import AttributionSkillInvocationRecord
    from app.services.attribution_skill_service import (
        AttributionSkillInvokeRequest,
        invoke_attribution_skill,
    )

    _seed_paper(session)
    request = AttributionSkillInvokeRequest(
        invocation_id="invoke-unit-of-work",
        skill_name="collect_auditable_attribution_evidence",
        paper_id="SKILL-P1",
        invocation_reason="Verify service transaction ownership.",
    )

    invoke_attribution_skill(session, request)
    with SessionLocal() as independent:
        assert (
            independent.get(
                AttributionSkillInvocationRecord,
                request.invocation_id,
            )
            is None
        )

    session.commit()
    with SessionLocal() as independent:
        assert (
            independent.get(
                AttributionSkillInvocationRecord,
                request.invocation_id,
            )
            is not None
        )


def test_service_rejects_session_with_unrelated_pending_mutation(session):
    from app.models import Paper
    from app.services.attribution_skill_service import (
        AttributionSkillInvokeRequest,
        AttributionSkillSessionError,
        invoke_attribution_skill,
    )

    _seed_paper(session)
    paper = session.get(Paper, "SKILL-P1")
    assert paper is not None and paper.classification is not None
    paper.classification.label = "EXCLUDE"

    with pytest.raises(AttributionSkillSessionError, match="clean"):
        invoke_attribution_skill(
            session,
            AttributionSkillInvokeRequest(
                invocation_id="invoke-dirty-session",
                skill_name="collect_auditable_attribution_evidence",
                paper_id="SKILL-P1",
                invocation_reason="Must not commit unrelated state.",
            ),
        )

    session.rollback()
    session.expire_all()
    paper = session.get(Paper, "SKILL-P1")
    assert paper is not None and paper.classification is not None
    assert paper.classification.label == "CORE_RELEVANT"


def test_read_skill_does_not_mutate_classification_or_network(session):
    from app.models import Paper, PaperLabLink

    _seed_paper(session, ac_known_publication=True)
    paper = session.get(Paper, "SKILL-P1")
    assert paper is not None and paper.classification is not None
    before = {
        "label": paper.classification.label,
        "confidence": paper.classification.confidence,
        "agreement": paper.classification.model_agreement_status,
        "known": paper.ac_known_publication,
    }

    response = _client().post(
        "/api/v1/attribution-skills/invoke",
        json=_payload(
            "determine_ac_paper_attribution",
            invocation_id="invoke-read-only",
        ),
    )

    assert response.status_code == 200, response.text
    session.expire_all()
    paper = session.get(Paper, "SKILL-P1")
    assert paper is not None and paper.classification is not None
    assert {
        "label": paper.classification.label,
        "confidence": paper.classification.confidence,
        "agreement": paper.classification.model_agreement_status,
        "known": paper.ac_known_publication,
    } == before
    assert list(session.scalars(select(PaperLabLink))) == []


def test_malformed_membership_dates_route_to_review_instead_of_failure(session):
    from app.models import PaperEvidence

    _seed_paper(session)
    session.add(
        PaperEvidence(
            id="membership-malformed",
            paper_id="SKILL-P1",
            evidence_type="membership",
            evidence_source="membership_registry",
            evidence_text="Malformed dated membership record.",
            score=1.0,
            extra={
                "temporal_validity": {
                    "status": "valid",
                    "valid_from": "not-a-date",
                    "valid_to": "2025-12-31",
                }
            },
        )
    )
    session.commit()

    response = _client().post(
        "/api/v1/attribution-skills/invoke",
        json=_payload(
            "verify_membership_at_publication_time",
            invocation_id="invoke-membership-malformed",
        ),
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "review_required"
    malformed = next(
        item
        for item in body["output_packet"]["evidence"]
        if item["provenance"]["source_record_id"] == "membership-malformed"
    )
    assert malformed["temporal_validity"]["status"] == "unknown"


def test_unknown_classifier_agreement_status_fails_closed_to_review(session):
    _seed_paper(
        session,
        agreement_status="new_unrecognized_disagreement_state",
    )

    response = _client().post(
        "/api/v1/attribution-skills/invoke",
        json=_payload(
            "adjudicate_classifier_disagreement",
            invocation_id="invoke-unknown-agreement",
        ),
    )

    assert response.status_code == 200, response.text
    assert response.json()["status"] == "review_required"


def test_replay_dispatch_rejects_unknown_stored_contract(session):
    from app.models import AttributionSkillInvocationRecord
    from app.services.attribution_skill_service import (
        UnsupportedStoredContractError,
        get_recorded_attribution_invocation,
    )

    _seed_paper(session)
    response = _client().post(
        "/api/v1/attribution-skills/invoke",
        json=_payload(
            "collect_auditable_attribution_evidence",
            invocation_id="invoke-future-contract",
        ),
    )
    assert response.status_code == 200
    record = session.get(
        AttributionSkillInvocationRecord,
        "invoke-future-contract",
    )
    assert record is not None
    record.invocation_json = {
        **record.invocation_json,
        "contract_version": "future-contract",
    }
    session.commit()

    with pytest.raises(UnsupportedStoredContractError):
        get_recorded_attribution_invocation(
            session,
            "invoke-future-contract",
        )


def test_starter_eval_set_covers_hard_negatives_counterfactuals_and_transfer(
    session,
):
    from app.models import Paper, PaperClassification, PaperEvidence

    fixture_path = (
        Path(__file__).parent / "fixtures" / "attribution_skill_eval_gold.json"
    )
    cases = json.loads(fixture_path.read_text())
    assert {
        "authoritative_positive",
        "hard_negative",
        "counterfactual",
        "cross_domain_transfer",
    } <= {case["family"] for case in cases}

    actual: list[tuple[dict, str, str]] = []
    for case in cases:
        paper = Paper(
            id=case["paper_id"],
            title=case["title"],
            abstract=case["abstract"],
            year=case.get("year"),
            ac_known_publication=case.get("ac_known_publication", False),
            ac_acknowledged=case.get("ac_acknowledged"),
        )
        classification = case.get("classification")
        if classification:
            paper.classification = PaperClassification(
                id=f"classification-{case['paper_id']}",
                paper_id=case["paper_id"],
                label=classification["label"],
                confidence=classification["confidence"],
                author_score=classification.get("author_score", 0.0),
                institution_score=classification.get("institution_score", 0.0),
                topic_score=classification.get("topic_score", 0.0),
                network_score=classification.get("network_score", 0.0),
                citation_score=classification.get("citation_score", 0.0),
                graph_signals=classification.get("graph_signals"),
                matched_topics=classification.get("matched_topics"),
                model_agreement_status=classification.get(
                    "model_agreement_status", "single_model"
                ),
            )
        session.add(paper)
        for index, evidence in enumerate(case.get("evidence", [])):
            session.add(
                PaperEvidence(
                    id=f"{case['paper_id']}-evidence-{index}",
                    paper_id=case["paper_id"],
                    evidence_type=evidence["evidence_type"],
                    evidence_source=evidence["evidence_source"],
                    evidence_text=evidence["evidence_text"],
                    score=evidence["score"],
                    extra=evidence.get("extra"),
                )
            )
        session.commit()

        response = _client().post(
            "/api/v1/attribution-skills/invoke",
            json=_payload(
                "determine_ac_paper_attribution",
                invocation_id=f"eval-{case['paper_id']}",
                paper_id=case["paper_id"],
                reason=f"Starter eval case {case['case_id']}.",
            ),
        )
        assert response.status_code == 200, response.text
        body = response.json()
        actual.append(
            (
                case,
                body["status"],
                body["output_packet"]["decision"]["decision"],
            )
        )

    agreement = sum(
        status == case["expected_status"] and decision == case["expected_decision"]
        for case, status, decision in actual
    ) / len(actual)
    positive_cases = [row for row in actual if row[0]["truth"] == "ATTRIBUTED"]
    positive_recall = sum(
        decision == "ATTRIBUTED" for _, _, decision in positive_cases
    ) / len(positive_cases)
    negative_cases = [row for row in actual if row[0]["truth"] == "NOT_ATTRIBUTED"]
    false_positive_rate = sum(
        decision == "ATTRIBUTED" for _, _, decision in negative_cases
    ) / len(negative_cases)
    review_rate = sum(decision == "REVIEW_REQUIRED" for _, _, decision in actual) / len(
        actual
    )

    assert agreement == 1.0
    assert positive_recall == 1.0
    assert false_positive_rate == 0.0
    assert 0.0 < review_rate < 1.0
