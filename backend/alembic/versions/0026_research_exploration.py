"""Project connections, screening and incremental discovery."""
from alembic import op
from app.db import Base
from app.models import exploration  # noqa: F401
from app.services.exploration_schema import adopt_exploration_schema, NAMES
revision = '0026'
down_revision = '0025'
branch_labels = depends_on = None


def upgrade():
    adopt_exploration_schema(op.get_bind(), Base.metadata)


def downgrade():
    for name in reversed(NAMES):
        op.drop_table(name)
