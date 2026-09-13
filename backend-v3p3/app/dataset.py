"""Image dataset pipeline: importers, rich vision descriptions, export and profile synthesis."""

import base64
import io
import json
import logging
import re
import time
from pathlib import Path

import httpx
from PIL import Image
from sqlalchemy import delete, func, select

from .char_schemas import CharacterProfile
from .config import settings
from .db import DatasetImage, DatasetSource, Session, now
from .image_library import embed_library_text
from .integrations.ollama import OllamaNotAvailable, chat

logger = logging.getLogger(__name__)

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
VIDEO_EXTENSIONS = {".mp4", ".webm", ".mov", ".m4v"}
TELEGRAM_IMAGE = re.compile(r"background-image:url\('([^']+)'\)")
TELEGRAM_VIDEO = re.compile(
    r"tgme_widget_message_video_thumb[^>]*background-image:url\('([^']+)'\)[\s\S]{0,6000}?<video[^>]+src=\"([^\"]+)\""
)
TELEGRAM_BEFORE = re.compile(r"[?&]before=(\d+)")
TELEGRAM_CDN = re.compile(r"^https?://cdn[^/]*\.(telesco\.pe|telegram\.org)/", re.IGNORECASE)

DESCRIBE_FIELDS = (
    "caption",
    "pose",
    "setting",
    "lighting",
    "scene",
    "outfit",
    "body",
    "skin",
    "camera",
    "mood",
    "art_style",
)
DESCRIBE_SCHEMA = {
    "type": "object",
    "properties": {
        **{field: {"type": "string"} for field in DESCRIBE_FIELDS},
        "minor_apparent": {"type": "boolean"},
        "tags": {"type": "array", "items": {"type": "string"}},
    },
    "required": [*DESCRIBE_FIELDS, "minor_apparent", "tags"],
    "additionalProperties": False,
}


def _cdn_url(url: str) -> str | None:
    """Normalize protocol-relative URLs and keep only Telegram CDN media (skip emoji assets)."""
    if url.startswith("//"):
        url = f"https:{url}"
    return url if TELEGRAM_CDN.match(url) else None


def parse_telegram_page(html: str) -> dict:
    """Extract photo URLs, video entries (url + thumbnail) and the pagination cursor."""
    videos = []
    video_thumbs = set()
    for thumb, video in TELEGRAM_VIDEO.findall(html):
        video_url = _cdn_url(video.replace("\\/", "/"))
        if video_url is None:
            continue
        thumb_url = _cdn_url(thumb.replace("\\/", "/"))
        videos.append({"url": video_url, "thumb": thumb_url})
        if thumb_url:
            video_thumbs.add(thumb_url)
    images = []
    for url in TELEGRAM_IMAGE.findall(html):
        normalized = _cdn_url(url)
        if normalized and normalized not in video_thumbs:
            images.append(normalized)
    before_values = [int(value) for value in TELEGRAM_BEFORE.findall(html)]
    return {"images": images, "videos": videos, "before": min(before_values) if before_values else None}


def _source_dir(source_id: str) -> Path:
    path = (settings.dataset_dir / source_id).resolve()
    path.mkdir(parents=True, exist_ok=True)
    return path


def _suffix(content_type: str | None, data: bytes) -> str:
    mapping = {"image/jpeg": ".jpg", "image/jpg": ".jpg", "image/png": ".png", "image/webp": ".webp"}
    if content_type and content_type.split(";")[0].strip().lower() in mapping:
        return mapping[content_type.split(";")[0].strip().lower()]
    try:
        with Image.open(io.BytesIO(data)) as image:
            return f".{image.format.lower()}" if image.format else ".jpg"
    except OSError:
        return ".jpg"


