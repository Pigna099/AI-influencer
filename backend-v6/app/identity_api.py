"""Identity runs: multi-angle canonical identity set from the character anchor.

A run applies the versioned angle template to the identity anchor with the
strongest local identity-preserving edit model, storing every candidate with
its angle, seed, prompt and recipe so results stay traceable and reviewable.
"""

from __future__ import annotations

import hashlib
import logging
import random
from concurrent.futures import ThreadPoolExecutor

from fastapi import APIRouter, Depends, HTTPException
from pydantic import Field
from sqlalchemy import select

from .audit import record as audit_record
from .auth import authorize
from .char_schemas import StrictModel
from .config import settings
from .consistency_api import resize_jpeg
from .db import (
    ExecutionJob,
    IdentityCandidate,
    IdentityRun,
    ImageLibrary,
    Influencer,
    Session,
    identifier,
    now,
)
from .image_library import average_hash
from .integrations.comfyui import ComfyUIError, pick_target, qwen_image_edit
from .integrations.ollama import OllamaNotAvailable
from .integrations.text import vision_json
from .jobs import create_job, finish_job, start_job, update_progress

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["Identity"], dependencies=[Depends(authorize)])

IDENTITY_TEMPLATE_VERSION = "1"

# (angle key, prompt fragment). Hair, age, skin and identity stay fixed; only
# angle/expression/light vary. "role" groups candidates for the balance check.
ANGLES: list[tuple[str, str, str]] = [
    ("front_neutral", "front view, looking straight at the camera, neutral expression, studio light", "front"),
    ("front_smile", "front view, looking at the camera, slight smile, studio light", "front"),
    ("close_up_front", "close-up of the face, front view, neutral expression, studio light", "close_front"),
    ("yaw_left_20", "head turned about 20 degrees to her left, neutral expression, studio light", "yaw"),
    ("yaw_right_20", "head turned about 20 degrees to her right, neutral expression, studio light", "yaw"),
    ("yaw_left_40", "head turned about 40 degrees to her left, neutral expression", "yaw"),
    ("yaw_right_40", "head turned about 40 degrees to her right, neutral expression", "yaw"),
    ("yaw_left_60", "head turned about 60 degrees to her left, neutral expression", "yaw"),
    ("yaw_right_60", "head turned about 60 degrees to her right, neutral expression", "yaw"),
    ("profile_left", "full left profile view, 90 degrees, neutral expression", "profile_left"),
    ("profile_right", "full right profile view, 90 degrees, neutral expression", "profile_right"),
    ("three_quarter_left", "three-quarter view from her left, slight smile, studio light", "three_quarter_left"),
    ("three_quarter_right", "three-quarter view from her right, slight smile, studio light", "three_quarter_right"),
    ("pitch_up", "head slightly tilted up, looking at the camera", "pitch"),
    ("pitch_down", "head slightly tilted down, looking at the camera", "pitch"),
    ("upper_body_front", "upper body portrait, front view, natural window light", "upper_body"),
    ("full_body_front", "full body, standing, front view, natural light", "full_body"),
    ("full_body_side", "full body, standing, side view, natural light", "full_body"),
]
ANGLE_INDEX = {key: (fragment, role) for key, fragment, role in ANGLES}

REQUIRED_ROLES = ("close_front", "three_quarter_left", "three_quarter_right", "profile_left", "profile_right", "upper_body", "full_body")
CANONICAL_MIN = 6
CANONICAL_MAX = 10

SCORE_PROMPT = (
    "You are checking identity consistency for a fictional adult (25+) character. "
    "Image 1 is the anchor. Image 2 is a generated candidate that should show the SAME person "
    "at a requested angle. Score similarity (how much the face is the same person, 0-100), "
    "same_person (boolean), angle_accuracy (how well the candidate matches a neutral portrait "
    "angle, 0-100), and quality_notes (short text: blur, occlusion, artifacts; empty if fine)."
)
SCORE_SCHEMA = {
    "type": "object",
    "properties": {
        "similarity": {"type": "integer"},
        "same_person": {"type": "boolean"},
        "angle_accuracy": {"type": "integer"},
        "quality_notes": {"type": "string"},
    },
    "required": ["similarity", "same_person", "angle_accuracy", "quality_notes"],
    "additionalProperties": False,
}


