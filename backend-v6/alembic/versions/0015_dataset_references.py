"""dataset canonical references: role tag on dataset items."""

import sqlalchemy as sa

from alembic import op

revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("lora_dataset_items") as batch:
        batch.add_column(sa.Column("reference_role", sa.String(24), nullable=True))


def downgrade():
    with op.batch_alter_table("lora_dataset_items") as batch:
        batch.drop_column("reference_role")
