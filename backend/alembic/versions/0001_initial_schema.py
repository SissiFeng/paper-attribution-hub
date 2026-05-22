"""Initial schema — all tables via ORM models.

Revision ID: 0001
Revises:
Create Date: 2025-01-01 00:00:00.000000

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Import models so SQLAlchemy registers all tables on Base.metadata,
    # then create_all issues the correct CREATE TABLE statements.
    from app.db import Base
    from app.models import all_models  # noqa: F401

    bind = op.get_bind()
    Base.metadata.create_all(bind=bind)


def downgrade() -> None:
    from app.db import Base
    from app.models import all_models  # noqa: F401

    bind = op.get_bind()
    Base.metadata.drop_all(bind=bind)
