"""Per-character LoRA registry and training job queue (pipeline Phase A)."""

import hashlib
import json
import random
import re
import secrets
import shutil
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import Field
from sqlalchemy import func, select, update

from .audit import record as audit_record
from .auth import authorize
from .char_schemas import BulkIdsInput, StrictModel
from .chat_service import build_negative_prompt, translate_scene
from .config import settings
from .db import (
    CharacterLora,
    ExecutionJob,
    IdentityCandidate,
    IdentityRun,
    ImageLibrary,
    Influencer,
    LoraDataset,
    LoraDatasetItem,
    PoseReference,
    Session,
    TrainingJob,
    identifier,
    now,
)
from .image_library import average_hash
from .integrations.comfyui import ComfyUIError, checkpoint_meta, generate_image, pick_target, qwen_image_edit
from .integrations.faces import embedding_for, embedding_for_path, similarity_percent
from .jobs import create_job, finish_job, request_cancel, start_job, update_progress

router = APIRouter(prefix="/api", tags=["LoRA"], dependencies=[Depends(authorize)])

JOB_ACTIVE = ("queued", "running")
JOB_FINISHED = ("succeeded", "failed", "canceled")
LORA_BUSY = ("queued", "training")


class LoraCreate(StrictModel):
    name: str = Field(min_length=1, max_length=120)
    family: Literal["real", "pony", "anime", "qwen-image"]
    trigger: str | None = Field(default=None, max_length=64)
    base_checkpoint: str | None = Field(default=None, max_length=200)
    rank: int = Field(default=32, ge=4, le=128)


class LoraPatch(StrictModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    trigger: str | None = Field(default=None, min_length=1, max_length=64)
    family: Literal["real", "pony", "anime", "qwen-image"] | None = None
    rank: int | None = Field(default=None, ge=4, le=128)
    status: Literal["draft", "archived"] | None = None


class TrainingJobCreate(StrictModel):
    images_dir: str | None = Field(default=None, max_length=300)
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
    error_info: dict | None = None
    filename: str | None = Field(default=None, max_length=300)
    artifact_filename: str | None = Field(default=None, max_length=300)
    metrics: dict = Field(default_factory=dict)


def required(db, model, item_id):
    item = db.get(model, item_id)
    if item is None:
        raise HTTPException(404, "Item not found")
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
        raise HTTPException(400, "Invalid image folder: provide a folder inside data/")
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
        "previous_active_id": item.previous_active_id,
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
        "error_info": job.error_info,
        "worker": job.worker,
        "heartbeat_at": job.heartbeat_at.isoformat() if job.heartbeat_at else None,
        "created_at": job.created_at.isoformat(),
        "started_at": job.started_at.isoformat() if job.started_at else None,
        "finished_at": job.finished_at.isoformat() if job.finished_at else None,
        "lora": lora_out(lora) if lora else None,
        "character": {"id": character.id, "name": character.name} if character else None,
        "name": job_display_name(job, lora),
    }


def job_display_name(job: TrainingJob, lora: CharacterLora | None) -> str:
    params = job.params or {}
    stem = str(params.get("output_stem") or "").strip()
    if lora is not None:
        return lora.name
    if stem:
        family = str(params.get("family") or "").strip()
        return f"{stem} ({family})" if family else stem
    return f"job {(job.id or 'pending')[:8]}"


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
            raise HTTPException(409, "Trigger already used by another LoRA of this character")
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
            raise HTTPException(409, "LoRA is training: wait for it to finish or cancel the job")
        if body.name is not None:
            item.name = body.name
        if body.family is not None:
            item.family = body.family
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
                raise HTTPException(409, "Trigger already used by another LoRA of this character")
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
    comfy_filename: str | None = None
    with Session.begin() as db:
        item = required(db, CharacterLora, lora_id)
        if item.status in LORA_BUSY:
            raise HTTPException(409, "LoRA is training: cancel the job first")
        if item.artifact_filename:
            candidate = (settings.lora_dir / item.artifact_filename).resolve()
            if candidate.is_relative_to(settings.lora_dir.resolve()) and candidate.is_file():
                artifact = candidate
        if item.filename:
            comfy_filename = item.filename
        db.execute(update(TrainingJob).where(TrainingJob.lora_id == lora_id).values(lora_id=None))
        db.delete(item)
    if artifact is not None:
        artifact.unlink(missing_ok=True)
    if comfy_filename:
        pending = settings.lora_dir / "pending_delete"
        pending.mkdir(parents=True, exist_ok=True)
        (pending / f"{lora_id}.txt").write_text(comfy_filename)
    return {"deleted": True, "id": lora_id}


@router.post("/loras/{lora_id}/activate")
def activate_lora(lora_id: str):
    with Session.begin() as db:
        item = required(db, CharacterLora, lora_id)
        if item.status != "ready":
            raise HTTPException(409, "Only a ready LoRA can be activated")
        previous = db.scalar(
            select(CharacterLora).where(
                CharacterLora.character_id == item.character_id,
                CharacterLora.family == item.family,
                CharacterLora.is_active.is_(True),
                CharacterLora.id != item.id,
            )
        )
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
        item.previous_active_id = previous.id if previous is not None else None
        item.updated_at = now()
        audit_record(db, "lora.activate", "lora", item.id, previous=previous.id if previous else None)
    return lora_out(item)


@router.post("/loras/{lora_id}/rollback")
def rollback_lora(lora_id: str):
    """Re-activate the artifact that was active before this one (kept for rollback)."""
    with Session.begin() as db:
        item = required(db, CharacterLora, lora_id)
        if not item.previous_active_id:
            raise HTTPException(409, "No previous active artifact recorded for this LoRA")
        previous = db.get(CharacterLora, item.previous_active_id)
        if previous is None or previous.status != "ready":
            raise HTTPException(409, "The previous artifact is no longer available")
        item.is_active = False
        previous.previous_active_id = item.id
        previous.is_active = True
        previous.updated_at = now()
        item.updated_at = now()
        audit_record(db, "lora.rollback", "lora", previous.id, from_lora=item.id)
        result = lora_out(previous)
    return result


def _exec_job(db, training_job) -> ExecutionJob | None:
    return db.scalar(
        select(ExecutionJob).where(ExecutionJob.external_id == training_job.id, ExecutionJob.type == "training")
    )


@router.post("/loras/{lora_id}/training-jobs", status_code=201)
def queue_training(lora_id: str, body: TrainingJobCreate):
    if not body.images_dir and not body.dataset_id:
        raise HTTPException(400, "Provide an image folder or a dataset")
    with Session.begin() as db:
        lora = required(db, CharacterLora, lora_id)
        if lora.status in LORA_BUSY:
            raise HTTPException(409, "Training already in progress for this LoRA")
        dataset = required(db, LoraDataset, body.dataset_id) if body.dataset_id else None
        if dataset is not None and dataset.character_id != lora.character_id:
            raise HTTPException(400, "The dataset belongs to another character")
        base_checkpoint = body.base_checkpoint or lora.base_checkpoint
        rank = body.rank or lora.rank
        if base_checkpoint:
            meta = checkpoint_meta(str(base_checkpoint))
            detected = meta["family"] if meta["usable"] else None
            if lora.family == "qwen-image" and detected not in (None, "qwen-image"):
                raise HTTPException(
                    400,
                    f"Checkpoint {base_checkpoint} belongs to the {detected} family: this LoRA is set to qwen-image",
                )
            if lora.family != "qwen-image" and detected in ("qwen-image", "flux2", "z-image"):
                raise HTTPException(
                    400,
                    f"Checkpoint {base_checkpoint} belongs to the {detected} family: set the LoRA family to "
                    f"{detected} (or pick a {lora.family} checkpoint)",
                )
        if base_checkpoint and not lora.base_checkpoint:
            lora.base_checkpoint = base_checkpoint
        versions = db.scalar(
            select(func.count())
            .select_from(CharacterLora)
            .where(CharacterLora.character_id == lora.character_id, CharacterLora.family == lora.family)
        ) or 0
        stem = output_stem(lora.name, lora.family, versions)
        if dataset is not None:
            images_dir = materialize_dataset(db, dataset, stem)
        else:
            images_dir = resolve_data_dir(body.images_dir)
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
        params["spec_sha256"] = hashlib.sha256(
            json.dumps(params, sort_keys=True, default=str).encode("utf-8")
        ).hexdigest()
        job = TrainingJob(
            character_id=lora.character_id,
            lora_id=lora.id,
            dataset_id=body.dataset_id,
            params=params,
        )
        db.add(job)
        db.flush()
        create_job(
            db,
            type="training",
            character_id=lora.character_id,
            dataset_id=body.dataset_id,
            external_id=job.id,
            idempotency_key=f"training:{job.id}",
            message=f"training queued for {stem}",
        )
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
            raise HTTPException(409, "Job not available in the queue")
        job.status = "running"
        job.worker = body.worker.strip() or None
        job.started_at = now()
        job.heartbeat_at = now()
        lora = db.get(CharacterLora, job.lora_id) if job.lora_id else None
        if lora is not None and lora.status == "queued":
            lora.status = "training"
            lora.updated_at = now()
        exec_job = _exec_job(db, job)
        if exec_job is not None and exec_job.state == "queued":
            start_job(db, exec_job, worker=job.worker, gpu=(job.params or {}).get("gpu"))
        character = db.get(Influencer, job.character_id)
    return job_out(job, lora, character)


