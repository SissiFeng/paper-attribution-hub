"""Source-adapter interface.

The pipeline only consumes the records emitted here. Replace the CSV adapter
with a database, OpenAlex API, or GROBID full-text adapter without touching
normalization / matching / classification.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterable
from dataclasses import dataclass, field


@dataclass
class PaperRecord:
    paper_id: str
    title: str
    abstract: str | None = None
    authors: list[str] = field(default_factory=list)
    affiliations: list[str] = field(default_factory=list)
    year: int | None = None
    doi: str | None = None
    venue: str | None = None
    keywords: list[str] = field(default_factory=list)
    source: str = "csv"
    raw: dict | None = None


@dataclass
class PersonRecord:
    person_id: str
    name: str
    aliases: list[str] = field(default_factory=list)
    institution: str | None = None
    department: str | None = None
    lab: str | None = None
    role: str | None = None
    is_ac_member: bool = False
    orcid: str | None = None


@dataclass
class InstitutionRecord:
    canonical_name: str
    aliases: list[str] = field(default_factory=list)
    country: str | None = None
    city: str | None = None
    is_partner: bool = False


@dataclass
class TopicKeyword:
    term: str
    weight: float = 1.0


@dataclass
class TopicRecord:
    topic_id: str
    name: str
    description: str | None = None
    keywords: list[TopicKeyword] = field(default_factory=list)
    is_core: bool = True
    negative_keywords: list[str] = field(default_factory=list)


class PaperSource(ABC):
    """Anything that can stream papers/people/institutions/topics."""

    @abstractmethod
    def papers(self) -> Iterable[PaperRecord]: ...

    @abstractmethod
    def people(self) -> Iterable[PersonRecord]: ...

    @abstractmethod
    def institutions(self) -> Iterable[InstitutionRecord]: ...

    @abstractmethod
    def topics(self) -> Iterable[TopicRecord]: ...
