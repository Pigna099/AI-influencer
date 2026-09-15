import uuid
from datetime import UTC, datetime

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Index, Integer, String, Text, create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker
from sqlalchemy.types import TypeDecorator

from .config import settings


def now():
    return datetime.now(UTC)


def identifier():
    return str(uuid.uuid4())


class UTCDateTime(TypeDecorator):
    """SQLite drops timezone information; timestamps sent to browsers must remain UTC."""

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_result_value(self, value, dialect):
        return value.replace(tzinfo=UTC) if value is not None and value.tzinfo is None else value


class Base(DeclarativeBase):
    pass


class Influencer(Base):
    __tablename__ = "influencers"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=identifier)
    name: Mapped[str] = mapped_column(String(120))
    bible: Mapped[dict] = mapped_column(JSON)
    version: Mapped[int] = mapped_column(Integer, default=1)
    avatar_filename: Mapped[str | None] = mapped_column(String(120), nullable=True)
    image_checkpoint: Mapped[str | None] = mapped_column(String(200), nullable=True)
    image_style: Mapped[str | None] = mapped_column(String(16), nullable=True)
    ppv_enabled: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0")
    ppv_price_cents: Mapped[int] = mapped_column(Integer, default=500, server_default="500")
    reply_delay_min_seconds: Mapped[int] = mapped_column(Integer, default=8, server_default="8")
    reply_delay_max_seconds: Mapped[int] = mapped_column(Integer, default=40, server_default="40")
    activity_enabled: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0")
    activity_start_hour: Mapped[int] = mapped_column(Integer, default=9, server_default="9")
    activity_end_hour: Mapped[int] = mapped_column(Integer, default=23, server_default="23")
    activity_days: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=now)


class BibleVersion(Base):
    __tablename__ = "bible_versions"
    influencer_id: Mapped[str] = mapped_column(ForeignKey("influencers.id"), primary_key=True)
    version: Mapped[int] = mapped_column(Integer, primary_key=True)
    bible: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=now)


class Job(Base):
    __tablename__ = "jobs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=identifier)
    influencer_id: Mapped[str] = mapped_column(ForeignKey("influencers.id"))
    status: Mapped[str] = mapped_column(String(24), default="queued", index=True)
    request: Mapped[dict] = mapped_column(JSON)
    character_snapshot: Mapped[dict] = mapped_column(JSON)
    result: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=now)
    started_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)


class Asset(Base):
    __tablename__ = "assets"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=identifier)
    job_id: Mapped[str] = mapped_column(ForeignKey("jobs.id"), index=True)
    filename: Mapped[str] = mapped_column(String(120))
    sha256: Mapped[str] = mapped_column(String(64))
    media_type: Mapped[str] = mapped_column(String(60))


class Review(Base):
    __tablename__ = "reviews"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=identifier)
    job_id: Mapped[str] = mapped_column(ForeignKey("jobs.id"))
    decision: Mapped[str] = mapped_column(String(24))
    note: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=now)


class Fan(Base):
    __tablename__ = "fans"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=identifier)
    name: Mapped[str] = mapped_column(String(120))
    notes: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=now)


class BenchmarkSample(Base):
    __tablename__ = "benchmark_samples"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=identifier)
    batch_id: Mapped[str] = mapped_column(String(36), index=True)
    character_id: Mapped[str] = mapped_column(ForeignKey("influencers.id"))
    fan_id: Mapped[str | None] = mapped_column(ForeignKey("fans.id"), nullable=True)
    model: Mapped[str] = mapped_column(String(120))
    prompt: Mapped[str] = mapped_column(Text)
    response: Mapped[str] = mapped_column(Text, default="")
    metrics: Mapped[dict] = mapped_column(JSON, default=dict)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=now)


class Conversation(Base):
    __tablename__ = "conversations"
    fan_id: Mapped[str | None] = mapped_column(ForeignKey("fans.id"), nullable=True, index=True)
    busy_until: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    memory_status: Mapped[str] = mapped_column(String(24), default="idle", server_default="idle")
    images_enabled: Mapped[bool] = mapped_column(default=True, server_default="1")
    last_read_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=identifier)
    character_id: Mapped[str] = mapped_column(ForeignKey("influencers.id"))
    title: Mapped[str] = mapped_column(String(200))
    model: Mapped[str] = mapped_column(String(120))
    character_snapshot: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=now)
    updated_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)


class ChatMessage(Base):
    __tablename__ = "chat_messages"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=identifier)
    conversation_id: Mapped[str] = mapped_column(ForeignKey("conversations.id"))
    role: Mapped[str] = mapped_column(String(24))
    content: Mapped[str] = mapped_column(Text)
    model: Mapped[str | None] = mapped_column(String(120), nullable=True)
    ollama_metrics: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=now)


