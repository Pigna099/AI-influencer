"""videos: thumbnail filename."""

import sqlalchemy as sa

from alembic import op

revision = "0018"
down_revision = "0017"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("videos") as batch:
        batch.add_column(sa.Column("thumb_filename", sa.String(160), nullable=True))


def downgrade():
    with op.batch_alter_table("videos") as batch:
        batch.drop_column("thumb_filename")
