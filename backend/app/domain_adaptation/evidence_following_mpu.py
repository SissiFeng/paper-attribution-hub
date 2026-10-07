"""Contracts and analysis for the two-domain evidence-following MPU.

The MPU measures model behavior. It does not train adapters and it does not use
chain-of-thought as evidence about a model's internal reasoning.
"""

from __future__ import annotations

import hashlib
import json
import math
import random
from collections import Counter, defaultdict
from typing import Annotated, Literal

from pydantic import Field, model_validator
from scipy.stats import spearmanr

from app.domain_adaptation.models import DomainModel


MpuCondition = Literal[
    "closed_book_blind",
    "closed_book_identified",
    "fact_injected_probe",
    "counterfactual",
    "counterfactual_fact_injected",
]
MpuReportType = Literal["primary_experiment", "review", "case_study", "unknown"]

REQUIRED_CONDITIONS: tuple[MpuCondition, ...] = (
    "closed_book_blind",
    "closed_book_identified",
    "fact_injected_probe",
    "counterfactual",
    "counterfactual_fact_injected",
)
MAX_PROMPT_COUNT = 10_000
MAX_BOOTSTRAP_SCORE_VISITS = 10_000_000


class MpuPolicy(DomainModel):
    schema_version: Literal["evidence-following-mpu-policy-v0.1"] = (
        "evidence-following-mpu-policy-v0.1"
    )
    min_primary_papers_per_domain: int = Field(default=100, ge=1)
    min_tasks_per_domain: int = Field(default=100, ge=1)
    min_model_count: int = Field(default=3, ge=2)
    bootstrap_replicates: int = Field(default=2000, ge=100, le=10000)
    bootstrap_seed: int = Field(default=20260901, ge=0)
    trait_rank_correlation_threshold: float = Field(default=0.6, ge=-1, le=1)
    max_mean_cross_domain_gap: float = Field(default=0.1, ge=0, le=1)
    correlation_equivalence_bound: float = Field(default=0.3, gt=0, lt=1)


class MpuModel(DomainModel):
    schema_version: Literal["evidence-following-mpu-model-v0.1"] = (
        "evidence-following-mpu-model-v0.1"
    )
    alias: str = Field(min_length=1, max_length=200)
    family: str = Field(min_length=1, max_length=200)
    model_id: str = Field(min_length=1, max_length=500)


class MpuPaper(DomainModel):
    schema_version: Literal["evidence-following-mpu-paper-v0.1"] = (
        "evidence-following-mpu-paper-v0.1"
    )
    paper_id: str = Field(min_length=1, max_length=500)
    domain: str = Field(min_length=1, max_length=200)
    title: str = Field(min_length=1, max_length=2000)
    doi: str = Field(min_length=1, max_length=500)
    report_type: MpuReportType
    source_markdown_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


def _normalized(value: str) -> str:
    return " ".join(value.casefold().split())


class MpuTask(DomainModel):
    schema_version: Literal["evidence-following-mpu-task-v0.1"] = (
        "evidence-following-mpu-task-v0.1"
    )
    task_id: str = Field(min_length=1, max_length=500)
    paper_id: str = Field(min_length=1, max_length=500)
    domain: str = Field(min_length=1, max_length=200)
    field_type: str = Field(min_length=1, max_length=500)
    question: str = Field(min_length=1, max_length=5000)
    paper_identity: str = Field(min_length=1, max_length=5000)
    blind_context: str = Field(min_length=1, max_length=5000)
    original_value: str = Field(min_length=1, max_length=2000)
    replacement_value: str = Field(min_length=1, max_length=2000)
    counterfactual_evidence: str = Field(min_length=1, max_length=20000)
    fact_injection: str = Field(min_length=1, max_length=5000)
    source_evidence_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def validate_counterfactual(self) -> "MpuTask":
        if _normalized(self.original_value) == _normalized(self.replacement_value):
            raise ValueError("Original and replacement values must differ")
        if _normalized(self.replacement_value) not in _normalized(
            self.counterfactual_evidence
        ):
            raise ValueError("Counterfactual evidence must contain the replacement value")
        if _normalized(self.original_value) not in _normalized(self.fact_injection):
            raise ValueError("Fact injection must contain the original value")
        return self


