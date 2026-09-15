"""chat images: character avatar, per-conversation toggle and generated photos."""

import sqlalchemy as sa

from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("influencers") as batch:
        batch.add_column(sa.Column("avatar_filename", sa.String(120), nullable=True))
    with op.batch_alter_table("conversations") as batch:
        batch.add_column(sa.Column("images_enabled", sa.Boolean(), nullable=False, server_default=sa.true()))
    op.create_table(
        "chat_images",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("message_id", sa.String(36), sa.ForeignKey("chat_messages.id"), nullable=False),
        sa.Column("conversation_id", sa.String(36), sa.ForeignKey("conversations.id"), nullable=False),
        sa.Column("character_id", sa.String(36), sa.ForeignKey("influencers.id"), nullable=False),
        sa.Column("filename", sa.String(120), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("media_type", sa.String(60), nullable=False),
        sa.Column("prompt", sa.Text(), nullable=False),
        sa.Column("negative_prompt", sa.Text(), nullable=False),
        sa.Column("seed", sa.Integer(), nullable=False),
        sa.Column("nsfw", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("provider", sa.String(24), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_chat_images_message_id", "chat_images", ["message_id"])
    op.create_index("ix_chat_images_conversation_id", "chat_images", ["conversation_id"])
    op.create_index("ix_chat_images_character_id", "chat_images", ["character_id"])


def downgrade():
    op.drop_index("ix_chat_images_character_id", table_name="chat_images")
    op.drop_index("ix_chat_images_conversation_id", table_name="chat_images")
    op.drop_index("ix_chat_images_message_id", table_name="chat_images")
    op.drop_table("chat_images")
    with op.batch_alter_table("conversations") as batch:
        batch.drop_column("images_enabled")
    with op.batch_alter_table("influencers") as batch:
        batch.drop_column("avatar_filename")
