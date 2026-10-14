"""Video playground: image-to-video clips per character (Wan 2.2 I2V + lightx2v)."""

from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import Field
from sqlalchemy import select

from .auth import authorize
from .char_schemas import StrictModel
from .config import settings
from .db import ImageLibrary, Influencer, Session, VideoClip, identifier, now
from .integrations.comfyui import (
    ComfyUIError,
    comfyui_available,
    generate_hunyuan_video,
    generate_ltx_video,
    generate_wan_video,
    get_loras,
    lora_family,
    pick_target,
)

router = APIRouter(prefix="/api", tags=["Video"], dependencies=[Depends(authorize)])

DEFAULT_NEGATIVE = "blurry, low quality, distorted, extra limbs, watermark, text"
VIDEO_MEDIA_TYPES = {".webm": "video/webm", ".mp4": "video/mp4"}


class VideoLora(StrictModel):
    name: str = Field(min_length=1, max_length=300)
    weight: float = Field(default=1.0, ge=0, le=2)


class VideoGenerateInput(StrictModel):
    prompt: str = Field(min_length=1, max_length=2000)
    negative: str | None = Field(default=None, max_length=2000)
    mode: Literal["image", "text"] = "image"
    model: Literal["wan", "ltx-distilled", "ltx-dev", "hunyuan"] = "wan"
    image_id: str | None = None
    loras: list[VideoLora] = Field(default_factory=list, max_length=4)
    width: int = Field(default=832, ge=256, le=1280)
    height: int = Field(default=480, ge=256, le=1280)
    length: int = Field(default=81, ge=25, le=161)
    steps: int = Field(default=4, ge=2, le=30)
    seed: int | None = Field(default=None, ge=0, le=2**31)


def required(db, model, item_id):
    item = db.get(model, item_id)
    if item is None:
        raise HTTPException(404, "Item not found")
    return item


AUTO_LORAS = ("lightx2v", "distilled-lora")


def validate_video_loras(loras: list[VideoLora], model: str) -> list[dict]:
    if not loras:
        return []
    if model == "wan":
        family = "wan"
    elif model == "hunyuan":
        family = "hunyuan"
    else:
        family = "ltx"
    available = set(get_loras())
    result = []
    for lora in loras:
        name = lora.name.strip()
        if ".." in name or name.startswith("/"):
            raise HTTPException(400, f"Invalid LoRA name: {name}")
        if any(marker in name.lower() for marker in AUTO_LORAS):
            raise HTTPException(400, "This LoRA is already applied automatically by the model")
        if lora_family(name) != family:
            raise HTTPException(400, f"LoRA not compatible with the video model: {name}")
        if name not in available:
            raise HTTPException(400, f"LoRA unavailable: {name}")
        result.append({"name": name, "weight": lora.weight})
    return result


def video_out(item: VideoClip) -> dict:
    return {
        "id": item.id,
        "character_id": item.character_id,
        "filename": item.filename,
        "thumb_filename": item.thumb_filename,
        "prompt": item.prompt,
        "negative_prompt": item.negative_prompt,
        "source_image_id": item.source_image_id,
        "model": item.model,
        "params": item.params or {},
        "status": item.status,
        "error": item.error,
        "seed": item.seed,
        "created_at": item.created_at.isoformat(),
    }


@router.get("/characters/{character_id}/videos")
def list_videos(character_id: str, limit: int = 100, offset: int = 0):
    with Session() as db:
        required(db, Influencer, character_id)
        items = db.scalars(
            select(VideoClip)
            .where(VideoClip.character_id == character_id)
            .order_by(VideoClip.created_at.desc())
            .limit(max(1, min(limit, 500)))
            .offset(max(0, offset))
        ).all()
        return [video_out(item) for item in items]


