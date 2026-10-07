"""Source-first RAG review queues, baseline retrieval, and honest scoring."""

from __future__ import annotations

import hashlib
import math
import re
import unicodedata
from collections import Counter, defaultdict
from typing import Literal

from pydantic import Field

from app.domain_adaptation.gold import ReviewStatus, normalize_gold_value
from app.domain_adaptation.models import (
    DomainModel,
    EvidenceScope,
    ProtocolUnit,
    ScientificChunk,
    ScientificSemanticRole,
)


RagQuestionType = Literal[
    "material_lookup",
    "instrument_lookup",
    "software_lookup",
    "protocol_step_lookup",
    "characterization_lookup",
    "reported_result_lookup",
    "caveat_lookup",
    "cross_protocol_comparison",
    "abstention",
]
ExpectedBehavior = Literal["answer", "abstain"]

_QUESTION_TYPE_ORDER: tuple[RagQuestionType, ...] = (
    "material_lookup",
    "instrument_lookup",
    "software_lookup",
    "protocol_step_lookup",
    "characterization_lookup",
    "reported_result_lookup",
    "caveat_lookup",
    "cross_protocol_comparison",
    "abstention",
)
_TOKEN_RE = re.compile(r"[a-z0-9]+(?:[-./][a-z0-9]+)*|[α-ωμµ]+", re.I)


def _stable_id(prefix: str, *parts: str) -> str:
    digest = hashlib.sha256("\0".join(parts).encode("utf-8")).hexdigest()
    return f"{prefix}_{digest[:16]}"


def _tokens(text: str) -> list[str]:
    normalized = unicodedata.normalize("NFKC", text).casefold()
    normalized = re.sub(r"[‐‑‒–—―−﹘﹣－]", "-", normalized)
    return _TOKEN_RE.findall(normalized)


class RagQuestion(DomainModel):
    schema_version: str = "domain-adapter-rag-question-v0.2"
    question_id: str
    text: str = Field(min_length=1)
    question_type: RagQuestionType
    paper_ids: list[str] = Field(min_length=1)
    semantic_role_filters: list[ScientificSemanticRole] = Field(
        default_factory=list
    )
    evidence_scope_filters: list[EvidenceScope] = Field(default_factory=list)


class ProposedRagAnswerItem(DomainModel):
    source_value: str
    normalized_value: str
    evidence_ids: list[str] = Field(min_length=1)


class RagQuestionCandidate(DomainModel):
    schema_version: str = "domain-adapter-rag-question-candidate-v0.2"
    question: RagQuestion
    source_protocol_ids: list[str] = Field(min_length=1)
    proposed_answer_items: list[ProposedRagAnswerItem] = Field(min_length=1)
    proposed_evidence_ids: list[str] = Field(min_length=1)
    proposed_scientific_chunk_ids: list[str] = Field(min_length=1)
    proposal_policy: str = "deterministic_protocol_question_v0.1"


class RagGoldQuestion(DomainModel):
    schema_version: str = "domain-adapter-rag-gold-v0.2"
    question: RagQuestion
    review_status: ReviewStatus = "pending"
    annotation_complete: bool = False
    expected_behavior: ExpectedBehavior = "answer"
    accepted_answer_items: list[str] = Field(default_factory=list)
    accepted_evidence_ids: list[str] = Field(default_factory=list)
    accepted_scientific_chunk_ids: list[str] = Field(default_factory=list)
    reviewer: str | None = None
    notes: str | None = None


class RetrievalHit(DomainModel):
    scientific_chunk_id: str
    paper_id: str
    rank: int = Field(ge=1)
    score: float = Field(ge=0)


class RagPrediction(DomainModel):
    schema_version: str = "domain-adapter-rag-prediction-v0.1"
    question_id: str
    answer_text: str
    answer_items: list[str] = Field(default_factory=list)
    cited_evidence_ids: list[str] = Field(default_factory=list)
    retrieved_scientific_chunk_ids: list[str] = Field(default_factory=list)
    abstained: bool
    system_id: str


