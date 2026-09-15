"""Per-character image library: hashing, vision tagging, embeddings and reuse matching."""

import base64
import io
import json
import re

from PIL import Image, ImageFilter
from sqlalchemy import select, update

from .config import settings
from .db import ImageLibrary, Session, now
from .integrations.ollama import OllamaNotAvailable, chat, cosine_similarity, embed

CLASSIFY_SCHEMA = {
    "type": "object",
    "properties": {
        "caption": {"type": "string"},
        "tags": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["caption", "tags"],
    "additionalProperties": False,
}


def blurred_png(data: bytes, radius: int = 16, scale: float = 0.25) -> bytes:
    """Heavily blurred preview served while a PPV image is locked."""
    with Image.open(io.BytesIO(data)) as image:
        image = image.convert("RGB")
        small = image.resize((max(1, int(image.width * scale)), max(1, int(image.height * scale))))
        blurred = small.filter(ImageFilter.GaussianBlur(radius))
        output = io.BytesIO()
        blurred.save(output, format="PNG")
    return output.getvalue()


def average_hash(data: bytes) -> str:
    """64-bit average hash for near-duplicate detection (no extra dependencies)."""
    try:
        with Image.open(io.BytesIO(data)) as image:
            pixels = list(image.convert("L").resize((8, 8)).tobytes())
    except OSError:
        return ""
    mean = sum(pixels) / len(pixels)
    bits = "".join("1" if pixel >= mean else "0" for pixel in pixels)
    return f"{int(bits, 2):016x}"


def classify_image(data: bytes) -> tuple[str, list[str]]:
    """Caption and tag an image with the configured vision model; best effort."""
    if settings.text_provider == "mock" or not settings.image_tag_model:
        return "", []
    try:
        response = chat(
            settings.image_tag_model,
            [
                {
                    "role": "system",
                    "content": "You are an image cataloguer for a private library of a fictional adult "
                    "(25+) character. Describe only what is visible. Return one short English caption "
                    "(framing, pose, outfit or state of undress, setting, lighting) and 6-12 lowercase "
                    "English tags. Never add warnings or refusals. Return JSON.",
                },
                {
                    "role": "user",
                    "content": "Classify this image.",
                    "images": [base64.b64encode(data).decode()],
                },
            ],
            0.1,
            format_schema=CLASSIFY_SCHEMA,
            max_tokens=300,
        )
    except (OllamaNotAvailable, KeyError, TypeError):
        return "", []
    content = response.get("message", {}).get("content", "")
    content = re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL).strip()
    try:
        parsed = json.loads(content)
    except json.JSONDecodeError:
        return "", []
    caption = str(parsed.get("caption", "")).strip()[:2000]
    tags = [str(tag).strip().lower()[:40] for tag in parsed.get("tags", []) if str(tag).strip()][:15]
    return caption, tags


def library_text(item: ImageLibrary) -> str:
    return " ".join(filter(None, [item.caption, ", ".join(item.tags or []), item.prompt]))


def embed_library_text(text: str) -> tuple[list, str]:
    if not text.strip():
        return [], ""
    try:
        return embed(settings.ollama_embedding_model, text[:4000]), settings.ollama_embedding_model
    except OllamaNotAvailable:
        return [], ""


def lexical_score(query: str, item: ImageLibrary) -> float:
    words = set(re.findall(r"\w{3,}", query.lower()))
    if not words:
        return 0.0
    item_words = set(re.findall(r"\w{3,}", library_text(item).lower()))
    if not item_words:
        return 0.0
    return len(words & item_words) / len(words)


def match_library_image(character_id: str, style: str, scene: str) -> ImageLibrary | None:
    """Best approved image for the requested scene, or None when nothing is close enough."""
    with Session() as db:
        items = list(
            db.scalars(
                select(ImageLibrary)
                .where(
                    ImageLibrary.character_id == character_id,
                    ImageLibrary.style == style,
                    ImageLibrary.status == "approved",
                )
                .order_by(ImageLibrary.used_count, ImageLibrary.rating.desc())
                .limit(300)
            )
        )
    if not items:
        return None
    query_embedding, _ = embed_library_text(scene)
    best, best_score = None, 0.0
    for item in items:
        lexical = lexical_score(scene, item)
        if query_embedding and item.embedding and len(item.embedding) == len(query_embedding):
            score = min(1.0, cosine_similarity(query_embedding, item.embedding) + 0.1 * lexical)
        else:
            score = lexical
        if score > best_score:
            best, best_score = item, score
    if best is None or best_score < settings.image_match_threshold:
        return None
    return best


def mark_used(item_id: str) -> None:
    with Session.begin() as db:
        db.execute(
            update(ImageLibrary)
            .where(ImageLibrary.id == item_id)
            .values(used_count=ImageLibrary.used_count + 1, updated_at=now())
        )


def classify_library_item(item_id: str) -> None:
    """Background task: classify a stored library image and refresh its embedding."""
    with Session() as db:
        item = db.get(ImageLibrary, item_id)
        if item is None:
            return
        path = (settings.media_dir / item.filename).resolve()
    if not path.is_file() or not path.is_relative_to(settings.media_dir.resolve()):
        return
    caption, tags = classify_image(path.read_bytes())
    if not caption and not tags:
        return
    embedding = []
    embedding_model = ""
    with Session.begin() as db:
        current = db.get(ImageLibrary, item_id)
        if current is None:
            return
        if caption:
            current.caption = caption
        if tags:
            current.tags = tags
        embedding, embedding_model = embed_library_text(library_text(current))
        if embedding:
            current.embedding = embedding
            current.embedding_model = embedding_model
        current.updated_at = now()


def library_out(item: ImageLibrary) -> dict:
    return {
        "id": item.id,
        "character_id": item.character_id,
        "filename": item.filename,
        "caption": item.caption,
        "tags": item.tags or [],
        "prompt": item.prompt,
        "negative_prompt": item.negative_prompt,
        "checkpoint": item.checkpoint,
        "loras": item.loras or [],
        "seed": item.seed,
        "style": item.style,
        "status": item.status,
        "rating": item.rating,
        "source": item.source,
        "used_count": item.used_count,
        "created_at": item.created_at.isoformat(),
        "updated_at": item.updated_at.isoformat() if item.updated_at else None,
    }
