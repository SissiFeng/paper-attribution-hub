"""Evidence anchors, personal annotations, comparison matrices and projects."""
from alembic import op
from app.db import Base
from app.models import research  # noqa: F401
from app.services.research_schema import adopt_research_schema, NAMES
revision = '0025'
down_revision = '0024'
branch_labels = depends_on = None


def upgrade():
    adopt_research_schema(op.get_bind(), Base.metadata)


def downgrade():
    for name in reversed(NAMES):
        op.drop_table(name)
