from __future__ import annotations

from sqlalchemy import JSON, Boolean, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class Institution(Base):
    __tablename__ = "institutions"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    canonical_name: Mapped[str] = mapped_column(String, nullable=False, unique=True, index=True)
    aliases: Mapped[list[str] | None] = mapped_column(JSON)
    normalized_aliases: Mapped[list[str] | None] = mapped_column(JSON)
    country: Mapped[str | None] = mapped_column(String)
    city: Mapped[str | None] = mapped_column(String)
    is_partner: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    raw_metadata: Mapped[dict | None] = mapped_column(JSON)

    authors: Mapped[list["Author"]] = relationship(back_populates="institution")  # noqa: F821
