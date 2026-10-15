"""characters: per-platform policy checklists."""

import sqlalchemy as sa

from alembic import op

revision = "0033"
down_revision = "0032"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("influencers") as batch:
        batch.add_column(sa.Column("platform_policy", sa.JSON(), nullable=False, server_default="{}"))


def downgrade():
    with op.batch_alter_table("influencers") as batch:
        batch.drop_column("platform_policy")