class RagScoreReport(DomainModel):
    schema_version: str = "domain-adapter-rag-score-v0.1"
    reviewed_question_count: int = Field(ge=0)
    answered_gold_question_count: int = Field(ge=0)
    abstention_gold_question_count: int = Field(ge=0)
    answer_precision: float | None
    answer_recall: float | None
    answer_f1: float | None
    citation_validity_rate: float | None
    evidence_precision: float | None
    evidence_recall: float | None
    retrieval_recall_at_k: float | None
    mean_reciprocal_rank: float | None
    abstain_accuracy: float | None
    retrieval_k: int = Field(ge=1)
    claims_boundary: str = (
        "Only human-reviewed, annotation-complete questions contribute to metrics. "
        "Deterministic question proposals are not gold."
    )


def _format_material(item) -> str:
    return f"{item.name} ({item.amount})" if item.amount else item.name


def _format_instrument(item) -> str:
    return f"{item.name} ({item.model})" if item.model else item.name


def _format_software(item) -> str:
    return f"{item.name} ({item.version})" if item.version else item.name


def _format_settings(settings: dict[str, str]) -> str:
    return ", ".join(f"{key}={value}" for key, value in sorted(settings.items()))


def _format_step(item) -> str:
    if item.verb is None or not item.targets:
        return ""
    action = f"{item.verb} {', '.join(item.targets)}"
    params = _format_settings(item.params)
    return f"{action} [{params}]" if params else action


def _format_characterization(item) -> str:
    settings = _format_settings(item.settings)
    return f"{item.technique} [{settings}]" if settings else item.technique


def _format_result(item) -> str:
    value = f"{item.metric}: {item.raw_value}"
    return f"{value} ({item.context})" if item.context else value


def _answer_payload(
    protocol: ProtocolUnit, question_type: RagQuestionType
) -> tuple[list[str], list[list[str]]]:
    if question_type == "material_lookup":
        return (
            [_format_material(item) for item in protocol.materials],
            [item.evidence_ids for item in protocol.materials],
        )
    if question_type == "instrument_lookup":
        return (
            [_format_instrument(item) for item in protocol.instruments],
            [item.evidence_ids for item in protocol.instruments],
        )
    if question_type == "software_lookup":
        return (
            [_format_software(item) for item in protocol.software],
            [item.evidence_ids for item in protocol.software],
        )
    if question_type == "protocol_step_lookup":
        structured_steps = [item for item in protocol.steps if _format_step(item)]
        return (
            [_format_step(item) for item in structured_steps],
            [item.evidence_ids for item in structured_steps],
        )
    if question_type == "characterization_lookup":
        return (
            [
                _format_characterization(item)
                for item in protocol.characterization
            ],
            [item.evidence_ids for item in protocol.characterization],
        )
    if question_type == "reported_result_lookup":
        return (
            [_format_result(item) for item in protocol.results],
            [item.evidence_ids for item in protocol.results],
        )
    if question_type == "caveat_lookup":
        return (
            [item.text for item in protocol.caveats],
            [item.evidence_ids for item in protocol.caveats],
        )
    return [], []


def _question_text(protocol: ProtocolUnit, question_type: RagQuestionType) -> str:
    scope_label = {
        "primary_report": "a primary report",
        "secondary_report": "a secondary report",
        "unknown": "an evidence report of unknown origin",
    }[protocol.evidence_scope]
    subject = (
        f"the {protocol.protocol_name} protocol in {protocol.paper_id}, "
        f"classified as {scope_label}"
    )
    templates: dict[RagQuestionType, str] = {
        "material_lookup": (
            f"Which materials and explicitly reported quantities are used in {subject}?"
        ),
        "instrument_lookup": f"Which instruments and models are used in {subject}?",
        "software_lookup": f"Which software and versions are used in {subject}?",
        "protocol_step_lookup": (
            f"What ordered experimental or computational steps are reported for {subject}?"
        ),
        "characterization_lookup": (
            f"Which characterization techniques and settings are reported for {subject}?"
        ),
        "reported_result_lookup": (
            f"Which result values and contexts are explicitly reported for {subject}?"
        ),
        "caveat_lookup": (
            f"Which limitations, failure modes, or cautions are explicitly stated for {subject}?"
        ),
        "cross_protocol_comparison": f"How does {subject} compare with related protocols?",
        "abstention": f"Which unsupported detail is absent from {subject}?",
    }
    return templates[question_type]