class IdentityRunInput(StrictModel):
    angles: list[str] = Field(default_factory=list, max_length=24)
    per_angle: int = Field(default=1, ge=1, le=4)
    seed: int | None = Field(default=None, ge=0, le=2**31 - 1)
    steps: int = Field(default=4, ge=1, le=60)
    cfg: float = Field(default=1.0, ge=0, le=20)
    lora_weight: float = Field(default=1.0, ge=0, le=2)
    model: str | None = Field(default=None, max_length=200)


class CandidatePatch(StrictModel):
    status: str = Field(pattern="^(draft|accepted|rejected|uncertain)$")


class FreezeInput(StrictModel):
    override_reason: str = Field(default="", max_length=2000)


def run_out(run: IdentityRun, candidates: list[dict] | None = None) -> dict:
    return {
        "id": run.id,
        "character_id": run.character_id,
        "status": run.status,
        "template_version": run.template_version,
        "anchor_filename": run.anchor_filename,
        "anchor_sha256": run.anchor_sha256,
        "model": run.model,
        "params": run.params or {},
        "override_reason": run.override_reason,
        "frozen_at": run.frozen_at.isoformat() if run.frozen_at else None,
        "created_at": run.created_at.isoformat(),
        "finished_at": run.finished_at.isoformat() if run.finished_at else None,
        "candidates": candidates or [],
    }


def candidate_out(candidate: IdentityCandidate, library: ImageLibrary | None) -> dict:
    return {
        "id": candidate.id,
        "run_id": candidate.run_id,
        "image_id": candidate.image_id,
        "angle": candidate.angle,
        "seed": candidate.seed,
        "prompt": candidate.prompt,
        "status": candidate.status,
        "scores": candidate.scores or {},
        "filename": library.filename if library is not None else None,
        "created_at": candidate.created_at.isoformat(),
    }


def score_candidates(anchor_bytes: bytes, entries: list[dict], candidate_data: dict[str, bytes]) -> int:
    """Score candidates against the anchor with the local vision model; returns the scored count."""
    scored = 0
    anchor_b64 = resize_jpeg(anchor_bytes)
    for entry in entries:
        data = candidate_data.get(entry["id"])
        if not data:
            continue
        try:
            verdict = vision_json(
                settings.consistency_model,
                SCORE_PROMPT,
                [anchor_b64, resize_jpeg(data)],
                schema=SCORE_SCHEMA,
                max_tokens=160,
            )
        except (OllamaNotAvailable, OSError, ValueError) as error:
            logger.info("identity scoring failed for %s: %s", entry["id"], error)
            continue
        scores = {
            "similarity": max(0, min(100, int(verdict.get("similarity", 0) or 0))),
            "same_person": bool(verdict.get("same_person")),
            "angle_accuracy": max(0, min(100, int(verdict.get("angle_accuracy", 0) or 0))),
            "quality_notes": str(verdict.get("quality_notes") or "")[:200],
        }
        entry["scores"] = scores
        with Session.begin() as db:
            stored = db.get(IdentityCandidate, entry["id"])
            if stored is not None:
                stored.scores = scores
        scored += 1
    return scored


@router.get("/identity-template")
def get_identity_template():
    return {
        "version": IDENTITY_TEMPLATE_VERSION,
        "angles": [{"key": key, "prompt": fragment, "role": role} for key, fragment, role in ANGLES],
        "canonical_min": CANONICAL_MIN,
        "canonical_max": CANONICAL_MAX,
        "required_roles": list(REQUIRED_ROLES),
    }


