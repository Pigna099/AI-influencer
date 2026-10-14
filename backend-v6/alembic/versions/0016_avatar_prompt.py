"""character identity prompt: the avatar prompt reused for dataset candidates."""

import sqlalchemy as sa

from alembic import op

revision = "0016"
down_revision = "0015"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("influencers") as batch:
        batch.add_column(sa.Column("avatar_prompt", sa.Text(), nullable=True))


def downgrade():
    with op.batch_alter_table("influencers") as batch:
        batch.drop_column("avatar_prompt")
