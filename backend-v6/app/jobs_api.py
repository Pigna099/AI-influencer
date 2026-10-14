"""Unified jobs API: one list for every long-running operation."""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select

from .auth import authorize
from .db import ExecutionJob, JobEvent, Session
from .jobs import ACTIVE_STATES, event_out, job_out, queue_position, recover_stale, request_cancel

router = APIRouter(prefix="/api/jobs", tags=["ExecutionJobs"], dependencies=[Depends(authorize)])


@router.get("")
def list_jobs(
    state: str | None = None,
    type: str | None = None,
    character_id: str | None = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    with Session() as db:
        query = select(ExecutionJob)
        if state == "active":
            query = query.where(ExecutionJob.state.in_(ACTIVE_STATES))
        elif state:
            query = query.where(ExecutionJob.state == state)
        if type:
            query = query.where(ExecutionJob.type == type)
        if character_id:
            query = query.where(ExecutionJob.character_id == character_id)
        jobs = db.scalars(query.order_by(ExecutionJob.created_at.desc()).limit(limit).offset(offset)).all()
        return [job_out(job, queue_position(db, job)) for job in jobs]


@router.get("/summary")
def jobs_summary():
    with Session() as db:
        recover_stale(db)
        active = db.scalars(select(ExecutionJob).where(ExecutionJob.state.in_(ACTIVE_STATES))).all()
        failed = db.scalars(select(ExecutionJob).where(ExecutionJob.state == "failed").order_by(ExecutionJob.created_at.desc()).limit(20)).all()
        db.commit()
        return {
            "active": [job_out(job, queue_position(db, job)) for job in active],
            "failed": [job_out(job) for job in failed],
            "active_count": len(active),
            "failed_count": len(failed),
        }


@router.get("/{job_id}")
def get_job(job_id: str):
    with Session() as db:
        job = db.get(ExecutionJob, job_id)
        if job is None:
            raise HTTPException(404, "ExecutionJob not found")
        return job_out(job, queue_position(db, job))


@router.get("/{job_id}/events")
def list_events(job_id: str, limit: int = Query(100, ge=1, le=500)):
    with Session() as db:
        job = db.get(ExecutionJob, job_id)
        if job is None:
            raise HTTPException(404, "ExecutionJob not found")
        events = db.scalars(
            select(JobEvent).where(JobEvent.job_id == job_id).order_by(JobEvent.created_at.desc()).limit(limit)
        ).all()
        return [event_out(event) for event in events]


@router.post("/{job_id}/cancel")
def cancel_job(job_id: str):
    with Session.begin() as db:
        job = db.get(ExecutionJob, job_id)
        if job is None:
            raise HTTPException(404, "ExecutionJob not found")
        if job.state not in ACTIVE_STATES:
            raise HTTPException(409, "ExecutionJob already finished")
        request_cancel(db, job)
        result = job_out(job)
    return result


@router.post("/{job_id}/retry", status_code=201)
def retry_job(job_id: str):
    from .jobs import create_job

    with Session.begin() as db:
        job = db.get(ExecutionJob, job_id)
        if job is None:
            raise HTTPException(404, "ExecutionJob not found")
        if job.state not in ("failed", "canceled"):
            raise HTTPException(409, "Only failed or canceled jobs can be retried")
        retry = create_job(
            db,
            type=job.type,
            character_id=job.character_id,
            dataset_id=job.dataset_id,
            asset_id=job.asset_id,
            retry_of=job.id,
            message=f"retry of {job.id}",
        )
        result = job_out(retry)
    return result
