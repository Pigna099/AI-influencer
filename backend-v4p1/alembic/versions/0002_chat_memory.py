"""Add chat, memory, and character schemas."""

import sqlalchemy as sa

from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "conversations",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("character_id", sa.String(36), sa.ForeignKey("influencers.id"), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("model", sa.String(120), nullable=False),
        sa.Column("character_snapshot", sa.JSON, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_conversations_character", "conversations", ["character_id"])

    op.create_table(
        "chat_messages",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("conversation_id", sa.String(36), sa.ForeignKey("conversations.id"), nullable=False),
        sa.Column("role", sa.String(24), nullable=False),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("model", sa.String(120)),
        sa.Column("ollama_metrics", sa.JSON),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_chat_messages_conversation", "chat_messages", ["conversation_id"])

    op.create_table(
        "memories",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("character_id", sa.String(36), sa.ForeignKey("influencers.id"), nullable=False),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("category", sa.String(32), nullable=False),
        sa.Column("importance", sa.Integer, nullable=False),
        sa.Column("embedding", sa.JSON, nullable=False),
        sa.Column("embedding_model", sa.String(120), nullable=False),
        sa.Column("source_message_id", sa.String(36)),
        sa.Column("active", sa.Boolean, nullable=False, default=True),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True)),
        sa.Column("last_retrieved_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_memories_character_hash", "memories", ["character_id", "content_hash"])


def downgrade():
    op.drop_index("ix_memories_character_hash", table_name="memories")
    op.drop_table("memories")
    op.drop_index("ix_chat_messages_conversation", table_name="chat_messages")
    op.drop_table("chat_messages")
    op.drop_index("ix_conversations_character", table_name="conversations")
    op.drop_table("conversations")