@router.post("/characters/{character_id}/videos", status_code=201)
def generate_video(character_id: str, body: VideoGenerateInput):
    """Image-to-video: the selected library image is the first frame."""
    if not comfyui_available():
        raise HTTPException(503, "ComfyUI is unreachable: start the image service")
    if body.mode == "image" and not body.image_id:
        raise HTTPException(400, "A starting image from the character library is required")
    loras = validate_video_loras(body.loras, body.model)
    width = body.width
    height = body.height
    length = body.length
    if body.model == "hunyuan":
        width = max(256, (width // 32) * 32)
        height = max(256, (height // 32) * 32)
        length = max(9, round((length - 1) / 4) * 4 + 1)
    elif body.model != "wan":
        width = max(256, (width // 32) * 32)
        height = max(256, (height // 32) * 32)
        length = max(9, round((length - 1) / 8) * 8 + 1)
    image_path: Path | None = None
    with Session() as db:
        required(db, Influencer, character_id)
        source = required(db, ImageLibrary, body.image_id) if body.image_id else None
        if source is not None:
            if source.character_id != character_id:
                raise HTTPException(400, "The image belongs to another character")
            candidate = (settings.media_dir / source.filename).resolve()
            if not candidate.is_file() or not candidate.is_relative_to(settings.media_dir.resolve()):
                raise HTTPException(404, "Image file not found")
            image_path = candidate
    try:
        if body.model == "wan":
            data, thumb, meta = generate_wan_video(
                body.prompt,
                body.negative or DEFAULT_NEGATIVE,
                image_path,
                loras=loras,
                width=width,
                height=height,
                length=length,
                steps=body.steps,
                seed=body.seed,
                base_url=pick_target(),
            )
        elif body.model == "hunyuan":
            data, thumb, meta = generate_hunyuan_video(
                body.prompt,
                body.negative or DEFAULT_NEGATIVE,
                image_path,
                loras=loras,
                width=width,
                height=height,
                length=length,
                steps=body.steps,
                seed=body.seed,
                base_url=pick_target(),
            )
        else:
            data, thumb, meta = generate_ltx_video(
                body.prompt,
                body.negative or DEFAULT_NEGATIVE,
                image_path,
                model=body.model,
                loras=loras,
                width=width,
                height=height,
                length=length,
                steps=body.steps,
                seed=body.seed,
                base_url=pick_target(),
            )
    except ComfyUIError as error:
        raise HTTPException(502, f"Video generation failed: {error}") from error
    suffix = ".webm"
    base = identifier()
    filename = f"{base}{suffix}"
    target = settings.media_dir / filename
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)
    thumb_filename = None
    if thumb:
        thumb_filename = f"{base}_thumb.png"
        (settings.media_dir / thumb_filename).write_bytes(thumb)
    with Session.begin() as db:
        item = VideoClip(
            character_id=character_id,
            filename=filename,
            thumb_filename=thumb_filename,
            prompt=body.prompt,
            negative_prompt=body.negative or DEFAULT_NEGATIVE,
            source_image_id=body.image_id if image_path else None,
            model=str(meta.get("model") or ""),
            params=meta,
            status="ready",
            seed=int(meta.get("seed") or 0),
            created_at=now(),
        )
        db.add(item)
        db.flush()
        result = video_out(item)
    return result


@router.get("/videos/{video_id}/file")
def video_file(video_id: str):
    with Session() as db:
        item = required(db, VideoClip, video_id)
        filename = item.filename
    path = (settings.media_dir / filename).resolve()
    if not path.is_file() or not path.is_relative_to(settings.media_dir.resolve()):
        raise HTTPException(404, "Video not found")
    media_type = VIDEO_MEDIA_TYPES.get(path.suffix.lower(), "application/octet-stream")
    return FileResponse(path, media_type=media_type, filename=path.name)


@router.get("/videos/{video_id}/thumb")
def video_thumb(video_id: str):
    with Session() as db:
        item = required(db, VideoClip, video_id)
        thumb = item.thumb_filename
    if not thumb:
        raise HTTPException(404, "Thumbnail unavailable")
    path = (settings.media_dir / thumb).resolve()
    if not path.is_file() or not path.is_relative_to(settings.media_dir.resolve()):
        raise HTTPException(404, "Thumbnail not found")
    return FileResponse(path, media_type="image/png", filename=path.name)


@router.delete("/videos/{video_id}")
def delete_video(video_id: str):
    filenames: list[str] = []
    with Session.begin() as db:
        item = required(db, VideoClip, video_id)
        filenames = [item.filename, item.thumb_filename] if item.thumb_filename else [item.filename]
        db.delete(item)
    for name in filenames:
        path = (settings.media_dir / name).resolve()
        if path.is_relative_to(settings.media_dir.resolve()):
            path.unlink(missing_ok=True)
    return {"deleted": True, "id": video_id}