@router.post("/training-jobs/{job_id}/progress")
def update_training_progress(job_id: str, body: ProgressInput):
    with Session.begin() as db:
        job = required(db, TrainingJob, job_id)
        if job.status in JOB_FINISHED:
            if job.status == "canceled":
                lora = db.get(CharacterLora, job.lora_id) if job.lora_id else None
                character = db.get(Influencer, job.character_id)
                return job_out(job, lora, character)
            raise HTTPException(409, "Job already finished")
        job.progress = body.progress
        job.heartbeat_at = now()
        if body.log_path is not None:
            job.log_path = body.log_path
        exec_job = _exec_job(db, job)
        if exec_job is not None and exec_job.state in ("queued", "running"):
            if exec_job.state == "queued":
                start_job(db, exec_job)
            update_progress(
                db,
                exec_job,
                current=(body.progress or {}).get("step"),
                total=(body.progress or {}).get("total"),
                unit="step",
            )
        lora = db.get(CharacterLora, job.lora_id) if job.lora_id else None
        character = db.get(Influencer, job.character_id)
    return job_out(job, lora, character)


@router.post("/training-jobs/{job_id}/complete")
def complete_training_job(job_id: str, body: CompleteInput):
    with Session.begin() as db:
        job = required(db, TrainingJob, job_id)
        if job.status in JOB_FINISHED:
            raise HTTPException(409, "Job already finished")
        lora = db.get(CharacterLora, job.lora_id) if job.lora_id else None
        job.finished_at = now()
        if body.success:
            if not body.filename or not body.artifact_filename:
                raise HTTPException(400, "filename and artifact_filename are required")
            artifact = (settings.lora_dir / body.artifact_filename).resolve()
            if not artifact.is_relative_to(settings.lora_dir.resolve()) or not artifact.is_file():
                raise HTTPException(400, "Artifact not found in the server LoRA folder")
            job.status = "succeeded"
            if lora is not None:
                lora.status = "ready"
                lora.filename = body.filename
                lora.artifact_filename = body.artifact_filename
                artifact_sha = hashlib.sha256(artifact.read_bytes()).hexdigest()
                lora.metrics = {**body.metrics, "artifact_sha256": artifact_sha}
                job.params = {**(job.params or {}), "artifact_sha256": artifact_sha}
                lora.error = None
                lora.updated_at = now()
                # Evaluation gate: a freshly trained LoRA stays inactive until the
                # operator validates the grid and activates it explicitly.
        else:
            job.status = "failed"
            job.error = body.error
            job.error_info = body.error_info or "Training failed"
            if lora is not None:
                lora.status = "failed"
                lora.error = job.error
                lora.updated_at = now()
        exec_job = _exec_job(db, job)
        if exec_job is not None and exec_job.state in ("queued", "running"):
            if body.success:
                update_progress(
                    db,
                    exec_job,
                    current=(job.progress or {}).get("total"),
                    total=(job.progress or {}).get("total"),
                    unit="step",
                )
                finish_job(db, exec_job, state="succeeded", message="training finished")
            else:
                finish_job(
                    db,
                    exec_job,
                    state="failed",
                    error_info=body.error_info
                    or {
                        "code": "trainer_failed",
                        "summary": "Training failed.",
                        "remediation": "Check the technical details and retry.",
                        "technical_details": (body.error or "")[:800],
                    },
                )
        character = db.get(Influencer, job.character_id)
    return job_out(job, lora, character)


@router.post("/training-jobs/{job_id}/cancel")
def cancel_training_job(job_id: str):
    with Session.begin() as db:
        job = required(db, TrainingJob, job_id)
        if job.status in JOB_FINISHED:
            raise HTTPException(409, "Job already finished")
        job.status = "canceled"
        job.finished_at = now()
        lora = db.get(CharacterLora, job.lora_id) if job.lora_id else None
        if lora is not None and lora.status in LORA_BUSY:
            lora.status = "draft"
            lora.updated_at = now()
        exec_job = _exec_job(db, job)
        if exec_job is not None and exec_job.state in ("queued", "running"):
            request_cancel(db, exec_job)
            finish_job(db, exec_job, state="canceled", message="training canceled")
        character = db.get(Influencer, job.character_id)
    return job_out(job, lora, character)


def materialize_dataset(db, dataset: LoraDataset, stem: str) -> Path:
    """Copy the selected dataset images + captions into a folder the trainer can use."""
    rows = list(
        db.execute(
            select(LoraDatasetItem, ImageLibrary)
            .join(ImageLibrary, LoraDatasetItem.image_id == ImageLibrary.id)
            .where(
                LoraDatasetItem.dataset_id == dataset.id,
                LoraDatasetItem.selected.is_(True),
                ImageLibrary.deleted_at.is_(None),
            )
            .order_by(LoraDatasetItem.created_at)
        )
    )
    folder = settings.media_dir.parent / "lora_datasets" / stem
    if folder.exists():
        shutil.rmtree(folder)
    folder.mkdir(parents=True)
    trigger = dataset.trigger or ""
    copied = 0
    for item, library in rows:
        source = (settings.media_dir / library.filename).resolve()
        if not source.is_file() or not source.is_relative_to(settings.media_dir.resolve()):
            continue
        copied += 1
        name = f"img_{copied:03d}"
        shutil.copy2(source, folder / f"{name}.png")
        caption = (item.caption or library.caption or "").strip()
        if trigger and trigger not in caption:
            caption = f"{trigger}, {caption}".strip(", ")
        (folder / f"{name}.txt").write_text(caption or trigger)
    if copied < 4:
        shutil.rmtree(folder, ignore_errors=True)
        raise HTTPException(400, "At least 4 selected and available images are required in the dataset")
    return folder


class DatasetCreate(StrictModel):
    family: Literal["real", "pony", "anime", "qwen-image"] = "real"
    trigger: str | None = Field(default=None, max_length=64)
    base_checkpoint: str | None = Field(default=None, max_length=200)
    anchor_image_id: str | None = None


class DatasetGenerate(StrictModel):
    prompt: str = Field(min_length=1, max_length=2000)
    negative: str | None = Field(default=None, max_length=4000)
    pose_ids: list[str] = Field(default_factory=list, max_length=10)
    count: int = Field(default=1, ge=1, le=4)
    seed: int | None = Field(default=None, ge=0, le=2**31)
    checkpoint: str | None = Field(default=None, max_length=200)
    pose_strength: float = Field(default=0.8, ge=0, le=2)
    # auto: edit from the anchor when the family supports it (qwen-image), otherwise text-to-image.
    reference_mode: Literal["auto", "edit", "txt2img"] = "auto"


class DatasetItemPatch(StrictModel):
    caption: str | None = Field(default=None, max_length=2000)
    selected: bool | None = None
    reference_role: str | None = Field(default=None, max_length=24)


