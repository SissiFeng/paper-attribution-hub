"""PAS administrator grants and access-change audit; readers remain private."""
from alembic import op
from app.db import Base
from app.models.access import AdminGrant, AccessAudit
from app.services.access_schema import adopt_access_schema
revision = '0024'
down_revision = '0023'
branch_labels = depends_on = None


def upgrade():
    # The deployed additive overlay may already own these exact tables.
    adopt_access_schema(op.get_bind(), Base.metadata)


def downgrade():
    op.drop_table('pas_access_audit')
    op.drop_table('pas_admin_grants')
