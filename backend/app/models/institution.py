from __future__ import annotations

from sqlalchemy import JSON, Boolean, String, event
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.country_normalization import country_keys_v1


class Institution(Base):
    __tablename__ = "institutions"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    canonical_name: Mapped[str] = mapped_column(String, nullable=False, unique=True, index=True)
    aliases: Mapped[list[str] | None] = mapped_column(JSON)
    normalized_aliases: Mapped[list[str] | None] = mapped_column(JSON)
    country: Mapped[str | None] = mapped_column(String)
    country_keys: Mapped[list[str]] = mapped_column(
        JSON,
        default=list,
        nullable=False,
        server_default="[]",
    )
    city: Mapped[str | None] = mapped_column(String)
    is_partner: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    raw_metadata: Mapped[dict | None] = mapped_column(JSON)

    authors: Mapped[list["Author"]] = relationship(back_populates="institution")  # noqa: F821


@event.listens_for(Institution, "before_insert")
@event.listens_for(Institution, "before_update")
def _sync_country_keys(_mapper, _connection, institution: Institution) -> None:
    institution.country_keys = country_keys_v1(institution.country)
