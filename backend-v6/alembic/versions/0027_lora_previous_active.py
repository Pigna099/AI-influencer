"""character loras: previous active artifact for rollback."""

import sqlalchemy as sa

from alembic import op

revision = "0027"
down_revision = "0026"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("character_loras") as batch:
        batch.add_column(sa.Column("previous_active_id", sa.String(36), nullable=True))


def downgrade():
    with op.batch_alter_table("character_loras") as batch:
        batch.drop_column("previous_active_id")
