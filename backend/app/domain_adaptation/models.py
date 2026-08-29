"""Canonical models for the Domain Adaptation bounded context."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.domain_adaptation.package_graph import PackageDependency, PackageKind


class DomainModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SourceChunk(DomainModel):
    chunk_id: str
    section_type: str = "unknown"
    section_title: str | None = None
    section_path: list[str] = Field(default_factory=list)
    text: str
    document_char_start: int | None = Field(default=None, ge=0)
    document_char_end: int | None = Field(default=None, ge=0)


class SourcePaper(DomainModel):
    paper_id: str
    title: str
    year: int | None = None
    doi: str | None = None
    selection_tier: str
    selection_reasons: list[str]
    task_split: Literal["train", "evaluation"] = "train"
    source_bucket: str
    source_prefix: str
    source_manifest_key: str | None = None
    source_markdown_key: str | None = None
    source_markdown_sha256: str | None = None
    chunks: list[SourceChunk]


ScientificSemanticRole = Literal[
    "protocol",
    "characterization",
    "computation",
    "result",
    "caveat",
    "scientific_context",
]


class ScientificChunkSegment(DomainModel):
    source_chunk_id: str
    char_start: int = Field(ge=0)
    char_end: int = Field(gt=0)
    document_char_start: int | None = Field(default=None, ge=0)
    document_char_end: int | None = Field(default=None, ge=0)
    source_sha256: str


class ScientificChunk(DomainModel):
    scientific_chunk_id: str
    paper_id: str
    ordinal: int = Field(ge=0)
    parent_section_id: str
    section_type: str = "unknown"
    section_title: str | None = None
    section_path: list[str] = Field(default_factory=list)
    semantic_roles: list[ScientificSemanticRole] = Field(min_length=1)
    source_chunk_ids: list[str] = Field(min_length=1)
    segments: list[ScientificChunkSegment] = Field(min_length=1)
    text: str = Field(min_length=1)
    content_sha256: str


class PilotSelectionItem(DomainModel):
    paper_id: str
    selection_tier: Literal["primary_oer", "oer_case_study", "oer_review"]
    selection_reasons: list[str] = Field(min_length=1)
    task_split: Literal["train", "evaluation"] = "train"
    source_manifest_key: str | None = None


class PilotSelectionManifest(DomainModel):
    schema_version: str = "domain-adapter-selection-config-v0.1"
    package_id: str
    package_version: str
    domain: str
    papers: list[PilotSelectionItem] = Field(min_length=1)


class DomainPackageConfig(DomainModel):
    package_id: str
    package_version: str
    domain: str
    source_access: Literal["imported_api", "s3_markdown"]
    package_kind: PackageKind = "domain"
    facets: list[str] = Field(default_factory=list)
    dependencies: list[PackageDependency] = Field(default_factory=list)
    schema_version: str = "domain-adapter-package-v0.2"


class EvidenceSpan(DomainModel):
    evidence_id: str
    paper_id: str
    chunk_id: str
    quote: str
    char_start: int = Field(ge=0)
    char_end: int = Field(gt=0)
    source_sha256: str
    document_char_start: int | None = Field(default=None, ge=0)
    document_char_end: int | None = Field(default=None, ge=0)


class MaterialInput(DomainModel):
    entity_id: str
    name: str
    role: str | None = None
    amount: str | None = None
    purity: str | None = None
    supplier: str | None = None
    pretreatment: str | None = None
    evidence_ids: list[str] = Field(default_factory=list)


class InstrumentUse(DomainModel):
    entity_id: str
    name: str
    model: str | None = None
    manufacturer: str | None = None
    settings: dict[str, str] = Field(default_factory=dict)
    evidence_ids: list[str] = Field(default_factory=list)


class SoftwareUse(DomainModel):
    entity_id: str
    name: str
    version: str | None = None
    settings: dict[str, str] = Field(default_factory=dict)
    evidence_ids: list[str] = Field(default_factory=list)


class ProtocolStep(DomainModel):
    step_id: str
    order: int = Field(ge=1)
    action: str
    conditions: list[str] = Field(default_factory=list)
    notes: str | None = None
    evidence_ids: list[str] = Field(default_factory=list)


class CharacterizationUse(DomainModel):
    entity_id: str
    technique: str
    settings: dict[str, str] = Field(default_factory=dict)
    output: str | None = None
    evidence_ids: list[str] = Field(default_factory=list)


class ReportedResult(DomainModel):
    result_id: str
    metric: str
    raw_value: str
    context: str | None = None
    evidence_ids: list[str] = Field(default_factory=list)


class Caveat(DomainModel):
    caveat_id: str
    text: str
    evidence_ids: list[str] = Field(default_factory=list)


class KnowledgeRelation(DomainModel):
    relation_id: str
    subject_id: str
    predicate: str
    object_id: str
    evidence_ids: list[str] = Field(default_factory=list)


class ProtocolUnit(DomainModel):
    protocol_id: str
    paper_id: str
    protocol_name: str
    protocol_type: str
    source_paper_tier: str = "unknown"
    evidence_scope: Literal["primary_report", "secondary_report", "unknown"] = (
        "unknown"
    )
    source_chunk_ids: list[str]
    scientific_chunk_ids: list[str] = Field(default_factory=list)
    materials: list[MaterialInput] = Field(default_factory=list)
    instruments: list[InstrumentUse] = Field(default_factory=list)
    software: list[SoftwareUse] = Field(default_factory=list)
    steps: list[ProtocolStep] = Field(default_factory=list)
    characterization: list[CharacterizationUse] = Field(default_factory=list)
    results: list[ReportedResult] = Field(default_factory=list)
    caveats: list[Caveat] = Field(default_factory=list)
    relations: list[KnowledgeRelation] = Field(default_factory=list)
    evidence: list[EvidenceSpan] = Field(default_factory=list)


class PackageBuildResult(DomainModel):
    output_dir: str
    manifest: dict
    changed_files: int
