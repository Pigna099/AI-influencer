"""Operational metrics: queue/run times, success rates, asset and dataset coverage."""

from fastapi import APIRouter, Depends
from sqlalchemy import func, select

from .auth import authorize
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

        return {
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
