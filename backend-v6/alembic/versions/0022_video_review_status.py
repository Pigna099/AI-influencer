"""videos: review status (draft/approved/rejected)."""

import sqlalchemy as sa

from alembic import op

revision = "0022"
down_revision = "0021"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("videos") as batch:
        batch.add_column(sa.Column("review_status", sa.String(16), nullable=False, server_default="draft"))
    op.create_index("ix_videos_review_status", "videos", ["review_status"])
    op.execute("UPDATE videos SET review_status = 'approved'")


def downgrade():
    op.drop_index("ix_videos_review_status", table_name="videos")
    with op.batch_alter_table("videos") as batch:
        batch.drop_column("review_status")
