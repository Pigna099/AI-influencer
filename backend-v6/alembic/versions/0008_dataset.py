"""dataset sources and images for the caption dataset pipeline."""

import sqlalchemy as sa

from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "dataset_sources",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("reference", sa.Text(), nullable=False, server_default=""),
        sa.Column("character_id", sa.String(36), sa.ForeignKey("influencers.id"), nullable=True),
        sa.Column("status", sa.String(24), nullable=False, server_default="pending"),
        sa.Column("total", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("imported", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("classified", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_table(
        "dataset_images",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("source_id", sa.String(36), sa.ForeignKey("dataset_sources.id"), nullable=False),
        sa.Column("filename", sa.String(200), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("width", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("height", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("status", sa.String(16), nullable=False, server_default="pending"),
        sa.Column("caption", sa.Text(), nullable=False, server_default=""),
        sa.Column("details", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("tags", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("embedding", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_dataset_images_source_id", "dataset_images", ["source_id"])
    op.create_index("ix_dataset_images_sha256", "dataset_images", ["sha256"])
    op.create_index("ix_dataset_images_status", "dataset_images", ["status"])


def downgrade():
    op.drop_index("ix_dataset_images_status", table_name="dataset_images")
    op.drop_index("ix_dataset_images_sha256", table_name="dataset_images")
    op.drop_index("ix_dataset_images_source_id", table_name="dataset_images")
    op.drop_table("dataset_images")
    op.drop_table("dataset_sources")
