"""Per-character LoRA registry and training job queue (pipeline Phase A)."""

import hashlib
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

from .auth import authorize
from .char_schemas import BulkIdsInput, StrictModel
from .chat_service import build_negative_prompt, translate_scene
from .config import settings
from .db import (
    CharacterLora,
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
    if not body.images_dir and not body.dataset_id:
        raise HTTPException(400, "Indica una cartella immagini o un dataset")
    with Session.begin() as db:
        lora = required(db, CharacterLora, lora_id)
        if lora.status in LORA_BUSY:
            raise HTTPException(409, "Training già in corso per questa LoRA")
        dataset = required(db, LoraDataset, body.dataset_id) if body.dataset_id else None
        if dataset is not None and dataset.character_id != lora.character_id:
            raise HTTPException(400, "Il dataset appartiene a un altro personaggio")
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
            if job.status == "canceled":
                lora = db.get(CharacterLora, job.lora_id) if job.lora_id else None
                character = db.get(Influencer, job.character_id)
                return job_out(job, lora, character)
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


def materialize_dataset(db, dataset: LoraDataset, stem: str) -> Path:
    """Copy the selected dataset images + captions into a folder the trainer can use."""
    rows = list(
        db.execute(
            select(LoraDatasetItem, ImageLibrary)
            .join(ImageLibrary, LoraDatasetItem.image_id == ImageLibrary.id)
            .where(LoraDatasetItem.dataset_id == dataset.id, LoraDatasetItem.selected.is_(True))
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
        raise HTTPException(400, "Servono almeno 4 immagini selezionate e disponibili nel dataset")
    return folder


class DatasetCreate(StrictModel):
    family: Literal["real", "pony", "anime"] = "real"
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
                raise HTTPException(404, "Una o più pose non sono state trovate")
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
        reference_paths = _dataset_references(db, dataset_id)
    if not reference_paths and anchor_path is not None:
        reference_paths = [anchor_path]
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
        raise HTTPException(
            502, f"Generazione dataset non riuscita: {errors[0] if errors else 'errore sconosciuto'}"
        )
    created: list[dict] = []
    for pose, seed, data, meta in rendered:
        settings.media_dir.mkdir(parents=True, exist_ok=True)
        filename = f"{identifier()}.png"
        try:
            (settings.media_dir / filename).write_bytes(data)
        except OSError as error:
            raise HTTPException(500, "Impossibile salvare l'immagine") from error
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
                caption=body.prompt,
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
                400, "Serve un'immagine anchor: genera la foto profilo o imposta l'anchor del dataset"
            )
        character_id = dataset.character_id
        trigger = dataset.trigger
        reference_paths = _dataset_references(db, dataset_id)
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
        raise HTTPException(
            502, f"Generazione variazioni non riuscita: {errors[0] if errors else 'errore sconosciuto'}"
        )
    created: list[dict] = []
    for prompt, seed, data, meta in rendered:
        caption = prompt if (not trigger or trigger in prompt) else f"{trigger}, {prompt}"
        settings.media_dir.mkdir(parents=True, exist_ok=True)
        filename = f"{identifier()}.png"
        try:
            (settings.media_dir / filename).write_bytes(data)
        except OSError as error:
            raise HTTPException(500, "Impossibile salvare l'immagine") from error
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
                caption=prompt,
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
REFERENCE_ROLES = (
    "close_face",
    "three_quarter_face",
    "profile",
    "upper_body",
    "front_full_body",
    "three_quarter_full_body",
    "side_full_body",
)


def _dataset_references(db, dataset_id: str) -> list[Path]:
    """Canonical reference images of a dataset, ordered by role."""
    rows = list(
        db.execute(
            select(LoraDatasetItem, ImageLibrary)
            .join(ImageLibrary, LoraDatasetItem.image_id == ImageLibrary.id)
            .where(LoraDatasetItem.dataset_id == dataset_id, LoraDatasetItem.reference_role.isnot(None))
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
                raise HTTPException(400, "Ruolo di reference non valido")
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