@router.post("/characters/{character_id}/identity-runs", status_code=201)
def create_identity_run(character_id: str, body: IdentityRunInput):
    with Session() as db:
        character = db.get(Influencer, character_id)
        if character is None:
            raise HTTPException(404, "Item not found")
        if character.source_category == "reference_only":
            raise HTTPException(
                400, "Reference-only material cannot be used as an identity anchor: change the source category first"
            )
        if not character.avatar_filename:
            raise HTTPException(400, "Generate the profile picture first: it is the identity anchor")
        anchor_path = (settings.media_dir / character.avatar_filename).resolve()
        if not anchor_path.is_file():
            raise HTTPException(404, "Profile picture unavailable")
        anchor_bytes = anchor_path.read_bytes()
        anchor_sha = hashlib.sha256(anchor_bytes).hexdigest()
        anchor_filename = character.avatar_filename
        identity_core = (character.avatar_prompt or "").strip()
        if not identity_core:
            profile = character.bible.get("profile", {}) if isinstance(character.bible, dict) else {}
            identity_core = str(profile.get("appearance") or profile.get("description") or "").strip()
        model = body.model or settings.qwen_edit_unet_name

    selected = body.angles or [key for key, _fragment, _role in ANGLES]
    unknown = [key for key in selected if key not in ANGLE_INDEX]
    if unknown:
        raise HTTPException(400, f"Unknown angle(s): {', '.join(sorted(unknown))}")

    with Session.begin() as db:
        job = create_job(
            db,
            type="identity_run",
            character_id=character_id,
            message=f"identity set ({len(selected)} angles x {body.per_angle})",
        )
        start_job(db, job, worker="comfyui-edit")
        job_id = job.id
        run = IdentityRun(
            character_id=character_id,
            template_version=IDENTITY_TEMPLATE_VERSION,
            anchor_filename=anchor_filename,
            anchor_sha256=anchor_sha,
            model=model,
            params=body.model_dump(),
        )
        db.add(run)
        db.flush()
        run_id = run.id

    base_seed = body.seed if body.seed is not None else random.randrange(2**31)
    jobs: list[tuple[str, str, int]] = []
    for angle_key in selected:
        fragment, _role = ANGLE_INDEX[angle_key]
        for index in range(body.per_angle):
            jobs.append((angle_key, fragment, base_seed + len(jobs)))

    def render(job: tuple[str, str, int]):
        angle_key, fragment, seed = job
        prompt = ", ".join(part for part in [identity_core, fragment, "same person, keep hair, age, skin and identity fixed"] if part)
        data, meta = qwen_image_edit(
            anchor_path,
            prompt,
            seed=seed,
            steps=body.steps,
            cfg=body.cfg,
            lora_weight=body.lora_weight,
            unet_name=body.model,
            base_url=pick_target(),
        )
        return angle_key, seed, prompt, data, meta

    rendered = []
    errors: list[Exception] = []
    with ThreadPoolExecutor(max_workers=len(jobs)) as pool:
        futures = [pool.submit(render, job) for job in jobs]
        for future in futures:
            try:
                rendered.append(future.result())
            except ComfyUIError as error:
                errors.append(error)

    created: list[dict] = []
    candidate_data: dict[str, bytes] = {}
    for angle_key, seed, prompt, data, meta in rendered:
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
                prompt=prompt,
                negative_prompt="",
                caption="",
                tags=["identity", angle_key],
                checkpoint=meta.get("model") or model,
                loras=[],
                seed=meta.get("seed", seed),
                style="real",
                status="draft",
                rating=0,
                source="identity",
                used_count=0,
                embedding=[],
                embedding_model="",
            )
            db.add(library)
            db.flush()
            candidate = IdentityCandidate(
                run_id=run_id,
                image_id=library.id,
                angle=angle_key,
                seed=meta.get("seed", seed),
                prompt=prompt,
            )
            db.add(candidate)
            db.flush()
            candidate_data[candidate.id] = data
            created.append(candidate_out(candidate, library))

    scored = score_candidates(anchor_bytes, created, candidate_data)

    with Session.begin() as db:
        run = db.get(IdentityRun, run_id)
        run.finished_at = now()
        run.status = "finished" if created else "failed"
        exec_job = db.get(ExecutionJob, job_id)
        if exec_job is not None and exec_job.state == "running":
            update_progress(db, exec_job, current=len(created), total=len(jobs), unit="image")
            finish_job(
                db,
                exec_job,
                state="succeeded" if created else "failed",
                error_info=None
                if created
                else {
                    "code": "identity_run_failed",
                    "summary": "No identity candidate could be generated.",
                    "remediation": "Check Qwen-Image-Edit and the anchor image, then retry.",
                    "technical_details": str(errors[0])[:800] if errors else "",
                },
                message=f"{len(created)} candidates ready, {scored} scored",
            )
        result = run_out(run, created)
    if not created:
        raise HTTPException(502, "Identity generation failed: no candidate produced")
    return result


