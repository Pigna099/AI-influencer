"""per-character image style (anime or real)."""

import sqlalchemy as sa

from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("influencers") as batch:
        batch.add_column(sa.Column("image_style", sa.String(16), nullable=True))


def downgrade():
    with op.batch_alter_table("influencers") as batch:
        batch.drop_column("image_style")
