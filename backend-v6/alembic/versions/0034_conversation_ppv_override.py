"""conversations: per-conversation PPV override."""

import sqlalchemy as sa

from alembic import op

revision = "0034"
down_revision = "0033"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("conversations") as batch:
        batch.add_column(sa.Column("ppv_enabled", sa.Boolean(), nullable=True))
        batch.add_column(sa.Column("ppv_price_cents", sa.Integer(), nullable=True))


def downgrade():
    with op.batch_alter_table("conversations") as batch:
        batch.drop_column("ppv_price_cents")
        batch.drop_column("ppv_enabled")
