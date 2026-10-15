"""Maintenance: find and remove orphaned media files.

An orphan is a media file on disk that no database row references anymore and
that is older than 24 hours (fresh files may belong to an in-flight write).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

from sqlalchemy import select

from .config import settings
from .db import Asset, ChatImage, ImageLibrary, Influencer, Session, VideoClip

MIN_AGE = timedelta(hours=24)
MEDIA_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".webm", ".mp4"}


def _referenced(db) -> set[str]:
    names: set[str] = set()
    columns = (
        Influencer.avatar_filename,
        ImageLibrary.filename,
        VideoClip.filename,
        VideoClip.thumb_filename,
        ChatImage.filename,
        Asset.filename,
    )
    for column in columns:
        for value in db.scalars(select(column)):
            if value:
                names.add(value)
    return names


def scan_media_orphans(db, reference: datetime | None = None) -> list[Path]:
    moment = reference or datetime.now(UTC)
    media = settings.media_dir
    if not media.is_dir():
        return []
    referenced = _referenced(db)
    orphans: list[Path] = []
    for path in media.iterdir():
        if not path.is_file() or path.suffix.lower() not in MEDIA_SUFFIXES:
            continue
        if path.name in referenced:
            continue
        modified = datetime.fromtimestamp(path.stat().st_mtime, tz=UTC)
        if moment - modified < MIN_AGE:
            continue
        orphans.append(path)
    return orphans


def reconcile_media(delete: bool = False) -> dict:
    with Session() as db:
        orphans = scan_media_orphans(db)
    removed = 0
    freed = 0
    if delete:
        for path in orphans:
            try:
                size = path.stat().st_size
                path.unlink()
                removed += 1
                freed += size
            except OSError:
                continue
    return {
        "orphans": len(orphans),
        "removed": removed,
        "freed_bytes": freed,
        "sample": [path.name for path in orphans[:10]],
    }
