"""Playground API. Legacy content routes remain in main.py."""

import time
from collections import defaultdict
from datetime import timedelta
from statistics import mean, median

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from pydantic import ValidationError
from sqlalchemy import delete, or_, select, update

from .auth import authorize
from .char_schemas import (
    BenchmarkInput,
    CharacterInput,
    CharacterOutput,
    CharacterProfile,
    CharacterUpdate,
    ChatMessageInput,
    ConversationInput,
    ConversationPatch,
    EnhanceInput,
    FanInput,
    InitiateInput,
    MemoryInput,
)
from .chat_service import build_context, extract_memories, generate_reply, measured_chat
from .config import settings
from .db import (
    Asset,
    BenchmarkSample,
    BibleVersion,
    ChatMessage,
    Conversation,
    Fan,
    Influencer,
    Job,
    Memory,
    Review,
    Session,
    content_hash,
    identifier,
    now,
)
from .integrations.ollama import OllamaNotAvailable, chat, get_models, validate_model

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
        created_at=item.created_at.isoformat(),
    )


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
    db.execute(delete(ChatMessage).where(ChatMessage.conversation_id.in_(ids)))
    db.execute(delete(Conversation).where(Conversation.id.in_(ids)))


@router.delete("/fans/{fan_id}")
def delete_fan(fan_id: str):
    with Session.begin() as db:
        fan = required(db, Fan, fan_id)
        check_busy(db, select(Conversation.id).where(Conversation.fan_id == fan_id))
        ids = list(db.scalars(select(Conversation.id).where(Conversation.fan_id == fan_id)))
        purge_conversations(db, ids)
        db.execute(delete(Memory).where(Memory.fan_id == fan_id))
        db.execute(delete(BenchmarkSample).where(BenchmarkSample.fan_id == fan_id))
        db.delete(fan)
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
                return {
                    **{col.name: getattr(conv, col.name) for col in Conversation.__table__.columns},
                    "greeting_error": error.detail,
                }
    with Session() as db:
        return required(db, Conversation, conv.id)


@router.get("/conversations/{conversation_id}")
def get_conversation(conversation_id: str):
    with Session() as db:
        return required(db, Conversation, conversation_id)


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
        conv.updated_at = now()
        return conv


def run_turn(conversation_id, *, content=None, kind="reply", absence_hours=48, background_tasks=None):
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
        with Session.begin() as db:
            current = required(db, Conversation, conversation_id)
            if content is not None:
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
            if content is not None and background_tasks is not None:
                background_tasks.add_task(extract_memories, conv.id, user.id)
        return assistant
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
    return run_turn(conversation_id, content=body.content, background_tasks=background_tasks)


@router.post("/conversations/{conversation_id}/initiate")
def initiate(conversation_id: str, body: InitiateInput):
    return run_turn(conversation_id, kind=body.kind, absence_hours=body.absence_hours)


@router.get("/conversations/{conversation_id}/messages")
def list_conversation_messages(
    conversation_id: str, limit: int = Query(100, ge=1, le=500), offset: int = Query(0, ge=0)
):
    with Session() as db:
        required(db, Conversation, conversation_id)
        return list(
            db.scalars(
                select(ChatMessage)
                .where(ChatMessage.conversation_id == conversation_id)
                .order_by(ChatMessage.created_at, ChatMessage.id)
                .limit(limit)
                .offset(offset)
            )
        )


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
        return list(db.scalars(query.order_by(Conversation.created_at.desc()).limit(limit).offset(offset)))


@router.delete("/conversations/{conversation_id}")
def delete_conversation(conversation_id: str):
    with Session.begin() as db:
        required(db, Conversation, conversation_id)
        check_busy(db, select(Conversation.id).where(Conversation.id == conversation_id))
        purge_conversations(db, [conversation_id])
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
        purge_conversations(db, ids)
        db.execute(delete(Memory).where(Memory.character_id == character_id))
        db.execute(delete(BenchmarkSample).where(BenchmarkSample.character_id == character_id))
        jobs = list(db.scalars(select(Job.id).where(Job.influencer_id == character_id)))
        paths = list(db.scalars(select(Asset.filename).where(Asset.job_id.in_(jobs))))
        db.execute(delete(Review).where(Review.job_id.in_(jobs)))
        db.execute(delete(Asset).where(Asset.job_id.in_(jobs)))
        db.execute(delete(Job).where(Job.id.in_(jobs)))
        db.execute(delete(BibleVersion).where(BibleVersion.influencer_id == character_id))
        db.delete(character)
    for filename in paths:
        path = (settings.media_dir / filename).resolve()
        if path.is_relative_to(settings.media_dir.resolve()):
            path.unlink(missing_ok=True)
    return {"deleted": True, "id": character_id}


@router.post("/benchmarks", status_code=201)
def benchmark(body: BenchmarkInput):
    ensure_model(body.model)
    with Session() as db:
        character = required(db, Influencer, body.character_id)
        if body.fan_id:
            required(db, Fan, body.fan_id)
        conv = Conversation(
            id=identifier(),
            character_id=character.id,
            fan_id=body.fan_id,
            model=body.model,
            character_snapshot={
                "name": character.name,
                "profile": normalize_bible_profile(character.bible),
                "version": character.version,
            },
        )
    with Session() as db:
        first = db.scalar(
            select(BenchmarkSample)
            .where(BenchmarkSample.batch_id == body.batch_id)
            .order_by(BenchmarkSample.created_at)
            .limit(1)
        )
    if first is not None:
        if (first.character_id, first.fan_id, first.prompt, first.metrics.get("temperature")) != (
            body.character_id,
            body.fan_id,
            body.prompt,
            body.temperature,
        ):
            raise HTTPException(
                409, "Un confronto deve mantenere personaggio, fan, messaggio e temperatura uguali"
            )
        messages = first.metrics["context_messages"]
        recalled = first.metrics.get("recalled_memory_ids", [])
        character_version = first.metrics["character_version"]
    else:
        messages, recalled = build_context(conv, body.prompt, history=False)
        messages.append({"role": "user", "content": body.prompt})
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
    )
    with Session.begin() as db:
        # Concurrent deletion must not recreate a removed character or fan.
        required(db, Influencer, body.character_id)
        if body.fan_id:
            required(db, Fan, body.fan_id)
        sample = BenchmarkSample(
            **body.model_dump(exclude={"temperature"}), response=result, metrics=metrics, error=error
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