class MpuInputSource(DomainModel):
    schema_version: Literal["evidence-following-mpu-input-source-v0.1"] = (
        "evidence-following-mpu-input-source-v0.1"
    )
    role: Literal["base_study", "counterfactual_cases", "curated_task_source"]
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    path_hint: str = Field(min_length=1, max_length=1000)


class MpuStudyInput(DomainModel):
    schema_version: Literal["evidence-following-mpu-study-v0.1"] = (
        "evidence-following-mpu-study-v0.1"
    )
    study_id: str = Field(min_length=1, max_length=500)
    domains: list[str] = Field(max_length=2)
    policy: MpuPolicy = Field(default_factory=MpuPolicy)
    models: list[MpuModel] = Field(min_length=1, max_length=20)
    papers: list[MpuPaper] = Field(default_factory=list, max_length=500)
    tasks: list[MpuTask] = Field(default_factory=list, max_length=5000)
    input_sources: list[MpuInputSource] = Field(default_factory=list, max_length=100)

    @model_validator(mode="after")
    def validate_study_coordinates(self) -> "MpuStudyInput":
        if len(self.domains) != 2 or len(set(self.domains)) != 2:
            raise ValueError("The MPU requires exactly two domains")
        if any(not domain.strip() for domain in self.domains):
            raise ValueError("MPU domain names must be non-empty")

        aliases = [item.alias for item in self.models]
        if len(aliases) != len(set(aliases)):
            raise ValueError("MPU model registry contains duplicate aliases")
        model_ids = [item.model_id for item in self.models]
        if len(model_ids) != len(set(model_ids)):
            raise ValueError("MPU model registry contains duplicate model IDs")
        paper_ids = [item.paper_id for item in self.papers]
        if len(paper_ids) != len(set(paper_ids)):
            raise ValueError("MPU cohort contains duplicate paper IDs")
        dois = [_normalized(item.doi) for item in self.papers]
        if len(dois) != len(set(dois)):
            raise ValueError("MPU cohort contains duplicate DOIs")
        if any(item.report_type != "primary_experiment" for item in self.papers):
            raise ValueError("MPU cohorts accept primary experimental papers only")
        if any(item.domain not in self.domains for item in self.papers):
            raise ValueError("Every paper must belong to a declared MPU domain")

        task_ids = [item.task_id for item in self.tasks]
        if len(task_ids) != len(set(task_ids)):
            raise ValueError("MPU task suite contains duplicate task IDs")
        paper_by_id = {item.paper_id: item for item in self.papers}
        for task in self.tasks:
            paper = paper_by_id.get(task.paper_id)
            if paper is None:
                raise ValueError(f"MPU task references unknown paper: {task.paper_id}")
            if task.domain != paper.domain:
                raise ValueError("MPU task and paper domains must match")
        prompt_count = len(self.tasks) * len(self.models) * len(REQUIRED_CONDITIONS)
        if prompt_count > MAX_PROMPT_COUNT:
            raise ValueError(
                f"MPU prompt matrix exceeds the work budget of {MAX_PROMPT_COUNT}"
            )
        score_count = len(self.tasks) * len(self.models)
        bootstrap_visits = self.policy.bootstrap_replicates * score_count
        if bootstrap_visits > MAX_BOOTSTRAP_SCORE_VISITS:
            raise ValueError(
                "MPU bootstrap analysis exceeds the score-visit work budget of "
                f"{MAX_BOOTSTRAP_SCORE_VISITS}"
            )
        return self


class MpuPromptPayload(DomainModel):
    schema_version: Literal["evidence-following-mpu-prompt-payload-v0.1"] = (
        "evidence-following-mpu-prompt-payload-v0.1"
    )
    question: str = Field(min_length=1, max_length=5000)
    paper_identity: str | None = Field(default=None, max_length=5000)
    blind_context: str | None = Field(default=None, max_length=5000)
    prior_fact: str | None = Field(default=None, max_length=5000)
    current_source_evidence: str | None = Field(default=None, max_length=20000)


