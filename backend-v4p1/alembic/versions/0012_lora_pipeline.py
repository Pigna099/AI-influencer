"""per-character LoRA pipeline: registry, datasets, pose references and training jobs."""

import sqlalchemy as sa

from alembic import op

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "character_loras",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("character_id", sa.String(36), sa.ForeignKey("influencers.id"), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("trigger", sa.String(64), nullable=False, server_default=""),
        sa.Column("family", sa.String(16), nullable=False),
        sa.Column("base_checkpoint", sa.String(200), nullable=True),
        sa.Column("filename", sa.String(300), nullable=True),
        sa.Column("artifact_filename", sa.String(300), nullable=True),
        sa.Column("rank", sa.Integer(), nullable=False, server_default="32"),
        sa.Column("status", sa.String(16), nullable=False, server_default="draft"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("config", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("metrics", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("log_path", sa.String(300), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_character_loras_character_id", "character_loras", ["character_id"])
    op.create_index("ix_character_loras_status", "character_loras", ["status"])

    op.create_table(
        "pose_references",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("name", sa.String(120), nullable=False, server_default=""),
        sa.Column("source", sa.String(16), nullable=False, server_default="dataset"),
        sa.Column("source_image_id", sa.String(36), nullable=True),
        sa.Column("skeleton_filename", sa.String(300), nullable=True),
        sa.Column("keypoints", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("tags", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_pose_references_active", "pose_references", ["active"])

    op.create_table(
        "lora_datasets",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("character_id", sa.String(36), sa.ForeignKey("influencers.id"), nullable=False),
        sa.Column("family", sa.String(16), nullable=False),
        sa.Column("base_checkpoint", sa.String(200), nullable=True),
        sa.Column("anchor_image_id", sa.String(36), sa.ForeignKey("image_library.id"), nullable=True),
        sa.Column("trigger", sa.String(64), nullable=False, server_default=""),
        sa.Column("status", sa.String(16), nullable=False, server_default="draft"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_lora_datasets_character_id", "lora_datasets", ["character_id"])
    op.create_index("ix_lora_datasets_status", "lora_datasets", ["status"])

    op.create_table(
        "lora_dataset_items",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("dataset_id", sa.String(36), sa.ForeignKey("lora_datasets.id"), nullable=False),
        sa.Column("image_id", sa.String(36), sa.ForeignKey("image_library.id"), nullable=True),
        sa.Column("pose_ref_id", sa.String(36), sa.ForeignKey("pose_references.id"), nullable=True),
        sa.Column("caption", sa.Text(), nullable=False, server_default=""),
        sa.Column("similarity", sa.Float(), nullable=False, server_default="0"),
        sa.Column("selected", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("seed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_lora_dataset_items_dataset_id", "lora_dataset_items", ["dataset_id"])

    op.create_table(
        "training_jobs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("character_id", sa.String(36), sa.ForeignKey("influencers.id"), nullable=False),
        sa.Column("lora_id", sa.String(36), sa.ForeignKey("character_loras.id"), nullable=True),
        sa.Column("dataset_id", sa.String(36), sa.ForeignKey("lora_datasets.id"), nullable=True),
        sa.Column("trainer", sa.String(24), nullable=False, server_default="kohya"),
        sa.Column("status", sa.String(16), nullable=False, server_default="queued"),
        sa.Column("params", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("progress", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("log_path", sa.String(300), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("worker", sa.String(120), nullable=True),
        sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_training_jobs_character_id", "training_jobs", ["character_id"])
    op.create_index("ix_training_jobs_status", "training_jobs", ["status"])
    op.create_index("ix_training_jobs_lora_id", "training_jobs", ["lora_id"])


def downgrade():
    op.drop_index("ix_training_jobs_lora_id", table_name="training_jobs")
    op.drop_index("ix_training_jobs_status", table_name="training_jobs")
    op.drop_index("ix_training_jobs_character_id", table_name="training_jobs")
    op.drop_table("training_jobs")
    op.drop_index("ix_lora_dataset_items_dataset_id", table_name="lora_dataset_items")
    op.drop_table("lora_dataset_items")
    op.drop_index("ix_lora_datasets_status", table_name="lora_datasets")
    op.drop_index("ix_lora_datasets_character_id", table_name="lora_datasets")
    op.drop_table("lora_datasets")
    op.drop_index("ix_pose_references_active", table_name="pose_references")
    op.drop_table("pose_references")
    op.drop_index("ix_character_loras_status", table_name="character_loras")
    op.drop_index("ix_character_loras_character_id", table_name="character_loras")
    op.drop_table("character_loras")
