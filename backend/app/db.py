import uuid
from datetime import UTC, datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text, create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

from .config import settings


def now():
    return datetime.now(UTC)


def identifier():
    return str(uuid.uuid4())


class Base(DeclarativeBase):
    pass


class Influencer(Base):
    __tablename__ = "influencers"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=identifier)
    name: Mapped[str] = mapped_column(String(120))
    bible: Mapped[dict] = mapped_column(JSON)
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class BibleVersion(Base):
    __tablename__ = "bible_versions"
    influencer_id: Mapped[str] = mapped_column(ForeignKey("influencers.id"), primary_key=True)
    version: Mapped[int] = mapped_column(Integer, primary_key=True)
    bible: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Job(Base):
    __tablename__ = "jobs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=identifier)
    influencer_id: Mapped[str] = mapped_column(ForeignKey("influencers.id"))
    status: Mapped[str] = mapped_column(String(24), default="queued", index=True)
    request: Mapped[dict] = mapped_column(JSON)
    character_snapshot: Mapped[dict] = mapped_column(JSON)
    result: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


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
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


engine = create_engine(
    settings.database_url,
    **(
        {"connect_args": {"check_same_thread": False, "timeout": 30}}
        if settings.database_url.startswith("sqlite")
        else {"pool_pre_ping": True}
    ),
)
Session = sessionmaker(engine, expire_on_commit=False)
