"""unified job system: jobs and job_events."""

import sqlalchemy as sa

from alembic import op

revision = "0023"
down_revision = "0022"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "execution_jobs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("type", sa.String(32), nullable=False),
        sa.Column("state", sa.String(16), nullable=False, server_default="queued"),
        sa.Column("character_id", sa.String(36), nullable=True),
        sa.Column("dataset_id", sa.String(36), nullable=True),
        sa.Column("asset_id", sa.String(36), nullable=True),
        sa.Column("external_id", sa.String(36), nullable=True),
        sa.Column("progress", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("worker", sa.String(120), nullable=True),
        sa.Column("gpu", sa.Integer(), nullable=True),
        sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("idempotency_key", sa.String(120), nullable=True, unique=True),
        sa.Column("error_info", sa.JSON(), nullable=True),
        sa.Column("cancel_requested", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("retry_of", sa.String(36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_execution_jobs_type", "execution_jobs", ["type"])
    op.create_index("ix_execution_jobs_state", "execution_jobs", ["state"])
    op.create_index("ix_execution_jobs_character_id", "execution_jobs", ["character_id"])
    op.create_index("ix_execution_jobs_dataset_id", "execution_jobs", ["dataset_id"])
    op.create_index("ix_execution_jobs_external_id", "execution_jobs", ["external_id"])
    op.create_index("ix_execution_jobs_retry_of", "execution_jobs", ["retry_of"])
    op.create_index("ix_execution_jobs_created_at", "execution_jobs", ["created_at"])

    op.create_table(
        "job_events",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("job_id", sa.String(36), sa.ForeignKey("execution_jobs.id"), nullable=False),
        sa.Column("level", sa.String(16), nullable=False, server_default="info"),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_job_events_job_id", "job_events", ["job_id"])


def downgrade():
    op.drop_table("job_events")
    op.drop_table("execution_jobs")
