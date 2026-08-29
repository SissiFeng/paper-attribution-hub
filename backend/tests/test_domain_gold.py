from __future__ import annotations


def _protocol():
    from app.domain_adaptation.models import (
        EvidenceSpan,
        InstrumentUse,
        MaterialInput,
        ProtocolUnit,
    )

    quote = "The ink used 10 mg catalyst and was tested with a potentiostat."
    evidence = EvidenceSpan(
        evidence_id="ev-1",
        paper_id="paper-1",
        chunk_id="methods-1",
        quote=quote,
        char_start=20,
        char_end=20 + len(quote),
        source_sha256="a" * 64,
    )
    return ProtocolUnit(
        protocol_id="protocol-1",
        paper_id="paper-1",
        protocol_name="Ink testing",
        protocol_type="electrochemical_testing",
        source_chunk_ids=["methods-1"],
        materials=[
            MaterialInput(
                entity_id="material-1",
                name="catalyst",
                amount="10 mg",
                evidence_ids=["ev-1"],
            )
        ],
        instruments=[
            InstrumentUse(
                entity_id="instrument-1",
                name="potentiostat",
                evidence_ids=["ev-1"],
            )
        ],
        evidence=[evidence],
    )


def test_gold_queue_is_pending_and_preserves_evidence():
    from app.domain_adaptation.gold import build_gold_annotation_queue

    protocol_queue, entity_queue = build_gold_annotation_queue([_protocol()])

    assert len(protocol_queue) == 1
    assert protocol_queue[0].review_status == "pending"
    assert protocol_queue[0].annotation_complete is False
    assert {item.field_name for item in entity_queue} == {
        "amount",
        "name",
    }
    assert all(item.review_status == "pending" for item in entity_queue)
    assert all(item.evidence_quote for item in entity_queue)
    assert all(item.char_start == 20 for item in entity_queue)


def test_gold_score_uses_only_complete_reviewed_protocols():
    from app.domain_adaptation.gold import (
        GoldEntityAnnotation,
        GoldProtocolAnnotation,
        build_candidate_claims,
        score_gold_entities,
    )

    protocol = _protocol()
    candidates = build_candidate_claims([protocol])
    reviewed_protocols = [
        GoldProtocolAnnotation(
            gold_protocol_id="gold-protocol-1",
            paper_id="paper-1",
            protocol_id="protocol-1",
            review_status="reviewed",
            annotation_complete=True,
        ),
        GoldProtocolAnnotation(
            gold_protocol_id="gold-protocol-pending",
            paper_id="paper-2",
            protocol_id="protocol-pending",
            review_status="pending",
            annotation_complete=False,
        ),
    ]
    quote = protocol.evidence[0].quote
    gold_entities = [
        GoldEntityAnnotation(
            gold_entity_id="gold-material-name",
            paper_id="paper-1",
            protocol_id="protocol-1",
            entity_type="material",
            field_name="name",
            source_value="catalyst",
            evidence_chunk_id="methods-1",
            evidence_quote=quote,
            char_start=20,
            char_end=20 + len(quote),
            review_status="reviewed",
        ),
        GoldEntityAnnotation(
            gold_entity_id="gold-material-amount",
            paper_id="paper-1",
            protocol_id="protocol-1",
            entity_type="material",
            field_name="amount",
            source_value="10mg",
            evidence_chunk_id="methods-1",
            evidence_quote=quote,
            char_start=20,
            char_end=20 + len(quote),
            review_status="reviewed",
        ),
        GoldEntityAnnotation(
            gold_entity_id="gold-software-name",
            paper_id="paper-1",
            protocol_id="protocol-1",
            entity_type="software",
            field_name="name",
            source_value="EC-Lab",
            evidence_chunk_id="methods-1",
            evidence_quote="Data were processed using EC-Lab.",
            char_start=100,
            char_end=133,
            review_status="reviewed",
        ),
        GoldEntityAnnotation(
            gold_entity_id="ignored-pending-row",
            paper_id="paper-2",
            protocol_id="protocol-pending",
            entity_type="material",
            field_name="name",
            source_value="ignored",
            evidence_chunk_id="methods-1",
            evidence_quote="ignored",
            char_start=0,
            char_end=7,
            review_status="pending",
        ),
    ]

    report = score_gold_entities(
        gold_protocols=reviewed_protocols,
        gold_entities=gold_entities,
        candidate_claims=candidates,
    )

    assert report.reviewed_protocol_count == 1
    assert report.candidate_count == 3
    assert report.gold_count == 3
    assert report.true_positive_count == 2
    assert report.precision == 0.666667
    assert report.recall == 0.666667
    assert report.span_alignment_rate == 1.0
    assert report.by_entity_type["material"].precision == 1.0
    assert report.by_entity_type["software"].recall == 0.0