def _role_filters(question_type: RagQuestionType) -> list[ScientificSemanticRole]:
    mapping: dict[RagQuestionType, list[ScientificSemanticRole]] = {
        "material_lookup": ["protocol"],
        "instrument_lookup": ["protocol", "characterization"],
        "software_lookup": ["protocol", "computation"],
        "protocol_step_lookup": ["protocol", "computation"],
        "characterization_lookup": ["characterization"],
        "reported_result_lookup": ["result"],
        "caveat_lookup": ["caveat"],
        "cross_protocol_comparison": [],
        "abstention": [],
    }
    return mapping[question_type]


def build_rag_review_queue(
    protocols: list[ProtocolUnit],
    scientific_chunks: list[ScientificChunk],
    *,
    limit: int = 50,
) -> tuple[list[RagQuestionCandidate], list[RagGoldQuestion]]:
    """Create balanced review aids without copying proposals into human gold."""
    if limit < 1:
        raise ValueError("RAG review queue limit must be positive")
    scientific_by_source: dict[tuple[str, str], list[str]] = defaultdict(list)
    for chunk in scientific_chunks:
        for source_chunk_id in chunk.source_chunk_ids:
            scientific_by_source[(chunk.paper_id, source_chunk_id)].append(
                chunk.scientific_chunk_id
            )

    candidates: list[RagQuestionCandidate] = []
    for protocol in sorted(protocols, key=lambda item: item.protocol_id):
        evidence_by_id = {item.evidence_id: item for item in protocol.evidence}
        for question_type in _QUESTION_TYPE_ORDER:
            answer_values, answer_evidence_ids = _answer_payload(
                protocol, question_type
            )
            if not answer_values:
                continue
            evidence_groups = [
                list(dict.fromkeys(evidence_ids))
                for evidence_ids in answer_evidence_ids
            ]
            proposed_evidence_ids = list(
                dict.fromkeys(
                    evidence_id
                    for evidence_ids in evidence_groups
                    for evidence_id in evidence_ids
                )
            )
            proposed_scientific_chunk_ids = list(
                dict.fromkeys(
                    scientific_chunk_id
                    for evidence_id in proposed_evidence_ids
                    if evidence_id in evidence_by_id
                    for scientific_chunk_id in scientific_by_source.get(
                        (
                            protocol.paper_id,
                            evidence_by_id[evidence_id].chunk_id,
                        ),
                        [],
                    )
                )
            )
            if not proposed_evidence_ids or not proposed_scientific_chunk_ids:
                continue
            text = _question_text(protocol, question_type)
            question = RagQuestion(
                question_id=_stable_id(
                    "ragq", protocol.protocol_id, question_type, text
                ),
                text=text,
                question_type=question_type,
                paper_ids=[protocol.paper_id],
                semantic_role_filters=_role_filters(question_type),
                evidence_scope_filters=[protocol.evidence_scope],
            )
            candidates.append(
                RagQuestionCandidate(
                    question=question,
                    source_protocol_ids=[protocol.protocol_id],
                    proposed_answer_items=[
                        ProposedRagAnswerItem(
                            source_value=value,
                            normalized_value=normalize_gold_value(value),
                            evidence_ids=evidence_ids,
                        )
                        for value, evidence_ids in zip(
                            answer_values, evidence_groups, strict=True
                        )
                    ],
                    proposed_evidence_ids=proposed_evidence_ids,
                    proposed_scientific_chunk_ids=(
                        proposed_scientific_chunk_ids
                    ),
                )
            )

    selected: list[RagQuestionCandidate] = []
    remaining = list(candidates)
    paper_counts: Counter[str] = Counter()
    type_counts: Counter[RagQuestionType] = Counter()
    scope_counts: Counter[EvidenceScope] = Counter()
    question_type_order = {
        question_type: index
        for index, question_type in enumerate(_QUESTION_TYPE_ORDER)
    }
    while remaining and len(selected) < limit:
        candidate = min(
            remaining,
            key=lambda item: (
                paper_counts[item.question.paper_ids[0]] > 0,
                type_counts[item.question.question_type],
                scope_counts[item.question.evidence_scope_filters[0]],
                paper_counts[item.question.paper_ids[0]],
                question_type_order[item.question.question_type],
                item.question.question_id,
            ),
        )
        selected.append(candidate)
        remaining.remove(candidate)
        paper_counts[candidate.question.paper_ids[0]] += 1
        type_counts[candidate.question.question_type] += 1
        scope_counts[candidate.question.evidence_scope_filters[0]] += 1

    gold = [RagGoldQuestion(question=item.question) for item in selected]
    return selected, gold


