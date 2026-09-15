"""Dataset API: sources, images, classification, export and profile synthesis."""

import json
from typing import Literal

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from fastapi.responses import FileResponse, Response
from pydantic import Field
from sqlalchemy import select

from .auth import authorize
from .char_schemas import StrictModel
from .config import settings
from .dataset import (
    classification_running,
    classify_source,
    delete_source,
    export_rows,
    image_out,
    media_counts,
    run_import,
    source_out,
    synthesize_profile,
)
from .db import DatasetImage, DatasetSource, Influencer, Session
from .image_library import embed_library_text

router = APIRouter(prefix="/api", tags=["Dataset"], dependencies=[Depends(authorize)])

MEDIA_TYPES = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
    ".mp4": "video/mp4",
    ".webm": "video/webm",
    ".mov": "video/quicktime",
    ".m4v": "video/x-m4v",
}


class DatasetSourceInput(StrictModel):
    name: str = Field(min_length=1, max_length=120)
    kind: Literal["telegram", "urls", "folder"]
    reference: str = Field(min_length=1, max_length=20000)
    character_id: str | None = None
    limit: int = Field(default=200, ge=1, le=2000)
    classify: bool = True


class DatasetImagePatch(StrictModel):
    caption: str | None = Field(default=None, max_length=4000)
    tags: list[str] | None = Field(default=None, max_length=30)
    details: dict | None = None
    status: Literal["pending", "ready", "failed", "blocked"] | None = None


def required(db, model, item_id):
    item = db.get(model, item_id)
    if item is None:
        raise HTTPException(404, "Elemento non trovato")
    return item


@router.get("/dataset/sources")
def list_sources(limit: int = Query(100, ge=1, le=200), offset: int = Query(0, ge=0)):
    with Session() as db:
        result = []
        for source in db.scalars(
            select(DatasetSource).order_by(DatasetSource.created_at.desc()).limit(limit).offset(offset)
        ):
            images, videos = media_counts(db, source.id)
            result.append(source_out(source, images, videos))
        return result


@router.post("/dataset/sources", status_code=201)
def create_source(body: DatasetSourceInput, background_tasks: BackgroundTasks):
    with Session.begin() as db:
        if body.character_id:
            required(db, Influencer, body.character_id)
        source = DatasetSource(
            name=body.name,
            kind=body.kind,
            reference=body.reference,
            character_id=body.character_id,
            status="pending",
        )
        db.add(source)
        db.flush()
        result = source_out(source)
    background_tasks.add_task(run_import, result["id"], body.reference, body.limit, body.classify)
    return result


@router.get("/dataset/sources/{source_id}")
def get_source(source_id: str):
    with Session() as db:
        source = required(db, DatasetSource, source_id)
        images, videos = media_counts(db, source.id)
        return source_out(source, images, videos)


@router.delete("/dataset/sources/{source_id}")
def remove_source(source_id: str):
    with Session() as db:
        required(db, DatasetSource, source_id)
    delete_source(source_id)
    return {"deleted": True}


@router.post("/dataset/sources/{source_id}/classify")
def classify_source_images(source_id: str, background_tasks: BackgroundTasks):
    with Session() as db:
        required(db, DatasetSource, source_id)
    if classification_running(source_id):
        return {"started": False, "running": True}
    background_tasks.add_task(classify_source, source_id, True)
    return {"started": True}


@router.post("/dataset/sources/{source_id}/profile")
def dataset_profile(source_id: str):
    with Session() as db:
        required(db, DatasetSource, source_id)
    try:
        return {"profile": synthesize_profile(source_id)}
    except ValueError as error:
        raise HTTPException(409, str(error)) from error


@router.get("/dataset/sources/{source_id}/export")
def export_dataset(source_id: str):
    with Session() as db:
        source = required(db, DatasetSource, source_id)
        name = source.name
    rows = export_rows(source_id)
    body = "\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + ("\n" if rows else "")
    filename = "".join(char if char.isalnum() or char in "-_" else "_" for char in name)[:60] or "dataset"
    return Response(
        content=body,
        media_type="application/x-ndjson",
        headers={"Content-Disposition": f'attachment; filename="{filename}.jsonl"'},
    )


@router.get("/dataset/images")
def list_dataset_images(
    source_id: str | None = None,
    status: str | None = None,
    kind: str | None = None,
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
):
    with Session() as db:
        query = select(DatasetImage)
        if source_id:
            query = query.where(DatasetImage.source_id == source_id)
        if status:
            query = query.where(DatasetImage.status == status)
        if kind:
            query = query.where(DatasetImage.kind == kind)
        rows = db.scalars(query.order_by(DatasetImage.created_at.desc()).limit(limit).offset(offset))
        return [image_out(item) for item in rows]


@router.get("/dataset/images/{image_id}/thumb")
def download_dataset_thumb(image_id: str):
    with Session() as db:
        item = required(db, DatasetImage, image_id)
        filename = item.thumb_filename or item.filename
        source_id = item.source_id
    path = (settings.dataset_dir / source_id / filename).resolve()
    if not path.is_relative_to(settings.dataset_dir.resolve()) or not path.is_file():
        raise HTTPException(404, "Anteprima non disponibile")
    media_type = MEDIA_TYPES.get(path.suffix.lower(), "application/octet-stream")
    return FileResponse(path, media_type=media_type, filename=filename)


@router.get("/dataset/images/{image_id}/file")
def download_dataset_image(image_id: str):
    with Session() as db:
        item = required(db, DatasetImage, image_id)
        filename = item.filename
        source_id = item.source_id
    path = (settings.dataset_dir / source_id / filename).resolve()
    if not path.is_relative_to(settings.dataset_dir.resolve()) or not path.is_file():
        raise HTTPException(404, "Immagine non disponibile")
    media_type = MEDIA_TYPES.get(path.suffix.lower(), "application/octet-stream")
    return FileResponse(path, media_type=media_type, filename=filename)


@router.patch("/dataset/images/{image_id}")
def patch_dataset_image(image_id: str, body: DatasetImagePatch):
    with Session.begin() as db:
        item = required(db, DatasetImage, image_id)
        if body.caption is not None:
            item.caption = body.caption
        if body.tags is not None:
            item.tags = [tag.strip().lower()[:40] for tag in body.tags if tag.strip()][:30]
        if body.details is not None:
            item.details = {str(key)[:40]: str(value)[:2000] for key, value in body.details.items()}
        if body.status is not None:
            item.status = body.status
        embedding, _ = embed_library_text(" ".join(filter(None, [item.caption, " ".join(item.tags or [])])))
        if embedding:
            item.embedding = embedding
        db.flush()
        return image_out(item)


@router.delete("/dataset/images/{image_id}")
def delete_dataset_image(image_id: str):
    with Session.begin() as db:
        item = required(db, DatasetImage, image_id)
        path = (settings.dataset_dir / item.source_id / item.filename).resolve()
        if path.is_relative_to(settings.dataset_dir.resolve()):
            path.unlink(missing_ok=True)
        db.delete(item)
    return {"deleted": True}