def download_media(url: str, kind: str = "image") -> tuple[bytes, str] | None:
    limit = settings.dataset_video_max_bytes if kind == "video" else settings.dataset_download_max_bytes
    try:
        with httpx.Client(timeout=120 if kind == "video" else 30, follow_redirects=True) as client:
            response = client.get(url, headers={"User-Agent": "Mozilla/5.0 (dataset-importer)"})
        response.raise_for_status()
        content_type = response.headers.get("content-type", "").split(";")[0].strip().lower()
        allowed = ("video/", "application/octet-stream") if kind == "video" else ("image/",)
        if not content_type.startswith(allowed):
            return None
        data = response.content
        if len(data) > limit:
            return None
        suffix = _suffix(content_type, data) if kind == "image" else ".mp4"
        return data, suffix
    except (httpx.HTTPError, OSError):
        return None


def download_image(url: str) -> tuple[bytes, str] | None:
    return download_media(url, "image")


def store_media(
    db,
    source: DatasetSource,
    data: bytes,
    suffix: str,
    kind: str = "image",
    thumb: tuple[bytes, str] | None = None,
) -> DatasetImage | None:
    import hashlib

    digest = hashlib.sha256(data).hexdigest()
    exists = db.scalar(
        select(DatasetImage.id).where(DatasetImage.source_id == source.id, DatasetImage.sha256 == digest)
    )
    if exists:
        return None
    width, height = 0, 0
    if kind == "image":
        try:
            with Image.open(io.BytesIO(data)) as image:
                width, height = image.size
        except OSError:
            return None
    filename = f"{digest[:24]}{suffix}"
    directory = _source_dir(source.id)
    try:
        (directory / filename).write_bytes(data)
    except OSError:
        return None
    thumb_name = None
    if kind == "video" and thumb is not None:
        thumb_data, thumb_suffix = thumb
        thumb_name = f"{digest[:24]}_thumb{thumb_suffix or '.jpg'}"
        try:
            (directory / thumb_name).write_bytes(thumb_data)
        except OSError:
            thumb_name = None
    item = DatasetImage(
        source_id=source.id,
        filename=filename,
        sha256=digest,
        kind=kind,
        thumb_filename=thumb_name,
        width=width,
        height=height,
        status="ready" if kind == "video" else "pending",
    )
    db.add(item)
    db.flush()
    return item


def store_image(db, source: DatasetSource, data: bytes, suffix: str) -> DatasetImage | None:
    return store_media(db, source, data, suffix, "image")


def media_counts(db, source_id: str) -> tuple[int, int]:
    rows = db.execute(
        select(DatasetImage.kind, func.count())
        .where(DatasetImage.source_id == source_id)
        .group_by(DatasetImage.kind)
    ).all()
    counts = {kind: count for kind, count in rows}
    return counts.get("image", 0), counts.get("video", 0)


def import_urls(source: DatasetSource, reference: str, limit: int, db) -> int:
    count = 0
    for line in reference.splitlines():
        if count >= limit:
            break
        url = line.strip()
        if not url or url.startswith("#"):
            continue
        downloaded = download_image(url)
        if downloaded and store_image(db, source, downloaded[0], downloaded[1]):
            count += 1
    return count


def import_folder(source: DatasetSource, reference: str, limit: int, db) -> int:
    root = Path(reference).expanduser()
    if not root.is_absolute():
        root = settings.dataset_import_dir / reference
    root = root.resolve()
    if not root.is_relative_to(settings.dataset_import_dir.resolve()) or not root.is_dir():
        raise ValueError("Cartella non valida: usa un percorso dentro data/imports")
    count = 0
    for path in sorted(root.rglob("*")):
        if count >= limit:
            break
        suffix = path.suffix.lower()
        if not path.is_file() or suffix not in IMAGE_EXTENSIONS | VIDEO_EXTENSIONS:
            continue
        try:
            data = path.read_bytes()
        except OSError:
            continue
        kind = "video" if suffix in VIDEO_EXTENSIONS else "image"
        if kind == "video" and len(data) > settings.dataset_video_max_bytes:
            continue
        if store_media(db, source, data, suffix, kind):
            count += 1
    return count


