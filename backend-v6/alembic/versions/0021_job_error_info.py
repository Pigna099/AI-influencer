"""training jobs: structured error info."""

import sqlalchemy as sa

from alembic import op

revision = "0021"
down_revision = "0020"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("training_jobs") as batch:
        batch.add_column(sa.Column("error_info", sa.JSON(), nullable=True))


def downgrade():
    with op.batch_alter_table("training_jobs") as batch:
        batch.drop_column("error_info")