class ScientificChunkIndex:
    """Small deterministic BM25 baseline for chunking and retrieval audits."""

    def __init__(self, chunks: list[ScientificChunk]) -> None:
        self.chunks = list(chunks)
        self.term_frequencies = [Counter(_tokens(chunk.text)) for chunk in chunks]
        self.lengths = [sum(values.values()) for values in self.term_frequencies]
        self.average_length = (
            sum(self.lengths) / len(self.lengths) if self.lengths else 0.0
        )
        self.document_frequency = Counter(
            token
            for frequencies in self.term_frequencies
            for token in frequencies.keys()
        )

    def search(
        self,
        query: str,
        *,
        paper_ids: list[str] | None = None,
        semantic_roles: list[ScientificSemanticRole] | None = None,
        limit: int = 5,
    ) -> list[RetrievalHit]:
        if limit < 1:
            raise ValueError("Retrieval limit must be positive")
        query_tokens = _tokens(query)
        if not query_tokens or not self.chunks:
            return []
        paper_filter = set(paper_ids or [])
        role_filter = set(semantic_roles or [])
        total_documents = len(self.chunks)
        scored: list[tuple[float, ScientificChunk]] = []
        for index, chunk in enumerate(self.chunks):
            if paper_filter and chunk.paper_id not in paper_filter:
                continue
            if role_filter and not role_filter.intersection(chunk.semantic_roles):
                continue
            frequencies = self.term_frequencies[index]
            document_length = self.lengths[index]
            score = 0.0
            for token in query_tokens:
                frequency = frequencies.get(token, 0)
                if not frequency:
                    continue
                document_frequency = self.document_frequency[token]
                inverse_document_frequency = math.log(
                    1
                    + (total_documents - document_frequency + 0.5)
                    / (document_frequency + 0.5)
                )
                normalization = frequency + 1.5 * (
                    1
                    - 0.75
                    + 0.75
                    * document_length
                    / (self.average_length or 1.0)
                )
                score += inverse_document_frequency * frequency * 2.5 / normalization
            if score > 0:
                scored.append((score, chunk))
        scored.sort(key=lambda item: (-item[0], item[1].scientific_chunk_id))
        return [
            RetrievalHit(
                scientific_chunk_id=chunk.scientific_chunk_id,
                paper_id=chunk.paper_id,
                rank=rank,
                score=round(score, 8),
            )
            for rank, (score, chunk) in enumerate(scored[:limit], start=1)
        ]


