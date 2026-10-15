"""identity runs: multi-angle canonical identity set."""

import sqlalchemy as sa

from alembic import op

revision = "0026"
down_revision = "0025"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "identity_runs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("character_id", sa.String(36), sa.ForeignKey("influencers.id"), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="running"),
        sa.Column("template_version", sa.String(16), nullable=False, server_default="1"),
        sa.Column("anchor_filename", sa.String(160), nullable=False, server_default=""),
        sa.Column("anchor_sha256", sa.String(64), nullable=False, server_default=""),
        sa.Column("model", sa.String(200), nullable=False, server_default=""),
        sa.Column("params", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("override_reason", sa.Text(), nullable=False, server_default=""),
        sa.Column("frozen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_identity_runs_character_id", "identity_runs", ["character_id"])
    op.create_index("ix_identity_runs_status", "identity_runs", ["status"])

    op.create_table(
        "identity_candidates",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("run_id", sa.String(36), sa.ForeignKey("identity_runs.id"), nullable=False),
        sa.Column("image_id", sa.String(36), sa.ForeignKey("image_library.id"), nullable=True),
        sa.Column("angle", sa.String(40), nullable=False),
        sa.Column("seed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("prompt", sa.Text(), nullable=False, server_default=""),
        sa.Column("status", sa.String(16), nullable=False, server_default="draft"),
        sa.Column("scores", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_identity_candidates_run_id", "identity_candidates", ["run_id"])
    op.create_index("ix_identity_candidates_angle", "identity_candidates", ["angle"])
    op.create_index("ix_identity_candidates_status", "identity_candidates", ["status"])


def downgrade():
    op.drop_table("identity_candidates")
    op.drop_table("identity_runs")
