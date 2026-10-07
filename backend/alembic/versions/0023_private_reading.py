"""Private readers, browser sessions, bookmarks and conversation access.

Existing chats intentionally retain NULL owners and cannot be claimed by a reader.
"""
import sqlalchemy as sa
from alembic import op

revision = '0023'
down_revision = '0022'
branch_labels = depends_on = None


def upgrade():
    if sa.inspect(op.get_bind()).has_table('pas_readers'):
        from app.db import Base
        from app.services.reading_schema import validate_reading_schema
        validate_reading_schema(op.get_bind(), Base.metadata)
        return
    op.create_table('pas_readers',
        sa.Column('id', sa.String(), primary_key=True),
        sa.Column('workspace_id', sa.String(), nullable=False),
        sa.Column('slack_user_id', sa.String(), nullable=False),
        sa.Column('name', sa.String(160), nullable=False),
        sa.Column('active', sa.Boolean(), nullable=False),
        sa.UniqueConstraint('workspace_id', 'slack_user_id'))
    op.create_index('ix_pas_readers_workspace_id', 'pas_readers', ['workspace_id'])
    op.create_table('pas_reader_sessions',
        sa.Column('token_hash', sa.String(64), primary_key=True),
        sa.Column('reader_id', sa.String(), sa.ForeignKey('pas_readers.id'), nullable=False),
        sa.Column('expires', sa.Integer(), nullable=False))
    op.create_index('ix_pas_reader_sessions_reader_id', 'pas_reader_sessions', ['reader_id'])
    op.create_table('pas_bookmarks',
        sa.Column('reader_id', sa.String(), sa.ForeignKey('pas_readers.id'), primary_key=True),
        sa.Column('paper_id', sa.String(), sa.ForeignKey('papers.id'), primary_key=True),
        sa.Column('note', sa.Text(), nullable=False),
        sa.Column('saved_at', sa.Integer(), nullable=False))
    # Batch operations keep the migration reversible on SQLite as well as PostgreSQL.
    with op.batch_alter_table('chat_sessions') as batch:
        batch.add_column(sa.Column('owner_id', sa.String(), nullable=True))
        batch.add_column(sa.Column('workspace_id', sa.String(), nullable=True))
        batch.add_column(sa.Column('shared', sa.Boolean(), nullable=False, server_default=sa.false()))
        batch.create_foreign_key('fk_chat_owner', 'pas_readers', ['owner_id'], ['id'])
        batch.create_index('ix_chat_sessions_owner_id', ['owner_id'])
        batch.create_index('ix_chat_sessions_workspace_id', ['workspace_id'])
    with op.batch_alter_table('chat_messages') as batch:
        batch.add_column(sa.Column('reader_id', sa.String(), nullable=True))
        batch.create_foreign_key('fk_message_reader', 'pas_readers', ['reader_id'], ['id'])
    op.create_table('chat_participants',
        sa.Column('session_id', sa.String(), sa.ForeignKey('chat_sessions.id'), primary_key=True),
        sa.Column('reader_id', sa.String(), sa.ForeignKey('pas_readers.id'), primary_key=True))


def downgrade():
    op.drop_table('chat_participants')
    with op.batch_alter_table('chat_messages') as batch:
        batch.drop_constraint('fk_message_reader', type_='foreignkey')
        batch.drop_column('reader_id')
    with op.batch_alter_table('chat_sessions') as batch:
        batch.drop_constraint('fk_chat_owner', type_='foreignkey')
        batch.drop_index('ix_chat_sessions_owner_id')
        batch.drop_index('ix_chat_sessions_workspace_id')
        batch.drop_column('shared')
        batch.drop_column('workspace_id')
        batch.drop_column('owner_id')
    op.drop_table('pas_bookmarks')
    op.drop_table('pas_reader_sessions')
    op.drop_table('pas_readers')
