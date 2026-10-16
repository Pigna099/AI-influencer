"""Playground API. Legacy content routes remain in main.py."""

import hashlib
import json
import logging
import random
import re
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from pathlib import Path
from statistics import mean, median

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from fastapi.responses import FileResponse, Response
from pydantic import ValidationError
from sqlalchemy import delete, func, or_, select, update

from .audit import record as audit_record
from .auth import authorize
from .char_schemas import (
    AvatarEditInput,
    AvatarInput,
    AvatarPromptInput,
    AvatarUploadInput,
    BenchmarkInput,
    BulkIdsInput,
    BulkStatusInput,
    CharacterClone,
    CharacterInput,
    CharacterOutput,
    CharacterProfile,
    CharacterUpdate,
    ChatMessageInput,
    ChatVideoInput,
    CollectionInput,
    CollectionItemsInput,
    ConversationInput,
    ConversationPatch,
    EnhanceInput,
    FanInput,
    ImageCheckpointInput,
    ImageStyleInput,
    InitiateInput,
    LibraryGenerateInput,
    LibraryPatch,
    MemoryInput,
    PhotoInput,
    PpvInput,
    PromptAugmentInput,
    RealismInput,
)
from .chat_service import (
    FAN_MESSAGE_REMINDER,
    REFUSAL_PATTERN,
    build_avatar_prompt,
    build_context,
    build_identity_prompt,
    build_negative_prompt,
    build_prompt_from_profile,
    build_scene_prompt,
    checkpoint_family,
    extract_memories,
    fan_message,
    generate_reply,
    human_bursts,
    measured_chat,
    translate_scene,
)
from .config import settings
from .db import (
    Asset,
    BenchmarkSample,
    BibleVersion,
    CharacterLora,
    ChatImage,
    ChatMessage,
    ChatVideo,
    Conversation,
    ExecutionJob,
    Fan,
    ImageLibrary,
    Influencer,
    Job,
    LibraryCollection,
    LibraryCollectionItem,
    LoraDataset,
    LoraDatasetItem,
    Memory,
    PoseReference,
    Review,
    ScheduledReply,
    Session,
    SimulatedPayment,
    TrainingJob,
    VideoClip,
    content_hash,
    identifier,
    now,
)
from .image_library import (
    average_hash,
    blurred_png,
    classify_image,
    classify_library_item,
    embed_library_text,
    library_out,
    library_text,
    match_library_image,
)
from .integrations.comfyui import (
    ComfyUIError,
    comfyui_available,
    generate_image,
    get_checkpoints,
    get_loras,
    interrupt,
    lora_family,
    pick_target,
    qwen_image_edit,
)
from .integrations.gpu import gpu_status
from .integrations.text import OllamaNotAvailable, chat, get_models, validate_model
from .jobs import create_job, finish_job, start_job, update_progress
from .scheduler import maybe_schedule_proactive, pending_for_conversation, schedule_reply

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["Playground"], dependencies=[Depends(authorize)])


def required(db, model, item_id):
    item = db.get(model, item_id)
    if item is None:
        raise HTTPException(404, "Item not found")
    return item


def normalize_bible_profile(bible: dict) -> dict:
    if "profile" in bible:
        return bible["profile"]
    return {key: bible[key] for key in CharacterProfile.model_fields if key in bible}


def character_out(item):
    return CharacterOutput(
        id=item.id,
        name=item.name,
        profile=CharacterProfile(**normalize_bible_profile(item.bible)),
        version=item.version,
        avatar_filename=item.avatar_filename,
        avatar_prompt=item.avatar_prompt,
        image_checkpoint=item.image_checkpoint,
        image_style=item.image_style,
        ppv_enabled=item.ppv_enabled,
        ppv_price_cents=item.ppv_price_cents,
        reply_delay_min_seconds=item.reply_delay_min_seconds,
        reply_delay_max_seconds=item.reply_delay_max_seconds,
        activity_enabled=item.activity_enabled,
        activity_start_hour=item.activity_start_hour,
        activity_end_hour=item.activity_end_hour,
        activity_days=sorted(item.activity_days or []),
        age=item.age,
        synthetic_declared=item.synthetic_declared,
        provenance=item.provenance,
        source_category=item.source_category,
        rights_notes=item.rights_notes,
        source_reference=item.source_reference,
        source_hash=item.source_hash,
        permitted_uses=item.permitted_uses,
        lifecycle_state=item.lifecycle_state,
        platform_policy=item.platform_policy or {},
        avatar_sha256=item.avatar_sha256,
        avatar_validation=item.avatar_validation or {},
        created_at=item.created_at.isoformat(),
    )


def image_out(item):
    return {
        "id": item.id,
        "message_id": item.message_id,
        "conversation_id": item.conversation_id,
        "prompt": item.prompt,
        "seed": item.seed,
        "nsfw": item.nsfw,
        "price_cents": item.price_cents,
        "unlocked": item.unlocked_at is not None,
        "unlocked_at": item.unlocked_at.isoformat() if item.unlocked_at else None,
        "created_at": item.created_at.isoformat(),
    }


def chat_video_out(item, clip):
    return {
        "id": item.id,
        "message_id": item.message_id,
        "conversation_id": item.conversation_id,
        "video_id": item.video_id,
        "filename": clip.filename if clip else "",
        "thumb_filename": clip.thumb_filename if clip else None,
        "prompt": item.prompt,
        "price_cents": item.price_cents,
        "unlocked": item.unlocked_at is not None,
        "unlocked_at": item.unlocked_at.isoformat() if item.unlocked_at else None,
        "created_at": item.created_at.isoformat(),
    }


def messages_out(db, rows):
    images = defaultdict(list)
    videos = defaultdict(list)
    if rows:
        ids = [row.id for row in rows]
        for item in db.scalars(select(ChatImage).where(ChatImage.message_id.in_(ids))):
            images[item.message_id].append(image_out(item))
        for item, clip in db.execute(
            select(ChatVideo, VideoClip)
            .join(VideoClip, VideoClip.id == ChatVideo.video_id, isouter=True)
            .where(ChatVideo.message_id.in_(ids))
        ).all():
            videos[item.message_id].append(chat_video_out(item, clip))
    return [
        {
            "id": row.id,
            "conversation_id": row.conversation_id,
            "role": row.role,
            "content": row.content,
            "model": row.model,
            "ollama_metrics": row.ollama_metrics,
            "created_at": row.created_at.isoformat(),
            "images": images.get(row.id, []),
            "videos": videos.get(row.id, []),
        }
        for row in rows
    ]


def effective_ppv(conversation, character) -> tuple[bool, int]:
    """Per-conversation PPV override falling back to the character default."""
    enabled = conversation.ppv_enabled if conversation.ppv_enabled is not None else bool(character.ppv_enabled)
    price = conversation.ppv_price_cents if conversation.ppv_price_cents is not None else (character.ppv_price_cents or 0)
    return bool(enabled), int(price or 0)


def conversation_out(db, item):
    unread_query = (
        select(func.count())
        .select_from(ChatMessage)
        .where(ChatMessage.conversation_id == item.id, ChatMessage.role == "assistant")
    )
    if item.last_read_at is not None:
        unread_query = unread_query.where(ChatMessage.created_at > item.last_read_at)
    unread = int(db.scalar(unread_query) or 0)
    pending, pending_at = pending_for_conversation(db, item.id)
    return {
        **{column.name: getattr(item, column.name) for column in Conversation.__table__.columns},
        "unread": unread,
        "pending_replies": pending,
        "pending_reply_at": pending_at.isoformat() if pending_at else None,
        "last_read_at": item.last_read_at.isoformat() if item.last_read_at else None,
    }


def profile_fingerprint(profile: dict) -> str:
    canonical = json.dumps(profile, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]


def ensure_model(model):
    try:
        if not validate_model(model):
            raise HTTPException(400, "Select an installed chat-capable model")
    except OllamaNotAvailable as error:
        raise HTTPException(503, str(error)) from error


@router.get("/ollama/models")
def list_ollama_models():
    try:
        return {"models": get_models()}
    except OllamaNotAvailable as error:
        raise HTTPException(503, str(error)) from error


@router.get("/images/checkpoints")
def list_image_checkpoints():
    return {"available": comfyui_available(), "checkpoints": get_checkpoints()}


@router.get("/images/loras")
def list_image_loras():
    loras = get_loras()
    return {
        "available": comfyui_available(),
        "loras": loras,
        "families": {name: lora_family(name) for name in loras},
    }


@router.post("/images/interrupt")
def interrupt_image_generation():
    """Cancel the running ComfyUI generation (and clear the queue)."""
    return {"interrupted": interrupt()}


@router.get("/system/gpus")
def system_gpus():
    return gpu_status()


def library_query(character_id: str, status: str | None, style: str | None, trash: bool = False, collection_id: str | None = None):
    query = select(ImageLibrary).where(ImageLibrary.character_id == character_id)
    if collection_id:
        query = query.where(
            ImageLibrary.id.in_(
                select(LibraryCollectionItem.image_id).where(LibraryCollectionItem.collection_id == collection_id)
            )
        )
    if trash:
        query = query.where(ImageLibrary.deleted_at.is_not(None))
    else:
        query = query.where(ImageLibrary.deleted_at.is_(None))
    if status:
        query = query.where(ImageLibrary.status == status)
    if style:
        query = query.where(ImageLibrary.style == style)
    return query


