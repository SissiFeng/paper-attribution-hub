"""ORM models. Import `all_models` to ensure SQLAlchemy registers every table."""

from app.models.paper import Paper, PaperAuthor
from app.models.author import Author
from app.models.institution import Institution
from app.models.topic import Topic
from app.models.classification import PaperClassification
from app.models.review import HumanReview
from app.models.section import PaperSection
from app.models.chunk import PaperChunk
from app.models.evidence import PaperEvidence
from app.models.reference import AcCorePaper, PaperReference
from app.models.proposition import PaperProposition
from app.models.discovery import DiscoveryCandidate, ExternalCache
from app.models.pipeline_run import PipelineRun
from app.models.wiki import WikiPage
from app.models.dedup import AuthorDedupDecision
from app.models.rag_feedback import RagFeedback
from app.models.sdl import PaperEntity, PaperLabLink, SdlLab
from app.models.tku import TransferKnowledgeUnit
from app.models.attribution_skill_invocation import (
    AttributionSkillInvocationRecord,
)
from app.models.model_evolution import (
    ModelTrainingRun,
    ModelTrainingState,
    TrainingFeedbackEvent,
)
from app.models.authorship_metadata import (
    MetadataEnrichmentRun,
    PaperAuthorshipMetadata,
)
from app.models.chat import ChatMessage, ChatSession
from app.models.reading import Reader, ReaderSession, Bookmark, ChatParticipant
from app.models.scientific_knowledge import ScientificKnowledgeRecord

from app.models.access import AdminGrant, AccessAudit

from app.models.research import ResearchProject, ProjectMember, ProjectPaper, ProjectDiscussion, Annotation, EvidenceComparison
from app.models.exploration import ResearchConnection, ResearchWatch, ResearchScreening, ResearchAlert, ResearchAlertReceipt

all_models = (
    ResearchConnection, ResearchWatch, ResearchScreening, ResearchAlert, ResearchAlertReceipt,
    ResearchProject, ProjectMember, ProjectPaper, ProjectDiscussion, Annotation, EvidenceComparison,
    AdminGrant, AccessAudit,
    Reader, ReaderSession, Bookmark, ChatParticipant,
    Paper,
    PaperAuthor,
    Author,
    Institution,
    Topic,
    PaperClassification,
    HumanReview,
    PaperSection,
    PaperChunk,
    PaperEvidence,
    AcCorePaper,
    PaperReference,
    PaperProposition,
    DiscoveryCandidate,
    ExternalCache,
    PipelineRun,
    WikiPage,
    AuthorDedupDecision,
    RagFeedback,
    SdlLab,
    PaperLabLink,
    PaperEntity,
    TransferKnowledgeUnit,
    AttributionSkillInvocationRecord,
    ModelTrainingRun,
    ModelTrainingState,
    TrainingFeedbackEvent,
    PaperAuthorshipMetadata,
    MetadataEnrichmentRun,
    ChatSession,
    ChatMessage,
    ScientificKnowledgeRecord,
)

__all__ = [
    "Paper",
    "PaperAuthor",
    "Author",
    "Institution",
    "Topic",
    "PaperClassification",
    "HumanReview",
    "PaperSection",
    "PaperChunk",
    "PaperEvidence",
    "AcCorePaper",
    "PaperReference",
    "PaperProposition",
    "DiscoveryCandidate",
    "ExternalCache",
    "PipelineRun",
    "WikiPage",
    "AuthorDedupDecision",
    "RagFeedback",
    "SdlLab",
    "PaperLabLink",
    "PaperEntity",
    "TransferKnowledgeUnit",
    "AttributionSkillInvocationRecord",
    "ModelTrainingRun",
    "ModelTrainingState",
    "TrainingFeedbackEvent",
    "PaperAuthorshipMetadata",
    "MetadataEnrichmentRun",
    "ChatSession",
    "ChatMessage",
    "ScientificKnowledgeRecord",
    "all_models",
]
