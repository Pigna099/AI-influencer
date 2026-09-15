"""reply realism: delays, activity hours, scheduled replies and read tracking."""

import sqlalchemy as sa

from alembic import op

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("influencers") as batch:
        batch.add_column(
            sa.Column("reply_delay_min_seconds", sa.Integer(), nullable=False, server_default="8")
        )
        batch.add_column(
            sa.Column("reply_delay_max_seconds", sa.Integer(), nullable=False, server_default="40")
        )
        batch.add_column(
            sa.Column("activity_enabled", sa.Boolean(), nullable=False, server_default=sa.false())
        )
        batch.add_column(sa.Column("activity_start_hour", sa.Integer(), nullable=False, server_default="9"))
        batch.add_column(sa.Column("activity_end_hour", sa.Integer(), nullable=False, server_default="23"))
        batch.add_column(sa.Column("activity_days", sa.JSON(), nullable=False, server_default="[]"))
    with op.batch_alter_table("conversations") as batch:
        batch.add_column(sa.Column("last_read_at", sa.DateTime(timezone=True), nullable=True))
    op.create_table(
        "scheduled_replies",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("conversation_id", sa.String(36), sa.ForeignKey("conversations.id"), nullable=False),
        sa.Column("character_id", sa.String(36), sa.ForeignKey("influencers.id"), nullable=False),
        sa.Column("kind", sa.String(16), nullable=False, server_default="reply"),
        sa.Column("content", sa.Text(), nullable=True),
        sa.Column("absence_hours", sa.Integer(), nullable=False, server_default="48"),
        sa.Column("deliver_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="scheduled"),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("message_id", sa.String(36), nullable=True),
        sa.Column("source_message_id", sa.String(36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_scheduled_replies_conversation_id", "scheduled_replies", ["conversation_id"])
    op.create_index("ix_scheduled_replies_deliver_at", "scheduled_replies", ["deliver_at"])
    op.create_index("ix_scheduled_replies_status", "scheduled_replies", ["status"])


def downgrade():
    op.drop_index("ix_scheduled_replies_status", table_name="scheduled_replies")
    op.drop_index("ix_scheduled_replies_deliver_at", table_name="scheduled_replies")
    op.drop_index("ix_scheduled_replies_conversation_id", table_name="scheduled_replies")
    op.drop_table("scheduled_replies")
    with op.batch_alter_table("conversations") as batch:
        batch.drop_column("last_read_at")
    with op.batch_alter_table("influencers") as batch:
        batch.drop_column("activity_days")
        batch.drop_column("activity_end_hour")
        batch.drop_column("activity_start_hour")
        batch.drop_column("activity_enabled")
        batch.drop_column("reply_delay_max_seconds")
        batch.drop_column("reply_delay_min_seconds")
