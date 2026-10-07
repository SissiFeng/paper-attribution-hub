"""Add evidence-grounded chat sessions and messages.

Revision ID: 0021
Revises: 0020
Create Date: 2026-08-20
"""

from __future__ import annotations

from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "0021"
down_revision: Union[str, None] = "0020"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # The isolated reading deployment on revision 0018 can create these tables
    # before the complete application migration chain is promoted.
    if sa.inspect(op.get_bind()).has_table('chat_sessions'):
        from app.db import Base
        from app.services.reading_schema import validate_reading_schema
        validate_reading_schema(op.get_bind(), Base.metadata)
        return
    op.create_table(
        "chat_sessions",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("title", sa.String(length=160), nullable=True),
        sa.Column("scope", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_chat_sessions_created_at", "chat_sessions", ["created_at"])
    op.create_index("ix_chat_sessions_updated_at", "chat_sessions", ["updated_at"])

    op.create_table(
        "chat_messages",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("session_id", sa.String(), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("role", sa.String(length=16), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("answer_kind", sa.String(length=32), nullable=True),
        sa.Column("model", sa.String(length=120), nullable=True),
        sa.Column("tool_name", sa.String(length=80), nullable=True),
        sa.Column("sources", sa.JSON(), nullable=False),
        sa.Column("audit", sa.JSON(), nullable=False),
        sa.Column("scope", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["session_id"], ["chat_sessions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "session_id", "ordinal", name="uq_chat_messages_session_ordinal"
        ),
    )
    op.create_index("ix_chat_messages_session_id", "chat_messages", ["session_id"])
    op.create_index("ix_chat_messages_created_at", "chat_messages", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_chat_messages_created_at", table_name="chat_messages")
    op.drop_index("ix_chat_messages_session_id", table_name="chat_messages")
    op.drop_table("chat_messages")
    op.drop_index("ix_chat_sessions_updated_at", table_name="chat_sessions")
    op.drop_index("ix_chat_sessions_created_at", table_name="chat_sessions")
    op.drop_table("chat_sessions")
