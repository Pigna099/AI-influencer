"""image library: trash (soft delete)."""

import sqlalchemy as sa

from alembic import op

revision = "0028"
down_revision = "0027"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("image_library") as batch:
        batch.add_column(sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index("ix_image_library_deleted_at", "image_library", ["deleted_at"])


def downgrade():
    op.drop_index("ix_image_library_deleted_at", table_name="image_library")
    with op.batch_alter_table("image_library") as batch:
        batch.drop_column("deleted_at")
