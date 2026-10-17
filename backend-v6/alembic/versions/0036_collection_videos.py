"""collections: allow videos."""

import sqlalchemy as sa

from alembic import op

revision = "0036"
down_revision = "0035"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("library_collection_items") as batch:
        batch.alter_column("image_id", existing_type=sa.String(36), nullable=True)
        batch.add_column(sa.Column("video_id", sa.String(36), nullable=True))
    op.create_index("ix_library_collection_items_video_id", "library_collection_items", ["video_id"])


def downgrade():
    op.drop_index("ix_library_collection_items_video_id", table_name="library_collection_items")
    with op.batch_alter_table("library_collection_items") as batch:
        batch.drop_column("video_id")
        batch.alter_column("image_id", existing_type=sa.String(36), nullable=False)