class MpuPrompt(DomainModel):
    schema_version: Literal["evidence-following-mpu-prompt-v0.1"] = (
        "evidence-following-mpu-prompt-v0.1"
    )
    prompt_id: str = Field(min_length=1, max_length=1000)
    prompt_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    study_id: str = Field(min_length=1, max_length=500)
    task_id: str = Field(min_length=1, max_length=500)
    paper_id: str = Field(min_length=1, max_length=500)
    domain: str = Field(min_length=1, max_length=200)
    model_alias: str = Field(min_length=1, max_length=200)
    model_id: str = Field(min_length=1, max_length=500)
    condition: MpuCondition
    system_instruction: str = Field(min_length=1, max_length=5000)
    user_payload: MpuPromptPayload


class MpuDesign(DomainModel):
    schema_version: Literal["evidence-following-mpu-design-v0.1"] = (
        "evidence-following-mpu-design-v0.1"
    )
    study_id: str
    ready: bool
    failed_gates: list[str]
    primary_paper_counts: dict[str, int]
    task_counts: dict[str, int]
    model_count: int
    prompts: list[MpuPrompt]
    claims_boundary: str = (
        "This design measures observable evidence-following under controlled prompts. "
        "It does not measure chain-of-thought, prove training-set membership, or train adapters."
    )


def _prompt_for(
    task: MpuTask, condition: MpuCondition
) -> tuple[str, MpuPromptPayload]:
    response_contract = (
        'Return one JSON object: {"values":["exact value"]}. Use an empty values '
        "list when you do not know the answer."
    )
    if condition in {"closed_book_blind", "closed_book_identified"}:
        instruction = (
            "Answer from your existing model knowledge without external tools or supplied "
            f"paper text. {response_contract}"
        )
    elif condition == "fact_injected_probe":
        instruction = (
            "Use the supplied prior fact as memory for this question. "
            f"{response_contract}"
        )
    else:
        instruction = (
            "Use only the current source evidence for the answer, even when it conflicts "
            f"with prior memory. {response_contract}"
        )
    if condition == "closed_book_blind":
        payload = MpuPromptPayload(
            question=task.question,
            blind_context=task.blind_context,
        )
    elif condition == "closed_book_identified":
        payload = MpuPromptPayload(
            question=task.question,
            paper_identity=task.paper_identity,
        )
    elif condition == "fact_injected_probe":
        payload = MpuPromptPayload(
            question=task.question,
            prior_fact=task.fact_injection,
        )
    elif condition == "counterfactual":
        payload = MpuPromptPayload(
            question=task.question,
            current_source_evidence=task.counterfactual_evidence,
        )
    else:
        payload = MpuPromptPayload(
            question=task.question,
            prior_fact=task.fact_injection,
            current_source_evidence=task.counterfactual_evidence,
        )
    return instruction, payload


