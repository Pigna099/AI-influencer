"""characters: identity provenance fields (source category, rights, lifecycle, anchor hash)."""

import sqlalchemy as sa

from alembic import op

revision = "0025"
down_revision = "0024"
branch_labels = None
depends_on = None

COLUMNS = (
    ("source_category", sa.String(32), "generated"),
    ("rights_notes", sa.Text(), ""),
    ("source_reference", sa.String(500), ""),
    ("source_hash", sa.String(64), ""),
    ("permitted_uses", sa.String(300), ""),
    ("lifecycle_state", sa.String(24), "active"),
)


def upgrade():
    with op.batch_alter_table("influencers") as batch:
        for name, type_, default in COLUMNS:
            batch.add_column(sa.Column(name, type_, nullable=False, server_default=default))
        batch.add_column(sa.Column("avatar_sha256", sa.String(64), nullable=True))


def downgrade():
    with op.batch_alter_table("influencers") as batch:
        batch.drop_column("avatar_sha256")
        for name, _type, _default in reversed(COLUMNS):
            batch.drop_column(name)
