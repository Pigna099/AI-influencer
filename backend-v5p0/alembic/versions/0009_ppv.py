"""simulated PPV: paid chat images and unlock payments."""

import sqlalchemy as sa

from alembic import op

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("influencers") as batch:
        batch.add_column(sa.Column("ppv_enabled", sa.Boolean(), nullable=False, server_default=sa.false()))
        batch.add_column(sa.Column("ppv_price_cents", sa.Integer(), nullable=False, server_default="500"))
    with op.batch_alter_table("chat_images") as batch:
        batch.add_column(sa.Column("price_cents", sa.Integer(), nullable=False, server_default="0"))
        batch.add_column(sa.Column("unlocked_at", sa.DateTime(timezone=True), nullable=True))
    op.create_table(
        "simulated_payments",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("chat_image_id", sa.String(36), sa.ForeignKey("chat_images.id"), nullable=False),
        sa.Column("conversation_id", sa.String(36), sa.ForeignKey("conversations.id"), nullable=False),
        sa.Column("fan_id", sa.String(36), sa.ForeignKey("fans.id"), nullable=True),
        sa.Column("amount_cents", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_simulated_payments_chat_image_id", "simulated_payments", ["chat_image_id"])
    op.create_index("ix_simulated_payments_conversation_id", "simulated_payments", ["conversation_id"])


def downgrade():
    op.drop_index("ix_simulated_payments_conversation_id", table_name="simulated_payments")
    op.drop_index("ix_simulated_payments_chat_image_id", table_name="simulated_payments")
    op.drop_table("simulated_payments")
    with op.batch_alter_table("chat_images") as batch:
        batch.drop_column("unlocked_at")
        batch.drop_column("price_cents")
    with op.batch_alter_table("influencers") as batch:
        batch.drop_column("ppv_price_cents")
        batch.drop_column("ppv_enabled")