class StructuredRagBaseline:
    """Retrieve semantic chunks, then answer from linked structured protocols."""

    system_id = "structured-bm25-protocol-baseline-v0.2"

    def __init__(
        self, chunks: list[ScientificChunk], protocols: list[ProtocolUnit]
    ) -> None:
        self.index = ScientificChunkIndex(chunks)
        self.protocols = list(protocols)

    def answer(self, question: RagQuestion, *, top_k: int = 5) -> RagPrediction:
        hits = self.index.search(
            question.text,
            paper_ids=question.paper_ids,
            semantic_roles=question.semantic_role_filters,
            limit=top_k,
        )
        if question.semantic_role_filters and len(hits) < top_k:
            seen_chunk_ids = {item.scientific_chunk_id for item in hits}
            fallback_hits = self.index.search(
                question.text,
                paper_ids=question.paper_ids,
                limit=top_k,
            )
            hits.extend(
                item
                for item in fallback_hits
                if item.scientific_chunk_id not in seen_chunk_ids
            )
            hits = hits[:top_k]
            for rank, hit in enumerate(hits, start=1):
                hit.rank = rank
        retrieved_ids = [item.scientific_chunk_id for item in hits]
        retrieved_ranks = {
            item.scientific_chunk_id: item.rank for item in hits
        }
        question_tokens = set(_tokens(question.text))
        evidence_scope_filter = set(question.evidence_scope_filters)
        eligible: list[tuple[int, int, ProtocolUnit]] = []
        for protocol in self.protocols:
            if protocol.paper_id not in question.paper_ids:
                continue
            if (
                evidence_scope_filter
                and protocol.evidence_scope not in evidence_scope_filter
            ):
                continue
            linked_ranks = [
                retrieved_ranks[item]
                for item in protocol.scientific_chunk_ids
                if item in retrieved_ranks
            ]
            if not linked_ranks:
                continue
            protocol_tokens = set(
                _tokens(f"{protocol.protocol_name} {protocol.protocol_type}")
            )
            overlap = len(question_tokens.intersection(protocol_tokens))
            eligible.append((-overlap, min(linked_ranks), protocol))
        eligible.sort(key=lambda item: (item[0], item[1], item[2].protocol_id))
        if not eligible:
            return RagPrediction(
                question_id=question.question_id,
                answer_text="",
                abstained=True,
                retrieved_scientific_chunk_ids=retrieved_ids,
                system_id=self.system_id,
            )

        protocol = eligible[0][2]
        answer_items, evidence_groups = _answer_payload(
            protocol, question.question_type
        )
        cited_evidence_ids = list(
            dict.fromkeys(
                evidence_id
                for evidence_ids in evidence_groups
                for evidence_id in evidence_ids
            )
        )
        if not answer_items or not cited_evidence_ids:
            return RagPrediction(
                question_id=question.question_id,
                answer_text="",
                abstained=True,
                retrieved_scientific_chunk_ids=retrieved_ids,
                system_id=self.system_id,
            )
        return RagPrediction(
            question_id=question.question_id,
            answer_text="; ".join(answer_items),
            answer_items=answer_items,
            cited_evidence_ids=cited_evidence_ids,
            retrieved_scientific_chunk_ids=retrieved_ids,
            abstained=False,
            system_id=self.system_id,
        )


def _ratio(numerator: int, denominator: int) -> float | None:
    return round(numerator / denominator, 6) if denominator else None


