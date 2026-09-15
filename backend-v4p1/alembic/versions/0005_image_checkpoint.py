"""per-character image checkpoint."""

import sqlalchemy as sa

from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("influencers") as batch:
        batch.add_column(sa.Column("image_checkpoint", sa.String(200), nullable=True))


def downgrade():
    with op.batch_alter_table("influencers") as batch:
        batch.drop_column("image_checkpoint")
