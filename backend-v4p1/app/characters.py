"""Playground API. Legacy content routes remain in main.py."""

import hashlib
import json
import logging
import random
import re
import time
from collections import defaultdict
from datetime import timedelta
from statistics import mean, median

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from fastapi.responses import FileResponse, Response
from pydantic import ValidationError
from sqlalchemy import delete, func, or_, select, update

from .auth import authorize
from .char_schemas import (
    BenchmarkInput,
    CharacterClone,
    CharacterInput,
    CharacterOutput,
    CharacterProfile,
    CharacterUpdate,
    ChatMessageInput,
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
    build_negative_prompt,
    build_prompt_from_profile,
    build_scene_prompt,
    checkpoint_family,
    extract_memories,
    fan_message,
    generate_reply,
    measured_chat,
    translate_scene,
)
from .config import settings
from .db import (
    Asset,
    BenchmarkSample,
    BibleVersion,
    ChatImage,
    ChatMessage,
    Conversation,
    Fan,
    ImageLibrary,
    Influencer,
    Job,
    Memory,
    Review,
    ScheduledReply,
    Session,
    SimulatedPayment,
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
)
from .integrations.gpu import gpu_status
from .integrations.ollama import OllamaNotAvailable, chat, get_models, validate_model
from .scheduler import pending_for_conversation, schedule_reply

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["Playground"], dependencies=[Depends(authorize)])


def required(db, model, item_id):
    item = db.get(model, item_id)
    if item is None:
        raise HTTPException(404, "Elemento non trovato")
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


def messages_out(db, rows):
    images = defaultdict(list)
    if rows:
        for item in db.scalars(select(ChatImage).where(ChatImage.message_id.in_([row.id for row in rows]))):
            images[item.message_id].append(image_out(item))
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
        }
        for row in rows
    ]


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
            raise HTTPException(400, "Seleziona un modello installato capace di generare chat")
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
    return {"available": comfyui_available(), "loras": get_loras()}


@router.get("/system/gpus")
def system_gpus():
    return gpu_status()


