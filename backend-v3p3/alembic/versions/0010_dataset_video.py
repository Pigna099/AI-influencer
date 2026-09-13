"""dataset media kind (image/video) and video thumbnails."""

import sqlalchemy as sa

from alembic import op

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("dataset_images") as batch:
        batch.add_column(sa.Column("kind", sa.String(8), nullable=False, server_default="image"))
        batch.add_column(sa.Column("thumb_filename", sa.String(200), nullable=True))


def downgrade():
    with op.batch_alter_table("dataset_images") as batch:
        batch.drop_column("thumb_filename")
        batch.drop_column("kind")
