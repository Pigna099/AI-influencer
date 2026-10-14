"""chat videos for simulated PPV."""

import sqlalchemy as sa

from alembic import op

revision = "0019"
down_revision = "0018"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "chat_videos",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("message_id", sa.String(36), sa.ForeignKey("chat_messages.id"), nullable=False),
        sa.Column("conversation_id", sa.String(36), sa.ForeignKey("conversations.id"), nullable=False),
        sa.Column("character_id", sa.String(36), sa.ForeignKey("influencers.id"), nullable=False),
        sa.Column("video_id", sa.String(36), sa.ForeignKey("videos.id"), nullable=False),
        sa.Column("prompt", sa.Text(), nullable=False, server_default=""),
        sa.Column("price_cents", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("unlocked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_chat_videos_message_id", "chat_videos", ["message_id"])
    op.create_index("ix_chat_videos_conversation_id", "chat_videos", ["conversation_id"])
    op.create_index("ix_chat_videos_character_id", "chat_videos", ["character_id"])
    op.create_index("ix_chat_videos_video_id", "chat_videos", ["video_id"])
    with op.batch_alter_table("simulated_payments") as batch:
        batch.alter_column("chat_image_id", existing_type=sa.String(36), nullable=True)
        batch.add_column(sa.Column("chat_video_id", sa.String(36), sa.ForeignKey("chat_videos.id"), nullable=True))


def downgrade():
    with op.batch_alter_table("simulated_payments") as batch:
        batch.drop_column("chat_video_id")
        batch.alter_column("chat_image_id", existing_type=sa.String(36), nullable=False)
    op.drop_index("ix_chat_videos_video_id", table_name="chat_videos")
    op.drop_index("ix_chat_videos_character_id", table_name="chat_videos")
    op.drop_index("ix_chat_videos_conversation_id", table_name="chat_videos")
    op.drop_index("ix_chat_videos_message_id", table_name="chat_videos")
    op.drop_table("chat_videos")