def import_telegram(source: DatasetSource, reference: str, limit: int, db) -> int:
    channel = reference.strip().rstrip("/")
    for prefix in ("https://t.me/s/", "https://t.me/", "http://t.me/s/", "http://t.me/", "t.me/s/", "t.me/"):
        channel = channel.removeprefix(prefix)
    channel = channel.lstrip("@")
    if not channel:
        raise ValueError("Canale Telegram non valido")
    seen_images: set[str] = set()
    seen_videos: set[str] = set()
    order_images: list[str] = []
    order_videos: list[tuple[str, str]] = []
    before: int | None = None
    empty_pages = 0
    pages = 0
    with httpx.Client(timeout=30, follow_redirects=True) as client:
        while len(order_images) + len(order_videos) < limit and empty_pages < 4 and pages < 300:
            pages += 1
            params = {"before": before} if before else None
            try:
                response = client.get(f"https://t.me/s/{channel}", params=params)
                response.raise_for_status()
            except httpx.HTTPError as error:
                raise ValueError(f"Canale Telegram non raggiungibile: {error}") from error
            page = parse_telegram_page(response.text)
            new_items = 0
            for url in page["images"]:
                key = url.split("?")[0]
                if key not in seen_images:
                    seen_images.add(key)
                    order_images.append(url)
                    new_items += 1
            for entry in page["videos"]:
                key = entry["url"].split("?")[0]
                if key not in seen_videos:
                    seen_videos.add(key)
                    order_videos.append((entry["url"], entry["thumb"]))
                    new_items += 1
            empty_pages = empty_pages + 1 if new_items == 0 else 0
            next_before = page["before"]
            if next_before is None or (before is not None and next_before >= before):
                break
            before = next_before
            time.sleep(0.4)
    count = 0
    for url in order_images:
        if count >= limit:
            break
        downloaded = download_media(url, "image")
        if downloaded and store_media(db, source, downloaded[0], downloaded[1], "image"):
            count += 1
    for url, thumb_url in order_videos:
        if count >= limit:
            break
        downloaded = download_media(url, "video")
        if downloaded is None:
            continue
        thumb = download_media(thumb_url, "image")
        if store_media(db, source, downloaded[0], downloaded[1], "video", thumb=thumb):
            count += 1
    return count


def run_import(source_id: str, reference: str, limit: int, classify: bool) -> None:
    """Background task: import, then optionally describe every imported image."""
    try:
        with Session.begin() as db:
            source = db.get(DatasetSource, source_id)
            if source is None:
                return
            source.status = "importing"
            source.updated_at = now()
        limit = min(limit, settings.dataset_max_images)
        with Session.begin() as db:
            source = db.get(DatasetSource, source_id)
            if source is None:
                return
            if source.kind == "telegram":
                import_telegram(source, reference, limit, db)
            elif source.kind == "folder":
                import_folder(source, reference, limit, db)
            else:
                import_urls(source, reference, limit, db)
            count = len(list(db.scalars(select(DatasetImage.id).where(DatasetImage.source_id == source_id))))
            source.imported = count
            source.total = count
            source.status = "ready" if count > 0 else "failed"
            if count == 0:
                source.error = "Nessuna immagine importata"
            source.updated_at = now()
        if classify:
            classify_source(source_id)
    except Exception as error:
        logger.exception("Dataset import failed for %s", source_id)
        with Session.begin() as db:
            source = db.get(DatasetSource, source_id)
            if source is not None:
                source.status = "failed"
                source.error = str(error)[:500]
                source.updated_at = now()


