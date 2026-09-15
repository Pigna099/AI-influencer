"""Per-character LoRA registry and training job queue (pipeline Phase A)."""

import re
import secrets
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import Field
from sqlalchemy import func, select, update

from .auth import authorize
from .char_schemas import StrictModel
from .config import settings
from .db import CharacterLora, Influencer, LoraDataset, Session, TrainingJob, now

router = APIRouter(prefix="/api", tags=["LoRA"], dependencies=[Depends(authorize)])

JOB_ACTIVE = ("queued", "running")
JOB_FINISHED = ("succeeded", "failed", "canceled")
LORA_BUSY = ("queued", "training")


class LoraCreate(StrictModel):
    name: str = Field(min_length=1, max_length=120)
    family: Literal["real", "pony", "anime"]
    trigger: str | None = Field(default=None, max_length=64)
    base_checkpoint: str | None = Field(default=None, max_length=200)
    rank: int = Field(default=32, ge=4, le=128)


class LoraPatch(StrictModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    trigger: str | None = Field(default=None, min_length=1, max_length=64)
    rank: int | None = Field(default=None, ge=4, le=128)
    status: Literal["draft", "archived"] | None = None


class TrainingJobCreate(StrictModel):
    images_dir: str = Field(min_length=1, max_length=300)
    dataset_id: str | None = None
    base_checkpoint: str | None = Field(default=None, max_length=200)
    rank: int | None = Field(default=None, ge=4, le=128)
    resolution: int = Field(default=1024, ge=512, le=1536)
    steps: int | None = Field(default=None, ge=100, le=20000)
    learning_rate: float = Field(default=1e-4, gt=0, le=1e-2)
    repeats: int = Field(default=10, ge=1, le=100)
    batch_size: int = Field(default=1, ge=1, le=8)
    caption_prefix: str = Field(default="", max_length=500)
    save_every: int = Field(default=500, ge=50, le=5000)
    gpu: int | None = Field(default=None, ge=0, le=15)


class ClaimInput(StrictModel):
    worker: str = Field(default="", max_length=120)


class ProgressInput(StrictModel):
    progress: dict = Field(default_factory=dict)
    log_path: str | None = Field(default=None, max_length=300)


class CompleteInput(StrictModel):
    success: bool = True
    error: str | None = Field(default=None, max_length=4000)
    filename: str | None = Field(default=None, max_length=300)
    artifact_filename: str | None = Field(default=None, max_length=300)
    metrics: dict = Field(default_factory=dict)


def required(db, model, item_id):
    item = db.get(model, item_id)
    if item is None:
        raise HTTPException(404, "Elemento non trovato")
    return item


def data_root() -> Path:
    return settings.media_dir.resolve().parent


def resolve_data_dir(value: str) -> Path:
    root = data_root()
    candidate = Path(value)
    if not candidate.is_absolute():
        candidate = Path.cwd() / candidate
    path = candidate.resolve()
    if not path.is_relative_to(root) or not path.is_dir():
        raise HTTPException(400, "Cartella immagini non valida: indicare una cartella dentro data/")
    return path


def default_trigger(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "", name.lower())[:16] or "char"
    return f"{slug}_{secrets.token_hex(3)}"


def output_stem(name: str, family: str, version: int) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")[:40] or "char"
    return f"{slug}_{family}_v{version}"


def lora_out(item: CharacterLora) -> dict:
    return {
        "id": item.id,
        "character_id": item.character_id,
        "name": item.name,
        "trigger": item.trigger,
        "family": item.family,
        "base_checkpoint": item.base_checkpoint,
        "filename": item.filename,
        "artifact_filename": item.artifact_filename,
        "rank": item.rank,
        "status": item.status,
        "is_active": item.is_active,
        "config": item.config,
        "metrics": item.metrics,
        "log_path": item.log_path,
        "error": item.error,
        "created_at": item.created_at.isoformat(),
        "updated_at": item.updated_at.isoformat() if item.updated_at else None,
    }


def job_out(job: TrainingJob, lora: CharacterLora | None = None, character: Influencer | None = None) -> dict:
    return {
        "id": job.id,
        "character_id": job.character_id,
        "lora_id": job.lora_id,
        "dataset_id": job.dataset_id,
        "trainer": job.trainer,
        "status": job.status,
        "params": job.params,
        "progress": job.progress,
        "log_path": job.log_path,
        "error": job.error,
        "worker": job.worker,
        "heartbeat_at": job.heartbeat_at.isoformat() if job.heartbeat_at else None,
        "created_at": job.created_at.isoformat(),
        "started_at": job.started_at.isoformat() if job.started_at else None,
        "finished_at": job.finished_at.isoformat() if job.finished_at else None,
        "lora": lora_out(lora) if lora else None,
        "character": {"id": character.id, "name": character.name} if character else None,
    }


@router.get("/characters/{character_id}/loras")
def list_loras(character_id: str):
    with Session() as db:
        required(db, Influencer, character_id)
        items = db.scalars(
            select(CharacterLora)
            .where(CharacterLora.character_id == character_id)
            .order_by(CharacterLora.created_at.desc())
        )
        return [lora_out(item) for item in items]


@router.post("/characters/{character_id}/loras", status_code=201)
def create_lora(character_id: str, body: LoraCreate):
    with Session.begin() as db:
        required(db, Influencer, character_id)
        trigger = (body.trigger or default_trigger(body.name)).strip()
        duplicate = db.scalars(
            select(CharacterLora)
            .where(CharacterLora.character_id == character_id, CharacterLora.trigger == trigger)
            .limit(1)
        ).first()
        if duplicate is not None:
            raise HTTPException(409, "Trigger già usato da un'altra LoRA del personaggio")
        item = CharacterLora(
            character_id=character_id,
            name=body.name,
            trigger=trigger,
            family=body.family,
            base_checkpoint=body.base_checkpoint,
            rank=body.rank,
            status="draft",
        )
        db.add(item)
        db.flush()
    return lora_out(item)


@router.get("/loras/{lora_id}")
def get_lora(lora_id: str):
    with Session() as db:
        return lora_out(required(db, CharacterLora, lora_id))


@router.patch("/loras/{lora_id}")
def patch_lora(lora_id: str, body: LoraPatch):
    with Session.begin() as db:
        item = required(db, CharacterLora, lora_id)
        if item.status in LORA_BUSY:
            raise HTTPException(409, "LoRA in training: attendere la fine o annullare il job")
        if body.name is not None:
            item.name = body.name
        if body.trigger is not None:
            trigger = body.trigger.strip()
            duplicate = db.scalars(
                select(CharacterLora)
                .where(
                    CharacterLora.character_id == item.character_id,
                    CharacterLora.trigger == trigger,
                    CharacterLora.id != item.id,
                )
                .limit(1)
            ).first()
            if duplicate is not None:
                raise HTTPException(409, "Trigger già usato da un'altra LoRA del personaggio")
            item.trigger = trigger
        if body.rank is not None:
            item.rank = body.rank
        if body.status is not None:
            item.status = body.status
        item.updated_at = now()
    return lora_out(item)


@router.delete("/loras/{lora_id}")
def delete_lora(lora_id: str):
    artifact: Path | None = None
    with Session.begin() as db:
        item = required(db, CharacterLora, lora_id)
        if item.status in LORA_BUSY:
            raise HTTPException(409, "LoRA in training: annullare prima il job")
        if item.artifact_filename:
            candidate = (settings.lora_dir / item.artifact_filename).resolve()
            if candidate.is_relative_to(settings.lora_dir.resolve()) and candidate.is_file():
                artifact = candidate
        db.execute(update(TrainingJob).where(TrainingJob.lora_id == lora_id).values(lora_id=None))
        db.delete(item)
    if artifact is not None:
        artifact.unlink(missing_ok=True)
    return {"deleted": True, "id": lora_id}


@router.post("/loras/{lora_id}/activate")
def activate_lora(lora_id: str):
    with Session.begin() as db:
        item = required(db, CharacterLora, lora_id)
        if item.status != "ready":
            raise HTTPException(409, "Solo una LoRA pronta può essere attivata")
        db.execute(
            update(CharacterLora)
            .where(
                CharacterLora.character_id == item.character_id,
                CharacterLora.family == item.family,
                CharacterLora.is_active.is_(True),
            )
            .values(is_active=False, updated_at=now())
        )
        item.is_active = True
        item.updated_at = now()
    return lora_out(item)


@router.post("/loras/{lora_id}/training-jobs", status_code=201)
def queue_training(lora_id: str, body: TrainingJobCreate):
    images_dir = resolve_data_dir(body.images_dir)
    with Session.begin() as db:
        lora = required(db, CharacterLora, lora_id)
        if lora.status in LORA_BUSY:
            raise HTTPException(409, "Training già in corso per questa LoRA")
        if body.dataset_id:
            required(db, LoraDataset, body.dataset_id)
        base_checkpoint = body.base_checkpoint or lora.base_checkpoint
        rank = body.rank or lora.rank
        if base_checkpoint and not lora.base_checkpoint:
            lora.base_checkpoint = base_checkpoint
        versions = db.scalar(
            select(func.count())
            .select_from(CharacterLora)
            .where(CharacterLora.character_id == lora.character_id, CharacterLora.family == lora.family)
        ) or 0
        stem = output_stem(lora.name, lora.family, versions)
        params = {
            "images_dir": str(images_dir),
            "dataset_id": body.dataset_id,
            "trigger": lora.trigger,
            "family": lora.family,
            "base_checkpoint": base_checkpoint,
            "output_stem": stem,
            "filename": f"{settings.lora_comfyui_subdir}/{stem}.safetensors",
            "artifact_filename": f"{stem}.safetensors",
            "rank": rank,
            "resolution": body.resolution,
            "steps": body.steps,
            "learning_rate": body.learning_rate,
            "repeats": body.repeats,
            "batch_size": body.batch_size,
            "caption_prefix": body.caption_prefix,
            "save_every": body.save_every,
            "gpu": body.gpu,
        }
        job = TrainingJob(
            character_id=lora.character_id,
            lora_id=lora.id,
            dataset_id=body.dataset_id,
            params=params,
        )
        db.add(job)
        db.flush()
        lora.status = "queued"
        lora.updated_at = now()
        character = db.get(Influencer, lora.character_id)
    return job_out(job, lora, character)


@router.get("/training-jobs")
def list_training_jobs(
    status: str | None = Query(default=None, max_length=16),
    character_id: str | None = Query(default=None, max_length=36),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    with Session() as db:
        stmt = select(TrainingJob).order_by(TrainingJob.created_at.desc()).limit(limit).offset(offset)
        if status:
            stmt = stmt.where(TrainingJob.status == status)
        if character_id:
            stmt = stmt.where(TrainingJob.character_id == character_id)
        result = []
        for job in db.scalars(stmt):
            lora = db.get(CharacterLora, job.lora_id) if job.lora_id else None
            character = db.get(Influencer, job.character_id)
            result.append(job_out(job, lora, character))
        return result


@router.get("/training-jobs/{job_id}")
def get_training_job(job_id: str):
    with Session() as db:
        job = required(db, TrainingJob, job_id)
        lora = db.get(CharacterLora, job.lora_id) if job.lora_id else None
        character = db.get(Influencer, job.character_id)
        return job_out(job, lora, character)


@router.post("/training-jobs/{job_id}/claim")
def claim_training_job(job_id: str, body: ClaimInput):
    with Session.begin() as db:
        job = required(db, TrainingJob, job_id)
        if job.status != "queued":
            raise HTTPException(409, "Job non disponibile in coda")
        job.status = "running"
        job.worker = body.worker.strip() or None
        job.started_at = now()
        job.heartbeat_at = now()
        lora = db.get(CharacterLora, job.lora_id) if job.lora_id else None
        if lora is not None and lora.status == "queued":
            lora.status = "training"
            lora.updated_at = now()
        character = db.get(Influencer, job.character_id)
    return job_out(job, lora, character)


@router.post("/training-jobs/{job_id}/progress")
def update_training_progress(job_id: str, body: ProgressInput):
    with Session.begin() as db:
        job = required(db, TrainingJob, job_id)
        if job.status in JOB_FINISHED:
            raise HTTPException(409, "Job già concluso")
        job.progress = body.progress
        job.heartbeat_at = now()
        if body.log_path is not None:
            job.log_path = body.log_path
        lora = db.get(CharacterLora, job.lora_id) if job.lora_id else None
        character = db.get(Influencer, job.character_id)
    return job_out(job, lora, character)


@router.post("/training-jobs/{job_id}/complete")
def complete_training_job(job_id: str, body: CompleteInput):
    with Session.begin() as db:
        job = required(db, TrainingJob, job_id)
        if job.status in JOB_FINISHED:
            raise HTTPException(409, "Job già concluso")
        lora = db.get(CharacterLora, job.lora_id) if job.lora_id else None
        job.finished_at = now()
        if body.success:
            if not body.filename or not body.artifact_filename:
                raise HTTPException(400, "filename e artifact_filename sono richiesti")
            artifact = (settings.lora_dir / body.artifact_filename).resolve()
            if not artifact.is_relative_to(settings.lora_dir.resolve()) or not artifact.is_file():
                raise HTTPException(400, "Artefatto non trovato nella cartella LoRA del server")
            job.status = "succeeded"
            if lora is not None:
                lora.status = "ready"
                lora.filename = body.filename
                lora.artifact_filename = body.artifact_filename
                lora.metrics = body.metrics
                lora.error = None
                lora.updated_at = now()
                active = db.scalars(
                    select(CharacterLora)
                    .where(
                        CharacterLora.character_id == lora.character_id,
                        CharacterLora.family == lora.family,
                        CharacterLora.is_active.is_(True),
                    )
                    .limit(1)
                ).first()
                if active is None:
                    lora.is_active = True
        else:
            job.status = "failed"
            job.error = body.error or "Training fallito"
            if lora is not None:
                lora.status = "failed"
                lora.error = job.error
                lora.updated_at = now()
        character = db.get(Influencer, job.character_id)
    return job_out(job, lora, character)


@router.post("/training-jobs/{job_id}/cancel")
def cancel_training_job(job_id: str):
    with Session.begin() as db:
        job = required(db, TrainingJob, job_id)
        if job.status in JOB_FINISHED:
            raise HTTPException(409, "Job già concluso")
        job.status = "canceled"
        job.finished_at = now()
        lora = db.get(CharacterLora, job.lora_id) if job.lora_id else None
        if lora is not None and lora.status in LORA_BUSY:
            lora.status = "draft"
            lora.updated_at = now()
        character = db.get(Influencer, job.character_id)
    return job_out(job, lora, character)
