"""Source adapters. Swap CSV for DB/PDF/API by implementing PaperSource."""

from app.adapters.base import (
    InstitutionRecord,
    PaperRecord,
    PaperSource,
    PersonRecord,
    TopicRecord,
)
from app.adapters.csv_source import CsvPaperSource

__all__ = [
    "InstitutionRecord",
    "PaperRecord",
    "PaperSource",
    "PersonRecord",
    "TopicRecord",
    "CsvPaperSource",
]