class ChatImage(Base):
    __tablename__ = "chat_images"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=identifier)
    message_id: Mapped[str] = mapped_column(ForeignKey("chat_messages.id"), index=True)
    conversation_id: Mapped[str] = mapped_column(ForeignKey("conversations.id"), index=True)
    character_id: Mapped[str] = mapped_column(ForeignKey("influencers.id"), index=True)
    filename: Mapped[str] = mapped_column(String(120))
    sha256: Mapped[str] = mapped_column(String(64))
    media_type: Mapped[str] = mapped_column(String(60), default="image/png")
    prompt: Mapped[str] = mapped_column(Text)
    negative_prompt: Mapped[str] = mapped_column(Text, default="")
    seed: Mapped[int] = mapped_column(Integer)
    nsfw: Mapped[bool] = mapped_column(default=True)
    provider: Mapped[str] = mapped_column(String(24), default="mock")
    price_cents: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    unlocked_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=now)


class ScheduledReply(Base):
    __tablename__ = "scheduled_replies"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=identifier)
    conversation_id: Mapped[str] = mapped_column(ForeignKey("conversations.id"), index=True)
    character_id: Mapped[str] = mapped_column(ForeignKey("influencers.id"))
    kind: Mapped[str] = mapped_column(String(16), default="reply")
    content: Mapped[str | None] = mapped_column(Text, nullable=True)
    absence_hours: Mapped[int] = mapped_column(Integer, default=48)
    deliver_at: Mapped[datetime] = mapped_column(UTCDateTime(), index=True)
    status: Mapped[str] = mapped_column(String(16), default="scheduled", index=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    message_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    source_message_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=now)
    sent_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)


class SimulatedPayment(Base):
    __tablename__ = "simulated_payments"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=identifier)
    chat_image_id: Mapped[str] = mapped_column(ForeignKey("chat_images.id"), index=True)
    conversation_id: Mapped[str] = mapped_column(ForeignKey("conversations.id"), index=True)
    fan_id: Mapped[str | None] = mapped_column(ForeignKey("fans.id"), nullable=True)
    amount_cents: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=now)


class ImageLibrary(Base):
    __tablename__ = "image_library"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=identifier)
    character_id: Mapped[str] = mapped_column(ForeignKey("influencers.id"), index=True)
    filename: Mapped[str] = mapped_column(String(120))
    sha256: Mapped[str] = mapped_column(String(64), index=True)
    phash: Mapped[str] = mapped_column(String(16), default="")
    prompt: Mapped[str] = mapped_column(Text)
    negative_prompt: Mapped[str] = mapped_column(Text, default="")
    caption: Mapped[str] = mapped_column(Text, default="")
    tags: Mapped[list] = mapped_column(JSON, default=list)
    checkpoint: Mapped[str | None] = mapped_column(String(200), nullable=True)
    loras: Mapped[list] = mapped_column(JSON, default=list)
    seed: Mapped[int] = mapped_column(Integer, default=0)
    style: Mapped[str] = mapped_column(String(16), default="real")
    status: Mapped[str] = mapped_column(String(16), default="draft", index=True)
    rating: Mapped[int] = mapped_column(Integer, default=0)
    source: Mapped[str] = mapped_column(String(16), default="playground")
    used_count: Mapped[int] = mapped_column(Integer, default=0)
    embedding: Mapped[list] = mapped_column(JSON, default=list)
    embedding_model: Mapped[str] = mapped_column(String(120), default="")
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=now)
    updated_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)


class DatasetSource(Base):
    __tablename__ = "dataset_sources"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=identifier)
    name: Mapped[str] = mapped_column(String(120))
    kind: Mapped[str] = mapped_column(String(16))
    reference: Mapped[str] = mapped_column(Text, default="")
    character_id: Mapped[str | None] = mapped_column(ForeignKey("influencers.id"), nullable=True)
    status: Mapped[str] = mapped_column(String(24), default="pending")
    total: Mapped[int] = mapped_column(Integer, default=0)
    imported: Mapped[int] = mapped_column(Integer, default=0)
    classified: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=now)
    updated_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)


class DatasetImage(Base):
    __tablename__ = "dataset_images"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=identifier)
    source_id: Mapped[str] = mapped_column(ForeignKey("dataset_sources.id"), index=True)
    filename: Mapped[str] = mapped_column(String(200))
    sha256: Mapped[str] = mapped_column(String(64), index=True)
    kind: Mapped[str] = mapped_column(String(8), default="image", server_default="image")
    thumb_filename: Mapped[str | None] = mapped_column(String(200), nullable=True)
    width: Mapped[int] = mapped_column(Integer, default=0)
    height: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(16), default="pending", index=True)
    caption: Mapped[str] = mapped_column(Text, default="")
    details: Mapped[dict] = mapped_column(JSON, default=dict)
    tags: Mapped[list] = mapped_column(JSON, default=list)
    embedding: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=now)
    updated_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)