@router.get("/characters/{character_id}/identity-runs")
def list_identity_runs(character_id: str, limit: int = 20):
    with Session() as db:
        runs = db.scalars(
            select(IdentityRun)
            .where(IdentityRun.character_id == character_id)
            .order_by(IdentityRun.created_at.desc())
            .limit(max(1, min(limit, 100)))
        ).all()
        return [run_out(run) for run in runs]


@router.get("/identity-runs/{run_id}")
def get_identity_run(run_id: str):
    with Session() as db:
        run = db.get(IdentityRun, run_id)
        if run is None:
            raise HTTPException(404, "Identity run not found")
        rows = list(
            db.execute(
                select(IdentityCandidate, ImageLibrary)
                .outerjoin(ImageLibrary, IdentityCandidate.image_id == ImageLibrary.id)
                .where(IdentityCandidate.run_id == run_id)
                .order_by(IdentityCandidate.created_at)
            )
        )
        return run_out(run, [candidate_out(candidate, library) for candidate, library in rows])


@router.patch("/identity-candidates/{candidate_id}")
def patch_candidate(candidate_id: str, body: CandidatePatch):
    with Session.begin() as db:
        candidate = db.get(IdentityCandidate, candidate_id)
        if candidate is None:
            raise HTTPException(404, "Candidate not found")
        run = db.get(IdentityRun, candidate.run_id)
        if run is not None and run.status == "frozen":
            raise HTTPException(409, "The canonical set is frozen: create a new run to change it")
        candidate.status = body.status
        library = db.get(ImageLibrary, candidate.image_id) if candidate.image_id else None
        if library is not None:
            library.status = {"accepted": "approved", "rejected": "rejected"}.get(body.status, "draft")
        result = candidate_out(candidate, library)
    return result


class RegenerateInput(StrictModel):
    candidate_ids: list[str] = Field(default_factory=list, max_length=64)


