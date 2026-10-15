"""assets: content policy metadata."""

import sqlalchemy as sa

from alembic import op

revision = "0029"
down_revision = "0028"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("image_library") as batch:
        batch.add_column(sa.Column("policy", sa.JSON(), nullable=False, server_default="{}"))
    with op.batch_alter_table("videos") as batch:
        batch.add_column(sa.Column("policy", sa.JSON(), nullable=False, server_default="{}"))


def downgrade():
    with op.batch_alter_table("videos") as batch:
        batch.drop_column("policy")
    with op.batch_alter_table("image_library") as batch:
        batch.drop_column("policy")
