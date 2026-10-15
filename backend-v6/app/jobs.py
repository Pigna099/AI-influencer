"""Unified job system: execution records for every long-running operation.

Domain tables stay the source of domain state; `jobs` records execution state
(progress, heartbeat, worker/GPU, structured errors) so every operation shows
up in one list. `job_events` is an append-only audit trail per job.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, func, select

from .db import ExecutionJob, JobEvent, identifier, now

ACTIVE_STATES = ("queued", "running")
FINAL_STATES = ("succeeded", "failed", "canceled")

STALE_AFTER_SECONDS = {
    "training": 600,
    "image": 900,
    "video": 1800,
    "dataset_generate": 1800,
    "dataset_variation": 1200,
    "dataset_import": 1800,
    "dataset_classify": 900,
    "consistency_check": 600,
    "identity_run": 1800,
    "pose_extract": 300,
    "avatar": 900,
}
DEFAULT_STALE_AFTER = 900


def job_out(job: ExecutionJob, queue_position: int | None = None) -> dict:
    return {
        "id": job.id,
        "type": job.type,
        "state": job.state,
        "character_id": job.character_id,
        "dataset_id": job.dataset_id,
        "asset_id": job.asset_id,
        "external_id": job.external_id,
        "progress": job.progress or {},
        "queue_position": queue_position,
        "worker": job.worker,
        "gpu": job.gpu,
        "heartbeat_at": job.heartbeat_at.isoformat() if job.heartbeat_at else None,
        "idempotency_key": job.idempotency_key,
        "error_info": job.error_info,
        "cancel_requested": job.cancel_requested,
        "retry_of": job.retry_of,
        "created_at": job.created_at.isoformat(),
        "started_at": job.started_at.isoformat() if job.started_at else None,
        "finished_at": job.finished_at.isoformat() if job.finished_at else None,
    }


def event_out(event: JobEvent) -> dict:
    return {
        "id": event.id,
        "job_id": event.job_id,
        "level": event.level,
        "message": event.message,
        "created_at": event.created_at.isoformat(),
    }


def add_event(db, job: ExecutionJob, message: str, level: str = "info") -> None:
    db.add(JobEvent(id=identifier(), job_id=job.id, level=level, message=message[:2000]))


def create_job(
    db,
    *,
    type: str,
    character_id: str | None = None,
    dataset_id: str | None = None,
    asset_id: str | None = None,
    external_id: str | None = None,
    idempotency_key: str | None = None,
    retry_of: str | None = None,
    worker: str | None = None,
    gpu: int | None = None,
    message: str | None = None,
) -> ExecutionJob:
    if idempotency_key:
        existing = db.scalar(select(ExecutionJob).where(ExecutionJob.idempotency_key == idempotency_key))
        if existing is not None:
            return existing
    job = ExecutionJob(
        id=identifier(),
        type=type,
        state="queued",
        character_id=character_id,
        dataset_id=dataset_id,
        asset_id=asset_id,
        external_id=external_id,
        idempotency_key=idempotency_key,
        retry_of=retry_of,
        worker=worker,
        gpu=gpu,
    )
    db.add(job)
    db.flush()
    add_event(db, job, message or f"{type} queued")
    return job


def start_job(db, job: ExecutionJob, *, worker: str | None = None, gpu: int | None = None, message: str | None = None) -> None:
    job.state = "running"
    job.started_at = job.started_at or now()
    job.heartbeat_at = now()
    if worker:
        job.worker = worker
    if gpu is not None:
        job.gpu = gpu
    add_event(db, job, message or f"{job.type} started")


def update_progress(
    db,
    job: ExecutionJob,
    *,
    current: float | None = None,
    total: float | None = None,
    unit: str | None = None,
    message: str | None = None,
) -> None:
    progress = dict(job.progress or {})
    if current is not None:
        progress["current"] = current
    if total is not None:
        progress["total"] = total
    if unit is not None:
        progress["unit"] = unit
    job.progress = progress
    job.heartbeat_at = now()
    if message:
        add_event(db, job, message)


def heartbeat(db, job: ExecutionJob) -> None:
    job.heartbeat_at = now()


def finish_job(
    db,
    job: ExecutionJob,
    *,
    state: str,
    error_info: dict | None = None,
    message: str | None = None,
) -> None:
    if state not in FINAL_STATES:
        raise ValueError(f"invalid final state: {state}")
    job.state = state
    job.finished_at = now()
    job.heartbeat_at = now()
    if error_info:
        job.error_info = error_info
    add_event(db, job, message or f"{job.type} {state}", level="error" if state == "failed" else "info")


def request_cancel(db, job: ExecutionJob) -> None:
    job.cancel_requested = True
    add_event(db, job, "cancel requested", level="warning")


def stale_after(job_type: str) -> timedelta:
    return timedelta(seconds=STALE_AFTER_SECONDS.get(job_type, DEFAULT_STALE_AFTER))


def is_stale(job: ExecutionJob, reference: datetime | None = None) -> bool:
    if job.state not in ACTIVE_STATES:
        return False
    moment = reference or datetime.now(UTC)
    beat = job.heartbeat_at or job.started_at or job.created_at
    if beat is None:
        return True
    if beat.tzinfo is None:
        beat = beat.replace(tzinfo=UTC)
    return moment - beat > stale_after(job.type)


def recover_stale(db, reference: datetime | None = None) -> int:
    """Fail active jobs whose heartbeat is older than their policy allows."""
    moment = reference or datetime.now(UTC)
    jobs = db.scalars(select(ExecutionJob).where(ExecutionJob.state.in_(ACTIVE_STATES))).all()
    recovered = 0
    for job in jobs:
        if is_stale(job, moment):
            finish_job(
                db,
                job,
                state="failed",
                error_info={
                    "code": "stale_heartbeat",
                    "summary": "The job stopped sending heartbeats and was marked failed.",
                    "remediation": "Retry the job; if it keeps stalling check the worker and GPU.",
                    "technical_details": f"last heartbeat: {job.heartbeat_at}",
                },
                message="recovered: stale heartbeat",
            )
            recovered += 1
    return recovered


RETENTION_DAYS = 30


def prune_finished_jobs(db, days: int = RETENTION_DAYS) -> int:
    """Delete finished jobs (and their events) older than the retention window."""
    cutoff = datetime.now(UTC) - timedelta(days=days)
    jobs = db.scalars(
        select(ExecutionJob).where(ExecutionJob.state.in_(FINAL_STATES), ExecutionJob.finished_at < cutoff)
    ).all()
    for job in jobs:
        db.execute(delete(JobEvent).where(JobEvent.job_id == job.id))
        db.delete(job)
    return len(jobs)


def queue_position(db, job: ExecutionJob) -> int | None:
    if job.state != "queued":
        return None
    ahead = db.scalar(
        select(func.count())
        .select_from(ExecutionJob)
        .where(ExecutionJob.state == "queued", ExecutionJob.type == job.type, ExecutionJob.created_at < job.created_at)
    )
    return (ahead or 0) + 1