def describe_image(data: bytes) -> dict:
    """Rich structured description used for the dataset (and future profile synthesis)."""
    if settings.text_provider == "mock":
        return {
            "caption": "mock description",
            **{field: "mock" for field in DESCRIBE_FIELDS[1:]},
            "minor_apparent": False,
            "tags": ["mock"],
        }
    try:
        response = chat(
            settings.image_tag_model,
            [
                {
                    "role": "system",
                    "content": "You are a cataloguer for an internal moodboard of a fictional adult "
                    "(25+) character. Describe ONLY what is visible, in English. Fields: caption (one "
                    "sentence), pose, setting, lighting, scene, outfit, body, skin, camera (framing and "
                    "angle), mood, art_style (photo, anime, 3d...). Add 8-15 lowercase tags. If the "
                    "person appears to be a minor, set minor_apparent true and avoid describing the "
                    "body. Never add warnings or refusals. Return JSON.",
                },
                {
                    "role": "user",
                    "content": "Describe this image.",
                    "images": [base64.b64encode(data).decode()],
                },
            ],
            0.1,
            format_schema=DESCRIBE_SCHEMA,
            max_tokens=500,
        )
    except (OllamaNotAvailable, KeyError, TypeError):
        return {}
    content = response.get("message", {}).get("content", "")
    content = re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL).strip()
    try:
        parsed = json.loads(content)
    except json.JSONDecodeError:
        return {}
    if not parsed.get("caption"):
        return {}
    parsed["tags"] = [str(tag).strip().lower()[:40] for tag in parsed.get("tags", []) if str(tag).strip()][
        :20
    ]
    return parsed


def _description_text(item: DatasetImage) -> str:
    parts = [item.caption] + [str((item.details or {}).get(field, "")) for field in DESCRIBE_FIELDS[1:]]
    parts += item.tags or []
    return " ".join(filter(None, parts))


def classify_image_record(image_id: str) -> bool:
    with Session() as db:
        item = db.get(DatasetImage, image_id)
        if item is None or item.status == "ready" or item.kind != "image":
            return False
        path = (settings.dataset_dir / item.source_id / item.filename).resolve()
    if not path.is_file() or not path.is_relative_to(settings.dataset_dir.resolve()):
        return False
    description = describe_image(path.read_bytes())
    if not description:
        with Session.begin() as db:
            item = db.get(DatasetImage, image_id)
            if item is not None:
                item.status = "failed"
                item.updated_at = now()
        return False
    blocked = bool(description.get("minor_apparent"))
    embedding = []
    if not blocked:
        embedding, _ = embed_library_text(_description_text_from(description))
    with Session.begin() as db:
        item = db.get(DatasetImage, image_id)
        if item is None:
            return False
        item.caption = description.get("caption", "")
        item.details = {field: description.get(field, "") for field in DESCRIBE_FIELDS[1:]}
        item.tags = description.get("tags", [])
        item.embedding = embedding
        item.status = "blocked" if blocked else "ready"
        item.updated_at = now()
    return True


def _description_text_from(description: dict) -> str:
    parts = [description.get("caption", "")]
    parts += [str(description.get(field, "")) for field in DESCRIBE_FIELDS[1:]]
    parts += description.get("tags", [])
    return " ".join(filter(None, parts))


def classify_source(source_id: str) -> None:
    """Background task: describe every pending image of a source, sequentially."""
    with Session.begin() as db:
        source = db.get(DatasetSource, source_id)
        if source is None or source.status == "classifying":
            return
        source.status = "classifying"
        source.updated_at = now()
    try:
        with Session() as db:
            ids = list(
                db.scalars(
                    select(DatasetImage.id).where(
                        DatasetImage.source_id == source_id,
                        DatasetImage.status == "pending",
                        DatasetImage.kind == "image",
                    )
                )
            )
        for index, image_id in enumerate(ids, start=1):
            classify_image_record(image_id)
            with Session.begin() as db:
                source = db.get(DatasetSource, source_id)
                if source is not None:
                    source.classified = index
                    source.updated_at = now()
        with Session.begin() as db:
            source = db.get(DatasetSource, source_id)
            if source is not None:
                ready = len(
                    list(
                        db.scalars(
                            select(DatasetImage.id).where(
                                DatasetImage.source_id == source_id,
                                DatasetImage.kind == "image",
                                DatasetImage.status.in_(["ready", "blocked", "failed"]),
                            )
                        )
                    )
                )
                source.classified = ready
                source.status = "ready"
                source.updated_at = now()
    except Exception as error:
        logger.exception("Dataset classification failed for %s", source_id)
        with Session.begin() as db:
            source = db.get(DatasetSource, source_id)
            if source is not None:
                source.status = "failed"
                source.error = str(error)[:500]
                source.updated_at = now()


