from __future__ import annotations

import json


def _seed_and_invoke(
    session, *, paper_id: str, gold: bool, include_evidence: bool = True
):
    from app.models import Paper, PaperEvidence
    from app.services.attribution_skill_service import (
        AttributionSkillInvokeRequest,
        invoke_attribution_skill,
    )

    paper = Paper(
        id=paper_id,
        title=f"Evidence bundle paper {paper_id}",
        abstract="A closed-loop experimental platform.",
        year=2024,
        ac_known_publication=gold,
    )
    session.add(paper)
    if include_evidence:
        session.add(
            PaperEvidence(
                id=f"evidence-{paper_id}",
                paper_id=paper_id,
                evidence_type="funding_acknowledgement",
                evidence_source="acknowledgements",
                evidence_text="Supported by the Acceleration Consortium.",
                score=0.9,
                extra={"centrality": "core_contribution"},
            )
        )
    session.commit()
    invocation = invoke_attribution_skill(
        session,
        AttributionSkillInvokeRequest(
            invocation_id=f"invoke-{paper_id}",
            skill_name="determine_ac_paper_attribution",
            paper_id=paper_id,
            invocation_reason="Build a deterministic evidence bundle.",
        ),
    )
    session.commit()
    return invocation


def test_bundle_is_nested_validated_and_repeatable(session, tmp_path):
    from app.services.evidence_wiki_bundle import (
        export_evidence_wiki_bundle,
        validate_evidence_wiki_bundle,
    )

    _seed_and_invoke(session, paper_id="BUNDLE-P1", gold=True)
    review = _seed_and_invoke(
        session,
        paper_id="BUNDLE-P2",
        gold=False,
        include_evidence=False,
    )
    assert review.status == "review_required"

    output = tmp_path / "evidence-bundle"
    first = export_evidence_wiki_bundle(session, output)
    session.commit()
    first_manifest_text = (output / "manifest.json").read_text(encoding="utf-8")

    assert first["schema_version"] == "pas-evidence-wiki-bundle-v0.1"
    assert first["counts"]["pages"] == 2
    assert first["counts"]["decisions"] == {
        "ATTRIBUTED": 1,
        "REVIEW_REQUIRED": 1,
    }
    assert (output / "papers" / "index.md").is_file()
    assert (output / "indexes" / "by-decision.md").is_file()
    assert (output / "indexes" / "by-status.md").is_file()
    assert (output / "indexes" / "by-evidence-provider.md").is_file()
    assert "../papers/" in (output / "indexes" / "by-decision.md").read_text(
        encoding="utf-8"
    )
    assert "../papers/" not in (output / "papers" / "index.md").read_text(
        encoding="utf-8"
    )
    report = validate_evidence_wiki_bundle(output)
    assert report["status"] == "passed"
    assert report["issues"] == []
    assert json.loads(
        (output / "validation-report.json").read_text(encoding="utf-8")
    )["status"] == "passed"

    second = export_evidence_wiki_bundle(session, output)
    session.commit()
    second_manifest_text = (output / "manifest.json").read_text(encoding="utf-8")
    assert second["bundle_content_hash"] == first["bundle_content_hash"]
    assert second_manifest_text == first_manifest_text


def test_validator_detects_tampering_and_unsafe_paths(session, tmp_path):
    from app.services.evidence_wiki_bundle import (
        export_evidence_wiki_bundle,
        validate_evidence_wiki_bundle,
    )

    _seed_and_invoke(session, paper_id="BUNDLE-TAMPER", gold=True)
    output = tmp_path / "evidence-bundle"
    manifest = export_evidence_wiki_bundle(session, output)
    page_path = output / manifest["pages"][0]["path"]
    page_path.write_text(
        page_path.read_text(encoding="utf-8") + "\nforged\n",
        encoding="utf-8",
    )

    report = validate_evidence_wiki_bundle(output)
    assert report["status"] == "failed"
    assert {issue["check"] for issue in report["issues"]} >= {"page_checksum"}

    manifest_path = output / "manifest.json"
    stored = json.loads(manifest_path.read_text(encoding="utf-8"))
    stored["pages"][0]["path"] = "../outside.md"
    manifest_path.write_text(json.dumps(stored), encoding="utf-8")

    unsafe = validate_evidence_wiki_bundle(output)
    assert unsafe["status"] == "failed"
    assert {issue["check"] for issue in unsafe["issues"]} >= {"page_path_safe"}