def _build_prompt(
    *,
    spec: MpuStudyInput,
    task: MpuTask,
    model: MpuModel,
    condition: MpuCondition,
) -> MpuPrompt:
    coordinate = {
        "study_id": spec.study_id,
        "task_id": task.task_id,
        "model_alias": model.alias,
        "model_id": model.model_id,
        "condition": condition,
    }
    coordinate_digest = hashlib.sha256(
        json.dumps(coordinate, separators=(",", ":"), sort_keys=True).encode("utf-8")
    ).hexdigest()
    prompt_id = f"mpu_prompt_{coordinate_digest[:24]}"
    instruction, payload = _prompt_for(task, condition)
    hash_payload = {
        "study_id": spec.study_id,
        "prompt_id": prompt_id,
        "task_id": task.task_id,
        "paper_id": task.paper_id,
        "domain": task.domain,
        "model_alias": model.alias,
        "model_id": model.model_id,
        "condition": condition,
        "system_instruction": instruction,
        "user_payload": payload.model_dump(mode="json"),
    }
    prompt_sha256 = hashlib.sha256(
        json.dumps(
            hash_payload,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    ).hexdigest()
    return MpuPrompt(
        prompt_id=prompt_id,
        prompt_sha256=prompt_sha256,
        study_id=spec.study_id,
        task_id=task.task_id,
        paper_id=task.paper_id,
        domain=task.domain,
        model_alias=model.alias,
        model_id=model.model_id,
        condition=condition,
        system_instruction=instruction,
        user_payload=payload,
    )


def build_mpu_design(spec: MpuStudyInput) -> MpuDesign:
    paper_counts = Counter(item.domain for item in spec.papers)
    task_counts = Counter(item.domain for item in spec.tasks)
    failed_gates: list[str] = []
    for domain in spec.domains:
        if paper_counts[domain] < spec.policy.min_primary_papers_per_domain:
            failed_gates.append(f"primary_papers:{domain}")
    for domain in spec.domains:
        if task_counts[domain] < spec.policy.min_tasks_per_domain:
            failed_gates.append(f"counterfactual_tasks:{domain}")
    if len(spec.models) < spec.policy.min_model_count:
        failed_gates.append("model_count")
    prompts = [
        _build_prompt(spec=spec, task=task, model=model, condition=condition)
        for task in sorted(spec.tasks, key=lambda item: item.task_id)
        for model in sorted(spec.models, key=lambda item: item.alias)
        for condition in REQUIRED_CONDITIONS
    ]
    prompt_ids = [item.prompt_id for item in prompts]
    if len(prompt_ids) != len(set(prompt_ids)):
        raise ValueError("MPU prompt IDs are not unique")
    return MpuDesign(
        study_id=spec.study_id,
        ready=not failed_gates,
        failed_gates=failed_gates,
        primary_paper_counts={domain: paper_counts[domain] for domain in spec.domains},
        task_counts={domain: task_counts[domain] for domain in spec.domains},
        model_count=len(spec.models),
        prompts=prompts,
    )


class MpuObservation(DomainModel):
    schema_version: Literal["evidence-following-mpu-observation-v0.1"] = (
        "evidence-following-mpu-observation-v0.1"
    )
    study_id: str = Field(min_length=1, max_length=500)
    prompt_id: str = Field(min_length=1, max_length=1000)
    prompt_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    task_id: str = Field(min_length=1, max_length=500)
    model_alias: str = Field(min_length=1, max_length=200)
    model_id: str = Field(min_length=1, max_length=500)
    condition: MpuCondition
    run_id: str = Field(min_length=1, max_length=500)
    provider_request_id: str = Field(min_length=1, max_length=1000)
    response_text: str = Field(min_length=1, max_length=100000)
    response_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    values: list[Annotated[str, Field(min_length=1, max_length=2000)]] = Field(
        default_factory=list,
        max_length=32,
    )

    @model_validator(mode="after")
    def validate_values(self) -> "MpuObservation":
        if any(not value.strip() for value in self.values):
            raise ValueError("MPU observation values must be non-empty strings")
        actual_hash = hashlib.sha256(self.response_text.encode("utf-8")).hexdigest()
        if actual_hash != self.response_sha256:
            raise ValueError("MPU response hash does not match response_text")
        try:
            payload = json.loads(self.response_text)
        except json.JSONDecodeError as exc:
            raise ValueError("MPU response_text must be exact JSON") from exc
        if not isinstance(payload, dict) or set(payload) != {"values"}:
            raise ValueError("MPU response JSON must contain only values")
        if payload["values"] != self.values:
            raise ValueError("MPU scored values must equal the raw response values")
        return self


class MpuItemScore(DomainModel):
    schema_version: Literal["evidence-following-mpu-item-score-v0.1"] = (
        "evidence-following-mpu-item-score-v0.1"
    )
    task_id: str
    paper_id: str
    domain: str
    model_alias: str
    closed_book_knowledge: bool | None
    blind_domain_prior: bool | None
    exposure_score: int | None = Field(default=None, ge=-1, le=1)
    evidence_followed: bool | None
    fact_injected_knowledge: bool | None
    fact_injected_evidence_followed: bool | None


def _has_value(observation: MpuObservation | None, value: str) -> bool | None:
    if observation is None:
        return None
    target = _normalized(value)
    return any(_normalized(item) == target for item in observation.values)


def _followed(
    observation: MpuObservation | None,
    *,
    original: str,
    replacement: str,
) -> bool | None:
    if observation is None:
        return None
    original_hit = _has_value(observation, original)
    replacement_hit = _has_value(observation, replacement)
    return replacement_hit is True and original_hit is False


def _observation_index(
    spec: MpuStudyInput,
    observations: list[MpuObservation],
    design: MpuDesign,
) -> dict[tuple[str, str, MpuCondition], MpuObservation]:
    prompts = {
        (item.task_id, item.model_alias, item.condition): item
        for item in design.prompts
    }
    index: dict[tuple[str, str, MpuCondition], MpuObservation] = {}
    for item in observations:
        if item.study_id != spec.study_id:
            raise ValueError("MPU observation study ID does not match the study")
        key = (item.task_id, item.model_alias, item.condition)
        prompt = prompts.get(key)
        if prompt is None:
            raise ValueError("MPU observation references an unknown prompt coordinate")
        if item.prompt_id != prompt.prompt_id:
            raise ValueError("MPU observation prompt ID does not match the design")
        if item.prompt_sha256 != prompt.prompt_sha256:
            raise ValueError("MPU observation prompt hash does not match the design")
        if item.model_id != prompt.model_id:
            raise ValueError("MPU observation model ID does not match the design")
        if key in index:
            raise ValueError("MPU observations contain a duplicate coordinate")
        index[key] = item
    return index


def score_mpu_observations(
    spec: MpuStudyInput,
    observations: list[MpuObservation],
    *,
    design: MpuDesign | None = None,
) -> list[MpuItemScore]:
    resolved_design = design or build_mpu_design(spec)
    index = _observation_index(spec, observations, resolved_design)
    scores: list[MpuItemScore] = []
    for task in sorted(spec.tasks, key=lambda item: item.task_id):
        for model in sorted(spec.models, key=lambda item: item.alias):
            by_condition = {
                condition: index.get((task.task_id, model.alias, condition))
                for condition in REQUIRED_CONDITIONS
            }
            blind = _has_value(by_condition["closed_book_blind"], task.original_value)
            identified = _has_value(
                by_condition["closed_book_identified"], task.original_value
            )
            exposure = (
                int(identified) - int(blind)
                if identified is not None and blind is not None
                else None
            )
            scores.append(
                MpuItemScore(
                    task_id=task.task_id,
                    paper_id=task.paper_id,
                    domain=task.domain,
                    model_alias=model.alias,
                    closed_book_knowledge=identified,
                    blind_domain_prior=blind,
                    exposure_score=exposure,
                    evidence_followed=_followed(
                        by_condition["counterfactual"],
                        original=task.original_value,
                        replacement=task.replacement_value,
                    ),
                    fact_injected_knowledge=_has_value(
                        by_condition["fact_injected_probe"], task.original_value
                    ),
                    fact_injected_evidence_followed=_followed(
                        by_condition["counterfactual_fact_injected"],
                        original=task.original_value,
                        replacement=task.replacement_value,
                    ),
                )
            )
    return scores


class MpuModelDomainSummary(DomainModel):
    schema_version: Literal["evidence-following-mpu-model-domain-summary-v0.1"] = (
        "evidence-following-mpu-model-domain-summary-v0.1"
    )
    model_alias: str
    domain: str
    item_count: int = Field(ge=0)
    closed_book_knowledge_rate: float | None = Field(default=None, ge=0, le=1)
    blind_domain_prior_rate: float | None = Field(default=None, ge=0, le=1)
    mean_exposure_score: float | None = Field(default=None, ge=-1, le=1)
    evidence_following_rate: float | None = Field(default=None, ge=0, le=1)
    fact_injected_knowledge_rate: float | None = Field(default=None, ge=0, le=1)
    fact_injected_evidence_following_rate: float | None = Field(
        default=None, ge=0, le=1
    )


class MpuCrossDomainResult(DomainModel):
    schema_version: Literal["evidence-following-mpu-cross-domain-v0.1"] = (
        "evidence-following-mpu-cross-domain-v0.1"
    )
    model_count: int = Field(ge=0)
    rank_correlation: float | None = Field(default=None, ge=-1, le=1)
    rank_correlation_interval: list[float] | None = None
    mean_absolute_rate_gap: float | None = Field(default=None, ge=0, le=1)
    mean_absolute_rate_gap_interval: list[float] | None = None
    trait_supported: bool


class MpuDissociationResult(DomainModel):
    schema_version: Literal["evidence-following-mpu-dissociation-v0.1"] = (
        "evidence-following-mpu-dissociation-v0.1"
    )
    summary_cell_count: int = Field(ge=0)
    knowledge_correlation: float | None = Field(default=None, ge=-1, le=1)
    knowledge_correlation_interval: list[float] | None = None
    exposure_correlation: float | None = Field(default=None, ge=-1, le=1)
    exposure_correlation_interval: list[float] | None = None
    equivalence_bound: float = Field(gt=0, lt=1)
    supported: bool


class MpuFactInjectionResult(DomainModel):
    schema_version: Literal["evidence-following-mpu-fact-injection-v0.1"] = (
        "evidence-following-mpu-fact-injection-v0.1"
    )
    intervention: str = "contextual_prior_fact"
    paired_item_count: int = Field(ge=0)
    knowledge_delta: float | None = Field(default=None, ge=-1, le=1)
    knowledge_delta_interval: list[float] | None = None
    evidence_following_delta: float | None = Field(default=None, ge=-1, le=1)
    evidence_following_delta_interval: list[float] | None = None
    pareto_tradeoff_supported: bool
    claims_boundary: str = (
        "This MPU injects an original fact as controlled prior context. It can identify "
        "an inference-time knowledge-versus-updatability trade-off, not a trade-off caused "
        "by parameter updates or adapter training."
    )


class MpuAnalysisReport(DomainModel):
    schema_version: Literal["evidence-following-mpu-analysis-v0.1"] = (
        "evidence-following-mpu-analysis-v0.1"
    )
    study_id: str
    design_ready: bool
    analysis_ready: bool
    failed_gates: list[str]
    expected_observation_count: int = Field(ge=0)
    supplied_observation_count: int = Field(ge=0)
    missing_observation_count: int = Field(ge=0)
    model_domain_summaries: list[MpuModelDomainSummary]
    cross_domain: MpuCrossDomainResult
    knowledge_dissociation: MpuDissociationResult
    fact_injection: MpuFactInjectionResult
    claims_boundary: str = (
        "Reported associations measure behavior on this benchmark. They do not establish "
        "training-data membership, causal mechanisms inside model weights, or reasoning "
        "generality beyond the two declared domains. Null association does not establish "
        "dissociation unless its bootstrap interval passes the preregistered equivalence bound."
    )
    future_scope_exclusion: str = (
        "Adapter training and P2-proc procedural injection are excluded from this MPU and "
        "reserved for a subsequent study."
    )


def _mean(values: list[bool | int | float | None]) -> float | None:
    available = [float(value) for value in values if value is not None]
    return sum(available) / len(available) if available else None


def _summaries(scores: list[MpuItemScore]) -> list[MpuModelDomainSummary]:
    grouped: dict[tuple[str, str], list[MpuItemScore]] = defaultdict(list)
    for score in scores:
        grouped[(score.model_alias, score.domain)].append(score)
    return [
        MpuModelDomainSummary(
            model_alias=model_alias,
            domain=domain,
            item_count=len(items),
            closed_book_knowledge_rate=_mean(
                [item.closed_book_knowledge for item in items]
            ),
            blind_domain_prior_rate=_mean(
                [item.blind_domain_prior for item in items]
            ),
            mean_exposure_score=_mean([item.exposure_score for item in items]),
            evidence_following_rate=_mean([item.evidence_followed for item in items]),
            fact_injected_knowledge_rate=_mean(
                [item.fact_injected_knowledge for item in items]
            ),
            fact_injected_evidence_following_rate=_mean(
                [item.fact_injected_evidence_followed for item in items]
            ),
        )
        for (model_alias, domain), items in sorted(grouped.items())
    ]


def _spearman(left: list[float], right: list[float]) -> float | None:
    if len(left) < 3 or len(right) != len(left):
        return None
    if len(set(left)) < 2 or len(set(right)) < 2:
        return None
    value = float(spearmanr(left, right).statistic)
    return None if math.isnan(value) else max(-1.0, min(1.0, value))


def _interval(values: list[float]) -> list[float] | None:
    finite = sorted(value for value in values if math.isfinite(value))
    if len(finite) < 20:
        return None
    low = finite[int(0.025 * (len(finite) - 1))]
    high = finite[int(0.975 * (len(finite) - 1))]
    return [low, high]


def _cluster_scores(
    scores: list[MpuItemScore],
) -> tuple[
    dict[tuple[str, str], list[MpuItemScore]],
    dict[str, list[str]],
]:
    by_domain_paper: dict[tuple[str, str], list[MpuItemScore]] = defaultdict(list)
    papers_by_domain: dict[str, list[str]] = defaultdict(list)
    for score in scores:
        key = (score.domain, score.paper_id)
        if key not in by_domain_paper:
            papers_by_domain[score.domain].append(score.paper_id)
        by_domain_paper[key].append(score)
    return dict(by_domain_paper), dict(papers_by_domain)


def _resample_scores(
    *,
    by_domain_paper: dict[tuple[str, str], list[MpuItemScore]],
    papers_by_domain: dict[str, list[str]],
    rng: random.Random,
) -> list[MpuItemScore]:
    sample: list[MpuItemScore] = []
    for domain, paper_ids in sorted(papers_by_domain.items()):
        for _ in paper_ids:
            paper_id = rng.choice(paper_ids)
            sample.extend(by_domain_paper[(domain, paper_id)])
    return sample


def _cross_domain(
    summaries: list[MpuModelDomainSummary],
    domains: list[str],
) -> tuple[float | None, float | None, int]:
    by_model: dict[str, dict[str, float]] = defaultdict(dict)
    for item in summaries:
        if item.evidence_following_rate is not None:
            by_model[item.model_alias][item.domain] = item.evidence_following_rate
    paired = {
        model: rates
        for model, rates in by_model.items()
        if all(domain in rates for domain in domains)
    }
    left = [paired[model][domains[0]] for model in sorted(paired)]
    right = [paired[model][domains[1]] for model in sorted(paired)]
    gaps = [abs(a - b) for a, b in zip(left, right, strict=True)]
    return _spearman(left, right), _mean(gaps), len(paired)


def _dissociation(
    summaries: list[MpuModelDomainSummary],
) -> tuple[float | None, float | None, int]:
    cells = [
        item
        for item in summaries
        if item.evidence_following_rate is not None
        and item.closed_book_knowledge_rate is not None
        and item.mean_exposure_score is not None
    ]
    evidence = [float(item.evidence_following_rate) for item in cells]
    knowledge = [float(item.closed_book_knowledge_rate) for item in cells]
    exposure = [float(item.mean_exposure_score) for item in cells]
    return _spearman(knowledge, evidence), _spearman(exposure, evidence), len(cells)


def _fact_deltas(scores: list[MpuItemScore]) -> tuple[float | None, float | None, int]:
    paired = [
        item
        for item in scores
        if item.closed_book_knowledge is not None
        and item.fact_injected_knowledge is not None
        and item.evidence_followed is not None
        and item.fact_injected_evidence_followed is not None
    ]
    knowledge = _mean(
        [
            int(item.fact_injected_knowledge) - int(item.closed_book_knowledge)
            for item in paired
        ]
    )
    evidence = _mean(
        [
            int(item.fact_injected_evidence_followed) - int(item.evidence_followed)
            for item in paired
        ]
    )
    return knowledge, evidence, len(paired)


def analyze_mpu(
    spec: MpuStudyInput,
    observations: list[MpuObservation],
    *,
    design: MpuDesign | None = None,
    scores: list[MpuItemScore] | None = None,
) -> MpuAnalysisReport:
    resolved_design = design or build_mpu_design(spec)
    resolved_scores = (
        scores
        if scores is not None
        else score_mpu_observations(
            spec,
            observations,
            design=resolved_design,
        )
    )
    summaries = _summaries(resolved_scores)
    expected = len(spec.tasks) * len(spec.models) * len(REQUIRED_CONDITIONS)
    missing = expected - len(observations)
    failed_gates = list(resolved_design.failed_gates)
    if missing:
        failed_gates.append("complete_observation_matrix")
    analysis_ready = not failed_gates

    cross_corr, cross_gap, model_count = _cross_domain(summaries, spec.domains)
    knowledge_corr, exposure_corr, summary_count = _dissociation(summaries)
    knowledge_delta, evidence_delta, paired_count = _fact_deltas(resolved_scores)

    cross_samples: list[float] = []
    cross_gap_samples: list[float] = []
    knowledge_samples: list[float] = []
    exposure_samples: list[float] = []
    knowledge_delta_samples: list[float] = []
    evidence_delta_samples: list[float] = []
    if analysis_ready:
        rng = random.Random(spec.policy.bootstrap_seed)
        by_domain_paper, papers_by_domain = _cluster_scores(resolved_scores)
        for _ in range(spec.policy.bootstrap_replicates):
            sampled = _resample_scores(
                by_domain_paper=by_domain_paper,
                papers_by_domain=papers_by_domain,
                rng=rng,
            )
            sampled_summaries = _summaries(sampled)
            sampled_cross, sampled_gap, _count = _cross_domain(
                sampled_summaries, spec.domains
            )
            sampled_knowledge, sampled_exposure, _cells = _dissociation(
                sampled_summaries
            )
            sampled_k_delta, sampled_e_delta, _pairs = _fact_deltas(sampled)
            if sampled_cross is not None:
                cross_samples.append(sampled_cross)
            if sampled_gap is not None:
                cross_gap_samples.append(sampled_gap)
            if sampled_knowledge is not None:
                knowledge_samples.append(sampled_knowledge)
            if sampled_exposure is not None:
                exposure_samples.append(sampled_exposure)
            if sampled_k_delta is not None:
                knowledge_delta_samples.append(sampled_k_delta)
            if sampled_e_delta is not None:
                evidence_delta_samples.append(sampled_e_delta)

    cross_interval = _interval(cross_samples)
    cross_gap_interval = _interval(cross_gap_samples)
    knowledge_interval = _interval(knowledge_samples)
    exposure_interval = _interval(exposure_samples)
    knowledge_delta_interval = _interval(knowledge_delta_samples)
    evidence_delta_interval = _interval(evidence_delta_samples)
    bound = spec.policy.correlation_equivalence_bound
    dissociation_supported = (
        analysis_ready
        and knowledge_interval is not None
        and exposure_interval is not None
        and knowledge_interval[0] > -bound
        and knowledge_interval[1] < bound
        and exposure_interval[0] > -bound
        and exposure_interval[1] < bound
    )
    trait_supported = (
        analysis_ready
        and cross_interval is not None
        and cross_interval[0] >= spec.policy.trait_rank_correlation_threshold
        and cross_gap_interval is not None
        and cross_gap_interval[1] <= spec.policy.max_mean_cross_domain_gap
    )
    pareto_supported = (
        analysis_ready
        and knowledge_delta_interval is not None
        and evidence_delta_interval is not None
        and knowledge_delta_interval[0] > 0
        and evidence_delta_interval[1] < 0
    )
    return MpuAnalysisReport(
        study_id=spec.study_id,
        design_ready=resolved_design.ready,
        analysis_ready=analysis_ready,
        failed_gates=failed_gates,
        expected_observation_count=expected,
        supplied_observation_count=len(observations),
        missing_observation_count=missing,
        model_domain_summaries=summaries,
        cross_domain=MpuCrossDomainResult(
            model_count=model_count,
            rank_correlation=cross_corr,
            rank_correlation_interval=cross_interval,
            mean_absolute_rate_gap=cross_gap,
            mean_absolute_rate_gap_interval=cross_gap_interval,
            trait_supported=trait_supported,
        ),
        knowledge_dissociation=MpuDissociationResult(
            summary_cell_count=summary_count,
            knowledge_correlation=knowledge_corr,
            knowledge_correlation_interval=knowledge_interval,
            exposure_correlation=exposure_corr,
            exposure_correlation_interval=exposure_interval,
            equivalence_bound=bound,
            supported=dissociation_supported,
        ),
        fact_injection=MpuFactInjectionResult(
            paired_item_count=paired_count,
            knowledge_delta=knowledge_delta,
            knowledge_delta_interval=knowledge_delta_interval,
            evidence_following_delta=evidence_delta,
            evidence_following_delta_interval=evidence_delta_interval,
            pareto_tradeoff_supported=pareto_supported,
        ),
    )