class DatasetVariations(StrictModel):
    prompts: list[str] = Field(min_length=1, max_length=20)
    count: int = Field(default=1, ge=1, le=4)
    seed: int | None = Field(default=None, ge=0, le=2**31)
    steps: int | None = Field(default=None, ge=1, le=50)
    cfg: float | None = Field(default=None, ge=0, le=10)
    lora_weight: float = Field(default=1.0, ge=0, le=2)
    model: str | None = Field(default=None, max_length=200)


def dataset_item_out(item: LoraDatasetItem, library: ImageLibrary | None) -> dict:
    return {
        "id": item.id,
        "dataset_id": item.dataset_id,
        "image_id": item.image_id,
        "pose_ref_id": item.pose_ref_id,
        "caption": item.caption,
        "similarity": item.similarity,
        "selected": item.selected,
        "reference_role": item.reference_role,
        "seed": item.seed,
        "tags": (library.tags if library else []) or [],
        "filename": library.filename if library else None,
        "status": library.status if library else None,
        "created_at": item.created_at.isoformat(),
    }


def dataset_out(dataset: LoraDataset, item_count: int, selected_count: int) -> dict:
    return {
        "id": dataset.id,
        "character_id": dataset.character_id,
        "family": dataset.family,
        "base_checkpoint": dataset.base_checkpoint,
        "anchor_image_id": dataset.anchor_image_id,
        "trigger": dataset.trigger,
        "status": dataset.status,
        "item_count": item_count,
        "selected_count": selected_count,
        "created_at": dataset.created_at.isoformat(),
        "updated_at": dataset.updated_at.isoformat() if dataset.updated_at else None,
    }


@router.get("/characters/{character_id}/datasets")
def list_datasets(character_id: str):
    with Session() as db:
        required(db, Influencer, character_id)
        datasets = list(
            db.scalars(
                select(LoraDataset)
                .where(LoraDataset.character_id == character_id)
                .order_by(LoraDataset.created_at.desc())
            )
        )
        result = []
        for dataset in datasets:
            total = db.scalar(
                select(func.count()).select_from(LoraDatasetItem).where(LoraDatasetItem.dataset_id == dataset.id)
            ) or 0
            selected = db.scalar(
                select(func.count())
                .select_from(LoraDatasetItem)
                .where(LoraDatasetItem.dataset_id == dataset.id, LoraDatasetItem.selected.is_(True))
            ) or 0
            result.append(dataset_out(dataset, total, selected))
        return result


@router.post("/characters/{character_id}/datasets", status_code=201)
def create_dataset(character_id: str, body: DatasetCreate):
    with Session.begin() as db:
        character = required(db, Influencer, character_id)
        if body.anchor_image_id:
            required(db, ImageLibrary, body.anchor_image_id)
        dataset = LoraDataset(
            character_id=character_id,
            family=body.family,
            base_checkpoint=body.base_checkpoint or character.image_checkpoint,
            anchor_image_id=body.anchor_image_id,
            trigger=(body.trigger or default_trigger(character.name)).strip(),
            status="draft",
        )
        db.add(dataset)
        db.flush()
    return dataset_out(dataset, 0, 0)


@router.get("/datasets/{dataset_id}")
def get_dataset(dataset_id: str):
    with Session() as db:
        dataset = required(db, LoraDataset, dataset_id)
        rows = list(
            db.execute(
                select(LoraDatasetItem, ImageLibrary)
                .outerjoin(ImageLibrary, LoraDatasetItem.image_id == ImageLibrary.id)
                .where(LoraDatasetItem.dataset_id == dataset_id)
                .order_by(LoraDatasetItem.created_at)
            )
        )
        items = [dataset_item_out(item, library) for item, library in rows]
    return {**dataset_out(dataset, len(items), sum(1 for item in items if item["selected"])), "items": items}


@router.post("/datasets/{dataset_id}/generate", status_code=201)
def generate_dataset_candidates(dataset_id: str, body: DatasetGenerate):
    with Session() as db:
        dataset = required(db, LoraDataset, dataset_id)
        character = required(db, Influencer, dataset.character_id)
        anchor_path = None
        if dataset.anchor_image_id:
            anchor = db.get(ImageLibrary, dataset.anchor_image_id)
            if anchor is not None:
                candidate = (settings.media_dir / anchor.filename).resolve()
                if candidate.is_file():
                    anchor_path = candidate
        if anchor_path is None and character.avatar_filename:
            candidate = (settings.media_dir / character.avatar_filename).resolve()
            if candidate.is_file():
                anchor_path = candidate
        poses: list[PoseReference] = []
        if body.pose_ids:
            poses = list(db.scalars(select(PoseReference).where(PoseReference.id.in_(body.pose_ids))))
            if len(poses) != len(set(body.pose_ids)):
                raise HTTPException(404, "One or more poses were not found")
        checkpoint = body.checkpoint or dataset.base_checkpoint or character.image_checkpoint
        style = character.image_style or "real"
        character_id = dataset.character_id
        trigger = dataset.trigger
        character_prompt = (character.avatar_prompt or "").strip()
        family = dataset.family
        if checkpoint:
            meta = checkpoint_meta(checkpoint)
            if meta["usable"]:
                family = meta["family"]
        identity_paths, identity_run_id = identity_set_references(db, character_id)
        if identity_run_id is None:
            raise HTTPException(
                400,
                "Freeze an identity set first: LoRA tab -> Identity set -> generate candidates and freeze 6-10.",
            )
    if not identity_paths and anchor_path is not None:
        # Frozen set exists but files are missing: fall back to the anchor.
        identity_paths = [anchor_path]
    reference_paths = identity_paths
    edit_capable = family == "qwen-image"
    mode = body.reference_mode
    if mode == "auto":
        # Scene variations must always start from the frozen identity set references.
        mode = "edit" if edit_capable else "txt2img"
    if mode == "edit":
        if not edit_capable:
            raise HTTPException(400, "Edit-from-anchor is only available for the qwen-image family")
        if not reference_paths:
            raise HTTPException(
                400, "An anchor image is required: generate the profile picture or set the dataset anchor"
            )
    with Session.begin() as db:
        job = create_job(
            db,
            type="dataset_generate",
            character_id=character_id,
            dataset_id=dataset_id,
            message=f"dataset candidates ({len(poses) or 1} poses x {body.count}, {mode})",
        )
        start_job(db, job, worker="comfyui")
        job_id = job.id
    scene = translate_scene(body.prompt, style)
    parts = [trigger, character_prompt, scene]
    prompt = ", ".join(part for part in parts if part)
    negative = body.negative or build_negative_prompt(family)
    targets: list[PoseReference | None] = poses or [None]
    jobs: list[tuple[PoseReference | None, Path | None, Path | None, int]] = []
    for pose in targets:
        pose_path = None
        if pose is not None and pose.skeleton_filename:
            candidate = (settings.pose_dir / pose.skeleton_filename).resolve()
            if candidate.is_file():
                pose_path = candidate
        for index in range(body.count):
            seed = (body.seed + index) if body.seed is not None else random.randrange(2**31)
            reference = reference_paths[len(jobs) % len(reference_paths)] if reference_paths else None
            jobs.append((pose, pose_path, reference, seed))

    def render(job: tuple[PoseReference | None, Path | None, Path | None, int]):
        pose, pose_path, reference, seed = job
        if mode == "edit" and reference is not None:
            # Identity-preserving: edit from the canonical reference / anchor instead of text-to-image.
            data, meta = qwen_image_edit(
                reference,
                prompt,
                seed=seed,
                steps=settings.qwen_edit_steps,
                cfg=settings.qwen_edit_cfg,
                lora_weight=1.0,
                base_url=pick_target(),
            )
            meta = {**meta, "identity_reference": True}
            return pose, seed, data, meta
        data, meta = generate_image(
            prompt,
            negative,
            seed=seed,
            reference_path=reference,
            checkpoint=checkpoint,
            style=style,
            family=family,
            pose_path=pose_path,
            pose_strength=body.pose_strength,
            base_url=pick_target(),
        )
        return pose, seed, data, meta

    rendered = []
    errors: list[Exception] = []
    with ThreadPoolExecutor(max_workers=len(jobs)) as pool:
        futures = [pool.submit(render, job) for job in jobs]
        for future in futures:
            try:
                rendered.append(future.result())
            except ComfyUIError as error:
                errors.append(error)
    if not rendered:
        with Session.begin() as db:
            job = db.get(ExecutionJob, job_id)
            if job is not None and job.state == "running":
                finish_job(
                    db,
                    job,
                    state="failed",
                    error_info={
                        "code": "dataset_generation_failed",
                        "summary": "Dataset generation failed.",
                        "remediation": "Check the ComfyUI instance and the anchor/reference images, then retry.",
                        "technical_details": str(errors[0])[:800] if errors else "",
                    },
                )
        raise HTTPException(
            502, f"Dataset generation failed: {errors[0] if errors else 'unknown error'}"
        )
    created: list[dict] = []
    for pose, seed, data, meta in rendered:
        settings.media_dir.mkdir(parents=True, exist_ok=True)
        filename = f"{identifier()}.png"
        try:
            (settings.media_dir / filename).write_bytes(data)
        except OSError as error:
            raise HTTPException(500, "Could not save the image") from error
        with Session.begin() as db:
            required(db, LoraDataset, dataset_id)
            library = ImageLibrary(
                character_id=character_id,
                filename=filename,
                sha256=hashlib.sha256(data).hexdigest(),
                phash=average_hash(data),
                prompt=prompt,
                negative_prompt=negative,
                caption="",
                tags=[],
                checkpoint=meta.get("checkpoint") or checkpoint,
                loras=[],
                seed=meta.get("seed", seed),
                style=style,
                status="draft",
                rating=0,
                source="dataset",
                used_count=0,
                embedding=[],
                embedding_model="",
            )
            db.add(library)
            db.flush()
            item = LoraDatasetItem(
                dataset_id=dataset_id,
                image_id=library.id,
                pose_ref_id=pose.id if pose else None,
                caption=" ".join(body.prompt.split()),
                similarity=0.0,
                selected=False,
                seed=meta.get("seed", seed),
            )
            db.add(item)
            db.flush()
            row = db.get(LoraDataset, dataset_id)
            if row is not None:
                row.updated_at = now()
            created.append(dataset_item_out(item, library))
    with Session.begin() as db:
        job = db.get(ExecutionJob, job_id)
        if job is not None and job.state == "running":
            update_progress(db, job, current=len(created), total=len(jobs), unit="image")
            finish_job(db, job, state="succeeded", message=f"{len(created)} candidates ready")
    return created


