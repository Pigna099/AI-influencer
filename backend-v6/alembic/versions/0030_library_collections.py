"""library collections."""

import sqlalchemy as sa

from alembic import op

revision = "0030"
down_revision = "0029"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "library_collections",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("name", sa.String(80), nullable=False, unique=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_table(
        "library_collection_items",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("collection_id", sa.String(36), sa.ForeignKey("library_collections.id"), nullable=False),
        sa.Column("image_id", sa.String(36), sa.ForeignKey("image_library.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_library_collection_items_collection_id", "library_collection_items", ["collection_id"])
    op.create_index("ix_library_collection_items_image_id", "library_collection_items", ["image_id"])


def downgrade():
    op.drop_table("library_collection_items")
    op.drop_table("library_collections")
