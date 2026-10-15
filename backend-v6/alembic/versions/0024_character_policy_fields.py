"""characters: policy fields (adult age, synthetic declaration, provenance)."""

import sqlalchemy as sa

from alembic import op

revision = "0024"
down_revision = "0023"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("influencers") as batch:
        batch.add_column(sa.Column("age", sa.Integer(), nullable=True))
        batch.add_column(
            sa.Column("synthetic_declared", sa.Boolean(), nullable=False, server_default=sa.false())
        )
        batch.add_column(
            sa.Column("provenance", sa.String(32), nullable=False, server_default="synthetic")
        )


def downgrade():
    with op.batch_alter_table("influencers") as batch:
        batch.drop_column("provenance")
        batch.drop_column("synthetic_declared")
        batch.drop_column("age")
