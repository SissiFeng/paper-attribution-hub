"""Administrative grants are separate from ownership of private reader data."""
from sqlalchemy import ForeignKey, Integer, JSON, String
from sqlalchemy.orm import Mapped, mapped_column
from app.db import Base


class AdminGrant(Base):
    __tablename__ = 'pas_admin_grants'
    reader_id: Mapped[str] = mapped_column(ForeignKey('pas_readers.id'), primary_key=True)


class AccessAudit(Base):
    __tablename__ = 'pas_access_audit'
    id: Mapped[str] = mapped_column(String, primary_key=True)
    workspace_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    actor_id: Mapped[str] = mapped_column(String, nullable=False)
    target_id: Mapped[str] = mapped_column(String, nullable=False)
    action: Mapped[str] = mapped_column(String, nullable=False)
    changes: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[int] = mapped_column(Integer, nullable=False)
