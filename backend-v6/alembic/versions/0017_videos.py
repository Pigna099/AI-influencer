"""videos: image-to-video clips per character."""

import sqlalchemy as sa

from alembic import op

revision = "0017"
down_revision = "0016"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "videos",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("character_id", sa.String(36), sa.ForeignKey("influencers.id"), nullable=False),
        sa.Column("filename", sa.String(160), nullable=False),
        sa.Column("prompt", sa.Text(), nullable=False),
        sa.Column("negative_prompt", sa.Text(), nullable=False, server_default=""),
        sa.Column("source_image_id", sa.String(36), sa.ForeignKey("image_library.id"), nullable=True),
        sa.Column("model", sa.String(200), nullable=False, server_default=""),
        sa.Column("params", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("status", sa.String(16), nullable=False, server_default="ready"),
        sa.Column("error", sa.Text(), nullable=False, server_default=""),
        sa.Column("seed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_videos_character_id", "videos", ["character_id"])
    op.create_index("ix_videos_status", "videos", ["status"])


def downgrade():
    op.drop_index("ix_videos_status", table_name="videos")
    op.drop_index("ix_videos_character_id", table_name="videos")
    op.drop_table("videos")
