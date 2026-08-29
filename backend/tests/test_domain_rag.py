from __future__ import annotations


def _rag_fixture():
    from app.domain_adaptation.chunking import build_scientific_chunks
    from app.domain_adaptation.models import (
        EvidenceSpan,
        InstrumentUse,
        MaterialInput,
        ProtocolUnit,
        ScientificChunk,
        SourceChunk,
        SourcePaper,
    )

    text = (
        "For catalyst ink preparation, 10 mg of NiFe catalyst was dispersed "
        "in 1 mL of ethanol and sonicated for 30 min. The OER activity was "
        "measured using a BioLogic VSP-300 workstation at 10 mV s-1."
    )
    paper = SourcePaper(
        paper_id="DOI:10.1000_rag",
        title="Evidence-grounded OER protocol",
        selection_tier="primary_oer",
        selection_reasons=["RAG regression fixture"],
        source_bucket="test-bucket",
        source_prefix="raw/test/",
        chunks=[
            SourceChunk(
                chunk_id="methods-1",
                section_type="experimental",
                section_title="Catalyst ink preparation",
                section_path=["Experimental", "Catalyst ink preparation"],
                text=text,
                document_char_start=100,
                document_char_end=100 + len(text),
            )
        ],
    )
    scientific_chunks: list[ScientificChunk] = build_scientific_chunks(paper)
    scientific_chunk_id = scientific_chunks[0].scientific_chunk_id
    evidence = EvidenceSpan(
        evidence_id="ev-rag-1",
        paper_id=paper.paper_id,
        chunk_id="methods-1",
        quote=text,
        char_start=0,
        char_end=len(text),
        source_sha256=scientific_chunks[0].segments[0].source_sha256,
        document_char_start=100,
        document_char_end=100 + len(text),
    )
    protocol = ProtocolUnit(
        protocol_id="protocol-rag-1",
        paper_id=paper.paper_id,
        protocol_name="catalyst ink preparation",
        protocol_type="electrode_preparation",
        source_paper_tier="primary_oer",
        evidence_scope="primary_report",
        source_chunk_ids=["methods-1"],
        scientific_chunk_ids=[scientific_chunk_id],
        materials=[
            MaterialInput(
                entity_id="material-rag-1",
                name="NiFe catalyst",
                amount="10 mg",
                evidence_ids=[evidence.evidence_id],
            )
        ],
        instruments=[
            InstrumentUse(
                entity_id="instrument-rag-1",
                name="electrochemical workstation",
                model="BioLogic VSP-300",
                evidence_ids=[evidence.evidence_id],
            )
        ],
        evidence=[evidence],
    )
    return paper, scientific_chunks, [protocol]


def test_rag_candidate_answers_remain_separate_from_human_gold():
    from app.domain_adaptation.rag import build_rag_review_queue

    _paper, chunks, protocols = _rag_fixture()
    candidates, gold = build_rag_review_queue(protocols, chunks, limit=10)

    assert {item.question.question_type for item in candidates} == {
        "instrument_lookup",
        "material_lookup",
    }
    assert all(item.proposed_answer_items for item in candidates)
    assert all(item.review_status == "pending" for item in gold)
    assert all(item.accepted_answer_items == [] for item in gold)
    assert all(item.accepted_evidence_ids == [] for item in gold)
    assert all(item.accepted_scientific_chunk_ids == [] for item in gold)


def test_scientific_chunk_index_filters_scope_and_ranks_relevant_text():
    from app.domain_adaptation.models import ScientificChunk
    from app.domain_adaptation.rag import ScientificChunkIndex

    paper, chunks, _protocols = _rag_fixture()
    unrelated = ScientificChunk(
        scientific_chunk_id="scichk-unrelated",
        paper_id="DOI:10.1000_other",
        ordinal=0,
        parent_section_id="scisec-other",
        section_type="methods",
        semantic_roles=["protocol"],
        source_chunk_ids=["other-methods"],
        segments=[chunks[0].segments[0].model_copy(update={"source_chunk_id": "other-methods"})],
        text="A polymer film was dried under vacuum for 12 h.",
        content_sha256="0" * 64,
    )
    index = ScientificChunkIndex([unrelated, *chunks])

    hits = index.search(
        "Which workstation measured OER activity?",
        paper_ids=[paper.paper_id],
        limit=5,
    )

    assert [hit.scientific_chunk_id for hit in hits] == [
        chunks[0].scientific_chunk_id
    ]


