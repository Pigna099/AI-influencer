import secrets
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.security import APIKeyHeader
from fastapi.staticfiles import StaticFiles
from sqlalchemy import select, text, update

from .config import settings
from .db import Asset, BibleVersion, Influencer, Job, Review, Session
from .schemas import Bible, InfluencerInput, JobInput, ReviewInput

key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def authorize(key: str | None = Depends(key_header)):
    if not settings.api_key:
        raise HTTPException(503, "Configure API_KEY in .env before using the API")
    if key is None or not secrets.compare_digest(key, settings.api_key):
        raise HTTPException(401, "Invalid API key")


app = FastAPI(title="AI Influencer Backend", version="0.1.0", )

WEBUI_DIR = Path(__file__).parent.parent / "webui"

app.mount("/static", StaticFiles(directory=WEBUI_DIR), name="webui")


@app.get("/", response_class=HTMLResponse, include_in_schema=False, dependencies=[])
def root():
    return FileResponse(WEBUI_DIR / "index.html")


def required(db, model, item_id):
    item = db.get(model, item_id)
    if item is None:
        raise HTTPException(404, "Not found")
    return item


@app.get("/ping", tags=["System"])
def ping():
    return {"status": "ok"}


@app.get("/health", tags=["System"])
def health():
    with Session() as db:
        db.execute(text("SELECT 1"))
    return {
        "status": "ok",
        "text_provider": settings.text_provider,
        "image_provider": settings.image_provider,
        "fanvue_enabled": False,
    }


@app.post("/influencers", status_code=201, tags=["Influencers"])
def create_influencer(body: InfluencerInput):
    with Session.begin() as db:
        item = Influencer(name=body.name, bible=body.bible.model_dump())
        db.add(item)
        db.flush()
        db.add(BibleVersion(influencer_id=item.id, version=1, bible=item.bible))
    return item


@app.get("/influencers", tags=["Influencers"])
def list_influencers(limit: int = Query(50, ge=1, le=100), offset: int = Query(0, ge=0)):
    with Session() as db:
        return list(
            db.scalars(select(Influencer).order_by(Influencer.created_at).limit(limit).offset(offset))
        )


@app.get("/influencers/{influencer_id}", tags=["Influencers"])
def get_influencer(influencer_id: str):
    with Session() as db:
        return required(db, Influencer, influencer_id)


@app.put("/influencers/{influencer_id}/bible", tags=["Influencers"])
def update_bible(influencer_id: str, body: Bible):
    with Session.begin() as db:
        item = required(db, Influencer, influencer_id)
        old_version = item.version
        updated = db.execute(
            update(Influencer)
            .where(Influencer.id == influencer_id, Influencer.version == old_version)
            .values(bible=body.model_dump(), version=old_version + 1)
        )
        if updated.rowcount != 1:
            raise HTTPException(409, "Character was modified concurrently; reload and retry")
        db.add(BibleVersion(influencer_id=influencer_id, version=old_version + 1, bible=body.model_dump()))
        db.flush()
        db.refresh(item)
    return item


@app.get("/influencers/{influencer_id}/versions", tags=["Influencers"])
def versions(influencer_id: str):
    with Session() as db:
        required(db, Influencer, influencer_id)
        return list(
            db.scalars(
                select(BibleVersion)
                .where(BibleVersion.influencer_id == influencer_id)
                .order_by(BibleVersion.version)
            )
        )


def new_job(db, body):
    influencer = required(db, Influencer, body.influencer_id)
    job = Job(
        influencer_id=influencer.id,
        request=body.model_dump(),
        character_snapshot={
            "name": influencer.name,
            "version": influencer.version,
            "bible": influencer.bible,
        },
    )
    db.add(job)
    db.flush()
    return job


@app.post("/content-jobs", status_code=202, tags=["Content"])
def create_job(body: JobInput):
    with Session.begin() as db:
        job = new_job(db, body)
    return job


@app.get("/content-jobs", tags=["Content"])
def list_jobs(status: str | None = None, limit: int = Query(50, ge=1, le=100), offset: int = Query(0, ge=0)):
    with Session() as db:
        query = select(Job).order_by(Job.created_at.desc())
        if status:
            query = query.where(Job.status == status)
        return list(db.scalars(query.limit(limit).offset(offset)))


@app.get("/content-jobs/{job_id}", tags=["Content"])
def get_job(job_id: str):
    with Session() as db:
        job = required(db, Job, job_id)
        return {
            "job": job,
            "assets": list(db.scalars(select(Asset).where(Asset.job_id == job_id))),
            "reviews": list(db.scalars(select(Review).where(Review.job_id == job_id))),
        }


@app.post("/content-jobs/{job_id}/review", tags=["Review"])
def review_job(job_id: str, body: ReviewInput):
    with Session.begin() as db:
        required(db, Job, job_id)
        changed = db.execute(
            update(Job).where(Job.id == job_id, Job.status == "awaiting_review").values(status=body.decision)
        )
        if changed.rowcount != 1:
            raise HTTPException(409, "Only content awaiting review can be approved or rejected")
        db.add(Review(job_id=job_id, decision=body.decision, note=body.note))
    return {"id": job_id, "status": body.decision}


@app.post("/content-jobs/{job_id}/regenerate", status_code=202, tags=["Review"])
def regenerate(job_id: str):
    with Session.begin() as db:
        old = required(db, Job, job_id)
        if old.status in ("queued", "running"):
            raise HTTPException(409, "Wait for current generation to finish")
        request = {**old.request, "seed": (old.request["seed"] + 1) % (2**32 - 4)}
        # Reuse the exact character snapshot; original job and review remain unchanged.
        job = Job(influencer_id=old.influencer_id, request=request, character_snapshot=old.character_snapshot)
        db.add(job)
        db.flush()
    return job


@app.get("/assets/{asset_id}/file", tags=["Media"])
def download_asset(asset_id: str):
    with Session() as db:
        asset = required(db, Asset, asset_id)
        path = (settings.media_dir / asset.filename).resolve()
        if not path.is_relative_to(settings.media_dir.resolve()) or not path.is_file():
            raise HTTPException(404, "Media file unavailable")
        return FileResponse(path, media_type=asset.media_type, filename=asset.filename)