@router.delete("/datasets/{dataset_id}")
def delete_dataset(dataset_id: str):
    """Delete a dataset with its items and the images it generated."""
    filenames: list[str] = []
    with Session.begin() as db:
        dataset = required(db, LoraDataset, dataset_id)
        rows = list(
            db.execute(
                select(LoraDatasetItem, ImageLibrary)
                .outerjoin(ImageLibrary, LoraDatasetItem.image_id == ImageLibrary.id)
                .where(LoraDatasetItem.dataset_id == dataset_id)
            )
        )
        for item, library in rows:
            if library is not None:
                filenames.append(library.filename)
            db.delete(item)
        db.flush()
        for _, library in rows:
            if library is not None:
                db.delete(library)
        db.execute(update(TrainingJob).where(TrainingJob.dataset_id == dataset_id).values(dataset_id=None))
        db.delete(dataset)
    for filename in filenames:
        path = (settings.media_dir / filename).resolve()
        if path.is_relative_to(settings.media_dir.resolve()):
            path.unlink(missing_ok=True)
    return {"deleted": True, "id": dataset_id}


@router.post("/datasets/{dataset_id}/variations", status_code=201)
def generate_dataset_variations(dataset_id: str, body: DatasetVariations):
    with Session() as db:
        dataset = required(db, LoraDataset, dataset_id)
        character = required(db, Influencer, dataset.character_id)
        anchor_path = None
        if dataset.anchor_image_id:
            anchor = db.get(ImageLibrary, dataset.anchor_image_id)
            if anchor is not None:
                candidate = (settings.media_dir / anchor.filename).resolve()
                if candidate.is_file():
                    anchor_path = candidate
        if anchor_path is None and character.avatar_filename:
            candidate = (settings.media_dir / character.avatar_filename).resolve()
            if candidate.is_file():
                anchor_path = candidate
        if anchor_path is None:
            raise HTTPException(
                400, "An anchor image is required: generate the profile picture or set the dataset anchor"
            )
        character_id = dataset.character_id
        trigger = dataset.trigger
        reference_paths = _dataset_references(db, dataset_id)
    with Session.begin() as db:
        job = create_job(
            db,
            type="dataset_variation",
            character_id=character_id,
            dataset_id=dataset_id,
            message=f"dataset variations ({len(body.prompts)} prompts x {body.count})",
        )
        start_job(db, job, worker="comfyui-edit")
        job_id = job.id
    if not reference_paths and anchor_path is not None:
        reference_paths = [anchor_path]
    jobs: list[tuple[int, str, str, int]] = []
    for raw_prompt in body.prompts:
        prompt = raw_prompt.strip()
        if not prompt:
            continue
        caption = prompt if (not trigger or trigger in prompt) else f"{trigger}, {prompt}"
        for index in range(body.count):
            seed = (body.seed + index) if body.seed is not None else random.randrange(2**31)
            jobs.append((len(jobs), prompt, caption, seed))

    def render(job: tuple[int, str, str, int]):
        index, prompt, _caption, seed = job
        data, meta = qwen_image_edit(
            reference_paths[index % len(reference_paths)],
            prompt,
            seed=seed,
            steps=body.steps,
            cfg=body.cfg,
            lora_weight=body.lora_weight,
            unet_name=body.model,
            base_url=pick_target(),
        )
        return prompt, seed, data, meta

    rendered = []
    errors: list[Exception] = []
    with ThreadPoolExecutor(max_workers=len(jobs)) as pool:
        futures = [pool.submit(render, job) for job in jobs]
        for future in futures:
            try:
                rendered.append(future.result())
            except ComfyUIError as error:
                errors.append(error)
    if not rendered:
        with Session.begin() as db:
            job = db.get(ExecutionJob, job_id)
            if job is not None and job.state == "running":
                finish_job(
                    db,
                    job,
                    state="failed",
                    error_info={
                        "code": "variations_generation_failed",
                        "summary": "Variations generation failed.",
                        "remediation": "Check Qwen-Image-Edit and the reference images, then retry.",
                        "technical_details": str(errors[0])[:800] if errors else "",
                    },
                )
        raise HTTPException(
            502, f"Variations generation failed: {errors[0] if errors else 'unknown error'}"
        )
    created: list[dict] = []
    for prompt, seed, data, meta in rendered:
        caption = prompt if (not trigger or trigger in prompt) else f"{trigger}, {prompt}"
        settings.media_dir.mkdir(parents=True, exist_ok=True)
        filename = f"{identifier()}.png"
        try:
            (settings.media_dir / filename).write_bytes(data)
        except OSError as error:
            raise HTTPException(500, "Could not save the image") from error
        with Session.begin() as db:
            library = ImageLibrary(
                character_id=character_id,
                filename=filename,
                sha256=hashlib.sha256(data).hexdigest(),
                phash=average_hash(data),
                prompt=caption,
                negative_prompt="",
                caption="",
                tags=[],
                checkpoint=meta.get("model"),
                loras=[],
                seed=meta.get("seed", seed),
                style="real",
                status="draft",
                rating=0,
                source="dataset",
                used_count=0,
                embedding=[],
                embedding_model="",
            )
            db.add(library)
            db.flush()
            item = LoraDatasetItem(
                dataset_id=dataset_id,
                image_id=library.id,
                pose_ref_id=None,
                caption=" ".join(prompt.split()),
                similarity=0.0,
                selected=False,
                seed=meta.get("seed", seed),
            )
            db.add(item)
            db.flush()
            row = db.get(LoraDataset, dataset_id)
            if row is not None:
                row.updated_at = now()
            created.append(dataset_item_out(item, library))
    with Session.begin() as db:
        job = db.get(ExecutionJob, job_id)
        if job is not None and job.state == "running":
            update_progress(db, job, current=len(created), total=len(jobs), unit="image")
            finish_job(db, job, state="succeeded", message=f"{len(created)} variations ready")
    return created


