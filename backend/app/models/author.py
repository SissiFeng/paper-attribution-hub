from __future__ import annotations

from sqlalchemy import JSON, Boolean, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class Author(Base):
    __tablename__ = "authors"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    canonical_name: Mapped[str] = mapped_column(String, nullable=False, index=True)
    aliases: Mapped[list[str] | None] = mapped_column(JSON)
    normalized_name: Mapped[str] = mapped_column(String, index=True)
    orcid: Mapped[str | None] = mapped_column(String, unique=True)
    institution_id: Mapped[str | None] = mapped_column(ForeignKey("institutions.id"))
    department: Mapped[str | None] = mapped_column(String)
    lab: Mapped[str | None] = mapped_column(String)
    role: Mapped[str | None] = mapped_column(String)
    is_ac_member: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    raw_metadata: Mapped[dict | None] = mapped_column(JSON)

    institution: Mapped["Institution | None"] = relationship(back_populates="authors")  # noqa: F821
    papers: Mapped[list["PaperAuthor"]] = relationship(back_populates="author")  # noqa: F821
