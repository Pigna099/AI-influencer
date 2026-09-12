"""playground_v3: fan isolation, chat leases and persistent benchmark samples."""

import sqlalchemy as sa

from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade():
    fans = op.create_table(
        "fans",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("notes", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.bulk_insert(
        fans,
        [
            {
                "id": "legacy",
                "name": "Archivio v2",
                "notes": "Chat e ricordi precedenti alla separazione dei fan. Non usarli per misurare l’isolamento dei nuovi account.",
            },
            {
                "id": "demo-luca",
                "name": "Luca · fan curioso",
                "notes": "Adulto, 29 anni. Test: raccontagli che ami il jazz e che il tuo cane si chiama Milo. Apri una nuova chat e verifica il ricordo.",
            },
            {
                "id": "demo-sofia",
                "name": "Sofia · fan abituale",
                "notes": "Adulta, 31 anni. Test: preferisci il trekking e hai un gatto chiamato Nori. Non deve confondere questi dettagli con quelli di Luca.",
            },
            {
                "id": "demo-marco",
                "name": "Marco · fan di ritorno",
                "notes": "Adulto, 35 anni. Simula 48 ore di silenzio. Valuta iniziativa, naturalezza e rispetto quando dici che non vuoi comprare nulla.",
            },
        ],
    )
    with op.batch_alter_table("conversations") as batch:
        batch.add_column(sa.Column("fan_id", sa.String(36), nullable=True))
        batch.create_foreign_key("fk_conversations_fan", "fans", ["fan_id"], ["id"])
        batch.create_index("ix_conversations_fan_id", ["fan_id"])
        batch.add_column(sa.Column("busy_until", sa.DateTime(timezone=True), nullable=True))
        batch.add_column(sa.Column("memory_status", sa.String(24), nullable=False, server_default="idle"))
    with op.batch_alter_table("memories") as batch:
        batch.add_column(sa.Column("fan_id", sa.String(36), nullable=True))
        batch.create_foreign_key("fk_memories_fan", "fans", ["fan_id"], ["id"])
        batch.create_index("ix_memories_fan_id", ["fan_id"])
    op.execute("UPDATE conversations SET fan_id = 'legacy'")
    op.execute("UPDATE memories SET fan_id = 'legacy'")
    op.create_table(
        "benchmark_samples",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("batch_id", sa.String(36), nullable=False),
        sa.Column("character_id", sa.String(36), sa.ForeignKey("influencers.id"), nullable=False),
        sa.Column("fan_id", sa.String(36), sa.ForeignKey("fans.id"), nullable=True),
        sa.Column("model", sa.String(120), nullable=False),
        sa.Column("prompt", sa.Text(), nullable=False),
        sa.Column("response", sa.Text(), nullable=False),
        sa.Column("metrics", sa.JSON(), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_benchmark_samples_batch_id", "benchmark_samples", ["batch_id"])


def downgrade():
    op.drop_table("benchmark_samples")
    with op.batch_alter_table("memories") as batch:
        batch.drop_index("ix_memories_fan_id")
        batch.drop_constraint("fk_memories_fan", type_="foreignkey")
        batch.drop_column("fan_id")
    with op.batch_alter_table("conversations") as batch:
        batch.drop_index("ix_conversations_fan_id")
        batch.drop_constraint("fk_conversations_fan", type_="foreignkey")
        batch.drop_column("fan_id")
        batch.drop_column("busy_until")
        batch.drop_column("memory_status")
    op.drop_table("fans")
