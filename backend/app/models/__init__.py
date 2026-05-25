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

all_models = (
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
    "all_models",
]
