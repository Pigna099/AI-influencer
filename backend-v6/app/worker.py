"""Durable database queue; conditional updates prevent double claiming."""

import hashlib
import logging
import time
from datetime import timedelta

from sqlalchemy import select, update

from .config import settings
from .db import Asset, Job, Session, identifier, now
from .integrations.comfyui import generate_images
from .integrations.ollama import generate_brief

logger = logging.getLogger(__name__)


def claim_job():
    with Session.begin() as db:
        db.execute(
            update(Job)
            .where(
                Job.status == "running",
                Job.started_at < (now() - timedelta(seconds=settings.worker_lease_seconds)),
            )
            .values(
                status="failed",
                error="Worker interrupted or lease expired. Check remote generation before retry.",
                finished_at=now(),
            )
        )
        candidate = db.scalar(select(Job.id).where(Job.status == "queued").order_by(Job.created_at).limit(1))
        if candidate is None:
            return None
        changed = db.execute(
            update(Job)
            .where(Job.id == candidate, Job.status == "queued")
            .values(status="running", started_at=now())
        )
        return candidate if changed.rowcount == 1 else None


def process_job(job_id):
    paths = []
    try:
        with Session() as db:
            job = db.get(Job, job_id)
            if not job or job.status != "running":
                return
            request, character = job.request, job.character_snapshot
        brief = generate_brief(character, request)
        images, generation = generate_images(brief, request)
        settings.media_dir.mkdir(parents=True, exist_ok=True)
        assets = []
        for data in images:
            filename = f"{identifier()}.png"
            path = settings.media_dir / filename
            paths.append(path)
            path.write_bytes(data)
            assets.append(
                Asset(
                    job_id=job_id,
                    filename=filename,
                    media_type="image/png",
                    sha256=hashlib.sha256(data).hexdigest(),
                )
            )
        with Session.begin() as db:
            changed = db.execute(
                update(Job)
                .where(Job.id == job_id, Job.status == "running")
                .values(
                    status="awaiting_review",
                    result={
                        "brief": brief.model_dump(),
                        "generation": generation,
                        "text_provider": settings.text_provider,
                        "ollama_model": settings.ollama_model if settings.text_provider == "ollama" else None,
                    },
                    finished_at=now(),
                )
            )
            if changed.rowcount != 1:
                raise RuntimeError("Job lease expired before completion")
            db.add_all(assets)
    except Exception as error:
        for path in paths:
            path.unlink(missing_ok=True)
        logger.exception("Job %s failed", job_id)
        with Session.begin() as db:
            db.execute(
                update(Job)
                .where(Job.id == job_id, Job.status == "running")
                .values(
                    status="failed",
                    error=f"{type(error).__name__}: generation failed; inspect worker logs.",
                    finished_at=now(),
                )
            )


def main():
    logging.basicConfig(level=logging.INFO)
    if settings.worker_lease_seconds <= settings.generation_timeout + 240:
        raise ValueError("Worker lease must exceed generation timeout by more than 240 seconds")
    while True:
        try:
            job_id = claim_job()
            if job_id:
                process_job(job_id)
            else:
                time.sleep(2)
        except Exception:
            logger.exception("Worker queue error")
            time.sleep(5)


if __name__ == "__main__":
    main()
