"""Operational metrics: queue/run times, success rates, asset and dataset coverage."""

import json
import shutil
from datetime import UTC, datetime
from pathlib import Path

from fastapi import APIRouter, Depends
from sqlalchemy import func, select

from .auth import authorize
from .config import settings
from .db import (
    CharacterLora,
    ExecutionJob,
    IdentityRun,
    ImageLibrary,
    Influencer,
    LoraDataset,
    LoraDatasetItem,
    Session,
    VideoClip,
)
from .integrations.comfyui import checkpoint_meta, get_checkpoints, workflow_checkpoint

router = APIRouter(prefix="/api", tags=["Metrics"], dependencies=[Depends(authorize)])

FINISHED = ("succeeded", "failed", "canceled")


@router.get("/metrics")
def get_metrics():
    with Session() as db:
        def count(model, *criteria):
            return db.scalar(select(func.count()).select_from(model).where(*criteria)) or 0

        jobs_by_state: dict[str, int] = {}
        for state in ("queued", "running", "succeeded", "failed", "canceled"):
            jobs_by_state[state] = count(ExecutionJob, ExecutionJob.state == state)

        by_type: dict[str, dict[str, int]] = {}
        for job_type, state in db.execute(
            select(ExecutionJob.type, ExecutionJob.state).where(ExecutionJob.state.in_(FINISHED))
        ).all():
            entry = by_type.setdefault(job_type, {})
            entry[state] = entry.get(state, 0) + 1

        run_times: dict[str, float] = {}
        queue_times: dict[str, float] = {}
        finished = db.scalars(
            select(ExecutionJob)
            .where(ExecutionJob.state.in_(FINISHED), ExecutionJob.started_at.is_not(None))
            .order_by(ExecutionJob.finished_at.desc())
            .limit(300)
        ).all()
        durations: dict[str, list[float]] = {}
        queues: dict[str, list[float]] = {}
        for job in finished:
            if job.started_at and job.created_at:
                queues.setdefault(job.type, []).append((job.started_at - job.created_at).total_seconds())
            if job.finished_at and job.started_at:
                durations.setdefault(job.type, []).append((job.finished_at - job.started_at).total_seconds())
        for job_type, values in durations.items():
            run_times[job_type] = round(sum(values) / len(values), 1)
        for job_type, values in queues.items():
            queue_times[job_type] = round(sum(values) / len(values), 1)

        library_total = count(ImageLibrary, ImageLibrary.deleted_at.is_(None))
        approved = count(ImageLibrary, ImageLibrary.status == "approved", ImageLibrary.deleted_at.is_(None))
        videos_total = count(VideoClip)
        datasets = db.scalars(select(LoraDataset)).all()
        selected_total = db.scalar(
            select(func.count()).select_from(LoraDatasetItem).where(LoraDatasetItem.selected.is_(True))
        ) or 0

        available_checkpoints = {item["name"] for item in get_checkpoints()}
        missing_checkpoints = []
        for lora in db.scalars(
            select(CharacterLora).where(CharacterLora.base_checkpoint.is_not(None))
        ).all():
            meta = checkpoint_meta(lora.base_checkpoint or "")
            if not meta.get("usable") or (available_checkpoints and lora.base_checkpoint not in available_checkpoints):
                missing_checkpoints.append(lora.name)
        for workflow_path in sorted(Path("workflows").glob("*.json")):
            try:
                name = workflow_checkpoint(json.loads(workflow_path.read_text()))
            except (OSError, ValueError):
                continue
            if name and available_checkpoints and name not in available_checkpoints:
                missing_checkpoints.append(f"{workflow_path.name}: {name}")

        backup_info: dict = {}
        backups_dir = settings.media_dir.parent.parent / "backups"
        if not backups_dir.is_dir():
            backups_dir = Path("/app/backups")
        try:
            archives = sorted(
                (path for path in backups_dir.glob("*.tgz") if path.is_file()),
                key=lambda path: path.stat().st_mtime,
            )
            if archives:
                last = archives[-1]
                backup_info = {
                    "last_file": last.name,
                    "last_at": datetime.fromtimestamp(last.stat().st_mtime, tz=UTC).isoformat(),
                    "size_bytes": last.stat().st_size,
                    "count": len(archives),
                }
        except OSError:
            pass

        media_bytes = 0
        media_files = 0
        try:
            for entry in settings.media_dir.iterdir():
                if entry.is_file():
                    media_bytes += entry.stat().st_size
                    media_files += 1
        except OSError:
            pass
        disk_free = disk_total = 0
        try:
            usage = shutil.disk_usage(settings.media_dir if settings.media_dir.exists() else settings.media_dir.parent)
            disk_free, disk_total = usage.free, usage.total
        except OSError:
            pass

        return {
            "models": {
                "loras_missing_checkpoint": len(missing_checkpoints),
                "missing_sample": missing_checkpoints[:5],
            },
            "backups": backup_info,
            "storage": {
                "media_bytes": media_bytes,
                "media_files": media_files,
                "disk_free_bytes": disk_free,
                "disk_total_bytes": disk_total,
            },
            "jobs": {
                "by_state": jobs_by_state,
                "by_type": by_type,
                "avg_run_seconds": run_times,
                "avg_queue_seconds": queue_times,
            },
            "library": {
                "total": library_total,
                "approved": approved,
                "draft": count(ImageLibrary, ImageLibrary.status == "draft", ImageLibrary.deleted_at.is_(None)),
                "rejected": count(ImageLibrary, ImageLibrary.status == "rejected", ImageLibrary.deleted_at.is_(None)),
                "trashed": count(ImageLibrary, ImageLibrary.deleted_at.is_not(None)),
                "approval_rate": round(approved / library_total, 3) if library_total else 0.0,
            },
            "videos": {
                "total": videos_total,
                "draft": count(VideoClip, VideoClip.review_status == "draft"),
                "approved": count(VideoClip, VideoClip.review_status == "approved"),
                "rejected": count(VideoClip, VideoClip.review_status == "rejected"),
            },
            "datasets": {"count": len(datasets), "selected_items": selected_total},
            "identity": {
                "runs": count(IdentityRun),
                "frozen": count(IdentityRun, IdentityRun.status == "frozen"),
            },
            "characters": {
                "total": count(Influencer),
                "with_ready_lora": db.scalar(
                    select(func.count(func.distinct(CharacterLora.character_id))).where(CharacterLora.status == "ready")
                )
                or 0,
            },
        }
