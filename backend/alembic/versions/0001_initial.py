"""Initial schema, frozen independently of application models."""

from alembic import op
import sqlalchemy as sa

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "influencers",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("bible", sa.JSON, nullable=False),
        sa.Column("version", sa.Integer, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "bible_versions",
        sa.Column("influencer_id", sa.String(36), sa.ForeignKey("influencers.id"), primary_key=True),
        sa.Column("version", sa.Integer, primary_key=True),
        sa.Column("bible", sa.JSON, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "jobs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("influencer_id", sa.String(36), sa.ForeignKey("influencers.id"), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("request", sa.JSON, nullable=False),
        sa.Column("character_snapshot", sa.JSON, nullable=False),
        sa.Column("result", sa.JSON),
        sa.Column("error", sa.Text),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_jobs_status", "jobs", ["status"])
    op.create_table(
        "assets",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("job_id", sa.String(36), sa.ForeignKey("jobs.id"), nullable=False),
        sa.Column("filename", sa.String(120), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("media_type", sa.String(60), nullable=False),
    )
    op.create_index("ix_assets_job_id", "assets", ["job_id"])
    op.create_table(
        "reviews",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("job_id", sa.String(36), sa.ForeignKey("jobs.id"), nullable=False),
        sa.Column("decision", sa.String(24), nullable=False),
        sa.Column("note", sa.Text, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade():
    for name in ("reviews", "assets", "jobs", "bible_versions", "influencers"):
        op.drop_table(name)
