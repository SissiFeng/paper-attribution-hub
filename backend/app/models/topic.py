from __future__ import annotations

from sqlalchemy import JSON, Boolean, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class Topic(Base):
    __tablename__ = "topics"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    description: Mapped[str | None] = mapped_column(Text)
    keywords: Mapped[list[dict] | None] = mapped_column(JSON)
    # v0.7: negative_keywords blacklist; populated by active learning loop and
    # the topic taxonomy YAML. Strings, no weights — pure veto.
    negative_keywords: Mapped[list[str] | None] = mapped_column(JSON, default=list)
    is_core: Mapped[bool] = mapped_column(Boolean, default=True)
