"""characters: avatar upload validation record."""

import sqlalchemy as sa

from alembic import op

revision = "0035"
down_revision = "0034"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("influencers") as batch:
        batch.add_column(sa.Column("avatar_validation", sa.JSON(), nullable=False, server_default="{}"))


def downgrade():
    with op.batch_alter_table("influencers") as batch:
        batch.drop_column("avatar_validation")