KEYWORD_GROUPS = {
    "full_body": ("full body", "full-body", "fullbody"),
    "close_up": ("close-up", "close up", "closeup", "portrait"),
    "profile": ("profile", "side view", "from the side"),
    "back": ("from behind", "from the back", "back view", "rear"),
    "front": ("front", "facing the camera", "looking at the camera"),
    "standing": ("standing",),
    "sitting": ("sitting", "seated"),
    "lying": ("lying", "on the bed", "reclining"),
    "outdoor": ("outdoor", "outside", "street", "park", "beach", "garden", "field"),
    "indoor": ("indoor", "inside", "room", "bedroom", "kitchen", "studio"),
    "night": ("night", "evening", "neon"),
    "day": ("daylight", "sunny", "morning", "afternoon"),
}

DATASET_TARGET = 60
BLUEPRINT = (
    ("close_face", 12, ("close-up", "close up", "closeup", "portrait")),
    ("three_quarter_face", 8, ("three-quarter", "three quarter", "profile", "side view", "from the side")),
    ("upper_body", 10, ("upper body", "waist up", "half body")),
    ("front_full_body", 15, ("full body", "full-body", "fullbody", "standing")),
    ("dynamic", 8, ("walking", "sitting", "seated", "leaning", "lying", "reclining", "running")),
)
CANONICAL_ROLE_PROMPTS: dict[str, str] = {
    "close_face": "close-up of the face, front view, neutral expression, studio light",
    "three_quarter_face": "three-quarter face view, slight smile, studio light",
    "profile": "full side profile view of the face, neutral expression, studio light",
    "upper_body": "upper body portrait, front view, natural window light",
    "front_full_body": "full body, standing, front view, neutral pose, natural light",
    "three_quarter_full_body": "full body, standing, three-quarter view, natural light",
    "side_full_body": "full body, standing, side view, natural light",
}

STANDARD_POSES: dict[str, str] = {
    "standing_relaxed": "standing relaxed, front view, natural light",
    "walking": "walking toward the camera, candid photo, natural light",
    "sitting": "sitting on a chair, legs crossed, natural light",
    "leaning_wall": "leaning against a wall, casual pose",
    "lying_bed": "lying on a bed, propped up on elbows, warm lamp light",
    "looking_back": "standing, looking back over the shoulder, natural light",
}


def _anchor_embedding(anchor_path: Path | None) -> list[float] | None:
    if anchor_path is None or not anchor_path.is_file():
        return None
    return embedding_for_path(anchor_path)


def _reference_embedding_for_poses(db, dataset_id: str, anchor_path: Path | None) -> list[float] | None:
    """Score pose variations against the selected close-face reference when available."""
    row = db.execute(
        select(ImageLibrary)
        .join(LoraDatasetItem, LoraDatasetItem.image_id == ImageLibrary.id)
        .where(
            LoraDatasetItem.dataset_id == dataset_id,
            LoraDatasetItem.reference_role == "close_face",
            LoraDatasetItem.selected.is_(True),
            ImageLibrary.deleted_at.is_(None),
        )
        .order_by(LoraDatasetItem.similarity.desc())
        .limit(1)
    ).first()
    if row is not None:
        path = (settings.media_dir / row[0].filename).resolve()
        if path.is_file():
            embedding = embedding_for_path(path)
            if embedding is not None:
                return embedding
    return _anchor_embedding(anchor_path)


def _render_edit_batch(
    *,
    job_type: str,
    job_message: str,
    character_id: str,
    dataset_id: str,
    reference_paths: list[Path],
    prompt: str,
    caption: str,
    count: int,
    seed: int | None,
    tags: list[str],
    reference_role: str | None,
    score_embedding: list[float] | None,
) -> list[dict]:
    """Render `count` identity edits from the given references, score them and store items."""
    with Session.begin() as db:
        job = create_job(db, type=job_type, character_id=character_id, dataset_id=dataset_id, message=job_message)
        start_job(db, job, worker="comfyui-edit")
        job_id = job.id

    base_seed = seed if seed is not None else random.randrange(2**31)
    jobs = [
        (reference_paths[index % len(reference_paths)], base_seed + index) for index in range(count)
    ]

    def render(entry: tuple[Path, int]):
        reference, render_seed = entry
        data, meta = qwen_image_edit(
            reference,
            prompt,
            seed=render_seed,
            steps=settings.qwen_edit_steps,
            cfg=settings.qwen_edit_cfg,
            lora_weight=1.0,
            base_url=pick_target(),
        )
        return render_seed, data, meta

    rendered = []
    errors: list[Exception] = []
    with ThreadPoolExecutor(max_workers=count) as pool:
        futures = [pool.submit(render, entry) for entry in jobs]
        for future in futures:
            try:
                rendered.append(future.result())
            except ComfyUIError as error:
                errors.append(error)

    created: list[dict] = []
    for render_seed, data, meta in rendered:
        settings.media_dir.mkdir(parents=True, exist_ok=True)
        filename = f"{identifier()}.png"
        try:
            (settings.media_dir / filename).write_bytes(data)
        except OSError as error:
            raise HTTPException(500, "Could not save the image") from error
        score = similarity_percent(score_embedding, embedding_for(data))
        with Session.begin() as db:
            library = ImageLibrary(
                character_id=character_id,
                filename=filename,
                sha256=hashlib.sha256(data).hexdigest(),
                phash=average_hash(data),
                prompt=prompt,
                negative_prompt="",
                caption="",
                tags=tags,
                checkpoint=meta.get("model"),
                loras=[],
                seed=meta.get("seed", render_seed),
                style="real",
                status="draft",
                rating=0,
                source="dataset",
                used_count=0,
                embedding=[],
                embedding_model="",
            )
            db.add(library)
            db.flush()
            item = LoraDatasetItem(
                dataset_id=dataset_id,
                image_id=library.id,
                pose_ref_id=None,
                caption=" ".join(caption.split()),
                similarity=score if score is not None else 0.0,
                selected=False,
                reference_role=reference_role,
                seed=meta.get("seed", render_seed),
            )
            db.add(item)
            db.flush()
            row = db.get(LoraDataset, dataset_id)
            if row is not None:
                row.updated_at = now()
            entry = dataset_item_out(item, library)
            entry["similarity"] = score
            created.append(entry)

    with Session.begin() as db:
        exec_job = db.get(ExecutionJob, job_id)
        if exec_job is not None and exec_job.state == "running":
            update_progress(db, exec_job, current=len(created), total=count, unit="image")
            finish_job(
                db,
                exec_job,
                state="succeeded" if created else "failed",
                error_info=None
                if created
                else {
                    "code": "dataset_generation_failed",
                    "summary": "Generation failed.",
                    "remediation": "Check the Qwen-Image-Edit model and the references, then retry.",
                    "technical_details": str(errors[0])[:800] if errors else "",
                },
                message=f"{len(created)} images ready",
            )
    if not created:
        raise HTTPException(502, "Generation failed: no image produced")
    return created


class ReferenceSetInput(StrictModel):
    role: str = Field(min_length=1, max_length=40)
    count: int = Field(default=4, ge=1, le=4)
    seed: int | None = Field(default=None, ge=0, le=2**31)