def score_rag_predictions(
    *,
    gold_questions: list[RagGoldQuestion],
    predictions: list[RagPrediction],
    protocols: list[ProtocolUnit],
    retrieval_k: int = 5,
) -> RagScoreReport:
    """Score only human-reviewed complete questions against source IDs."""
    if retrieval_k < 1:
        raise ValueError("retrieval_k must be positive")
    reviewed = [
        item
        for item in gold_questions
        if item.review_status == "reviewed" and item.annotation_complete
    ]
    for item in reviewed:
        if item.expected_behavior == "answer" and (
            not item.accepted_answer_items
            or not item.accepted_evidence_ids
            or not item.accepted_scientific_chunk_ids
        ):
            raise ValueError(
                "A completed answerable RAG gold question lacks answer or evidence"
            )
    prediction_by_id: dict[str, RagPrediction] = {}
    for candidate_prediction in predictions:
        if candidate_prediction.question_id in prediction_by_id:
            raise ValueError("RAG predictions contain duplicate question IDs")
        prediction_by_id[candidate_prediction.question_id] = candidate_prediction

    valid_evidence_ids = {
        evidence.evidence_id
        for protocol in protocols
        for evidence in protocol.evidence
    }
    answer_true_positive = 0
    predicted_answer_count = 0
    gold_answer_count = 0
    valid_citation_count = 0
    predicted_citation_count = 0
    evidence_true_positive = 0
    gold_evidence_count = 0
    retrieved_gold_chunk_count = 0
    gold_chunk_count = 0
    reciprocal_ranks: list[float] = []
    abstain_correct = 0

    for gold in reviewed:
        prediction = prediction_by_id.get(gold.question.question_id)
        predicted_abstain = prediction is None or prediction.abstained
        expected_abstain = gold.expected_behavior == "abstain"
        abstain_correct += predicted_abstain == expected_abstain
        if expected_abstain:
            continue

        predicted_answers = Counter(
            normalize_gold_value(value)
            for value in (prediction.answer_items if prediction else [])
        )
        gold_answers = Counter(
            normalize_gold_value(value) for value in gold.accepted_answer_items
        )
        answer_true_positive += sum((predicted_answers & gold_answers).values())
        predicted_answer_count += sum(predicted_answers.values())
        gold_answer_count += sum(gold_answers.values())

        predicted_citations = set(
            prediction.cited_evidence_ids if prediction else []
        )
        gold_citations = set(gold.accepted_evidence_ids)
        valid_citation_count += len(
            predicted_citations.intersection(valid_evidence_ids)
        )
        predicted_citation_count += len(predicted_citations)
        evidence_true_positive += len(
            predicted_citations.intersection(gold_citations)
        )
        gold_evidence_count += len(gold_citations)

        retrieved = (
            prediction.retrieved_scientific_chunk_ids[:retrieval_k]
            if prediction
            else []
        )
        gold_chunks = set(gold.accepted_scientific_chunk_ids)
        retrieved_gold_chunk_count += len(set(retrieved).intersection(gold_chunks))
        gold_chunk_count += len(gold_chunks)
        first_relevant_rank = next(
            (
                rank
                for rank, chunk_id in enumerate(retrieved, start=1)
                if chunk_id in gold_chunks
            ),
            None,
        )
        reciprocal_ranks.append(
            1.0 / first_relevant_rank if first_relevant_rank else 0.0
        )

    answer_precision = _ratio(answer_true_positive, predicted_answer_count)
    answer_recall = _ratio(answer_true_positive, gold_answer_count)
    answer_f1 = (
        round(
            2 * answer_precision * answer_recall / (answer_precision + answer_recall),
            6,
        )
        if answer_precision is not None
        and answer_recall is not None
        and answer_precision + answer_recall
        else None
    )
    return RagScoreReport(
        reviewed_question_count=len(reviewed),
        answered_gold_question_count=sum(
            item.expected_behavior == "answer" for item in reviewed
        ),
        abstention_gold_question_count=sum(
            item.expected_behavior == "abstain" for item in reviewed
        ),
        answer_precision=answer_precision,
        answer_recall=answer_recall,
        answer_f1=answer_f1,
        citation_validity_rate=_ratio(
            valid_citation_count, predicted_citation_count
        ),
        evidence_precision=_ratio(
            evidence_true_positive, predicted_citation_count
        ),
        evidence_recall=_ratio(evidence_true_positive, gold_evidence_count),
        retrieval_recall_at_k=_ratio(
            retrieved_gold_chunk_count, gold_chunk_count
        ),
        mean_reciprocal_rank=(
            round(sum(reciprocal_ranks) / len(reciprocal_ranks), 6)
            if reciprocal_ranks
            else None
        ),
        abstain_accuracy=_ratio(abstain_correct, len(reviewed)),
        retrieval_k=retrieval_k,
    )
