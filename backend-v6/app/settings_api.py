"""App-wide defaults (chat/photo/video models) used by the Home page."""

import json
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import Field
from sqlalchemy import func, or_, select

from .auth import authorize
from .char_schemas import StrictModel
from .config import settings
from .db import AppSetting, CharacterLora, ImageLibrary, Influencer, Session, TrainingJob, VideoClip, now

router = APIRouter(prefix="/api", tags=["Settings"], dependencies=[Depends(authorize)])

DEFAULTS_KEY = "defaults"
DEFAULT_DEFAULTS = {"chat_model": "", "image_checkpoint": "", "video_model": "wan"}


@router.get("/overview")
def get_overview():
    """Operational counters for the Home page: what needs review or attention."""
    with Session() as db:
        def count(model, *criteria):
            return db.scalar(select(func.count()).select_from(model).where(*criteria)) or 0

        return {
            "characters": count(Influencer),
            "draft_images": count(ImageLibrary, ImageLibrary.status == "draft"),
            "draft_videos": count(VideoClip, VideoClip.review_status == "draft"),
            "jobs_running": count(TrainingJob, TrainingJob.status.in_(("queued", "running"))),
            "jobs_failed": count(TrainingJob, TrainingJob.status == "failed"),
            "loras_ready": count(CharacterLora, CharacterLora.status == "ready"),
            "characters_incomplete": count(
                Influencer, or_(Influencer.age.is_(None), Influencer.synthetic_declared.is_(False))
            ),
            "characters_undisclosed": _undisclosed_characters(db),
        }


def _undisclosed_characters(db) -> int:
    """Characters with a platform in use whose AI disclosure check is missing."""
    total = 0
    for policy in db.scalars(select(Influencer.platform_policy)):
        platforms = (policy or {}).get("platforms", {}) or {}
        if any(not (checks or {}).get("ai_disclosure") for checks in platforms.values()):
            total += 1
    return total


def read_defaults(db) -> dict:
    row = db.get(AppSetting, DEFAULTS_KEY)
    if row is None:
        return dict(DEFAULT_DEFAULTS)
    return {**DEFAULT_DEFAULTS, **(row.value or {})}


class DefaultsInput(StrictModel):
    chat_model: str | None = Field(default=None, max_length=200)
    image_checkpoint: str | None = Field(default=None, max_length=200)
    video_model: Literal["wan", "ltx-distilled", "ltx-dev", "hunyuan"] | None = None


@router.get("/settings/defaults")
def get_defaults():
    with Session() as db:
        defaults = read_defaults(db)
    vllm_available = False
    if settings.text_provider == "vllm":
        from .integrations.vllm import available

        vllm_available = available()
    return {**defaults, "text_provider": settings.text_provider, "vllm_available": vllm_available}


@router.put("/settings/defaults")
def set_defaults(body: DefaultsInput):
    with Session.begin() as db:
        row = db.get(AppSetting, DEFAULTS_KEY)
        if row is None:
            row = AppSetting(key=DEFAULTS_KEY, value={})
            db.add(row)
        value = {**DEFAULT_DEFAULTS, **(row.value or {})}
        for key, item in body.model_dump(exclude_none=True).items():
            value[key] = item
        row.value = value
        row.updated_at = now()
        db.flush()
        result = value
    return result


GPU_PLAN_KEY = "gpu_plan"
DEFAULT_GPU_PLAN = {"media": [0, 1], "text": [2, 3]}


class GpuPlanInput(StrictModel):
    media: list[int] = Field(min_length=1, max_length=4)
    text: list[int] = Field(default_factory=list, max_length=4)


def _validate_plan(media: list[int], text: list[int]) -> None:
    gpus = [*media, *text]
    if any(gpu < 0 or gpu > 3 for gpu in gpus):
        raise HTTPException(400, "Invalid GPU: use indexes 0-3")
    if len(set(gpus)) != len(gpus):
        raise HTTPException(400, "A GPU cannot be assigned to two uses")
    if len(text) not in (0, 2):
        raise HTTPException(400, "vLLM requires 0 or 2 GPUs (tensor parallel)")


def _data_dir():
    return settings.media_dir.parent


@router.get("/settings/gpu-plan")
def get_gpu_plan():
    with Session() as db:
        row = db.get(AppSetting, GPU_PLAN_KEY)
        plan = {**DEFAULT_GPU_PLAN, **(row.value or {})} if row is not None else dict(DEFAULT_GPU_PLAN)
    pending = (_data_dir() / "gpu_plan.request").exists()
    applied = {}
    applied_file = _data_dir() / "gpu_plan.applied.json"
    if applied_file.is_file():
        try:
            applied = json.loads(applied_file.read_text())
        except ValueError:
            applied = {}
    return {**plan, "pending": pending, "applied": applied}


@router.put("/settings/gpu-plan")
def set_gpu_plan(body: GpuPlanInput):
    _validate_plan(body.media, body.text)
    payload = {"media": sorted(set(body.media)), "text": sorted(set(body.text))}
    with Session.begin() as db:
        row = db.get(AppSetting, GPU_PLAN_KEY)
        if row is None:
            row = AppSetting(key=GPU_PLAN_KEY, value={})
            db.add(row)
        row.value = payload
        row.updated_at = now()
        db.flush()
    data_dir = _data_dir()
    (data_dir / "gpu_plan.json").write_text(json.dumps(payload))
    (data_dir / "gpu_plan.request").write_text(now().isoformat())
    return payload