@router.get("/characters/{character_id}/library")
def list_library(
    character_id: str,
    status: str | None = None,
    style: str | None = None,
    trash: bool = False,
    collection_id: str | None = None,
    limit: int = Query(60, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    with Session() as db:
        required(db, Influencer, character_id)
        items = db.scalars(
            library_query(character_id, status, style, trash, collection_id)
            .order_by(ImageLibrary.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return [library_out(item) for item in items]


@router.post("/characters/{character_id}/library/generate", status_code=201)
def generate_library_images(character_id: str, body: LibraryGenerateInput):
    """Generate a batch for the image playground and store it as draft."""
    if not comfyui_available():
        raise HTTPException(503, "ComfyUI is unreachable: start the image service")
    with Session() as db:
        character = required(db, Influencer, character_id)
        name = character.name
        profile = normalize_bible_profile(character.bible)
        avatar = character.avatar_filename
        checkpoint = body.checkpoint or character.image_checkpoint
        style = body.style or character.image_style or "real"
        pose_paths: list[Path] = []
        if body.pose_ids:
            poses = list(db.scalars(select(PoseReference).where(PoseReference.id.in_(body.pose_ids))))
            if len(poses) != len(set(body.pose_ids)):
                raise HTTPException(404, "One or more poses were not found")
            for pose in poses:
                candidate = (settings.pose_dir / (pose.skeleton_filename or "")).resolve()
                if candidate.is_file():
                    pose_paths.append(candidate)
    with Session.begin() as db:
        job = create_job(db, type="image", character_id=character_id, message=f"playground batch of {body.count}")
        start_job(db, job, worker="comfyui")
        job_id = job.id
    family = checkpoint_family(style, checkpoint)
    if body.loras:
        available = get_loras()
        if available and any(lora.name not in available for lora in body.loras):
            raise HTTPException(400, "One or more LoRAs are not installed in ComfyUI")
    reference = (settings.media_dir / avatar) if avatar else None
    scene = translate_scene(body.prompt, style)
    prompt = build_prompt_from_profile(name, profile, scene, style, family)
    negative = body.negative or build_negative_prompt(family)
    loras = [lora.model_dump() for lora in body.loras]
    batch_max = max(1, settings.image_library_batch_max)
    count = min(body.count, batch_max)

    def render(index: int) -> tuple[int, bytes, dict]:
        seed = (body.seed + index) if body.seed is not None else random.randrange(2**31)
        pose_path = pose_paths[index % len(pose_paths)] if pose_paths else None
        data, meta = generate_image(
            prompt,
            negative,
            seed=seed,
            reference_path=reference,
            checkpoint=checkpoint,
            style=style,
            family=family,
            loras=loras,
            pose_path=pose_path,
            pose_strength=body.pose_strength,
            base_url=pick_target(),
        )
        return seed, data, meta

    rendered: list[tuple[int, bytes, dict]] = []
    errors: list[Exception] = []
    with ThreadPoolExecutor(max_workers=count) as pool:
        futures = [pool.submit(render, index) for index in range(count)]
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
                        "code": "image_generation_failed",
                        "summary": "Photo generation failed.",
                        "remediation": "Check the ComfyUI instance and the selected checkpoint, then retry.",
                        "technical_details": str(errors[0])[:800] if errors else "",
                    },
                )
        raise HTTPException(502, f"Photo generation failed: {errors[0] if errors else 'unknown error'}")

    created = []
    for seed, data, meta in rendered:
        settings.media_dir.mkdir(parents=True, exist_ok=True)
        filename = f"{identifier()}.png"
        try:
            (settings.media_dir / filename).write_bytes(data)
        except OSError as error:
            raise HTTPException(500, "Could not save the photo") from error
        caption, tags = classify_image(data) if body.classify else ("", [])
        embedding, embedding_model = embed_library_text(
            " ".join(filter(None, [caption, ", ".join(tags), prompt]))
        )
        with Session.begin() as db:
            required(db, Influencer, character_id)
            item = ImageLibrary(
                character_id=character_id,
                filename=filename,
                sha256=hashlib.sha256(data).hexdigest(),
                phash=average_hash(data),
                prompt=prompt,
                negative_prompt=negative,
                caption=caption,
                tags=tags,
                checkpoint=meta.get("checkpoint") or checkpoint,
                loras=loras,
                seed=meta.get("seed", seed),
                style=style,
                status="draft",
                rating=0,
                source="playground",
                embedding=embedding,
                embedding_model=embedding_model,
                policy={"age_safety": "enforced", "adult_only": True, "checked_at": now().isoformat()},
            )
            db.add(item)
            db.flush()
            created.append(library_out(item))
    with Session.begin() as db:
        job = db.get(ExecutionJob, job_id)
        if job is not None and job.state == "running":
            update_progress(db, job, current=len(created), total=count, unit="image")
            finish_job(db, job, state="succeeded", message=f"{len(created)} images ready")
    return created


@router.get("/library/{item_id}")
def get_library_item(item_id: str):
    with Session() as db:
        return library_out(required(db, ImageLibrary, item_id))


@router.get("/library/{item_id}/thumb")
def library_thumbnail(item_id: str):
    """Small cached JPEG thumbnail for grids (avoids loading full images)."""
    import io

    from fastapi.responses import Response
    from PIL import Image

    with Session() as db:
        item = required(db, ImageLibrary, item_id)
        filename = item.filename
    source = (settings.media_dir / filename).resolve()
    if not source.is_file() or not source.is_relative_to(settings.media_dir.resolve()):
        raise HTTPException(404, "Image unavailable")
    cache_dir = settings.media_dir.parent / "thumbs"
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_file = cache_dir / f"{item_id}.jpg"
    if not cache_file.is_file() or cache_file.stat().st_mtime < source.stat().st_mtime:
        try:
            with Image.open(source) as image:
                image = image.convert("RGB")
                image.thumbnail((320, 320))
                buffer = io.BytesIO()
                image.save(buffer, format="JPEG", quality=82)
            cache_file.write_bytes(buffer.getvalue())
        except OSError as error:
            raise HTTPException(404, "Image unavailable") from error
    return Response(content=cache_file.read_bytes(), media_type="image/jpeg")


@router.get("/library/{item_id}/file")
def download_library_image(item_id: str):
    with Session() as db:
        item = required(db, ImageLibrary, item_id)
        filename = item.filename
    path = (settings.media_dir / filename).resolve()
    if not path.is_relative_to(settings.media_dir.resolve()) or not path.is_file():
        raise HTTPException(404, "Image unavailable")
    return FileResponse(path, media_type="image/png", filename=filename)


@router.patch("/library/{item_id}")
def patch_library_item(item_id: str, body: LibraryPatch):
    with Session.begin() as db:
        item = required(db, ImageLibrary, item_id)
        if body.status is not None:
            item.status = body.status
        if body.rating is not None:
            item.rating = body.rating
        if body.caption is not None:
            item.caption = body.caption
        if body.tags is not None:
            item.tags = [tag.strip().lower()[:40] for tag in body.tags if tag.strip()][:20]
        item.updated_at = now()
        db.flush()
        if body.content_label is not None:
            item.content_label = body.content_label
        if body.caption is not None or body.tags is not None:
            embedding, embedding_model = embed_library_text(library_text(item))
            item.embedding = embedding
            item.embedding_model = embedding_model
        if body.status is not None:
            audit_record(db, f"library.{body.status}", "image", item.id)
        return library_out(item)


@router.post("/library/{item_id}/trash")
def trash_library_item(item_id: str):
    """Soft-delete: move the asset to Trash; the file stays until deleted forever."""
    with Session.begin() as db:
        item = required(db, ImageLibrary, item_id)
        item.deleted_at = now()
        audit_record(db, "library.trash", "image", item.id)
        db.flush()
        result = library_out(item)
    return result


@router.post("/library/{item_id}/restore")
def restore_library_item(item_id: str):
    with Session.begin() as db:
        item = required(db, ImageLibrary, item_id)
        item.deleted_at = None
        audit_record(db, "library.restore", "image", item.id)
        db.flush()
        result = library_out(item)
    return result


@router.delete("/library/{item_id}")
def delete_library_item(item_id: str):
    with Session.begin() as db:
        item = required(db, ImageLibrary, item_id)
        filename = item.filename
        db.execute(delete(LoraDatasetItem).where(LoraDatasetItem.image_id == item_id))
        db.execute(update(VideoClip).where(VideoClip.source_image_id == item_id).values(source_image_id=None))
        db.execute(
            update(LoraDataset).where(LoraDataset.anchor_image_id == item_id).values(anchor_image_id=None)
        )
        db.delete(item)
        audit_record(db, "library.delete", "image", item_id)
    unlink_media([filename])
    return {"deleted": True}


@router.get("/collections")
def list_collections():
    with Session() as db:
        collections = db.scalars(select(LibraryCollection).order_by(LibraryCollection.name)).all()
        result = []
        for collection in collections:
            count = db.scalar(
                select(func.count())
                .select_from(LibraryCollectionItem)
                .where(LibraryCollectionItem.collection_id == collection.id)
            ) or 0
            result.append({"id": collection.id, "name": collection.name, "count": count})
        return result


@router.post("/collections", status_code=201)
def create_collection(body: CollectionInput):
    with Session.begin() as db:
        existing = db.scalar(select(LibraryCollection).where(LibraryCollection.name == body.name.strip()))
        if existing is not None:
            return {"id": existing.id, "name": existing.name}
        collection = LibraryCollection(name=body.name.strip())
        db.add(collection)
        db.flush()
        result = {"id": collection.id, "name": collection.name}
    return result


@router.post("/collections/{collection_id}/items")
def add_collection_items(collection_id: str, body: CollectionItemsInput):
    with Session.begin() as db:
        collection = db.get(LibraryCollection, collection_id)
        if collection is None:
            raise HTTPException(404, "Collection not found")
        present = set(
            db.scalars(
                select(LibraryCollectionItem.image_id).where(LibraryCollectionItem.collection_id == collection_id)
            )
        )
        added = 0
        for image_id in body.ids:
            if image_id in present:
                continue
            db.add(LibraryCollectionItem(collection_id=collection_id, image_id=image_id))
            added += 1
    return {"added": added}


@router.delete("/collections/{collection_id}/items")
def remove_collection_items(collection_id: str, body: CollectionItemsInput):
    with Session.begin() as db:
        changed = db.execute(
            delete(LibraryCollectionItem).where(
                LibraryCollectionItem.collection_id == collection_id,
                LibraryCollectionItem.image_id.in_(body.ids),
            )
        )
    return {"removed": changed.rowcount or 0}


@router.delete("/collections/{collection_id}")
def delete_collection(collection_id: str):
    with Session.begin() as db:
        db.execute(delete(LibraryCollectionItem).where(LibraryCollectionItem.collection_id == collection_id))
        db.execute(delete(LibraryCollection).where(LibraryCollection.id == collection_id))
    return {"deleted": True}


@router.post("/library/bulk-status")
def set_library_items_status(body: BulkStatusInput):
    with Session.begin() as db:
        changed = db.execute(
            update(ImageLibrary)
            .where(ImageLibrary.id.in_(body.ids))
            .values(status=body.status, updated_at=now())
        )
        audit_record(db, f"library.bulk_{body.status}", "image", None, count=changed.rowcount or 0)
    return {"updated": changed.rowcount or 0}


@router.post("/library/bulk-delete")
def delete_library_items(body: BulkIdsInput):
    with Session.begin() as db:
        items = db.scalars(select(ImageLibrary).where(ImageLibrary.id.in_(body.ids))).all()
        ids = [item.id for item in items]
        filenames = [item.filename for item in items]
        if ids:
            db.execute(delete(LoraDatasetItem).where(LoraDatasetItem.image_id.in_(ids)))
            db.execute(
                update(LoraDataset).where(LoraDataset.anchor_image_id.in_(ids)).values(anchor_image_id=None)
            )
            db.execute(update(VideoClip).where(VideoClip.source_image_id.in_(ids)).values(source_image_id=None))
        for item in items:
            db.delete(item)
    unlink_media(filenames)
    return {"deleted": len(filenames)}


@router.post("/library/{item_id}/classify")
def classify_library_image(item_id: str):
    with Session() as db:
        required(db, ImageLibrary, item_id)
    classify_library_item(item_id)
    with Session() as db:
        return library_out(required(db, ImageLibrary, item_id))


@router.post("/characters/{character_id}/library/prompt")
def augment_library_prompt(character_id: str, body: PromptAugmentInput):
    with Session() as db:
        required(db, Influencer, character_id)
    if settings.text_provider == "mock":
        return {"prompt": body.prompt}
    target = (
        "English Danbooru-style tags" if body.style == "anime" else "English comma-separated descriptive tags"
    )
    direction = body.direction.strip() or "Add detail, variety and a fitting setting"
    try:
        response = chat(
            settings.image_prompt_model,
            [
                {
                    "role": "system",
                    "content": "You are an automated image prompt writer for a fictional adult art "
                    f"platform. Rewrite and enrich the user scene into {target} for a text-to-image "
                    "model. Keep every explicit detail and follow the requested direction. Never add "
                    "warnings, notes or refusals. Output only the prompt.",
                },
                {"role": "user", "content": f"Scene: {body.prompt}\nDirection: {direction}"},
            ],
            0.7,
            max_tokens=350,
        )
    except OllamaNotAvailable as error:
        raise HTTPException(503, str(error)) from error
    content = response.get("message", {}).get("content", "")
    content = re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL).strip()
    if not content or REFUSAL_PATTERN.search(content):
        return {"prompt": body.prompt}
    return {"prompt": content[:1500]}


def _platform_payload(policy) -> dict:
    from .char_schemas import PLATFORMS

    data = policy.model_dump() if hasattr(policy, "model_dump") else dict(policy or {})
    platforms = data.get("platforms", {}) or {}
    unknown = [name for name in platforms if name not in PLATFORMS]
    if unknown:
        raise HTTPException(400, f"Unknown platform(s): {', '.join(sorted(unknown))}")
    return {"platforms": platforms}


@router.post("/characters", status_code=201)
def create_character(body: CharacterInput):
    with Session.begin() as db:
        item = Influencer(
            name=body.name,
            bible={"profile": body.profile.model_dump()},
            age=body.age,
            synthetic_declared=body.synthetic_declared,
            provenance=body.provenance,
            source_category=body.source_category,
            rights_notes=body.rights_notes,
            source_reference=body.source_reference,
            permitted_uses=body.permitted_uses,
            lifecycle_state=body.lifecycle_state,
            platform_policy=_platform_payload(body.platform_policy),
            ppv_enabled=body.ppv_enabled,
            ppv_price_cents=body.ppv_price_cents,
        )
        db.add(item)
        db.flush()
        db.add(BibleVersion(influencer_id=item.id, version=1, bible=item.bible))
        return character_out(item)


@router.get("/characters")
def list_characters(limit: int = Query(100, ge=1, le=100), offset: int = Query(0, ge=0)):
    with Session() as db:
        return [
            character_out(item)
            for item in db.scalars(
                select(Influencer).order_by(Influencer.created_at).limit(limit).offset(offset)
            )
        ]


@router.get("/characters/{character_id}")
def get_character(character_id: str):
    with Session() as db:
        return character_out(required(db, Influencer, character_id))


@router.put("/characters/{character_id}")
def update_character(character_id: str, body: CharacterUpdate):
    with Session.begin() as db:
        item = required(db, Influencer, character_id)
        version = item.version + 1
        bible = {**item.bible, "profile": body.profile.model_dump()} if body.profile else item.bible
        changed = db.execute(
            update(Influencer)
            .where(Influencer.id == item.id, Influencer.version == item.version)
            .values(
                name=body.name or item.name,
                bible=bible,
                version=version,
                age=body.age if body.age is not None else item.age,
                synthetic_declared=(
                    body.synthetic_declared if body.synthetic_declared is not None else item.synthetic_declared
                ),
                provenance=body.provenance or item.provenance,
                source_category=body.source_category or item.source_category,
                rights_notes=body.rights_notes if body.rights_notes is not None else item.rights_notes,
                source_reference=body.source_reference if body.source_reference is not None else item.source_reference,
                permitted_uses=body.permitted_uses if body.permitted_uses is not None else item.permitted_uses,
                lifecycle_state=body.lifecycle_state or item.lifecycle_state,
                platform_policy=(
                    _platform_payload(body.platform_policy)
                    if body.platform_policy is not None
                    else item.platform_policy
                ),
                ppv_enabled=body.ppv_enabled if body.ppv_enabled is not None else item.ppv_enabled,
                ppv_price_cents=(
                    body.ppv_price_cents if body.ppv_price_cents is not None else item.ppv_price_cents
                ),
            )
        )
        if changed.rowcount != 1:
            raise HTTPException(409, "The character was modified: reload the page")
        db.add(BibleVersion(influencer_id=item.id, version=version, bible=bible))
        db.refresh(item)
        return character_out(item)


AVATAR_VISION_PROMPT = (
    "You are validating an identity anchor for a fictional adult (25+) AI influencer. "
    "Answer strictly: adult (the person clearly looks 21+), one_person (exactly one person), "
    "face_visible (the face is clearly visible and not occluded), sharp (the photo is sharp, not "
    "blurred), and quality_notes (short text, empty when fine)."
)
AVATAR_VISION_SCHEMA = {
    "type": "object",
    "properties": {
        "adult": {"type": "boolean"},
        "one_person": {"type": "boolean"},
        "face_visible": {"type": "boolean"},
        "sharp": {"type": "boolean"},
        "quality_notes": {"type": "string"},
    },
    "required": ["adult", "one_person", "face_visible", "sharp", "quality_notes"],
    "additionalProperties": False,
}


@router.post("/characters/{character_id}/avatar/upload", status_code=201)
def upload_avatar(character_id: str, body: AvatarUploadInput):
    """Identity intake: accept an uploaded anchor after quality and adult validation."""
    import base64
    import io

    from PIL import Image

    from .consistency_api import resize_jpeg
    from .integrations.text import vision_json

    try:
        raw = base64.b64decode(body.image_base64, validate=True)
    except ValueError as error:
        raise HTTPException(400, "Invalid image data") from error
    if len(raw) > 12 * 1024 * 1024:
        raise HTTPException(400, "Image too large: maximum 12 MB")
    try:
        with Image.open(io.BytesIO(raw)) as image:
            image = image.convert("RGB")
            width, height = image.size
            normalized = io.BytesIO()
            image.save(normalized, format="PNG")
            png_bytes = normalized.getvalue()
    except Exception as error:
        raise HTTPException(400, "Invalid or unsupported image file") from error
    if min(width, height) < 512:
        raise HTTPException(
            400, f"Image too small ({width}x{height}): minimum 512 px on the short side"
        )

    with Session() as db:
        character = required(db, Influencer, character_id)
        if character.source_category == "reference_only":
            raise HTTPException(
                400, "Reference-only material cannot be used as an identity anchor: change the source category first"
            )
    try:
        verdict = vision_json(
            settings.consistency_model,
            AVATAR_VISION_PROMPT,
            [resize_jpeg(png_bytes)],
            schema=AVATAR_VISION_SCHEMA,
            max_tokens=160,
        )
    except (OllamaNotAvailable, OSError, ValueError) as error:
        raise HTTPException(
            503, "The vision model is not available: retry when the text model is ready"
        ) from error
    problems = []
    if not verdict.get("adult"):
        problems.append("the person does not clearly look 21+")
    if not verdict.get("one_person"):
        problems.append("the photo must contain exactly one person")
    if not verdict.get("face_visible"):
        problems.append("the face is not clearly visible")
    if not verdict.get("sharp"):
        problems.append("the photo is too blurry")
    if problems:
        raise HTTPException(400, "Image rejected: " + "; ".join(problems))

    settings.media_dir.mkdir(parents=True, exist_ok=True)
    filename = f"{identifier()}.png"
    (settings.media_dir / filename).write_bytes(png_bytes)
    validation = {
        "source": "upload",
        "adult": bool(verdict.get("adult")),
        "one_person": bool(verdict.get("one_person")),
        "face_visible": bool(verdict.get("face_visible")),
        "sharp": bool(verdict.get("sharp")),
        "quality_notes": str(verdict.get("quality_notes") or "")[:200],
        "width": width,
        "height": height,
        "checked_at": now().isoformat(),
    }
    with Session.begin() as db:
        item = required(db, Influencer, character_id)
        old_avatar = item.avatar_filename
        item.avatar_filename = filename
        item.avatar_sha256 = hashlib.sha256(png_bytes).hexdigest()
        item.avatar_validation = validation
        audit_record(db, "avatar.upload", "character", character_id, notes=validation["quality_notes"] or None)
        db.flush()
        result = character_out(item)
    unlink_media([old_avatar] if old_avatar else [])
    return result


@router.post("/characters/{character_id}/avatar", status_code=201)
def generate_avatar(character_id: str, body: AvatarInput | None = None):
    """Generate and remember the character's profile picture (adult, NSFW style)."""
    if not comfyui_available():
        raise HTTPException(503, "ComfyUI is unreachable: start the image service")
    with Session() as db:
        character = required(db, Influencer, character_id)
        if character.source_category == "reference_only":
            raise HTTPException(
                400, "Reference-only material cannot be used as an identity anchor: change the source category first"
            )
        name = character.name
        profile = normalize_bible_profile(character.bible)
        old_avatar = character.avatar_filename
        checkpoint = (body.checkpoint if body else None) or character.image_checkpoint
        style = (body.style if body else None) or character.image_style or "real"
        family = checkpoint_family(style, checkpoint)
    with Session.begin() as db:
        job = create_job(db, type="avatar", character_id=character_id, message="profile picture")
        start_job(db, job, worker="comfyui")
        job_id = job.id
    appearance = (profile.get("appearance") or profile.get("description") or "").strip()
    profile = {**profile, "appearance": translate_scene(appearance, style)}
    prompt = build_avatar_prompt(name, profile, style, family)
    identity_prompt = build_identity_prompt(name, profile, family)
    negative = build_negative_prompt(family)
    reference = (settings.media_dir / old_avatar) if old_avatar else None
    try:
        data, _ = generate_image(
            prompt,
            negative,
            reference_path=reference,
            checkpoint=checkpoint,
            style=style,
            family=family,
            size_label="NSFW DEMO AVATAR",
        )
    except ComfyUIError as error:
        with Session.begin() as db:
            job = db.get(ExecutionJob, job_id)
            if job is not None and job.state == "running":
                finish_job(
                    db,
                    job,
                    state="failed",
                    error_info={
                        "code": "avatar_generation_failed",
                        "summary": "Profile picture generation failed.",
                        "remediation": "Check the ComfyUI instance and the checkpoint, then retry.",
                        "technical_details": str(error)[:800],
                    },
                )
        raise HTTPException(502, f"Profile picture generation failed: {error}") from error
    settings.media_dir.mkdir(parents=True, exist_ok=True)
    filename = f"{identifier()}.png"
    try:
        (settings.media_dir / filename).write_bytes(data)
    except OSError as error:
        raise HTTPException(500, "Could not save the profile picture") from error
    with Session.begin() as db:
        item = required(db, Influencer, character_id)
        old = item.avatar_filename
        item.avatar_filename = filename
        item.avatar_prompt = identity_prompt
        item.avatar_sha256 = hashlib.sha256(data).hexdigest()
        db.flush()
        result = character_out(item)
    with Session.begin() as db:
        job = db.get(ExecutionJob, job_id)
        if job is not None and job.state == "running":
            update_progress(db, job, current=1, total=1, unit="image")
            finish_job(db, job, state="succeeded", message="profile picture ready")
    unlink_media([old] if old else [])
    return result


@router.put("/characters/{character_id}/avatar-prompt")
def set_avatar_prompt(character_id: str, body: AvatarPromptInput):
    with Session.begin() as db:
        item = required(db, Influencer, character_id)
        item.avatar_prompt = body.prompt or None
        db.flush()
        return character_out(item)


@router.post("/characters/{character_id}/avatar/edit", status_code=201)
def edit_avatar(character_id: str, body: AvatarEditInput):
    """Edit the current profile picture with Qwen-Image-Edit (same person, new look/scene)."""
    if not comfyui_available():
        raise HTTPException(503, "ComfyUI is unreachable: start the image service")
    with Session() as db:
        character = required(db, Influencer, character_id)
        if character.source_category == "reference_only":
            raise HTTPException(
                400, "Reference-only material cannot be used as an identity anchor: change the source category first"
            )
        old_avatar = character.avatar_filename
    if not old_avatar:
        raise HTTPException(400, "Generate a profile picture before editing it")
    with Session.begin() as db:
        job = create_job(db, type="avatar", character_id=character_id, message="profile picture edit")
        start_job(db, job, worker="comfyui-edit")
        job_id = job.id
    source = (settings.media_dir / old_avatar).resolve()
    if not source.is_file() or not source.is_relative_to(settings.media_dir.resolve()):
        raise HTTPException(404, "Profile picture unavailable")
    try:
        data, _ = qwen_image_edit(
            source,
            body.prompt,
            steps=body.steps,
            cfg=body.cfg,
            lora_weight=body.lora_weight,
        )
    except ComfyUIError as error:
        with Session.begin() as db:
            job = db.get(ExecutionJob, job_id)
            if job is not None and job.state == "running":
                finish_job(
                    db,
                    job,
                    state="failed",
                    error_info={
                        "code": "avatar_edit_failed",
                        "summary": "Profile picture edit failed.",
                        "remediation": "Check the Qwen-Image-Edit model and the ComfyUI instance, then retry.",
                        "technical_details": str(error)[:800],
                    },
                )
        raise HTTPException(502, f"Profile picture edit failed: {error}") from error
    settings.media_dir.mkdir(parents=True, exist_ok=True)
    filename = f"{identifier()}.png"
    try:
        (settings.media_dir / filename).write_bytes(data)
    except OSError as error:
        raise HTTPException(500, "Could not save the profile picture") from error
    with Session.begin() as db:
        item = required(db, Influencer, character_id)
        old = item.avatar_filename
        item.avatar_filename = filename
        item.avatar_sha256 = hashlib.sha256(data).hexdigest()
        db.flush()
        result = character_out(item)
    with Session.begin() as db:
        job = db.get(ExecutionJob, job_id)
        if job is not None and job.state == "running":
            update_progress(db, job, current=1, total=1, unit="image")
            finish_job(db, job, state="succeeded", message="profile picture edited")
    unlink_media([old] if old and old != filename else [])
    return result


@router.put("/characters/{character_id}/image-checkpoint")
def set_image_checkpoint(character_id: str, body: ImageCheckpointInput):
    if body.checkpoint:
        checkpoints = get_checkpoints()
        if checkpoints and body.checkpoint not in [item["name"] for item in checkpoints]:
            raise HTTPException(400, "Checkpoint not installed in ComfyUI")
    with Session.begin() as db:
        item = required(db, Influencer, character_id)
        item.image_checkpoint = body.checkpoint
        db.flush()
        return character_out(item)


@router.put("/characters/{character_id}/image-style")
def set_image_style(character_id: str, body: ImageStyleInput):
    with Session.begin() as db:
        item = required(db, Influencer, character_id)
        item.image_style = body.style
        db.flush()
        return character_out(item)


@router.put("/characters/{character_id}/ppv")
def set_character_ppv(character_id: str, body: PpvInput):
    with Session.begin() as db:
        item = required(db, Influencer, character_id)
        item.ppv_enabled = body.enabled
        item.ppv_price_cents = body.price_cents
        db.flush()
        return character_out(item)


@router.put("/characters/{character_id}/realism")
def set_character_realism(character_id: str, body: RealismInput):
    low, high = sorted((body.reply_delay_min_seconds, body.reply_delay_max_seconds))
    with Session.begin() as db:
        item = required(db, Influencer, character_id)
        item.reply_delay_min_seconds = low
        item.reply_delay_max_seconds = high
        item.activity_enabled = body.activity_enabled
        item.activity_start_hour = body.activity_start_hour
        item.activity_end_hour = body.activity_end_hour
        item.activity_days = body.activity_days
        db.flush()
        return character_out(item)


@router.get("/characters/{character_id}/avatar/file")
def download_avatar(character_id: str):
    with Session() as db:
        character = required(db, Influencer, character_id)
        filename = character.avatar_filename
    if not filename:
        raise HTTPException(404, "Profile picture unavailable")
    path = (settings.media_dir / filename).resolve()
    if not path.is_relative_to(settings.media_dir.resolve()) or not path.is_file():
        raise HTTPException(404, "Profile picture unavailable")
    return FileResponse(path, media_type="image/png", filename=filename)


@router.get("/chat-images/{image_id}/file")
def download_chat_image(image_id: str):
    with Session() as db:
        item = required(db, ChatImage, image_id)
        filename, media_type = item.filename, item.media_type
        locked = item.price_cents > 0 and item.unlocked_at is None
    path = (settings.media_dir / filename).resolve()
    if not path.is_relative_to(settings.media_dir.resolve()) or not path.is_file():
        raise HTTPException(404, "Image unavailable")
    if locked:
        try:
            return Response(content=blurred_png(path.read_bytes()), media_type="image/png")
        except OSError as error:
            raise HTTPException(404, "Image unavailable") from error
    return FileResponse(path, media_type=media_type, filename=filename)


@router.get("/chat-videos/{video_id}/file")
def download_chat_video(video_id: str):
    with Session() as db:
        item = required(db, ChatVideo, video_id)
        clip = db.get(VideoClip, item.video_id)
        locked = item.price_cents > 0 and item.unlocked_at is None
        filename = clip.filename if clip else ""
    if locked:
        raise HTTPException(403, "Video locked: unlock it to watch")
    path = (settings.media_dir / filename).resolve()
    if not path.is_file() or not path.is_relative_to(settings.media_dir.resolve()):
        raise HTTPException(404, "Video unavailable")
    return FileResponse(path, media_type="video/webm", filename=path.name)


@router.post("/chat-videos/{video_id}/unlock")
def unlock_chat_video(video_id: str):
    """Simulated PPV unlock for a chat video: records a fake payment, no real transaction."""
    with Session.begin() as db:
        item = required(db, ChatVideo, video_id)
        if item.price_cents <= 0:
            raise HTTPException(409, "This video is not paywalled")
        if item.unlocked_at is not None:
            raise HTTPException(409, "Video already unlocked")
        conversation = required(db, Conversation, item.conversation_id)
        payment = SimulatedPayment(
            chat_video_id=item.id,
            conversation_id=item.conversation_id,
            fan_id=conversation.fan_id,
            amount_cents=item.price_cents,
        )
        db.add(payment)
        item.unlocked_at = now()
        db.flush()
        result = chat_video_out(item, db.get(VideoClip, item.video_id))
        result["payment"] = {
            "amount_cents": payment.amount_cents,
            "simulated": True,
            "created_at": payment.created_at.isoformat(),
        }
    return result


@router.post("/chat-images/{image_id}/unlock")
def unlock_chat_image(image_id: str):
    """Simulated PPV unlock: records a fake payment, no real transaction."""
    with Session.begin() as db:
        item = required(db, ChatImage, image_id)
        if item.price_cents <= 0:
            raise HTTPException(409, "This image is not paywalled")
        if item.unlocked_at is not None:
            raise HTTPException(409, "Image already unlocked")
        conversation = required(db, Conversation, item.conversation_id)
        payment = SimulatedPayment(
            chat_image_id=item.id,
            conversation_id=item.conversation_id,
            fan_id=conversation.fan_id,
            amount_cents=item.price_cents,
        )
        db.add(payment)
        item.unlocked_at = now()
        db.flush()
        result = image_out(item)
        result["payment"] = {
            "amount_cents": payment.amount_cents,
            "simulated": True,
            "created_at": payment.created_at.isoformat(),
        }
        return result


@router.post("/characters/{character_id}/clone", status_code=201)
def clone_character(character_id: str, body: CharacterClone | None = None):
    with Session.begin() as db:
        source = required(db, Influencer, character_id)
        profile = normalize_bible_profile(source.bible)
        name = body.name if body and body.name else f"{source.name} (copy)"
        item = Influencer(
            name=name[:120],
            bible={"profile": profile},
            age=source.age,
            synthetic_declared=source.synthetic_declared,
            provenance=source.provenance,
            source_category=source.source_category,
            rights_notes=source.rights_notes,
            source_reference=source.source_reference,
            permitted_uses=source.permitted_uses,
            lifecycle_state=source.lifecycle_state,
            platform_policy=source.platform_policy,
        )
        db.add(item)
        db.flush()
        db.add(BibleVersion(influencer_id=item.id, version=1, bible=item.bible))
        return character_out(item)


@router.post("/character-drafts/enhance")
def enhance_character(body: EnhanceInput):
    ensure_model(body.model)
    start = time.perf_counter()
    # Keep Ollama's grammar small; full length/type validation happens after generation.
    profile_schema = {
        "type": "object",
        "properties": {name: {"type": "string"} for name in CharacterProfile.model_fields},
        "required": list(CharacterProfile.model_fields),
        "additionalProperties": False,
    }
    try:
        response = chat(
            body.model,
            [
                {
                    "role": "system",
                    "content": "Expand this adult fictional character into a distinctive chatbot "
                    "personality. Preserve identity, language and boundaries. Include natural speech habits, interests, "
                    "playfulness and initiative. Keep flirtation non-graphic and respectful. Output the full profile "
                    "as JSON matching the schema. Use one or two short sentences per field and a language code (it/en/etc). "
                    "This is a draft for human review.",
                },
                {"role": "user", "content": body.model_dump_json()},
            ],
            0.7,
            format_schema=profile_schema,
            max_tokens=2048,
        )
        profile = (
            body.profile
            if settings.text_provider == "mock"
            else CharacterProfile.model_validate_json(response["message"]["content"])
        )
        return {"profile": profile.model_dump(), "model": body.model, "seconds": time.perf_counter() - start}
    except (OllamaNotAvailable, ValidationError, KeyError) as error:
        raise HTTPException(
            502, "The model did not return a valid description. Try another model."
        ) from error


@router.get("/fans")
def list_fans():
    with Session() as db:
        return list(db.scalars(select(Fan).order_by(Fan.created_at)))


@router.post("/fans", status_code=201)
def create_fan(body: FanInput):
    with Session.begin() as db:
        item = Fan(**body.model_dump())
        db.add(item)
        db.flush()
        return item


@router.put("/fans/{fan_id}")
def update_fan(fan_id: str, body: FanInput):
    with Session.begin() as db:
        fan = required(db, Fan, fan_id)
        fan.name, fan.notes = body.name, body.notes
        return fan


def check_busy(db, query):
    if db.scalar(query.where(Conversation.busy_until > now()).limit(1)):
        raise HTTPException(409, "A reply is in progress. Wait before changing or deleting the chat.")


def purge_conversations(db, ids):
    filenames = list(db.scalars(select(ChatImage.filename).where(ChatImage.conversation_id.in_(ids))))
    db.execute(delete(ScheduledReply).where(ScheduledReply.conversation_id.in_(ids)))
    db.execute(delete(SimulatedPayment).where(SimulatedPayment.conversation_id.in_(ids)))
    db.execute(delete(ChatImage).where(ChatImage.conversation_id.in_(ids)))
    db.execute(delete(ChatMessage).where(ChatMessage.conversation_id.in_(ids)))
    db.execute(delete(Conversation).where(Conversation.id.in_(ids)))
    return filenames


def unlink_media(filenames):
    for filename in filenames:
        path = (settings.media_dir / filename).resolve()
        if path.is_relative_to(settings.media_dir.resolve()):
            path.unlink(missing_ok=True)


@router.delete("/fans/{fan_id}")
def delete_fan(fan_id: str):
    with Session.begin() as db:
        fan = required(db, Fan, fan_id)
        check_busy(db, select(Conversation.id).where(Conversation.fan_id == fan_id))
        ids = list(db.scalars(select(Conversation.id).where(Conversation.fan_id == fan_id)))
        filenames = purge_conversations(db, ids)
        db.execute(delete(Memory).where(Memory.fan_id == fan_id))
        db.execute(delete(BenchmarkSample).where(BenchmarkSample.fan_id == fan_id))
        db.delete(fan)
    unlink_media(filenames)
    return {"deleted": True}


@router.post("/characters/{character_id}/conversations", status_code=201)
def create_conversation(character_id: str, body: ConversationInput):
    ensure_model(body.model)
    with Session.begin() as db:
        character = required(db, Influencer, character_id)
        if body.fan_id:
            required(db, Fan, body.fan_id)
        conv = Conversation(
            character_id=character_id,
            fan_id=body.fan_id,
            model=body.model,
            title=body.title or f"Chat con {character.name}",
            character_snapshot={
                "id": character.id,
                "name": character.name,
                "profile": normalize_bible_profile(character.bible),
                "version": character.version,
            },
        )
        db.add(conv)
        db.flush()
    if body.auto_greet:
        try:
            run_turn(conv.id, kind="opener")
        except HTTPException as error:
            # Keep the created conversation available and make a failed greeting explicit.
            with Session() as db:
                conv = required(db, Conversation, conv.id)
                return {**conversation_out(db, conv), "greeting_error": error.detail}
    with Session() as db:
        return conversation_out(db, required(db, Conversation, conv.id))


@router.get("/conversations/{conversation_id}")
def get_conversation(conversation_id: str):
    with Session() as db:
        return conversation_out(db, required(db, Conversation, conversation_id))


@router.post("/conversations/{conversation_id}/read")
def mark_conversation_read(conversation_id: str):
    with Session.begin() as db:
        conv = required(db, Conversation, conversation_id)
        conv.last_read_at = now()
        db.flush()
        return conversation_out(db, conv)


@router.patch("/conversations/{conversation_id}")
def patch_conversation(conversation_id: str, body: ConversationPatch):
    if body.model:
        ensure_model(body.model)
    with Session.begin() as db:
        conv = required(db, Conversation, conversation_id)
        check_busy(db, select(Conversation.id).where(Conversation.id == conv.id))
        if body.title:
            conv.title = body.title
        if body.model:
            conv.model = body.model
        if body.images_enabled is not None:
            conv.images_enabled = body.images_enabled
        if body.human_mode is not None:
            conv.human_mode = body.human_mode
        # Nullable overrides: distinguish "not provided" from an explicit null (clears the override).
        provided = body.model_fields_set
        if "ppv_enabled" in provided:
            conv.ppv_enabled = body.ppv_enabled
        if "ppv_price_cents" in provided:
            conv.ppv_price_cents = body.ppv_price_cents
        conv.updated_at = now()
        db.flush()
        return conversation_out(db, conv)


def run_turn(
    conversation_id, *, content=None, kind="reply", absence_hours=48, background_tasks=None, store_user=True
):
    lease = now() + timedelta(seconds=settings.ollama_timeout_seconds + 90)
    with Session.begin() as db:
        required(db, Conversation, conversation_id)
        changed = db.execute(
            update(Conversation)
            .where(
                Conversation.id == conversation_id,
                or_(Conversation.busy_until.is_(None), Conversation.busy_until < now()),
            )
            .values(busy_until=lease)
        )
        if changed.rowcount != 1:
            raise HTTPException(409, "The character is already replying in this conversation")
        conv = required(db, Conversation, conversation_id)
    try:
        answer, metrics = generate_reply(conv, content or "", kind, absence_hours)
        image_data, image_meta, image_prompt, image_negative, filename = None, None, None, None, None
        reused_item = None
        draft_embedding, draft_embedding_model = [], ""
        video_item = None
        video_price = 0
        video_scene = metrics.get("video_scene")
        if video_scene:
            choices = []
            with Session() as db:
                character = db.get(Influencer, conv.character_id)
                ppv_on, video_price = effective_ppv(conv, character) if character else (False, 0)
                allowed = bool(
                    settings.chat_video_enabled
                    and settings.ppv_enabled
                    and character is not None
                    and ppv_on
                    and video_price > 0
                )
                if allowed:
                    sent_ids = set(
                        db.scalars(select(ChatVideo.video_id).where(ChatVideo.conversation_id == conv.id))
                    )
                    candidates = list(
                        db.scalars(
                            select(VideoClip)
                            .where(VideoClip.character_id == conv.character_id, VideoClip.status == "ready")
                            .order_by(VideoClip.created_at.desc())
                        )
                    )
                    choices = [clip for clip in candidates if clip.id not in sent_ids] or candidates
            if choices:
                video_item = random.choice(choices)
                metrics["video_sent"] = True
                metrics["video_locked"] = True
                metrics["video_price_cents"] = video_price
            else:
                metrics["video_error"] = "no ready clips"
        scene = metrics.get("photo_scene")
        if scene:
            with Session() as db:
                character = db.get(Influencer, conv.character_id)
                reference = (
                    settings.media_dir / character.avatar_filename
                    if character and character.avatar_filename
                    else None
                )
                checkpoint = character.image_checkpoint if character else None
                style = (character.image_style or "real") if character else "real"
                ppv_enabled, ppv_price = effective_ppv(conv, character) if character else (False, 0)
                proposed_price = metrics.get("photo_price_cents")
                if isinstance(proposed_price, int) and 0 < proposed_price <= 100000:
                    ppv_price = proposed_price
            family = checkpoint_family(style, checkpoint)
            locked = bool(
                metrics.get("photo_locked_requested")
                and settings.ppv_enabled
                and ppv_enabled
                and ppv_price > 0
            )
            metrics["photo_locked"] = locked
            if metrics.get("photo_locked_requested") and not locked:
                metrics["photo_free"] = True
            scene_en = translate_scene(scene, style)
            image_prompt = build_scene_prompt(conv, scene_en, style, family)
            image_negative = build_negative_prompt(family)
            # Reuse an approved library image when the scene is close enough.
            reused_item = match_library_image(conv.character_id, style, scene_en)
            if reused_item is not None:
                try:
                    image_data = (settings.media_dir / reused_item.filename).read_bytes()
                except OSError:
                    reused_item = None
            if reused_item is not None:
                image_meta = {"provider": "library", "seed": reused_item.seed, "reference": False}
                metrics["image_reused"] = True
                metrics["image_seconds"] = 0.0
                metrics["image_style"] = style
                settings.media_dir.mkdir(parents=True, exist_ok=True)
                filename = f"{identifier()}.png"
                try:
                    (settings.media_dir / filename).write_bytes(image_data)
                except OSError:
                    reused_item, image_data, image_meta, filename = None, None, None, None
            if reused_item is None:
                try:
                    image_start = time.perf_counter()
                    image_data, image_meta = generate_image(
                        image_prompt,
                        image_negative,
                        reference_path=reference,
                        checkpoint=checkpoint,
                        style=style,
                        family=family,
                    )
                    metrics["image_seconds"] = time.perf_counter() - image_start
                    metrics["image_reference"] = image_meta.get("reference", False)
                    metrics["image_style"] = style
                    metrics["image_family"] = family
                    if image_meta.get("checkpoint"):
                        metrics["image_checkpoint"] = image_meta["checkpoint"]
                    filename = f"{identifier()}.png"
                    settings.media_dir.mkdir(parents=True, exist_ok=True)
                    (settings.media_dir / filename).write_bytes(image_data)
                    draft_embedding, draft_embedding_model = embed_library_text(image_prompt)
                except (ComfyUIError, OSError) as error:
                    logger.exception("Chat image generation failed for conversation %s", conversation_id)
                    metrics["image_error"] = str(error)[:300]
                    image_data, image_meta, filename = None, None, None
        bursts = human_bursts(answer) if conv.human_mode and not metrics.get("guarded") else [answer]
        with Session.begin() as db:
            current = required(db, Conversation, conversation_id)
            if content is not None and store_user:
                user = ChatMessage(conversation_id=conv.id, role="user", content=content)
                db.add(user)
                db.flush()
                current.memory_status = "pending"
            created = []
            for index, part in enumerate(bursts):
                item = ChatMessage(
                    conversation_id=conv.id,
                    role="assistant",
                    content=part,
                    model=conv.model,
                    ollama_metrics=metrics if index == len(bursts) - 1 else None,
                )
                db.add(item)
                db.flush()
                created.append(item)
            assistant = created[-1]
            followup_hours = metrics.get("followup_hours")
            if isinstance(followup_hours, (int, float)) and followup_hours > 0:
                character_row = db.get(Influencer, conv.character_id)
                if character_row is not None:
                    from .scheduler import compute_deliver_at

                    db.add(
                        ScheduledReply(
                            conversation_id=conv.id,
                            character_id=conv.character_id,
                            kind="reengage",
                            content=None,
                            absence_hours=48,
                            deliver_at=compute_deliver_at(
                                character_row, delay_seconds=float(followup_hours) * 3600
                            ),
                            status="scheduled",
                            source_message_id=assistant.id,
                        )
                    )
            current.updated_at = now()
            if metrics.get("policy_block"):
                audit_record(
                    db,
                    "chat.policy_block",
                    "conversation",
                    conv.id,
                    issues=metrics.get("policy_block"),
                )
            db.flush()
            if video_item is not None:
                db.add(
                    ChatVideo(
                        message_id=assistant.id,
                        conversation_id=conv.id,
                        character_id=conv.character_id,
                        video_id=video_item.id,
                        prompt=video_scene or "",
                        price_cents=video_price,
                    )
                )
            if filename and image_meta and image_prompt and image_negative:
                db.add(
                    ChatImage(
                        message_id=assistant.id,
                        conversation_id=conv.id,
                        character_id=conv.character_id,
                        filename=filename,
                        sha256=hashlib.sha256(image_data).hexdigest(),
                        media_type="image/png",
                        prompt=image_prompt,
                        negative_prompt=image_negative,
                        seed=image_meta["seed"],
                        nsfw=settings.chat_image_nsfw,
                        provider=image_meta["provider"],
                        price_cents=ppv_price if locked else 0,
                    )
                )
                metrics["image_sent"] = True
                if locked:
                    metrics["image_price_cents"] = ppv_price
                if reused_item is not None:
                    db.execute(
                        update(ImageLibrary)
                        .where(ImageLibrary.id == reused_item.id)
                        .values(used_count=ImageLibrary.used_count + 1, updated_at=now())
                    )
                    metrics["image_library_id"] = reused_item.id
                else:
                    digest = hashlib.sha256(image_data).hexdigest()
                    exists = db.scalar(
                        select(ImageLibrary.id).where(
                            ImageLibrary.character_id == conv.character_id,
                            ImageLibrary.sha256 == digest,
                        )
                    )
                    if not exists:
                        draft = ImageLibrary(
                            character_id=conv.character_id,
                            filename=filename,
                            sha256=digest,
                            phash=average_hash(image_data),
                            prompt=image_prompt,
                            negative_prompt=image_negative,
                            caption="",
                            tags=[],
                            checkpoint=image_meta.get("checkpoint"),
                            loras=image_meta.get("loras") or [],
                            seed=image_meta.get("seed", 0),
                            style=metrics.get("image_style") or "real",
                            status="draft",
                            rating=0,
                            source="chat",
                            embedding=draft_embedding,
                            embedding_model=draft_embedding_model,
                        )
                        db.add(draft)
                        db.flush()
                        if background_tasks is not None:
                            background_tasks.add_task(classify_library_item, draft.id)
            if store_user and content is not None and background_tasks is not None:
                background_tasks.add_task(extract_memories, conv.id, user.id)
            out = messages_out(db, created)
            last = out[-1]
            if len(out) > 1:
                delay = 0
                burst = []
                for index, message in enumerate(out):
                    if index:
                        delay += random.randint(700, 2200)
                    burst.append({"id": message["id"], "content": message["content"], "delay_ms": delay})
                last["burst"] = burst
            return last
    except OllamaNotAvailable as error:
        raise HTTPException(503, str(error)) from error
    finally:
        with Session.begin() as db:
            db.execute(
                update(Conversation)
                .where(Conversation.id == conversation_id, Conversation.busy_until == lease)
                .values(busy_until=None)
            )


@router.post("/conversations/{conversation_id}/video", status_code=201)
def send_video(conversation_id: str, body: ChatVideoInput):
    """Manual video: send a reviewed library clip to the fan without asking the chat model."""
    if not settings.chat_video_enabled:
        raise HTTPException(409, "Chat videos are disabled")
    lease = now() + timedelta(seconds=settings.generation_timeout + 60)
    with Session.begin() as db:
        changed = db.execute(
            update(Conversation)
            .where(
                Conversation.id == conversation_id,
                or_(Conversation.busy_until.is_(None), Conversation.busy_until < now()),
            )
            .values(busy_until=lease)
        )
        if changed.rowcount != 1:
            raise HTTPException(409, "The character is already replying in this conversation")
        conv = required(db, Conversation, conversation_id)
        character = required(db, Influencer, conv.character_id)
        clip = required(db, VideoClip, body.video_id)
        if clip.character_id != conv.character_id:
            raise HTTPException(404, "Video unavailable")
        if clip.status != "ready":
            raise HTTPException(409, "The video is not ready yet")
        _ppv_on, ppv_price = effective_ppv(conv, character)
        locked_price = 0
        if body.locked and settings.ppv_enabled:
            locked_price = body.price_cents or ppv_price or 500
        caption = (body.caption or clip.prompt or "guarda qua 😏").strip()[:1000]
    try:
        with Session.begin() as db:
            current = required(db, Conversation, conversation_id)
            message = ChatMessage(
                conversation_id=conversation_id,
                role="assistant",
                content=caption,
                model=conv.model,
                ollama_metrics={
                    "kind": "video",
                    "manual": True,
                    "video_sent": True,
                    "video_locked": locked_price > 0,
                    "video_price_cents": locked_price,
                },
            )
            db.add(message)
            db.flush()
            db.add(
                ChatVideo(
                    message_id=message.id,
                    conversation_id=conversation_id,
                    character_id=conv.character_id,
                    video_id=clip.id,
                    prompt=clip.prompt or "",
                    price_cents=locked_price,
                )
            )
            current.updated_at = now()
            db.flush()
            return messages_out(db, [message])[0]
    finally:
        with Session.begin() as db:
            db.execute(
                update(Conversation)
                .where(Conversation.id == conversation_id, Conversation.busy_until == lease)
                .values(busy_until=None)
            )


@router.post("/conversations/{conversation_id}/messages")
def create_chat_message(conversation_id: str, body: ChatMessageInput, background_tasks: BackgroundTasks):
    if body.scheduled:
        return schedule_turn(conversation_id, body.content, background_tasks)
    reply = run_turn(conversation_id, content=body.content, background_tasks=background_tasks)
    maybe_schedule_proactive(conversation_id)
    return reply


def schedule_turn(conversation_id: str, content: str, background_tasks):
    """Realistic mode: store the fan message now, deliver the reply after a delay."""
    with Session() as db:
        conversation = required(db, Conversation, conversation_id)
        character = required(db, Influencer, conversation.character_id)
        immediate = not settings.chat_scheduling_enabled or (character.reply_delay_max_seconds or 0) <= 0
    if immediate:
        reply = run_turn(conversation_id, content=content, background_tasks=background_tasks)
        maybe_schedule_proactive(conversation_id)
        return {"scheduled": False, "message": None, "reply": reply, "deliver_at": None}
    with Session.begin() as db:
        conversation = required(db, Conversation, conversation_id)
        user = ChatMessage(conversation_id=conversation_id, role="user", content=content)
        db.add(user)
        db.flush()
        conversation.updated_at = now()
        message = messages_out(db, [user])[0]
        source_id = user.id
    pending = schedule_reply(conversation_id, content, source_message_id=source_id)
    return {
        "scheduled": True,
        "message": message,
        "reply": None,
        "deliver_at": pending.deliver_at.isoformat(),
    }


@router.post("/conversations/{conversation_id}/initiate")
def initiate(conversation_id: str, body: InitiateInput, background_tasks: BackgroundTasks):
    return run_turn(
        conversation_id,
        kind=body.kind,
        absence_hours=body.absence_hours,
        background_tasks=background_tasks,
    )


@router.post("/conversations/{conversation_id}/photo", status_code=201)
def send_photo(conversation_id: str, body: PhotoInput):
    """Manual photo: the operator generates a photo without asking the chat model."""
    if not settings.chat_image_enabled:
        raise HTTPException(409, "Chat photos are disabled")
    if not comfyui_available():
        raise HTTPException(503, "ComfyUI is unreachable: start the image service")
    lease = now() + timedelta(seconds=settings.generation_timeout + 60)
    with Session.begin() as db:
        changed = db.execute(
            update(Conversation)
            .where(
                Conversation.id == conversation_id,
                or_(Conversation.busy_until.is_(None), Conversation.busy_until < now()),
            )
            .values(busy_until=lease)
        )
        if changed.rowcount != 1:
            raise HTTPException(409, "The character is already replying in this conversation")
        conv = required(db, Conversation, conversation_id)
        character = required(db, Influencer, conv.character_id)
        reference = settings.media_dir / character.avatar_filename if character.avatar_filename else None
        checkpoint = character.image_checkpoint
        style = character.image_style or "real"
        family = checkpoint_family(style, checkpoint)
        _ppv_on, ppv_default_price = effective_ppv(conv, character)
        locked_price = 0
        if body.locked and settings.ppv_enabled:
            # Manual photos can be locked explicitly; the price falls back to the effective default.
            locked_price = body.price_cents or ppv_default_price or 500
        chosen = required(db, ImageLibrary, body.library_id) if body.library_id else None
        if chosen is not None and chosen.character_id != conv.character_id:
            raise HTTPException(404, "Image unavailable")
    try:
        if chosen is not None:
            source = (settings.media_dir / chosen.filename).resolve()
            if not source.is_file() or not source.is_relative_to(settings.media_dir.resolve()):
                raise HTTPException(404, "Image unavailable")
            image_data = source.read_bytes()
            image_meta = {"provider": "library", "seed": chosen.seed, "reference": False}
            prompt, negative, style, seconds = chosen.prompt, chosen.negative_prompt, chosen.style, 0.0
        else:
            scene = body.scene or "sensual selfie, lying on bed, looking at viewer, flirty expression"
            prompt = build_scene_prompt(conv, translate_scene(scene, style), style, family)
            negative = build_negative_prompt(family)
            try:
                image_start = time.perf_counter()
                image_data, image_meta = generate_image(
                    prompt,
                    negative,
                    reference_path=reference,
                    checkpoint=checkpoint,
                    style=style,
                    family=family,
                )
            except ComfyUIError as error:
                raise HTTPException(502, f"Photo generation failed: {error}") from error
            seconds = time.perf_counter() - image_start
        settings.media_dir.mkdir(parents=True, exist_ok=True)
        filename = f"{identifier()}.png"
        try:
            (settings.media_dir / filename).write_bytes(image_data)
        except OSError as error:
            raise HTTPException(500, "Could not save the photo") from error
        metrics = {
            "kind": "photo",
            "manual": True,
            "image_sent": True,
            "image_seconds": seconds,
            "image_reference": image_meta.get("reference", False),
            "image_style": style,
            "image_family": family,
            "image_price_cents": locked_price,
            "request_seconds": seconds,
            "guarded": False,
            "guard_reason": None,
        }
        if chosen is not None:
            metrics["image_library_id"] = chosen.id
        if image_meta.get("checkpoint"):
            metrics["image_checkpoint"] = image_meta["checkpoint"]
        caption = body.caption if body.caption is not None else (chosen.caption if chosen else "")
        with Session.begin() as db:
            required(db, Conversation, conversation_id)
            assistant = ChatMessage(
                conversation_id=conversation_id,
                role="assistant",
                content=caption or "",
                model=None,
                ollama_metrics=metrics,
            )
            db.add(assistant)
            db.flush()
            db.add(
                ChatImage(
                    message_id=assistant.id,
                    conversation_id=conversation_id,
                    character_id=conv.character_id,
                    filename=filename,
                    sha256=hashlib.sha256(image_data).hexdigest(),
                    media_type="image/png",
                    prompt=prompt,
                    negative_prompt=negative,
                    seed=image_meta["seed"],
                    nsfw=settings.chat_image_nsfw,
                    provider=image_meta["provider"],
                    price_cents=locked_price,
                )
            )
            if chosen is not None:
                db.execute(
                    update(ImageLibrary)
                    .where(ImageLibrary.id == chosen.id)
                    .values(used_count=ImageLibrary.used_count + 1, updated_at=now())
                )
            return messages_out(db, [assistant])[0]
    finally:
        with Session.begin() as db:
            db.execute(
                update(Conversation)
                .where(Conversation.id == conversation_id, Conversation.busy_until == lease)
                .values(busy_until=None)
            )


@router.get("/conversations/{conversation_id}/messages")
def list_conversation_messages(
    conversation_id: str, limit: int = Query(100, ge=1, le=500), offset: int = Query(0, ge=0)
):
    with Session() as db:
        required(db, Conversation, conversation_id)
        rows = list(
            db.scalars(
                select(ChatMessage)
                .where(ChatMessage.conversation_id == conversation_id)
                .order_by(ChatMessage.created_at, ChatMessage.id)
                .limit(limit)
                .offset(offset)
            )
        )
        return messages_out(db, rows)


@router.get("/characters/{character_id}/conversations")
def list_character_conversations(
    character_id: str,
    fan_id: str | None = None,
    limit: int = Query(100, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    with Session() as db:
        required(db, Influencer, character_id)
        query = select(Conversation).where(Conversation.character_id == character_id)
        if fan_id is not None:
            query = query.where(Conversation.fan_id == fan_id)
        rows = list(db.scalars(query.order_by(Conversation.created_at.desc()).limit(limit).offset(offset)))
        return [conversation_out(db, row) for row in rows]


@router.delete("/conversations/{conversation_id}")
def delete_conversation(conversation_id: str):
    with Session.begin() as db:
        required(db, Conversation, conversation_id)
        check_busy(db, select(Conversation.id).where(Conversation.id == conversation_id))
        filenames = purge_conversations(db, [conversation_id])
    unlink_media(filenames)
    return {"deleted": True}


@router.get("/characters/{character_id}/memories")
def list_memories(character_id: str, fan_id: str | None = None):
    with Session() as db:
        required(db, Influencer, character_id)
        return list(
            db.scalars(
                select(Memory)
                .where(Memory.character_id == character_id, Memory.fan_id == fan_id, Memory.active.is_(True))
                .order_by(Memory.created_at.desc())
            )
        )


@router.post("/characters/{character_id}/memories", status_code=201)
def add_memory(character_id: str, body: MemoryInput, fan_id: str | None = None):
    with Session.begin() as db:
        required(db, Influencer, character_id)
        if fan_id:
            required(db, Fan, fan_id)
        digest = content_hash(body.content)
        item = db.scalar(
            select(Memory).where(
                Memory.character_id == character_id, Memory.fan_id == fan_id, Memory.content_hash == digest
            )
        )
        if not item:
            item = Memory(
                character_id=character_id,
                fan_id=fan_id,
                **body.model_dump(),
                embedding={},
                embedding_model="manual",
                content_hash=digest,
                active=True,
            )
            db.add(item)
            db.flush()
        return item


@router.delete("/memories/{memory_id}")
def delete_memory(memory_id: str):
    with Session.begin() as db:
        db.delete(required(db, Memory, memory_id))
    return {"deleted": True}


@router.delete("/characters/{character_id}/memories")
def delete_all_memories(character_id: str, fan_id: str | None = None):
    with Session.begin() as db:
        required(db, Influencer, character_id)
        changed = db.execute(
            delete(Memory).where(Memory.character_id == character_id, Memory.fan_id == fan_id)
        )
    return {"deleted": True, "count": changed.rowcount}


@router.delete("/characters/{character_id}")
def delete_character(character_id: str):
    paths = []
    with Session.begin() as db:
        character = required(db, Influencer, character_id)
        check_busy(db, select(Conversation.id).where(Conversation.character_id == character_id))
        if db.scalar(
            select(Job.id).where(Job.influencer_id == character_id, Job.status.in_(["queued", "running"]))
        ):
            raise HTTPException(409, "The character has generations in progress")
        if db.scalar(
            select(TrainingJob.id).where(
                TrainingJob.character_id == character_id, TrainingJob.status.in_(["queued", "running"])
            )
        ):
            raise HTTPException(409, "The character has a LoRA training in progress")
        dataset_ids = list(db.scalars(select(LoraDataset.id).where(LoraDataset.character_id == character_id)))
        if dataset_ids:
            db.execute(delete(LoraDatasetItem).where(LoraDatasetItem.dataset_id.in_(dataset_ids)))
            db.execute(delete(LoraDataset).where(LoraDataset.id.in_(dataset_ids)))
        db.execute(delete(TrainingJob).where(TrainingJob.character_id == character_id))
        artifacts = list(
            db.scalars(
                select(CharacterLora.artifact_filename).where(CharacterLora.character_id == character_id)
            )
        )
        db.execute(delete(CharacterLora).where(CharacterLora.character_id == character_id))
        ids = list(db.scalars(select(Conversation.id).where(Conversation.character_id == character_id)))
        paths = purge_conversations(db, ids)
        paths += list(
            db.scalars(select(ImageLibrary.filename).where(ImageLibrary.character_id == character_id))
        )
        paths += list(db.scalars(select(VideoClip.filename).where(VideoClip.character_id == character_id)))
        paths += list(
            db.scalars(
                select(VideoClip.thumb_filename).where(
                    VideoClip.character_id == character_id, VideoClip.thumb_filename.is_not(None)
                )
            )
        )
        db.execute(delete(VideoClip).where(VideoClip.character_id == character_id))
        db.execute(delete(ImageLibrary).where(ImageLibrary.character_id == character_id))
        db.execute(delete(Memory).where(Memory.character_id == character_id))
        db.execute(delete(BenchmarkSample).where(BenchmarkSample.character_id == character_id))
        jobs = list(db.scalars(select(Job.id).where(Job.influencer_id == character_id)))
        paths += list(db.scalars(select(Asset.filename).where(Asset.job_id.in_(jobs))))
        if character.avatar_filename:
            paths.append(character.avatar_filename)
        db.execute(delete(Review).where(Review.job_id.in_(jobs)))
        db.execute(delete(Asset).where(Asset.job_id.in_(jobs)))
        db.execute(delete(Job).where(Job.id.in_(jobs)))
        db.execute(delete(BibleVersion).where(BibleVersion.influencer_id == character_id))
        db.delete(character)
    unlink_media(paths)
    for artifact in artifacts:
        if not artifact:
            continue
        path = (settings.lora_dir / artifact).resolve()
        if path.is_relative_to(settings.lora_dir.resolve()):
            path.unlink(missing_ok=True)
    return {"deleted": True, "id": character_id}


@router.post("/benchmarks", status_code=201)
def benchmark(body: BenchmarkInput):
    ensure_model(body.model)
    with Session() as db:
        character = required(db, Influencer, body.character_id)
        if body.fan_id:
            required(db, Fan, body.fan_id)
    profile = body.profile.model_dump() if body.profile else normalize_bible_profile(character.bible)
    fingerprint = profile_fingerprint(profile)
    with Session() as db:
        batch = list(
            db.scalars(
                select(BenchmarkSample)
                .where(BenchmarkSample.batch_id == body.batch_id)
                .order_by(BenchmarkSample.created_at, BenchmarkSample.id)
            )
        )
    if batch:
        first = batch[0]
        if (first.character_id, first.fan_id, first.prompt, first.metrics.get("temperature")) != (
            body.character_id,
            body.fan_id,
            body.prompt,
            body.temperature,
        ):
            raise HTTPException(
                409, "Un confronto deve mantenere personaggio, fan, messaggio e temperatura uguali"
            )
    # Every personality variant freezes its own context; models stay comparable within a variant.
    variant = next((s for s in batch if s.metrics.get("profile_hash") == fingerprint), None)
    if variant is not None:
        messages = variant.metrics["context_messages"]
        recalled = variant.metrics.get("recalled_memory_ids", [])
        character_version = variant.metrics["character_version"]
    else:
        conv = Conversation(
            id=identifier(),
            character_id=character.id,
            fan_id=body.fan_id,
            model=body.model,
            character_snapshot={
                "name": character.name,
                "profile": profile,
                "version": character.version,
            },
        )
        messages, recalled = build_context(conv, body.prompt, history=False)
        messages.append({"role": "user", "content": fan_message(body.prompt)})
        messages.append({"role": "system", "content": FAN_MESSAGE_REMINDER})
        character_version = character.version
    result, error, metrics = "", None, {}
    start = time.perf_counter()
    try:
        result, metrics = measured_chat(body.model, messages, body.temperature, "benchmark")
    except OllamaNotAvailable as exc:
        error = str(exc)
        metrics = {"request_seconds": time.perf_counter() - start}
    metrics.update(
        character_version=character_version,
        recalled_memory_ids=recalled,
        context_messages=messages,
        temperature=body.temperature,
        profile_hash=fingerprint,
        profile_label=body.label or ("Personalità salvata" if body.profile is None else "Variante"),
        profile_custom=body.profile is not None,
    )
    with Session.begin() as db:
        # Concurrent deletion must not recreate a removed character or fan.
        required(db, Influencer, body.character_id)
        if body.fan_id:
            required(db, Fan, body.fan_id)
        sample = BenchmarkSample(
            **body.model_dump(exclude={"temperature", "profile", "label"}),
            response=result,
            metrics=metrics,
            error=error,
        )
        db.add(sample)
        db.flush()
        return sample


@router.get("/benchmarks")
def list_benchmarks(batch_id: str | None = None):
    with Session() as db:
        query = select(BenchmarkSample).order_by(BenchmarkSample.created_at.desc()).limit(200)
        if batch_id:
            query = (
                select(BenchmarkSample)
                .where(BenchmarkSample.batch_id == batch_id)
                .order_by(BenchmarkSample.created_at)
            )
        return list(db.scalars(query))


@router.get("/metrics/models")
def model_metrics(character_id: str | None = None, fan_id: str | None = None):
    with Session() as db:
        query = select(ChatMessage).join(Conversation).where(ChatMessage.role == "assistant")
        if character_id:
            query = query.where(Conversation.character_id == character_id)
        if fan_id:
            query = query.where(Conversation.fan_id == fan_id)
        messages = list(db.scalars(query))
    groups = defaultdict(list)
    for message in messages:
        metrics = message.ollama_metrics or {}
        if metrics.get("request_seconds") is not None:
            groups[message.model].append(metrics)
    return [
        {
            "model": model,
            "samples": len(rows),
            "mean_seconds": mean(r["request_seconds"] for r in rows),
            "median_seconds": median(r["request_seconds"] for r in rows),
            "mean_load_seconds": mean((r.get("load_duration") or 0) / 1e9 for r in rows),
        }
        for model, rows in groups.items()
    ]