def test_gold_score_rejects_pending_rows_inside_complete_scope():
    import pytest

    from app.domain_adaptation.gold import (
        GoldEntityAnnotation,
        GoldProtocolAnnotation,
        score_gold_entities,
    )

    with pytest.raises(ValueError, match="pending gold entity"):
        score_gold_entities(
            gold_protocols=[
                GoldProtocolAnnotation(
                    gold_protocol_id="gold-protocol-1",
                    paper_id="paper-1",
                    protocol_id="protocol-1",
                    review_status="reviewed",
                    annotation_complete=True,
                )
            ],
            gold_entities=[
                GoldEntityAnnotation(
                    gold_entity_id="pending",
                    paper_id="paper-1",
                    protocol_id="protocol-1",
                    entity_type="material",
                    field_name="name",
                    source_value="catalyst",
                    evidence_chunk_id="methods-1",
                    evidence_quote="catalyst",
                    char_start=0,
                    char_end=8,
                    review_status="pending",
                )
            ],
            candidate_claims=[],
        )


def test_prepare_gold_set_writes_review_files_without_overwriting(tmp_path):
    import json

    import pytest

    from app.scripts.prepare_domain_gold_set import prepare_gold_set

    package_dir = tmp_path / "package"
    protocol_path = package_dir / "knowledge/protocols.jsonl"
    protocol_path.parent.mkdir(parents=True)
    protocol_path.write_text(_protocol().model_dump_json() + "\n")

    counts = prepare_gold_set(package_dir)

    assert counts == {
        "candidate_claim_count": 3,
        "evidence_dependency_annotation_count": 3,
        "gold_entity_queue_count": 3,
        "gold_protocol_queue_count": 1,
        "review_batch_candidate_claim_count": 3,
        "review_batch_protocol_count": 1,
    }
    assert len(
        (package_dir / "gold/candidate_claims.jsonl").read_text().splitlines()
    ) == 3
    assert len(
        (package_dir / "gold/evidence_dependencies.jsonl").read_text().splitlines()
    ) == 3
    protocol_row = json.loads(
        (package_dir / "gold/gold_protocols.jsonl")
        .read_text()
        .splitlines()[0]
    )
    assert protocol_row["review_status"] == "pending"
    entity_schema = json.loads(
        (package_dir / "gold/schemas/gold_entities.schema.json").read_text()
    )
    assert entity_schema["title"] == "GoldEntityAnnotation"
    assert "evidence_quote" in entity_schema["properties"]
    review_batch = json.loads(
        (package_dir / "gold/review_batch_001.json").read_text()
    )
    assert review_batch["protocol_ids"] == ["protocol-1"]
    assert review_batch["candidate_claim_count"] == 3
    with pytest.raises(FileExistsError, match="Refusing to overwrite"):
        prepare_gold_set(package_dir)


def test_evaluate_gold_set_writes_machine_readable_report(tmp_path):
    import json

    import pytest

    from app.scripts.evaluate_domain_gold_set import evaluate_gold_set
    from app.scripts.prepare_domain_gold_set import prepare_gold_set

    package_dir = tmp_path / "package"
    protocol_path = package_dir / "knowledge/protocols.jsonl"
    protocol_path.parent.mkdir(parents=True)
    protocol_path.write_text(_protocol().model_dump_json() + "\n")
    prepare_gold_set(package_dir)

    gold_protocol_path = package_dir / "gold/gold_protocols.jsonl"
    protocol_rows = [
        json.loads(line) for line in gold_protocol_path.read_text().splitlines()
    ]
    protocol_rows[0]["review_status"] = "reviewed"
    protocol_rows[0]["annotation_complete"] = True
    gold_protocol_path.write_text(
        "".join(json.dumps(row) + "\n" for row in protocol_rows)
    )
    gold_entity_path = package_dir / "gold/gold_entities.jsonl"
    entity_rows = [
        json.loads(line) for line in gold_entity_path.read_text().splitlines()
    ]
    for row in entity_rows:
        row["review_status"] = "reviewed"
    gold_entity_path.write_text(
        "".join(json.dumps(row) + "\n" for row in entity_rows)
    )

    with pytest.raises(ValueError, match="pending evidence dependency"):
        evaluate_gold_set(package_dir)

    dependency_path = package_dir / "gold/evidence_dependencies.jsonl"
    dependency_rows = [
        json.loads(line) for line in dependency_path.read_text().splitlines()
    ]
    for row in dependency_rows:
        row["review_status"] = "reviewed"
        row["reviewed_labels"] = row["proposed_labels"]
        row["reviewer"] = "reviewer-1"
    dependency_path.write_text(
        "".join(json.dumps(row) + "\n" for row in dependency_rows)
    )

    report = evaluate_gold_set(package_dir)

    assert report.precision == 1.0
    assert report.recall == 1.0
    saved = json.loads(
        (package_dir / "reports/gold_score.json").read_text()
    )
    assert saved["reviewed_protocol_count"] == 1
    assert saved["span_alignment_rate"] == 1.0
    dependency_summary = json.loads(
        (package_dir / "reports/evidence_dependency_summary.json").read_text()
    )
    assert dependency_summary["reviewed_count"] == 3
