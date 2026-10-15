"""assets: content labels (sfw/suggestive/explicit)."""

import sqlalchemy as sa

from alembic import op

revision = "0032"
down_revision = "0031"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("image_library") as batch:
        batch.add_column(
            sa.Column("content_label", sa.String(16), nullable=False, server_default="suggestive")
        )
    with op.batch_alter_table("videos") as batch:
        batch.add_column(
            sa.Column("content_label", sa.String(16), nullable=False, server_default="suggestive")
        )


def downgrade():
    with op.batch_alter_table("videos") as batch:
        batch.drop_column("content_label")
    with op.batch_alter_table("image_library") as batch:
        batch.drop_column("content_label")
