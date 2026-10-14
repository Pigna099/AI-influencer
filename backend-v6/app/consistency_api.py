"""Character consistency check: a vision model compares every picture against the character references."""

import base64
import io
import logging

from fastapi import APIRouter, Depends, HTTPException
from PIL import Image
from pydantic import Field
from sqlalchemy import select

from .auth import authorize
from .char_schemas import StrictModel
from .config import settings
from .db import ImageLibrary, Influencer, LoraDataset, LoraDatasetItem, Session
from .integrations.text import OllamaNotAvailable, vision_json

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["Consistency"], dependencies=[Depends(authorize)])

SCORE_SCHEMA = {
    "type": "object",
    "properties": {
        "score": {"type": "integer", "minimum": 0, "maximum": 100},
        "same_person": {"type": "boolean"},
        "reason": {"type": "string"},
    },
    "required": ["score", "same_person", "reason"],
    "additionalProperties": False,
}

PROMPT = (
    "You are checking character consistency for a fictional adult (25+) influencer dataset. "
    "The FIRST image is the reference identity. The SECOND image is a candidate. "
    "Compare face, hair, body and overall identity. Return JSON only: "
    '{"score": 0-100 (100 = identical person), "same_person": true/false, "reason": "max 12 words"}'
)


class ConsistencyInput(StrictModel):
    dataset_id: str | None = None
    limit: int = Field(default=20, ge=1, le=80)
    threshold: int = Field(default=60, ge=0, le=100)


def _required(db, model, item_id):
    item = db.get(model, item_id)
    if item is None:
        raise HTTPException(404, "Item not found")
    return item


def resize_jpeg(data: bytes, max_side: int = 448) -> str:
    """Downscale any image to a small JPEG and return it base64-encoded."""
    with Image.open(io.BytesIO(data)) as image:
        image = image.convert("RGB")
        image.thumbnail((max_side, max_side))
        buffer = io.BytesIO()
        image.save(buffer, format="JPEG", quality=88)
    return base64.b64encode(buffer.getvalue()).decode()


def _reference_image(db, character: Influencer, dataset: LoraDataset | None) -> tuple[str, str]:
    """Return (base64 image, description) preferring canonical dataset references, then the avatar."""
    if dataset is not None:
        rows = db.execute(
            select(ImageLibrary)
            .join(LoraDatasetItem, LoraDatasetItem.image_id == ImageLibrary.id)
            .where(LoraDatasetItem.dataset_id == dataset.id, LoraDatasetItem.reference_role.is_not(None))
            .limit(1)
        ).scalar()
        if rows is not None:
            path = settings.media_dir / rows.filename
            if path.is_file():
                return resize_jpeg(path.read_bytes()), f"canonical reference ({rows.filename})"
    if character.avatar_filename:
        path = settings.media_dir / character.avatar_filename
        if path.is_file():
            return resize_jpeg(path.read_bytes()), "profile picture"
    raise HTTPException(400, "A profile picture or a canonical reference is required for the comparison")


def _candidates(db, character: Influencer, dataset: LoraDataset | None, limit: int):
    if dataset is not None:
        rows = db.execute(
            select(ImageLibrary)
            .join(LoraDatasetItem, LoraDatasetItem.image_id == ImageLibrary.id)
            .where(LoraDatasetItem.dataset_id == dataset.id)
            .order_by(LoraDatasetItem.created_at.desc())
            .limit(limit)
        ).scalars().all()
        return list(rows)
    return list(
        db.scalars(
            select(ImageLibrary)
            .where(ImageLibrary.character_id == character.id)
            .order_by(ImageLibrary.status.desc(), ImageLibrary.created_at.desc())
            .limit(limit)
        )
    )


@router.post("/characters/{character_id}/consistency-check")
def consistency_check(character_id: str, body: ConsistencyInput):
    """Compare images against the character reference with a vision model and flag incoherent ones."""
    with Session() as db:
        character = _required(db, Influencer, character_id)
        dataset = None
        if body.dataset_id:
            dataset = _required(db, LoraDataset, body.dataset_id)
            if dataset.character_id != character_id:
                raise HTTPException(400, "The dataset belongs to another character")
        reference_b64, reference_label = _reference_image(db, character, dataset)
        candidates = _candidates(db, character, dataset, body.limit)
        if not candidates:
            raise HTTPException(400, "No images to check")

    model = settings.consistency_model
    results: list[dict] = []
    errors = 0
    for item in candidates:
        path = settings.media_dir / item.filename
        if not path.is_file():
            continue
        try:
            candidate_b64 = resize_jpeg(path.read_bytes())
            verdict = vision_json(model, PROMPT, [reference_b64, candidate_b64], schema=SCORE_SCHEMA, max_tokens=120)
        except (OllamaNotAvailable, OSError, ValueError) as error:
            logger.info("consistency check failed for %s: %s", item.filename, error)
            errors += 1
            continue
        score = int(verdict.get("score", 0) or 0)
        results.append(
            {
                "image_id": item.id,
                "filename": item.filename,
                "caption": (item.caption or item.prompt or "")[:120],
                "status": item.status,
                "score": max(0, min(100, score)),
                "same_person": bool(verdict.get("same_person")),
                "reason": str(verdict.get("reason") or "")[:160],
            }
        )
    results.sort(key=lambda entry: entry["score"])
    flagged = [entry for entry in results if entry["score"] < body.threshold or not entry["same_person"]]
    return {
        "reference": reference_label,
        "model": model,
        "threshold": body.threshold,
        "checked": len(results),
        "errors": errors,
        "flagged_count": len(flagged),
        "results": results,
    }