@router.post("/datasets/{dataset_id}/references", status_code=201)
def generate_reference_set(dataset_id: str, body: ReferenceSetInput):
    """Canonical references for one role, generated by editing the profile picture."""
    if body.role not in CANONICAL_ROLE_PROMPTS:
        raise HTTPException(400, f"Unknown role: {body.role}")
    with Session() as db:
        dataset = required(db, LoraDataset, dataset_id)
        character = required(db, Influencer, dataset.character_id)
        anchor_path = None
        if dataset.anchor_image_id:
            anchor = db.get(ImageLibrary, dataset.anchor_image_id)
            if anchor is not None:
                candidate = (settings.media_dir / anchor.filename).resolve()
                if candidate.is_file():
                    anchor_path = candidate
        if anchor_path is None and character.avatar_filename:
            candidate = (settings.media_dir / character.avatar_filename).resolve()
            if candidate.is_file():
                anchor_path = candidate
        if anchor_path is None:
            raise HTTPException(400, "Generate the profile picture first: it is the identity anchor")
        character_id = dataset.character_id
        trigger = dataset.trigger
        identity = (character.avatar_prompt or "").strip()
    prompt = ", ".join(
        part for part in [identity, CANONICAL_ROLE_PROMPTS[body.role], "same person, keep hair, age, skin and identity fixed"] if part
    )
    caption = ", ".join(part for part in [trigger, CANONICAL_ROLE_PROMPTS[body.role]] if part)
    created = _render_edit_batch(
        job_type="dataset_generate",
        job_message=f"canonical references: {body.role} x{body.count}",
        character_id=character_id,
        dataset_id=dataset_id,
        reference_paths=[anchor_path],
        prompt=prompt,
        caption=caption,
        count=body.count,
        seed=body.seed,
        tags=["canonical", body.role],
        reference_role=body.role,
        score_embedding=_anchor_embedding(anchor_path),
    )
    return _mark_recommended(created, top=2)


class PoseVariationInput(StrictModel):
    pose: str = Field(min_length=1, max_length=40)
    count: int = Field(default=4, ge=1, le=4)
    seed: int | None = Field(default=None, ge=0, le=2**31)


@router.post("/datasets/{dataset_id}/pose-variations", status_code=201)
def generate_pose_variations(dataset_id: str, body: PoseVariationInput):
    """Standard pose variations for every LoRA, edited from the selected canonical references."""
    if body.pose not in STANDARD_POSES:
        raise HTTPException(400, f"Unknown pose: {body.pose}")
    with Session() as db:
        dataset = required(db, LoraDataset, dataset_id)
        character = required(db, Influencer, dataset.character_id)
        anchor_path = None
        if character.avatar_filename:
            candidate = (settings.media_dir / character.avatar_filename).resolve()
            if candidate.is_file():
                anchor_path = candidate
        reference_paths = _selected_references(db, dataset_id)
        if not reference_paths:
            raise HTTPException(
                400,
                "Select at least one canonical reference first: pose variations are edited from step 1 photos.",
            )
        character_id = dataset.character_id
        trigger = dataset.trigger
        identity = (character.avatar_prompt or "").strip()
        score_embedding = _reference_embedding_for_poses(db, dataset_id, anchor_path)
    prompt = ", ".join(
        part for part in [identity, STANDARD_POSES[body.pose], "same person, keep hair, age, skin and identity fixed"] if part
    )
    caption = ", ".join(part for part in [trigger, STANDARD_POSES[body.pose]] if part)
    created = _render_edit_batch(
        job_type="dataset_generate",
        job_message=f"pose variation: {body.pose} x{body.count}",
        character_id=character_id,
        dataset_id=dataset_id,
        reference_paths=reference_paths,
        prompt=prompt,
        caption=caption,
        count=body.count,
        seed=body.seed,
        tags=["pose", body.pose],
        reference_role=None,
        score_embedding=score_embedding,
    )
    return _mark_recommended(created, top=2)


def _mark_recommended(items: list[dict], top: int = 2) -> list[dict]:
    scored = [entry for entry in items if entry.get("similarity") is not None]
    scored.sort(key=lambda entry: entry["similarity"], reverse=True)
    for entry in scored[:top]:
        entry["recommended"] = True
    return items


def _selected_references(db, dataset_id: str) -> list[Path]:
    rows = list(
        db.execute(
            select(ImageLibrary)
            .join(LoraDatasetItem, LoraDatasetItem.image_id == ImageLibrary.id)
            .where(
                LoraDatasetItem.dataset_id == dataset_id,
                LoraDatasetItem.reference_role.isnot(None),
                LoraDatasetItem.selected.is_(True),
                ImageLibrary.deleted_at.is_(None),
            )
            .order_by(LoraDatasetItem.created_at)
        )
    )
    paths: list[Path] = []
    for (library,) in rows:
        candidate = (settings.media_dir / library.filename).resolve()
        if candidate.is_file():
            paths.append(candidate)
    return paths[:8]


REFERENCE_ROLES = (
    "close_face",
    "three_quarter_face",
    "profile",
    "upper_body",
    "front_full_body",
    "three_quarter_full_body",
    "side_full_body",
)


IDENTITY_ROLE_ORDER = (
    "full_body",
    "upper_body",
    "three_quarter_left",
    "three_quarter_right",
    "profile_left",
    "profile_right",
    "close_front",
    "front",
    "yaw",
    "pitch",
)


def identity_set_references(db, character_id: str) -> tuple[list[Path], str | None]:
    """Paths of the accepted candidates of the latest frozen identity run, plus its id.

    Ordered to prioritize body and three-quarter views over close-ups so scene edits keep both
    face and body identity.
    """
    run = db.scalar(
        select(IdentityRun)
        .where(IdentityRun.character_id == character_id, IdentityRun.status == "frozen")
        .order_by(IdentityRun.frozen_at.desc())
        .limit(1)
    )
    if run is None:
        return [], None
    rows = list(
        db.execute(
            select(IdentityCandidate, ImageLibrary)
            .join(ImageLibrary, IdentityCandidate.image_id == ImageLibrary.id)
            .where(
                IdentityCandidate.run_id == run.id,
                IdentityCandidate.status == "accepted",
                ImageLibrary.deleted_at.is_(None),
            )
        )
    )
    from .identity_api import ANGLE_INDEX

    def role_of(candidate: IdentityCandidate) -> str:
        entry = ANGLE_INDEX.get(candidate.angle)
        return entry[1] if entry else "other"

    rows.sort(key=lambda pair: IDENTITY_ROLE_ORDER.index(role_of(pair[0])) if role_of(pair[0]) in IDENTITY_ROLE_ORDER else 99)
    paths: list[Path] = []
    for _candidate, library in rows:
        candidate_path = (settings.media_dir / library.filename).resolve()
        if candidate_path.is_file():
            paths.append(candidate_path)
    return paths[:8], run.id


def _dataset_references(db, dataset_id: str) -> list[Path]:
    """Canonical reference images of a dataset, ordered by role."""
    rows = list(
        db.execute(
            select(LoraDatasetItem, ImageLibrary)
            .join(ImageLibrary, LoraDatasetItem.image_id == ImageLibrary.id)
            .where(
                LoraDatasetItem.dataset_id == dataset_id,
                LoraDatasetItem.reference_role.isnot(None),
                ImageLibrary.deleted_at.is_(None),
            )
        )
    )
    order = {role: index for index, role in enumerate(REFERENCE_ROLES)}
    rows.sort(key=lambda pair: order.get(pair[0].reference_role or "", 99))
    paths: list[Path] = []
    for _item, library in rows:
        candidate = (settings.media_dir / library.filename).resolve()
        if candidate.is_file():
            paths.append(candidate)
    return paths


@router.get("/loras/{lora_id}/recommendation")
def lora_recommendation(lora_id: str, dataset_id: str | None = None):
    """Auto-recommended training hyperparameters from family and dataset size."""
    with Session() as db:
        lora = required(db, CharacterLora, lora_id)
        selected = 0
        if dataset_id:
            selected = db.scalar(
                select(func.count())
                .select_from(LoraDatasetItem)
                .join(ImageLibrary, LoraDatasetItem.image_id == ImageLibrary.id)
                .where(LoraDatasetItem.dataset_id == dataset_id, LoraDatasetItem.selected.is_(True))
            ) or 0
        family = lora.family

    images = max(selected, 4)
    if family == "qwen-image":
        rank = 16 if images < 30 else 24
        steps = max(1000, min(2500, images * 30))
        learning_rate = 0.00005
        resolution = 1024
        repeats = 1
        rationale = "qwen-image: lower rank and LR, one pass per image, more steps."
    else:
        rank = 16 if images < 20 else 24 if images <= 40 else 32
        steps = max(800, min(3000, images * 40))
        learning_rate = 0.0001
        resolution = 1024
        repeats = max(1, round(60 / images))
        rationale = "SDXL family: rank by dataset size, ~40 steps per image, repeats to reach ~60 images per epoch."
    return {
        "family": family,
        "selected": selected,
        "rank": rank,
        "steps": steps,
        "learning_rate": learning_rate,
        "resolution": resolution,
        "repeats": repeats,
        "rationale": rationale,
    }