class Memory(Base):
    __tablename__ = "memories"
    fan_id: Mapped[str | None] = mapped_column(ForeignKey("fans.id"), nullable=True, index=True)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=identifier)
    character_id: Mapped[str] = mapped_column(ForeignKey("influencers.id"))
    content: Mapped[str] = mapped_column(Text)
    category: Mapped[str] = mapped_column(String(32))
    importance: Mapped[int] = mapped_column(Integer)
    embedding: Mapped[dict] = mapped_column(JSON)
    embedding_model: Mapped[str] = mapped_column(String(120))
    source_message_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    active: Mapped[bool] = mapped_column(default=True)
    content_hash: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=now)
    updated_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    last_retrieved_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)


class CharacterLora(Base):
    __tablename__ = "character_loras"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=identifier)
    character_id: Mapped[str] = mapped_column(ForeignKey("influencers.id"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    trigger: Mapped[str] = mapped_column(String(64), default="", server_default="")
    family: Mapped[str] = mapped_column(String(16))
    base_checkpoint: Mapped[str | None] = mapped_column(String(200), nullable=True)
    filename: Mapped[str | None] = mapped_column(String(300), nullable=True)
    artifact_filename: Mapped[str | None] = mapped_column(String(300), nullable=True)
    rank: Mapped[int] = mapped_column(Integer, default=32, server_default="32")
    status: Mapped[str] = mapped_column(String(16), default="draft", server_default="draft", index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0")
    config: Mapped[dict] = mapped_column(JSON, default=dict, server_default="{}")
    metrics: Mapped[dict] = mapped_column(JSON, default=dict, server_default="{}")
    log_path: Mapped[str | None] = mapped_column(String(300), nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=now)
    updated_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)


class PoseReference(Base):
    __tablename__ = "pose_references"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=identifier)
    name: Mapped[str] = mapped_column(String(120), default="", server_default="")
    source: Mapped[str] = mapped_column(String(16), default="dataset", server_default="dataset")
    source_image_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    skeleton_filename: Mapped[str | None] = mapped_column(String(300), nullable=True)
    keypoints: Mapped[list] = mapped_column(JSON, default=list, server_default="[]")
    description: Mapped[str] = mapped_column(Text, default="", server_default="")
    tags: Mapped[list] = mapped_column(JSON, default=list, server_default="[]")
    active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="1", index=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=now)


class LoraDataset(Base):
    __tablename__ = "lora_datasets"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=identifier)
    character_id: Mapped[str] = mapped_column(ForeignKey("influencers.id"), index=True)
    family: Mapped[str] = mapped_column(String(16))
    base_checkpoint: Mapped[str | None] = mapped_column(String(200), nullable=True)
    anchor_image_id: Mapped[str | None] = mapped_column(ForeignKey("image_library.id"), nullable=True)
    trigger: Mapped[str] = mapped_column(String(64), default="", server_default="")
    status: Mapped[str] = mapped_column(String(16), default="draft", server_default="draft", index=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=now)
    updated_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)


class LoraDatasetItem(Base):
    __tablename__ = "lora_dataset_items"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=identifier)
    dataset_id: Mapped[str] = mapped_column(ForeignKey("lora_datasets.id"), index=True)
    image_id: Mapped[str | None] = mapped_column(ForeignKey("image_library.id"), nullable=True)
    pose_ref_id: Mapped[str | None] = mapped_column(ForeignKey("pose_references.id"), nullable=True)
    caption: Mapped[str] = mapped_column(Text, default="", server_default="")
    similarity: Mapped[float] = mapped_column(Float, default=0.0, server_default="0")
    selected: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0")
    seed: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=now)


class TrainingJob(Base):
    __tablename__ = "training_jobs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=identifier)
    character_id: Mapped[str] = mapped_column(ForeignKey("influencers.id"), index=True)
    lora_id: Mapped[str | None] = mapped_column(ForeignKey("character_loras.id"), nullable=True, index=True)
    dataset_id: Mapped[str | None] = mapped_column(ForeignKey("lora_datasets.id"), nullable=True)
    trainer: Mapped[str] = mapped_column(String(24), default="kohya", server_default="kohya")
    status: Mapped[str] = mapped_column(String(16), default="queued", server_default="queued", index=True)
    params: Mapped[dict] = mapped_column(JSON, default=dict, server_default="{}")
    progress: Mapped[dict] = mapped_column(JSON, default=dict, server_default="{}")
    log_path: Mapped[str | None] = mapped_column(String(300), nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    worker: Mapped[str | None] = mapped_column(String(120), nullable=True)
    heartbeat_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=now)
    started_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)


engine = create_engine(
    settings.database_url,
    **(
        {"connect_args": {"check_same_thread": False, "timeout": 30}}
        if settings.database_url.startswith("sqlite")
        else {"pool_pre_ping": True}
    ),
)
Session = sessionmaker(engine, expire_on_commit=False)


def content_hash(text: str) -> str:
    import hashlib

    normalized = text.strip().lower()
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


Index("ix_memories_character_hash", Memory.character_id, Memory.content_hash)
Index("ix_chat_messages_conversation", ChatMessage.conversation_id)
Index("ix_conversations_character", Conversation.character_id)
