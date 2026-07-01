"""Transferable Knowledge Unit (TKU): a paper compressed into a structured,
domain-separable unit so methods and lessons can be transferred across SDLs.

A TKU holds:
  - problem_signature: the abstract problem shape (task type, cost, search space…)
  - method_core: the domain-agnostic method (workflow, surrogate, acquisition…)
  - assumptions: conditions the method relies on
  - lessons: faithful takeaways (negative results are especially valuable)
  - domain_bindings: domain-specific nouns that do NOT transfer
  - source_domain: one lowercase word for the application domain
"""
from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import JSON, DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


def _utcnow() -> datetime:
    return datetime.now(UTC)


class TransferKnowledgeUnit(Base):
    __tablename__ = "transfer_knowledge_units"

    id: Mapped[str] = mapped_column(String, primary_key=True)  # "tku-<paper_id>"
    paper_id: Mapped[str] = mapped_column(
        ForeignKey("papers.id"), nullable=False, unique=True, index=True
    )
    source_domain: Mapped[str] = mapped_column(String, nullable=False)
    problem_signature: Mapped[dict] = mapped_column(JSON, nullable=False)
    method_core: Mapped[dict] = mapped_column(JSON, nullable=False)
    assumptions: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    lessons: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    domain_bindings: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    extractor: Mapped[str] = mapped_column(String, nullable=False)  # llm | example
    model: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow
    )