@router.get("/loras/{lora_id}/preflight")
def lora_preflight(lora_id: str, dataset_id: str | None = None):
    """Preflight checks shown before queueing training, as remediation cards."""
    checks: list[dict] = []

    def add(code: str, ok: bool, summary: str, remediation: str = "") -> None:
        checks.append({"code": code, "ok": ok, "summary": summary, "remediation": remediation})

    with Session() as db:
        lora = required(db, CharacterLora, lora_id)
        character = db.get(Influencer, lora.character_id)
        checkpoint = lora.base_checkpoint or (character.image_checkpoint if character else None)
        if not checkpoint:
            add("checkpoint_missing", False, "No base checkpoint selected.", "Set a base checkpoint on the LoRA or the character.")
        else:
            meta = checkpoint_meta(checkpoint)
            if not meta.get("usable"):
                add("checkpoint_missing", False, f"Checkpoint {checkpoint} is not installed in ComfyUI.", "Install it or pick another checkpoint.")
            elif lora.family == "qwen-image" and meta.get("family") not in (None, "qwen-image"):
                add("family_mismatch", False, f"Checkpoint family {meta.get('family')} does not match qwen-image.", "Pick a qwen-image checkpoint or change the LoRA family.")
            elif lora.family != "qwen-image" and meta.get("family") in ("qwen-image", "flux2", "z-image"):
                add("family_mismatch", False, f"Checkpoint family {meta.get('family')} does not match {lora.family}.", f"Set the LoRA family to {meta.get('family')} or pick a {lora.family} checkpoint.")
            else:
                add("checkpoint_ok", True, f"Checkpoint {checkpoint} is installed.")

        if lora.status in LORA_BUSY:
            add("no_conflict", False, "This LoRA already has a run in progress.", "Wait for it to finish or cancel the job first.")
        else:
            add("no_conflict", True, "No conflicting run for this LoRA.")

        running = db.scalar(select(TrainingJob).where(TrainingJob.status == "running").limit(1))
        if running is not None:
            fresh = running.heartbeat_at is not None and (now() - running.heartbeat_at).total_seconds() < 600
            add(
                "worker_busy",
                not fresh,
                "The trainer is running another job." if fresh else "A stale run exists (worker not responding).",
                "Queue now: the worker picks jobs in order." if fresh else "The stale run will be recovered automatically.",
            )
        else:
            add("worker_idle", True, "The trainer queue is free.")

        if dataset_id:
            dataset = db.get(LoraDataset, dataset_id)
            if dataset is None:
                add("dataset_missing", False, "The dataset was not found.", "Pick an existing dataset.")
            elif dataset.character_id != lora.character_id:
                add("dataset_owner", False, "The dataset belongs to another character.", "Pick a dataset of this character.")
            else:
                usable = db.scalar(
                    select(func.count())
                    .select_from(LoraDatasetItem)
                    .join(ImageLibrary, LoraDatasetItem.image_id == ImageLibrary.id)
                    .where(LoraDatasetItem.dataset_id == dataset.id, LoraDatasetItem.selected.is_(True))
                ) or 0
                add(
                    "dataset_size",
                    usable >= 4,
                    f"{usable} selected images are ready for training.",
                    "Select at least 4 images (aim for 50-70).",
                )
                captions = db.scalars(
                    select(LoraDatasetItem.caption)
                    .where(LoraDatasetItem.dataset_id == dataset.id, LoraDatasetItem.selected.is_(True))
                ).all()
                trigger = dataset.trigger or ""
                with_trigger = sum(1 for caption in captions if trigger and trigger.lower() in (caption or "").lower())
                add(
                    "trigger_in_captions",
                    with_trigger > 0 or not trigger,
                    f"Trigger appears in {with_trigger}/{len(captions)} selected captions.",
                    "Add the trigger to captions before training.",
                )
        else:
            add("dataset_none", True, "No dataset selected (training from an image folder).")

        try:
            import shutil

            free = shutil.disk_usage(settings.lora_dir).free
            add("disk_space", free > 5 * 1024**3, f"{free / 1024**3:.1f} GB free on the LoRA volume.", "Free disk space before training.")
        except OSError:
            add("disk_space", True, "Disk space not checked.")

    return {"ok": all(check["ok"] for check in checks), "checks": checks}


VALIDATION_PROMPTS = (
    ("close_face", "close-up portrait of the face, neutral expression, studio light"),
    ("profile", "profile view, looking to the side, studio light"),
    ("upper_body", "upper body portrait, front view, natural window light"),
    ("full_body", "full body, standing, front view, natural light"),
    ("lifestyle_street", "walking on a sunny city street, casual outfit, candid photo"),
    ("lifestyle_home", "relaxing at home on a sofa, warm lamp light, candid photo"),
    ("difficult_pose", "sitting on the floor, leaning against a wall, looking up at the camera"),
)


class ValidationInput(StrictModel):
    weight: float = Field(default=0.85, ge=0, le=2)
    seed: int | None = Field(default=None, ge=0, le=2**31 - 1)
    checkpoint: str | None = Field(default=None, max_length=200)


@router.post("/loras/{lora_id}/validation", status_code=201)
def create_validation_grid(lora_id: str, body: ValidationInput):
    """Render the fixed validation grid for a trained LoRA before activation."""
    with Session() as db:
        lora = required(db, CharacterLora, lora_id)
        if not lora.filename:
            raise HTTPException(400, "The LoRA has no trained artifact yet")
        character = required(db, Influencer, lora.character_id)
        checkpoint = body.checkpoint or lora.base_checkpoint or character.image_checkpoint
        style = character.image_style or "real"
        reference = (settings.media_dir / character.avatar_filename) if character.avatar_filename else None
        identity = (character.avatar_prompt or "").strip()
        trigger = lora.trigger
        family = lora.family
        filename = lora.filename
        character_id = lora.character_id

    with Session.begin() as db:
        job = create_job(
            db,
            type="lora_validation",
            character_id=character_id,
            message=f"validation grid for {filename}",
        )
        start_job(db, job, worker="comfyui")
        job_id = job.id

    base_seed = body.seed if body.seed is not None else random.randrange(2**31)
    prompts = [
        (key, ", ".join(part for part in [trigger, identity, fragment] if part))
        for key, fragment in VALIDATION_PROMPTS
    ]

    def render(entry: tuple[str, str], index: int):
        key, prompt = entry
        data, meta = generate_image(
            prompt,
            build_negative_prompt(family),
            seed=base_seed + index,
            reference_path=reference,
            checkpoint=checkpoint,
            style=style,
            family=family,
            loras=[{"name": filename, "weight": body.weight}],
            base_url=pick_target(),
        )
        return key, prompt, data, meta

    rendered = []
    errors: list[Exception] = []
    with ThreadPoolExecutor(max_workers=len(prompts)) as pool:
        futures = [pool.submit(render, entry, index) for index, entry in enumerate(prompts)]
        for future in futures:
            try:
                rendered.append(future.result())
            except ComfyUIError as error:
                errors.append(error)

    created: list[dict] = []
    for key, prompt, data, meta in rendered:
        settings.media_dir.mkdir(parents=True, exist_ok=True)
        out_name = f"{identifier()}.png"
        (settings.media_dir / out_name).write_bytes(data)
        with Session.begin() as db:
            library = ImageLibrary(
                character_id=character_id,
                filename=out_name,
                sha256=hashlib.sha256(data).hexdigest(),
                phash=average_hash(data),
                prompt=prompt,
                negative_prompt=build_negative_prompt(family),
                caption="",
                tags=["validation", key, filename],
                checkpoint=meta.get("checkpoint") or checkpoint,
                loras=[{"name": filename, "weight": body.weight}],
                seed=meta.get("seed", base_seed),
                style=style,
                status="draft",
                rating=0,
                source="validation",
                used_count=0,
                embedding=[],
                embedding_model="",
            )
            db.add(library)
            db.flush()
            created.append({
                "id": library.id,
                "filename": library.filename,
                "prompt": library.prompt,
                "seed": library.seed,
                "tags": library.tags,
                "status": library.status,
                "source": library.source,
            })

    with Session.begin() as db:
        exec_job = db.get(ExecutionJob, job_id)
        if exec_job is not None and exec_job.state == "running":
            update_progress(db, exec_job, current=len(created), total=len(prompts), unit="image")
            finish_job(
                db,
                exec_job,
                state="succeeded" if created else "failed",
                error_info=None
                if created
                else {
                    "code": "lora_validation_failed",
                    "summary": "Validation grid generation failed.",
                    "remediation": "Check the ComfyUI instance and the LoRA file, then retry.",
                    "technical_details": str(errors[0])[:800] if errors else "",
                },
                message=f"{len(created)} validation images",
            )
    if not created:
        raise HTTPException(502, "Validation grid failed: no image produced")
    return created