def test_structured_rag_baseline_answers_and_cites_source_evidence():
    from app.domain_adaptation.rag import (
        StructuredRagBaseline,
        build_rag_review_queue,
    )

    _paper, chunks, protocols = _rag_fixture()
    candidates, _gold = build_rag_review_queue(protocols, chunks, limit=10)
    material_question = next(
        item.question
        for item in candidates
        if item.question.question_type == "material_lookup"
    )

    prediction = StructuredRagBaseline(chunks, protocols).answer(
        material_question, top_k=5
    )

    assert prediction.abstained is False
    assert prediction.answer_items == ["NiFe catalyst (10 mg)"]
    assert prediction.cited_evidence_ids == ["ev-rag-1"]
    assert prediction.retrieved_scientific_chunk_ids == [
        chunks[0].scientific_chunk_id
    ]


def test_rag_scoring_uses_only_completed_human_gold():
    from app.domain_adaptation.rag import (
        StructuredRagBaseline,
        build_rag_review_queue,
        score_rag_predictions,
    )

    _paper, chunks, protocols = _rag_fixture()
    candidates, pending_gold = build_rag_review_queue(protocols, chunks, limit=10)
    material_candidate = next(
        item
        for item in candidates
        if item.question.question_type == "material_lookup"
    )
    material_gold = next(
        item
        for item in pending_gold
        if item.question.question_id == material_candidate.question.question_id
    ).model_copy(
        update={
            "review_status": "reviewed",
            "annotation_complete": True,
            "reviewer": "human-reviewer",
            "accepted_answer_items": ["NiFe catalyst (10 mg)"],
            "accepted_evidence_ids": ["ev-rag-1"],
            "accepted_scientific_chunk_ids": [
                chunks[0].scientific_chunk_id
            ],
        }
    )
    prediction = StructuredRagBaseline(chunks, protocols).answer(
        material_candidate.question, top_k=5
    )

    empty_report = score_rag_predictions(
        gold_questions=pending_gold,
        predictions=[prediction],
        protocols=protocols,
        retrieval_k=5,
    )
    report = score_rag_predictions(
        gold_questions=[material_gold],
        predictions=[prediction],
        protocols=protocols,
        retrieval_k=5,
    )

    assert empty_report.reviewed_question_count == 0
    assert empty_report.answer_f1 is None
    assert report.reviewed_question_count == 1
    assert report.answer_f1 == 1.0
    assert report.citation_validity_rate == 1.0
    assert report.evidence_precision == 1.0
    assert report.evidence_recall == 1.0
    assert report.retrieval_recall_at_k == 1.0
    assert report.mean_reciprocal_rank == 1.0


def test_rag_scoring_penalizes_invalid_citations_and_scores_abstention():
    from app.domain_adaptation.rag import (
        RagGoldQuestion,
        RagPrediction,
        RagQuestion,
        score_rag_predictions,
    )

    _paper, chunks, protocols = _rag_fixture()
    answer_question = RagQuestion(
        question_id="ragq-answer",
        text="Which material was used?",
        question_type="material_lookup",
        paper_ids=[protocols[0].paper_id],
    )
    abstain_question = RagQuestion(
        question_id="ragq-abstain",
        text="Which software version was reported?",
        question_type="abstention",
        paper_ids=[protocols[0].paper_id],
    )
    gold = [
        RagGoldQuestion(
            question=answer_question,
            review_status="reviewed",
            annotation_complete=True,
            reviewer="human-reviewer",
            accepted_answer_items=["NiFe catalyst (10 mg)"],
            accepted_evidence_ids=["ev-rag-1"],
            accepted_scientific_chunk_ids=[chunks[0].scientific_chunk_id],
        ),
        RagGoldQuestion(
            question=abstain_question,
            review_status="reviewed",
            annotation_complete=True,
            reviewer="human-reviewer",
            expected_behavior="abstain",
        ),
    ]
    predictions = [
        RagPrediction(
            question_id=answer_question.question_id,
            answer_text="NiFe catalyst (10 mg)",
            answer_items=["NiFe catalyst (10 mg)"],
            cited_evidence_ids=["fictional-evidence"],
            retrieved_scientific_chunk_ids=[chunks[0].scientific_chunk_id],
            abstained=False,
            system_id="test-system",
        ),
        RagPrediction(
            question_id=abstain_question.question_id,
            answer_text="",
            abstained=True,
            system_id="test-system",
        ),
    ]

    report = score_rag_predictions(
        gold_questions=gold,
        predictions=predictions,
        protocols=protocols,
    )

    assert report.answer_f1 == 1.0
    assert report.citation_validity_rate == 0.0
    assert report.evidence_precision == 0.0
    assert report.evidence_recall == 0.0
    assert report.abstain_accuracy == 1.0


