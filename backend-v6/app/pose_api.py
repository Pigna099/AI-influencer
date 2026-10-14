"""Pose library: extract DWPose skeletons from dataset/library images and manage poses."""

from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import Field
from sqlalchemy import func, select

from .auth import authorize
from .char_schemas import StrictModel
from .config import settings
from .db import DatasetImage, ImageLibrary, PoseReference, Session, identifier
from .integrations.comfyui import ComfyUIError, extract_pose

router = APIRouter(prefix="/api", tags=["Pose"], dependencies=[Depends(authorize)])


class PoseExtractInput(StrictModel):
    source: Literal["dataset", "library"] = "dataset"
    source_image_id: str
    name: str | None = Field(default=None, max_length=120)
    description: str = Field(default="", max_length=2000)
    tags: list[str] = Field(default_factory=list, max_length=30)
    resolution: int = Field(default=1024, ge=384, le=2048)


class PosePatch(StrictModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=2000)
    tags: list[str] | None = Field(default=None, max_length=30)
    active: bool | None = None


def required(db, model, item_id):
    item = db.get(model, item_id)
    if item is None:
        raise HTTPException(404, "Elemento non trovato")
    return item


def pose_out(item: PoseReference) -> dict:
    return {
        "id": item.id,
        "name": item.name,
        "source": item.source,
        "source_image_id": item.source_image_id,
        "skeleton_filename": item.skeleton_filename,
        "keypoint_count": len(item.keypoints or []),
        "description": item.description,
        "tags": item.tags or [],
        "active": item.active,
        "created_at": item.created_at.isoformat(),
    }


def _source_path(db, source: str, image_id: str) -> Path:
    if source == "dataset":
        item = required(db, DatasetImage, image_id)
        if item.kind != "image":
            raise HTTPException(400, "I video non hanno ancora una posa estraibile")
        path = (settings.dataset_dir / item.source_id / item.filename).resolve()
        if not path.is_file() or not path.is_relative_to(settings.dataset_dir.resolve()):
            raise HTTPException(404, "File immagine non trovato")
        return path
    item = required(db, ImageLibrary, image_id)
    path = (settings.media_dir / item.filename).resolve()
    if not path.is_file() or not path.is_relative_to(settings.media_dir.resolve()):
        raise HTTPException(404, "File immagine non trovato")
    return path


@router.get("/poses")
def list_poses(
    tag: str | None = Query(default=None, max_length=40),
    active_only: bool = Query(default=False),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    with Session() as db:
        stmt = select(PoseReference).order_by(PoseReference.created_at.desc()).limit(limit).offset(offset)
        if active_only:
            stmt = stmt.where(PoseReference.active.is_(True))
        items = list(db.scalars(stmt))
        if tag:
            wanted = tag.strip().lower()
            items = [item for item in items if wanted in (item.tags or [])]
        return [pose_out(item) for item in items]


@router.post("/poses/extract", status_code=201)
def extract_pose_from_image(body: PoseExtractInput):
    with Session() as db:
        path = _source_path(db, body.source, body.source_image_id)
    try:
        data = extract_pose(path, resolution=body.resolution)
    except ComfyUIError as error:
        raise HTTPException(502, f"Estrazione posa non riuscita: {error}") from error
    settings.pose_dir.mkdir(parents=True, exist_ok=True)
    filename = f"{identifier()}.png"
    try:
        (settings.pose_dir / filename).write_bytes(data)
    except OSError as error:
        raise HTTPException(500, "Impossibile salvare lo skeleton") from error
    with Session.begin() as db:
        count = db.scalar(select(func.count()).select_from(PoseReference)) or 0
        item = PoseReference(
            name=body.name or f"Posa {count + 1}",
            source=body.source,
            source_image_id=body.source_image_id,
            skeleton_filename=filename,
            keypoints=[],
            description=body.description,
            tags=[tag.strip().lower()[:40] for tag in body.tags if tag.strip()][:30],
            active=True,
        )
        db.add(item)
        db.flush()
    return pose_out(item)


@router.get("/poses/{pose_id}")
def get_pose(pose_id: str):
    with Session() as db:
        return pose_out(required(db, PoseReference, pose_id))


@router.get("/poses/{pose_id}/skeleton")
def pose_skeleton(pose_id: str):
    with Session() as db:
        item = required(db, PoseReference, pose_id)
    path = (settings.pose_dir / (item.skeleton_filename or "")).resolve()
    if not path.is_file() or not path.is_relative_to(settings.pose_dir.resolve()):
        raise HTTPException(404, "Skeleton non disponibile")
    return FileResponse(path, media_type="image/png")


@router.get("/poses/{pose_id}/source")
def pose_source(pose_id: str):
    with Session() as db:
        item = required(db, PoseReference, pose_id)
        path = _source_path(db, item.source, item.source_image_id)
    return FileResponse(path, media_type="image/png")


@router.patch("/poses/{pose_id}")
def patch_pose(pose_id: str, body: PosePatch):
    with Session.begin() as db:
        item = required(db, PoseReference, pose_id)
        if body.name is not None:
            item.name = body.name
        if body.description is not None:
            item.description = body.description
        if body.tags is not None:
            item.tags = [tag.strip().lower()[:40] for tag in body.tags if tag.strip()][:30]
        if body.active is not None:
            item.active = body.active
        db.flush()
        return pose_out(item)


@router.delete("/poses/{pose_id}")
def delete_pose(pose_id: str):
    with Session.begin() as db:
        item = required(db, PoseReference, pose_id)
        filename = item.skeleton_filename
        db.delete(item)
    if filename:
        path = (settings.pose_dir / filename).resolve()
        if path.is_relative_to(settings.pose_dir.resolve()):
            path.unlink(missing_ok=True)
    return {"deleted": True, "id": pose_id}