@router.get("/datasets/{dataset_id}/blueprint")
def dataset_blueprint(dataset_id: str):
    """Per-category progress of the selected items against the 60-image blueprint."""
    with Session() as db:
        required(db, LoraDataset, dataset_id)
        rows = list(
            db.execute(
                select(LoraDatasetItem, ImageLibrary)
                .outerjoin(ImageLibrary, LoraDatasetItem.image_id == ImageLibrary.id)
                .where(LoraDatasetItem.dataset_id == dataset_id, LoraDatasetItem.selected.is_(True))
            )
        )
    selected = len(rows)
    categories = []
    matched_total = 0
    for key, target, keywords in BLUEPRINT:
        count = 0
        for item, library in rows:
            text_value = " ".join(filter(None, [item.caption, library.prompt if library else ""])).lower()
            if any(keyword in text_value for keyword in keywords):
                count += 1
        matched_total += count
        categories.append({"key": key, "target": target, "count": count})
    return {
        "target": DATASET_TARGET,
        "selected": selected,
        "categories": categories,
        "other": max(0, selected - matched_total),
        "missing_total": max(0, DATASET_TARGET - selected),
    }


@router.get("/datasets/{dataset_id}/analysis")
def dataset_analysis(dataset_id: str):
    """Deterministic quality analysis for the curation UI (keyword + phash based)."""
    with Session() as db:
        required(db, LoraDataset, dataset_id)
        rows = list(
            db.execute(
                select(LoraDatasetItem, ImageLibrary)
                .outerjoin(ImageLibrary, LoraDatasetItem.image_id == ImageLibrary.id)
                .where(LoraDatasetItem.dataset_id == dataset_id)
            )
        )
        pose_names = {pose.id: pose.name for pose in db.scalars(select(PoseReference))}
    total = len(rows)
    selected = sum(1 for item, _ in rows if item.selected)
    captions = [(item.caption or (library.prompt if library else "") or "").lower() for item, library in rows]
    keywords = {
        name: sum(1 for text in captions if any(word in text for word in words))
        for name, words in KEYWORD_GROUPS.items()
    }
    phashes: dict[str, int] = {}
    for _, library in rows:
        if library and library.phash:
            phashes[library.phash] = phashes.get(library.phash, 0) + 1
    duplicates = sum(count - 1 for count in phashes.values() if count > 1)
    pose_counts: dict[str, int] = {}
    reference_counts: dict[str, int] = {}
    for item, _ in rows:
        if item.pose_ref_id:
            pose_counts[item.pose_ref_id] = pose_counts.get(item.pose_ref_id, 0) + 1
        if item.reference_role:
            reference_counts[item.reference_role] = reference_counts.get(item.reference_role, 0) + 1
    caption_counts: dict[str, int] = {}
    for text in captions:
        if text:
            caption_counts[text] = caption_counts.get(text, 0) + 1
    repeated_caption = max(caption_counts.values()) if caption_counts else 0

    warnings: list[dict] = []

    def warn(code: str, detail: str) -> None:
        warnings.append({"code": code, "detail": detail})

    if selected < DATASET_TARGET:
        warn("select_more", f"{selected}/{DATASET_TARGET} selezionate")
    if total and len(reference_counts) < 4:
        warn("few_references", f"solo {len(reference_counts)} reference canoniche (servono 4-8)")
    if duplicates:
        warn("duplicates", f"{duplicates} immagini quasi identiche")
    if total >= 10:
        if keywords["full_body"] < max(2, int(total * 0.1)):
            warn("few_full_body", f"solo {keywords['full_body']} full body")
        if keywords["profile"] < max(1, int(total * 0.1)):
            warn("few_profile", f"solo {keywords['profile']} profili")
        if keywords["front"] > total * 0.7:
            warn("too_frontal", f"{keywords['front']} frontali su {total}")
        if pose_counts:
            top_id = max(pose_counts, key=pose_counts.get)
            if pose_counts[top_id] > total * 0.6:
                warn("same_pose", f"posa '{pose_names.get(top_id, top_id)}' usata {pose_counts[top_id]} volte")
        if repeated_caption > total * 0.5:
            warn("same_scene", "stessa scena ripetuta in oltre metà delle immagini")
    return {
        "total": total,
        "selected": selected,
        "target": DATASET_TARGET,
        "keywords": keywords,
        "duplicates": duplicates,
        "reference_counts": reference_counts,
        "pose_counts": [
            {"pose_id": pose_id, "name": pose_names.get(pose_id, pose_id), "count": count}
            for pose_id, count in pose_counts.items()
        ],
        "warnings": warnings,
    }


@router.patch("/dataset-items/{item_id}")
def patch_dataset_item(item_id: str, body: DatasetItemPatch):
    with Session.begin() as db:
        item = required(db, LoraDatasetItem, item_id)
        if body.caption is not None:
            item.caption = body.caption
        if body.selected is not None:
            item.selected = body.selected
        if body.reference_role is not None:
            role = body.reference_role or None
            if role is not None and role not in REFERENCE_ROLES:
                raise HTTPException(400, "Invalid reference role")
            item.reference_role = role
        library = db.get(ImageLibrary, item.image_id) if item.image_id else None
        db.flush()
        return dataset_item_out(item, library)


@router.post("/loras/dataset-items/bulk-delete")
def delete_dataset_items(body: BulkIdsInput):
    filenames: list[str] = []
    with Session.begin() as db:
        items = db.scalars(select(LoraDatasetItem).where(LoraDatasetItem.id.in_(body.ids))).all()
        for item in items:
            library = db.get(ImageLibrary, item.image_id) if item.image_id else None
            if library is not None:
                filenames.append(library.filename)
                db.execute(
                    update(LoraDataset)
                    .where(LoraDataset.anchor_image_id == library.id)
                    .values(anchor_image_id=None)
                )
            db.delete(item)
            db.flush()
            if library is not None:
                db.delete(library)
        deleted = len(items)
    for filename in filenames:
        path = (settings.media_dir / filename).resolve()
        if path.is_relative_to(settings.media_dir.resolve()):
            path.unlink(missing_ok=True)
    return {"deleted": deleted}


@router.delete("/dataset-items/{item_id}")
def delete_dataset_item(item_id: str):
    filename = None
    with Session.begin() as db:
        item = required(db, LoraDatasetItem, item_id)
        library = db.get(ImageLibrary, item.image_id) if item.image_id else None
        if library is not None:
            filename = library.filename
            db.execute(
                update(LoraDataset)
                .where(LoraDataset.anchor_image_id == library.id)
                .values(anchor_image_id=None)
            )
        db.delete(item)
        db.flush()
        if library is not None:
            db.delete(library)
    if filename:
        path = (settings.media_dir / filename).resolve()
        if path.is_relative_to(settings.media_dir.resolve()):
            path.unlink(missing_ok=True)
    return {"deleted": True, "id": item_id}