def library_query(character_id: str, status: str | None, style: str | None):
    query = select(ImageLibrary).where(ImageLibrary.character_id == character_id)
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
    limit: int = Query(60, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    with Session() as db:
        required(db, Influencer, character_id)
        items = db.scalars(
            library_query(character_id, status, style)
            .order_by(ImageLibrary.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return [library_out(item) for item in items]


@router.post("/characters/{character_id}/library/generate", status_code=201)
def generate_library_images(character_id: str, body: LibraryGenerateInput):
    """Generate a batch for the image playground and store it as draft."""
    if not comfyui_available():
        raise HTTPException(503, "ComfyUI non è raggiungibile: avvia il servizio immagini")
    with Session() as db:
        character = required(db, Influencer, character_id)
        name = character.name
        profile = normalize_bible_profile(character.bible)
        avatar = character.avatar_filename
        checkpoint = body.checkpoint or character.image_checkpoint
        style = body.style or character.image_style or "real"
    family = checkpoint_family(style, checkpoint)
    if body.loras:
        available = get_loras()
        if available and any(lora.name not in available for lora in body.loras):
            raise HTTPException(400, "Uno o più LoRA non sono installati in ComfyUI")
    reference = (settings.media_dir / avatar) if avatar else None
    scene = translate_scene(body.prompt, style)
    prompt = build_prompt_from_profile(name, profile, scene, style, family)
    negative = body.negative or build_negative_prompt(family)
    loras = [lora.model_dump() for lora in body.loras]
    batch_max = max(1, settings.image_library_batch_max)
    created = []
    for index in range(min(body.count, batch_max)):
        seed = (body.seed + index) if body.seed is not None else random.randrange(2**31)
        try:
            data, meta = generate_image(
                prompt,
                negative,
                seed=seed,
                reference_path=reference,
                checkpoint=checkpoint,
                style=style,
                family=family,
                loras=loras,
            )
        except ComfyUIError as error:
            if created:
                break
            raise HTTPException(502, f"Generazione foto non riuscita: {error}") from error
        settings.media_dir.mkdir(parents=True, exist_ok=True)
        filename = f"{identifier()}.png"
        try:
            (settings.media_dir / filename).write_bytes(data)
        except OSError as error:
            raise HTTPException(500, "Impossibile salvare la foto") from error
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
            )
            db.add(item)
            db.flush()
            created.append(library_out(item))
    return created


@router.get("/library/{item_id}")
def get_library_item(item_id: str):
    with Session() as db:
        return library_out(required(db, ImageLibrary, item_id))


@router.get("/library/{item_id}/file")
def download_library_image(item_id: str):
    with Session() as db:
        item = required(db, ImageLibrary, item_id)
        filename = item.filename
    path = (settings.media_dir / filename).resolve()
    if not path.is_relative_to(settings.media_dir.resolve()) or not path.is_file():
        raise HTTPException(404, "Immagine non disponibile")
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
        if body.caption is not None or body.tags is not None:
            embedding, embedding_model = embed_library_text(library_text(item))
            item.embedding = embedding
            item.embedding_model = embedding_model
        return library_out(item)


@router.delete("/library/{item_id}")
def delete_library_item(item_id: str):
    with Session.begin() as db:
        item = required(db, ImageLibrary, item_id)
        filename = item.filename
        db.delete(item)
    unlink_media([filename])
    return {"deleted": True}


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


@router.post("/characters", status_code=201)
def create_character(body: CharacterInput):
    with Session.begin() as db:
        item = Influencer(name=body.name, bible={"profile": body.profile.model_dump()})
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
            .values(name=body.name or item.name, bible=bible, version=version)
        )
        if changed.rowcount != 1:
            raise HTTPException(409, "Il personaggio è stato modificato: ricarica la pagina")
        db.add(BibleVersion(influencer_id=item.id, version=version, bible=bible))
        db.refresh(item)
        return character_out(item)


@router.post("/characters/{character_id}/avatar", status_code=201)
def generate_avatar(character_id: str):
    """Generate and remember the character's profile picture (adult, NSFW style)."""
    if not comfyui_available():
        raise HTTPException(503, "ComfyUI non è raggiungibile: avvia il servizio immagini")
    with Session() as db:
        character = required(db, Influencer, character_id)
        name = character.name
        profile = normalize_bible_profile(character.bible)
        old_avatar = character.avatar_filename
        checkpoint = character.image_checkpoint
        style = character.image_style or "real"
        family = checkpoint_family(style, checkpoint)
    appearance = (profile.get("appearance") or profile.get("description") or "").strip()
    profile = {**profile, "appearance": translate_scene(appearance, style)}
    prompt = build_avatar_prompt(name, profile, style, family)
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
        raise HTTPException(502, f"Generazione immagine profilo non riuscita: {error}") from error
    settings.media_dir.mkdir(parents=True, exist_ok=True)
    filename = f"{identifier()}.png"
    try:
        (settings.media_dir / filename).write_bytes(data)
    except OSError as error:
        raise HTTPException(500, "Impossibile salvare l'immagine profilo") from error
    with Session.begin() as db:
        item = required(db, Influencer, character_id)
        old = item.avatar_filename
        item.avatar_filename = filename
        db.flush()
        result = character_out(item)
    unlink_media([old] if old else [])
    return result


@router.put("/characters/{character_id}/image-checkpoint")
def set_image_checkpoint(character_id: str, body: ImageCheckpointInput):
    if body.checkpoint:
        checkpoints = get_checkpoints()
        if checkpoints and body.checkpoint not in [item["name"] for item in checkpoints]:
            raise HTTPException(400, "Checkpoint non installato in ComfyUI")
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
        raise HTTPException(404, "Immagine profilo non disponibile")
    path = (settings.media_dir / filename).resolve()
    if not path.is_relative_to(settings.media_dir.resolve()) or not path.is_file():
        raise HTTPException(404, "Immagine profilo non disponibile")
    return FileResponse(path, media_type="image/png", filename=filename)


@router.get("/chat-images/{image_id}/file")
def download_chat_image(image_id: str):
    with Session() as db:
        item = required(db, ChatImage, image_id)
        filename, media_type = item.filename, item.media_type
        locked = item.price_cents > 0 and item.unlocked_at is None
    path = (settings.media_dir / filename).resolve()
    if not path.is_relative_to(settings.media_dir.resolve()) or not path.is_file():
        raise HTTPException(404, "Immagine non disponibile")
    if locked:
        try:
            return Response(content=blurred_png(path.read_bytes()), media_type="image/png")
        except OSError as error:
            raise HTTPException(404, "Immagine non disponibile") from error
    return FileResponse(path, media_type=media_type, filename=filename)


@router.post("/chat-images/{image_id}/unlock")
def unlock_chat_image(image_id: str):
    """Simulated PPV unlock: records a fake payment, no real transaction."""
    with Session.begin() as db:
        item = required(db, ChatImage, image_id)
        if item.price_cents <= 0:
            raise HTTPException(409, "Questa immagine non è a pagamento")
        if item.unlocked_at is not None:
            raise HTTPException(409, "Immagine già sbloccata")
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
        name = body.name if body and body.name else f"{source.name} (copia)"
        item = Influencer(name=name[:120], bible={"profile": profile})
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
            502, "Il modello non ha restituito una descrizione valida. Prova un altro modello."
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
        raise HTTPException(409, "Una risposta è in corso. Attendi prima di modificare o eliminare la chat.")


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
            raise HTTPException(409, "Il personaggio sta già rispondendo in questa conversazione")
        conv = required(db, Conversation, conversation_id)
    try:
        answer, metrics = generate_reply(conv, content or "", kind, absence_hours)
        image_data, image_meta, image_prompt, image_negative, filename = None, None, None, None, None
        reused_item = None
        draft_embedding, draft_embedding_model = [], ""
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
                ppv_enabled = bool(character.ppv_enabled) if character else False
                ppv_price = character.ppv_price_cents if character else 0
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
        with Session.begin() as db:
            current = required(db, Conversation, conversation_id)
            if content is not None and store_user:
                user = ChatMessage(conversation_id=conv.id, role="user", content=content)
                db.add(user)
                db.flush()
                current.memory_status = "pending"
            assistant = ChatMessage(
                conversation_id=conv.id,
                role="assistant",
                content=answer,
                model=conv.model,
                ollama_metrics=metrics,
            )
            db.add(assistant)
            current.updated_at = now()
            db.flush()
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
            return messages_out(db, [assistant])[0]
    except OllamaNotAvailable as error:
        raise HTTPException(503, str(error)) from error
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
    return run_turn(conversation_id, content=body.content, background_tasks=background_tasks)


def schedule_turn(conversation_id: str, content: str, background_tasks):
    """Realistic mode: store the fan message now, deliver the reply after a delay."""
    with Session() as db:
        conversation = required(db, Conversation, conversation_id)
        character = required(db, Influencer, conversation.character_id)
        immediate = not settings.chat_scheduling_enabled or (character.reply_delay_max_seconds or 0) <= 0
    if immediate:
        reply = run_turn(conversation_id, content=content, background_tasks=background_tasks)
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
        raise HTTPException(409, "Le foto in chat sono disattivate")
    if not comfyui_available():
        raise HTTPException(503, "ComfyUI non è raggiungibile: avvia il servizio immagini")
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
            raise HTTPException(409, "Il personaggio sta già rispondendo in questa conversazione")
        conv = required(db, Conversation, conversation_id)
        character = required(db, Influencer, conv.character_id)
        reference = settings.media_dir / character.avatar_filename if character.avatar_filename else None
        checkpoint = character.image_checkpoint
        style = character.image_style or "real"
        family = checkpoint_family(style, checkpoint)
        locked_price = 0
        if body.locked and settings.ppv_enabled:
            locked_price = body.price_cents or character.ppv_price_cents or 500
        chosen = required(db, ImageLibrary, body.library_id) if body.library_id else None
        if chosen is not None and chosen.character_id != conv.character_id:
            raise HTTPException(404, "Immagine non disponibile")
    try:
        if chosen is not None:
            source = (settings.media_dir / chosen.filename).resolve()
            if not source.is_file() or not source.is_relative_to(settings.media_dir.resolve()):
                raise HTTPException(404, "Immagine non disponibile")
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
                raise HTTPException(502, f"Generazione foto non riuscita: {error}") from error
            seconds = time.perf_counter() - image_start
        settings.media_dir.mkdir(parents=True, exist_ok=True)
        filename = f"{identifier()}.png"
        try:
            (settings.media_dir / filename).write_bytes(image_data)
        except OSError as error:
            raise HTTPException(500, "Impossibile salvare la foto") from error
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
            raise HTTPException(409, "Il personaggio ha generazioni in corso")
        ids = list(db.scalars(select(Conversation.id).where(Conversation.character_id == character_id)))
        paths = purge_conversations(db, ids)
        paths += list(
            db.scalars(select(ImageLibrary.filename).where(ImageLibrary.character_id == character_id))
        )
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
