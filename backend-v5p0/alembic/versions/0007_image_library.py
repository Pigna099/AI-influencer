"""per-character image library for the image playground and chat reuse."""

import sqlalchemy as sa

from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "image_library",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("character_id", sa.String(36), sa.ForeignKey("influencers.id"), nullable=False),
        sa.Column("filename", sa.String(120), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("phash", sa.String(16), nullable=False, server_default=""),
        sa.Column("prompt", sa.Text(), nullable=False),
        sa.Column("negative_prompt", sa.Text(), nullable=False, server_default=""),
        sa.Column("caption", sa.Text(), nullable=False, server_default=""),
        sa.Column("tags", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("checkpoint", sa.String(200), nullable=True),
        sa.Column("loras", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("seed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("style", sa.String(16), nullable=False, server_default="real"),
        sa.Column("status", sa.String(16), nullable=False, server_default="draft"),
        sa.Column("rating", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("source", sa.String(16), nullable=False, server_default="playground"),
        sa.Column("used_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("embedding", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("embedding_model", sa.String(120), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_image_library_character_id", "image_library", ["character_id"])
    op.create_index("ix_image_library_sha256", "image_library", ["sha256"])
    op.create_index("ix_image_library_status", "image_library", ["status"])


def downgrade():
    op.drop_index("ix_image_library_status", table_name="image_library")
    op.drop_index("ix_image_library_sha256", table_name="image_library")
    op.drop_index("ix_image_library_character_id", table_name="image_library")
    op.drop_table("image_library")