def test_prepare_rag_evaluation_writes_non_overwriting_review_artifacts(tmp_path):
    import json

    import pytest

    from app.scripts.prepare_domain_rag_eval import prepare_rag_evaluation

    _paper, chunks, protocols = _rag_fixture()
    package = tmp_path / "domain-package"
    (package / "knowledge").mkdir(parents=True)
    (package / "knowledge/protocols.jsonl").write_text(
        "".join(
            json.dumps(
                {"schema_version": "domain-adapter-knowledge-v0.1", **item.model_dump(mode="json")}
            )
            + "\n"
            for item in protocols
        )
    )
    (package / "knowledge/scientific_chunks.jsonl").write_text(
        "".join(
            json.dumps(
                {
                    "schema_version": "domain-adapter-scientific-chunk-v0.1",
                    **item.model_dump(mode="json"),
                }
            )
            + "\n"
            for item in chunks
        )
    )

    result = prepare_rag_evaluation(package, limit=10)

    assert result == {
        "baseline_prediction_count": 2,
        "candidate_question_count": 2,
        "pending_gold_question_count": 2,
    }
    assert (package / "rag/candidate_questions.jsonl").is_file()
    assert (package / "gold/rag_questions.jsonl").is_file()
    assert (package / "rag/baseline_predictions.jsonl").is_file()
    readiness = json.loads((package / "reports/rag_readiness.json").read_text())
    assert readiness["human_reviewed_question_count"] == 0
    assert readiness["scientific_accuracy_metrics"] is None
    with pytest.raises(FileExistsError, match="Refusing to overwrite"):
        prepare_rag_evaluation(package, limit=10)


def test_evaluate_rag_set_scores_reviewed_questions_and_writes_report(tmp_path):
    import json

    from app.scripts.evaluate_domain_rag import evaluate_rag_set
    from app.scripts.prepare_domain_rag_eval import prepare_rag_evaluation

    _paper, chunks, protocols = _rag_fixture()
    package = tmp_path / "domain-package"
    (package / "knowledge").mkdir(parents=True)
    (package / "knowledge/protocols.jsonl").write_text(
        "".join(
            json.dumps(
                {"schema_version": "domain-adapter-knowledge-v0.1", **item.model_dump(mode="json")}
            )
            + "\n"
            for item in protocols
        )
    )
    (package / "knowledge/scientific_chunks.jsonl").write_text(
        "".join(
            json.dumps(
                {
                    "schema_version": "domain-adapter-scientific-chunk-v0.1",
                    **item.model_dump(mode="json"),
                }
            )
            + "\n"
            for item in chunks
        )
    )
    prepare_rag_evaluation(package, limit=10)
    candidates = [
        json.loads(line)
        for line in (package / "rag/candidate_questions.jsonl")
        .read_text()
        .splitlines()
    ]
    material = next(
        item
        for item in candidates
        if item["question"]["question_type"] == "material_lookup"
    )
    gold_rows = [
        json.loads(line)
        for line in (package / "gold/rag_questions.jsonl")
        .read_text()
        .splitlines()
    ]
    for row in gold_rows:
        if row["question"]["question_id"] != material["question"]["question_id"]:
            continue
        row.update(
            {
                "review_status": "reviewed",
                "annotation_complete": True,
                "reviewer": "human-reviewer",
                "accepted_answer_items": [
                    item["source_value"]
                    for item in material["proposed_answer_items"]
                ],
                "accepted_evidence_ids": material["proposed_evidence_ids"],
                "accepted_scientific_chunk_ids": material[
                    "proposed_scientific_chunk_ids"
                ],
            }
        )
    (package / "gold/rag_questions.jsonl").write_text(
        "".join(json.dumps(item) + "\n" for item in gold_rows)
    )

    report = evaluate_rag_set(package)

    assert report.reviewed_question_count == 1
    assert report.answer_f1 == 1.0
    assert json.loads((package / "reports/rag_eval.json").read_text())[
        "answer_f1"
    ] == 1.0