def source_out(source: DatasetSource, images: int | None = None, videos: int = 0) -> dict:
    return {
        "id": source.id,
        "name": source.name,
        "kind": source.kind,
        "reference": source.reference,
        "character_id": source.character_id,
        "status": source.status,
        "total": source.total,
        "imported": source.imported,
        "classified": source.classified,
        "images": images if images is not None else (source.imported or 0),
        "videos": videos,
        "error": source.error,
        "created_at": source.created_at.isoformat(),
        "updated_at": source.updated_at.isoformat() if source.updated_at else None,
    }


def image_out(item: DatasetImage) -> dict:
    return {
        "id": item.id,
        "source_id": item.source_id,
        "filename": item.filename,
        "kind": item.kind,
        "has_thumb": bool(item.thumb_filename),
        "width": item.width,
        "height": item.height,
        "status": item.status,
        "caption": item.caption,
        "details": item.details or {},
        "tags": item.tags or [],
        "created_at": item.created_at.isoformat(),
        "updated_at": item.updated_at.isoformat() if item.updated_at else None,
    }


def export_rows(source_id: str) -> list[dict]:
    with Session() as db:
        items = list(
            db.scalars(
                select(DatasetImage)
                .where(DatasetImage.source_id == source_id, DatasetImage.status == "ready")
                .order_by(DatasetImage.created_at)
            )
        )
    return [
        {
            "id": item.id,
            "kind": item.kind,
            "caption": item.caption,
            **{field: (item.details or {}).get(field, "") for field in DESCRIBE_FIELDS[1:]},
            "tags": item.tags or [],
            "width": item.width,
            "height": item.height,
        }
        for item in items
    ]


def synthesize_profile(source_id: str) -> dict:
    """Draft a character profile from the dataset descriptions of a source."""
    rows = export_rows(source_id)
    if not rows:
        raise ValueError("La fonte non ha immagini classificate")
    if settings.text_provider == "mock":
        return CharacterProfile(
            description="mock dataset profile",
            appearance="mock appearance",
            likes="mock interests",
        ).model_dump()
    sample = rows[:60]
    schema = {
        "type": "object",
        "properties": {name: {"type": "string"} for name in CharacterProfile.model_fields},
        "required": list(CharacterProfile.model_fields),
        "additionalProperties": False,
    }
    try:
        response = chat(
            settings.image_prompt_model,
            [
                {
                    "role": "system",
                    "content": "You design a fictional adult (25+) AI influencer from a moodboard dataset. "
                    "Read the image descriptions and synthesize a coherent character: identity, physical "
                    "appearance, style, interests and tone. Never copy a real person, keep it generic and "
                    "original. Adult only. Output JSON matching the schema, one or two sentences per field, "
                    "language code (it/en) in the language field. This is a draft for human review.",
                },
                {"role": "user", "content": json.dumps(sample, ensure_ascii=False)[:12000]},
            ],
            0.6,
            format_schema=schema,
            max_tokens=2048,
        )
    except (OllamaNotAvailable, KeyError, TypeError) as error:
        raise ValueError(f"Sintesi non riuscita: {error}") from error
    content = response.get("message", {}).get("content", "")
    content = re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL).strip()
    try:
        return CharacterProfile.model_validate_json(content).model_dump()
    except (ValueError, TypeError) as error:
        raise ValueError("Il modello non ha restituito un profilo valido") from error


def delete_source_files(source_id: str) -> None:
    directory = (settings.dataset_dir / source_id).resolve()
    if not directory.is_relative_to(settings.dataset_dir.resolve()) or not directory.is_dir():
        return
    for path in directory.iterdir():
        if path.is_file():
            path.unlink(missing_ok=True)
    directory.rmdir()


def delete_source(source_id: str) -> None:
    with Session.begin() as db:
        db.execute(delete(DatasetImage).where(DatasetImage.source_id == source_id))
        db.execute(delete(DatasetSource).where(DatasetSource.id == source_id))
    delete_source_files(source_id)