@router.post("/identity-runs/{run_id}/regenerate", status_code=201)
def regenerate_candidates(run_id: str, body: RegenerateInput):
    """Regenerate rejected/uncertain candidates (or the given ids) with fresh seeds."""
    with Session() as db:
        run = db.get(IdentityRun, run_id)
        if run is None:
            raise HTTPException(404, "Identity run not found")
        if run.status == "frozen":
            raise HTTPException(409, "The canonical set is frozen: create a new run to change it")
        if not run.anchor_filename:
            raise HTTPException(400, "The run has no anchor")
        anchor_path = (settings.media_dir / run.anchor_filename).resolve()
        if not anchor_path.is_file():
            raise HTTPException(404, "Anchor image unavailable")
        anchor_bytes = anchor_path.read_bytes()
        rows = list(
            db.execute(
                select(IdentityCandidate, ImageLibrary)
                .outerjoin(ImageLibrary, IdentityCandidate.image_id == ImageLibrary.id)
                .where(IdentityCandidate.run_id == run_id)
            )
        )
        if body.candidate_ids:
            wanted = set(body.candidate_ids)
            targets = [(candidate, library) for candidate, library in rows if candidate.id in wanted]
            if len(targets) != len(wanted):
                raise HTTPException(404, "One or more candidates were not found")
        else:
            targets = [
                (candidate, library) for candidate, library in rows if candidate.status in ("rejected", "uncertain")
            ]
        if not targets:
            raise HTTPException(400, "Nothing to regenerate: reject or mark candidates uncertain first")
        if any(candidate.status == "accepted" for candidate, _library in targets):
            raise HTTPException(409, "Accepted candidates cannot be regenerated")
        character_id = run.character_id
        model = run.model
        params = run.params or {}

    with Session.begin() as db:
        job = create_job(
            db,
            type="identity_run",
            character_id=character_id,
            message=f"regenerate {len(targets)} identity candidates",
        )
        start_job(db, job, worker="comfyui-edit")
        job_id = job.id

    created: list[dict] = []
    candidate_data: dict[str, bytes] = {}
    for candidate, _library in targets:
        new_seed = (candidate.seed + 1000003) % (2**31)
        try:
            data, meta = qwen_image_edit(
                anchor_path,
                candidate.prompt,
                seed=new_seed,
                steps=int(params.get("steps", 4)),
                cfg=float(params.get("cfg", 1.0)),
                lora_weight=float(params.get("lora_weight", 1.0)),
                unet_name=params.get("model") or None,
                base_url=pick_target(),
            )
        except ComfyUIError as error:
            logger.info("identity regenerate failed for %s: %s", candidate.id, error)
            continue
        settings.media_dir.mkdir(parents=True, exist_ok=True)
        filename = f"{identifier()}.png"
        (settings.media_dir / filename).write_bytes(data)
        with Session.begin() as db:
            stored = db.get(IdentityCandidate, candidate.id)
            if stored is not None:
                stored.status = "replaced"
            library = ImageLibrary(
                character_id=character_id,
                filename=filename,
                sha256=hashlib.sha256(data).hexdigest(),
                phash=average_hash(data),
                prompt=candidate.prompt,
                negative_prompt="",
                caption="",
                tags=["identity", candidate.angle],
                checkpoint=meta.get("model") or model,
                loras=[],
                seed=meta.get("seed", new_seed),
                style="real",
                status="draft",
                rating=0,
                source="identity",
                used_count=0,
                embedding=[],
                embedding_model="",
            )
            db.add(library)
            db.flush()
            replacement = IdentityCandidate(
                run_id=run_id,
                image_id=library.id,
                angle=candidate.angle,
                seed=meta.get("seed", new_seed),
                prompt=candidate.prompt,
            )
            db.add(replacement)
            db.flush()
            candidate_data[replacement.id] = data
            created.append(candidate_out(replacement, library))

    scored = score_candidates(anchor_bytes, created, candidate_data)
    with Session.begin() as db:
        exec_job = db.get(ExecutionJob, job_id)
        if exec_job is not None and exec_job.state == "running":
            update_progress(db, exec_job, current=len(created), total=len(targets), unit="image")
            finish_job(
                db,
                exec_job,
                state="succeeded" if created else "failed",
                message=f"{len(created)} replacements ready, {scored} scored",
            )
        run = db.get(IdentityRun, run_id)
        result = run_out(run, created)
    if not created:
        raise HTTPException(502, "Regeneration produced no candidate")
    return result


@router.post("/identity-runs/{run_id}/freeze")
def freeze_run(run_id: str, body: FreezeInput):
    with Session.begin() as db:
        run = db.get(IdentityRun, run_id)
        if run is None:
            raise HTTPException(404, "Identity run not found")
        if run.status == "frozen":
            raise HTTPException(409, "The canonical set is already frozen")
        rows = list(
            db.execute(
                select(IdentityCandidate, ImageLibrary)
                .outerjoin(ImageLibrary, IdentityCandidate.image_id == ImageLibrary.id)
                .where(IdentityCandidate.run_id == run_id)
            )
        )
        accepted = [candidate for candidate, _library in rows if candidate.status == "accepted"]
        roles = {ANGLE_INDEX[candidate.angle][1] for candidate in accepted if candidate.angle in ANGLE_INDEX}
        missing = [role for role in REQUIRED_ROLES if role not in roles]
        problems = []
        if not (CANONICAL_MIN <= len(accepted) <= CANONICAL_MAX):
            problems.append(f"accepted count must be between {CANONICAL_MIN} and {CANONICAL_MAX} (now {len(accepted)})")
        if missing:
            problems.append(f"missing roles: {', '.join(missing)}")
        if problems and not body.override_reason.strip():
            raise HTTPException(409, "Unbalanced canonical set: " + "; ".join(problems) + ". Provide an override reason.")
        run.status = "frozen"
        run.frozen_at = now()
        run.override_reason = body.override_reason.strip()
        audit_record(
            db,
            "identity.freeze",
            "identity_run",
            run.id,
            accepted=len(accepted),
            override=body.override_reason.strip() or None,
        )
        result = run_out(run)
    return result
