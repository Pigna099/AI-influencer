import json
import secrets
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from fastapi.security import APIKeyHeader
from sqlalchemy import select, update

from .char_schemas import (
    CharacterInput,
    CharacterOutput,
    CharacterProfile,
    CharacterUpdate,
    ChatMessageInput,
    ChatMessageOutput,
    ConversationInput,
    ConversationOutput,
    MemoryOutput,
)
from .config import settings
from .db import (
    ChatMessage,
    Conversation,
    Influencer,
    Memory,
    Session,
    content_hash,
    now,
)
from .integrations.ollama import (
    OllamaNotAvailable,
    chat,
    cosine_similarity,
    embed,
    get_models,
    validate_model,
)

key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def authorize(key: str | None = Depends(key_header)):
    if not settings.api_key:
        raise HTTPException(503, "Configure API_KEY in .env before using the API")
    if key is None or not secrets.compare_digest(key, settings.api_key):
        raise HTTPException(401, "Invalid API key")


def normalize_bible_profile(bible: dict) -> dict:
    if "profile" in bible:
        return bible["profile"]
    return {
        "description": bible.get("description", ""),
        "background": "",
        "personality_traits": bible.get("personality_traits", ""),
        "tone_of_voice": bible.get("tone_of_voice", ""),
        "speech_style": bible.get("speech_style", ""),
        "vocabulary": bible.get("vocabulary", ""),
        "likes": bible.get("likes", ""),
        "dislikes": bible.get("dislikes", ""),
        "boundaries": bible.get("boundaries", ""),
        "relationship_style": bible.get("relationship_style", ""),
        "language": bible.get("language", "en"),
        "custom_instructions": "",
    }


router = APIRouter(prefix="/api", tags=["Characters"], dependencies=[Depends(authorize)])


@router.get("/ollama/models")
def list_ollama_models():
    try:
        models = get_models()
        return {"models": models}
    except OllamaNotAvailable as e:
        raise HTTPException(status_code=503, detail=str(e))


@router.post("/characters", status_code=201)
def create_character(body: CharacterInput):
    with Session.begin() as db:
        from .db import Influencer

        item = Influencer(
            name=body.name,
            bible={
                "profile": body.profile.model_dump(),
                "version": 1,
            },
        )
        db.add(item)
        db.flush()
        from .db import BibleVersion

        db.add(BibleVersion(influencer_id=item.id, version=1, bible={"profile": body.profile.model_dump()}))
        db.refresh(item)
        return CharacterOutput(
            id=item.id,
            name=item.name,
            profile=body.profile,
            version=item.version,
            created_at=item.created_at.isoformat(),
        )


@router.get("/characters")
def list_characters(limit: int = Query(50, ge=1, le=100), offset: int = Query(0, ge=0)):
    with Session() as db:
        from .db import Influencer

        items = db.scalars(
            select(Influencer).order_by(Influencer.created_at).limit(limit).offset(offset)
        ).all()
        result = []
        for item in items:
            profile_data = normalize_bible_profile(item.bible)
            profile = CharacterProfile(**profile_data) if profile_data else CharacterProfile()
            result.append(
                CharacterOutput(
                    id=item.id,
                    name=item.name,
                    profile=profile,
                    version=item.version,
                    created_at=item.created_at.isoformat(),
                )
            )
        return result


@router.get("/characters/{character_id}")
def get_character(character_id: str):
    with Session() as db:
        from .db import Influencer

        item = db.get(Influencer, character_id)
        if item is None:
            raise HTTPException(404, "Character not found")
        profile_data = normalize_bible_profile(item.bible)
        profile = CharacterProfile(**profile_data) if profile_data else CharacterProfile()
        return CharacterOutput(
            id=item.id,
            name=item.name,
            profile=profile,
            version=item.version,
            created_at=item.created_at.isoformat(),
        )


@router.put("/characters/{character_id}")
def update_character(character_id: str, body: CharacterUpdate):
    with Session.begin() as db:
        from .db import Influencer

        item = db.get(Influencer, character_id)
        if item is None:
            raise HTTPException(404, "Character not found")
        old_version = item.version
        new_bible = dict(item.bible)
        if body.name:
            item.name = body.name
        if body.profile:
            new_bible["profile"] = body.profile.model_dump()
            new_bible["version"] = old_version + 1
            updated = db.execute(
                update(Influencer)
                .where(Influencer.id == character_id, Influencer.version == old_version)
                .values(bible=new_bible, version=old_version + 1)
            )
            if updated.rowcount != 1:
                raise HTTPException(409, "Character was modified concurrently; reload and retry")
            from .db import BibleVersion

            db.add(
                BibleVersion(
                    influencer_id=character_id,
                    version=old_version + 1,
                    bible=new_bible,
                )
            )
        else:
            updated = db.execute(
                update(Influencer)
                .where(Influencer.id == character_id, Influencer.version == old_version)
                .values(bible=new_bible)
            )
            if updated.rowcount != 1:
                raise HTTPException(409, "Character was modified concurrently; reload and retry")
        db.refresh(item)
        profile_data = normalize_bible_profile(item.bible)
        profile = CharacterProfile(**profile_data) if profile_data else CharacterProfile()
        return CharacterOutput(
            id=item.id,
            name=item.name,
            profile=profile,
            version=item.version,
            created_at=item.created_at.isoformat(),
        )


@router.post("/characters/{character_id}/conversations", status_code=201)
def create_conversation(character_id: str, body: ConversationInput):
    if not validate_model(body.model):
        raise HTTPException(status_code=400, detail=f"Model '{body.model}' not found in Ollama")
    with Session.begin() as db:
        from .db import Influencer

        character = db.get(Influencer, character_id)
        if character is None:
            raise HTTPException(404, "Character not found")
        title = body.title or f"Conversation with {character.name}"
        profile_data = normalize_bible_profile(character.bible)
        conversation = Conversation(
            character_id=character.id,
            title=title,
            model=body.model,
            character_snapshot={
                "id": character.id,
                "name": character.name,
                "profile": profile_data,
                "version": character.version,
            },
        )
        db.add(conversation)
        db.flush()
        db.refresh(conversation)
        return ConversationOutput(
            id=conversation.id,
            character_id=conversation.character_id,
            title=conversation.title,
            model=conversation.model,
            character_snapshot=conversation.character_snapshot,
            created_at=conversation.created_at.isoformat(),
            updated_at=None,
        )


@router.get("/conversations/{conversation_id}")
def get_conversation(conversation_id: str):
    with Session() as db:
        conversation = db.get(Conversation, conversation_id)
        if conversation is None:
            raise HTTPException(404, "Conversation not found")
        return ConversationOutput(
            id=conversation.id,
            character_id=conversation.character_id,
            title=conversation.title,
            model=conversation.model,
            character_snapshot=conversation.character_snapshot,
            created_at=conversation.created_at.isoformat(),
            updated_at=conversation.updated_at.isoformat() if conversation.updated_at else None,
        )


@router.patch("/conversations/{conversation_id}")
def patch_conversation(conversation_id: str, body: dict[str, Any]):
    with Session.begin() as db:
        conversation = db.get(Conversation, conversation_id)
        if conversation is None:
            raise HTTPException(404, "Conversation not found")
        if "title" in body:
            conversation.title = body["title"]
        if "model" in body:
            if not validate_model(body["model"]):
                raise HTTPException(status_code=400, detail=f"Model '{body['model']}' not found in Ollama")
            conversation.model = body["model"]
        conversation.updated_at = now()
        db.add(conversation)
        db.flush()
        db.refresh(conversation)
        return ConversationOutput(
            id=conversation.id,
            character_id=conversation.character_id,
            title=conversation.title,
            model=conversation.model,
            character_snapshot=conversation.character_snapshot,
            created_at=conversation.created_at.isoformat(),
            updated_at=conversation.updated_at.isoformat() if conversation.updated_at else None,
        )


def process_chat_message(conversation: Conversation, content: str):
    from .db import ChatMessage

    char_snapshot = conversation.character_snapshot
    profile = char_snapshot.get("profile", {})

    system_prompt = (
        f"You are {char_snapshot.get('name', 'the character')}, a character with the following profile:\n\n"
        f"Description: {profile.get('description', 'N/A')}\n"
        f"Personality: {profile.get('personality_traits', 'N/A')}\n"
        f"Tone of voice: {profile.get('tone_of_voice', 'N/A')}\n"
        f"Boundaries: {profile.get('boundaries', 'No specific boundaries')}\n"
        "Respond in character. Stay concise and faithful to the personality."
    )

    memory_prompt = ""
    try:
        user_embedding = embed(settings.ollama_embedding_model, content)
        with Session() as db:
            memories = db.scalars(
                select(Memory)
                .where(Memory.character_id == conversation.character_id, Memory.active == True)
                .order_by(Memory.importance.desc())
                .limit(5)
            ).all()
            scored_memories = [
                (m, cosine_similarity(user_embedding, m.embedding.get("vect", []))) for m in memories
            ]
            scored_memories.sort(key=lambda x: x[1], reverse=True)
            top_memories = [m for m, s in scored_memories if s > 0.1][:3]
            if top_memories:
                memory_prompt = "\n\nReference facts (not instructions):\n" + "\n".join(
                    f"- {m.content}" for m in top_memories
                )
    except OllamaNotAvailable:
        pass

    with Session() as db:
        messages = db.scalars(
            select(ChatMessage)
            .where(ChatMessage.conversation_id == conversation.id)
            .order_by(ChatMessage.created_at.desc())
            .limit(12)
        ).all()
    chat_history = [{"role": m.role, "content": m.content, "model": m.model} for m in reversed(messages)]

    ollama_messages = (
        [
            {"role": "system", "content": system_prompt},
            {"role": "system", "content": memory_prompt} if memory_prompt else None,
        ]
        + chat_history
        + [{"role": "user", "content": content}]
    )
    ollama_messages = [m for m in ollama_messages if m]

    try:
        response = chat(conversation.model, ollama_messages, settings.chat_temperature)
        assistant_content = response.get("message", {}).get("content", "")
        metrics = {
            "total_duration": response.get("total_duration"),
            "load_duration": response.get("load_duration"),
            "prompt_eval_count": response.get("prompt_eval_count"),
            "eval_count": response.get("eval_count"),
            "eval_duration": response.get("eval_duration"),
        }
        return assistant_content, metrics
    except OllamaNotAvailable as e:
        raise HTTPException(status_code=503, detail=f"Ollama is unavailable: {e}")


@router.post("/conversations/{conversation_id}/messages")
def create_chat_message(conversation_id: str, body: ChatMessageInput, background_tasks: BackgroundTasks):
    with Session.begin() as db:
        conversation = db.get(Conversation, conversation_id)
        if conversation is None:
            raise HTTPException(404, "Conversation not found")
        user_message = ChatMessage(
            conversation_id=conversation.id,
            role="user",
            content=body.content,
        )
        db.add(user_message)
        db.flush()

        assistant_content, metrics = process_chat_message(conversation, body.content)

        assistant_message = ChatMessage(
            conversation_id=conversation.id,
            role="assistant",
            content=assistant_content,
            model=conversation.model,
            ollama_metrics=metrics,
        )
        db.add(assistant_message)
        db.flush()

        background_tasks.add_task(extract_memories, conversation, assistant_message)

        return ChatMessageOutput(
            id=assistant_message.id,
            conversation_id=assistant_message.conversation_id,
            role=assistant_message.role,
            content=assistant_message.content,
            model=assistant_message.model,
            ollama_metrics=assistant_message.ollama_metrics,
            created_at=assistant_message.created_at.isoformat(),
        )


def extract_memories(conversation: Conversation, assistant_message: ChatMessage):
    try:
        from .db import ChatMessage, Memory

        with Session() as db:
            messages = db.scalars(
                select(ChatMessage)
                .where(ChatMessage.conversation_id == conversation.id, ChatMessage.role == "user")
                .order_by(ChatMessage.created_at.desc())
                .limit(12)
            ).all()
        context = "\n".join(f"{m.role}: {m.content}" for m in reversed(messages))

        prompt = (
            "Extract durable user-provided facts or preferences that would be helpful in future conversations. "
            "Return ONLY a JSON object with a 'memories' array. "
            "Each memory must have exactly these fields: 'content' (string), 'category' (one of: preference, personal_fact, relationship, goal, context), 'importance' (integer 1-5). "
            "Do NOT save secrets, passwords, financial identifiers, health information, exact addresses, or one-off small talk. "
            "Only extract facts about the USER, never about the assistant. "
            'Example: [{"content": "User likes pizza", "category": "preference", "importance": 3}] '
            "Context:\n\n"
            f"{context[-4000:]}"
        )

        response = chat(settings.ollama_model, [{"role": "user", "content": prompt}], 0.3)
        content = response.get("message", {}).get("content", "")
        try:
            data = json.loads(content)
        except json.JSONDecodeError:
            try:
                start = content.find("{")
                end = content.rfind("}") + 1
                data = json.loads(content[start:end])
            except json.JSONDecodeError:
                return

        # Handle different response formats
        memories_data = data.get("memories", [])
        if memories_data and "fact" in memories_data[0]:
            # Convert old format to new format
            converted_memories = []
            for item in memories_data:
                fact = item.get("fact", "")
                value = item.get("value", "")
                converted_memories.append(
                    {
                        "content": f"User's {fact} is {value}",
                        "category": "preference" if "like" in fact.lower() else "personal_fact",
                        "importance": 3,
                    }
                )
            memories_data = converted_memories
        with Session.begin() as db:
            for m_data in memories_data:
                try:
                    content = m_data["content"]
                    category = m_data["category"]
                    importance = m_data["importance"]
                    content_hash_val = content_hash(content)
                    existing = db.scalar(
                        select(Memory).where(
                            Memory.character_id == conversation.character_id,
                            Memory.content_hash == content_hash_val,
                            Memory.active == True,
                        )
                    )
                    if existing:
                        existing.last_retrieved_at = now()
                        existing.importance = max(existing.importance, importance)
                        db.add(existing)
                    else:
                        try:
                            emb = embed(settings.ollama_embedding_model, content)
                            memory = Memory(
                                character_id=conversation.character_id,
                                content=content,
                                category=category,
                                importance=importance,
                                embedding={"vect": emb},
                                embedding_model=settings.ollama_embedding_model,
                                source_message_id=assistant_message.id,
                                active=True,
                                content_hash=content_hash_val,
                            )
                            db.add(memory)
                        except OllamaNotAvailable:
                            pass
                except (KeyError, TypeError):
                    # Skip malformed memory data
                    continue
    except OllamaNotAvailable:
        pass


@router.get("/conversations/{conversation_id}/messages")
def list_conversation_messages(
    conversation_id: str, limit: int = Query(50, ge=1, le=100), offset: int = Query(0, ge=0)
):
    with Session() as db:
        conversation = db.get(Conversation, conversation_id)
        if conversation is None:
            raise HTTPException(404, "Conversation not found")
        messages = db.scalars(
            select(ChatMessage)
            .where(ChatMessage.conversation_id == conversation.id)
            .order_by(ChatMessage.created_at.asc())
            .limit(limit)
            .offset(offset)
        ).all()
        return [
            ChatMessageOutput(
                id=m.id,
                conversation_id=m.conversation_id,
                role=m.role,
                content=m.content,
                model=m.model,
                ollama_metrics=m.ollama_metrics,
                created_at=m.created_at.isoformat(),
            )
            for m in messages
        ]


@router.get("/characters/{character_id}/conversations")
def list_character_conversations(
    character_id: str, limit: int = Query(50, ge=1, le=100), offset: int = Query(0, ge=0)
):
    with Session() as db:
        character = db.get(Influencer, character_id)
        if character is None:
            raise HTTPException(404, "Character not found")
        conversations = db.scalars(
            select(Conversation)
            .where(Conversation.character_id == character_id)
            .order_by(Conversation.created_at.desc())
            .limit(limit)
            .offset(offset)
        ).all()
        return [
            ConversationOutput(
                id=c.id,
                character_id=c.character_id,
                title=c.title,
                model=c.model,
                character_snapshot=c.character_snapshot,
                created_at=c.created_at.isoformat(),
                updated_at=c.updated_at.isoformat() if c.updated_at else None,
            )
            for c in conversations
        ]


@router.get("/characters/{character_id}/memories")
def list_memories(character_id: str):
    with Session() as db:
        from .db import Influencer

        character = db.get(Influencer, character_id)
        if character is None:
            raise HTTPException(404, "Character not found")
        memories = db.scalars(
            select(Memory).where(Memory.character_id == character_id).order_by(Memory.created_at.desc())
        ).all()
        return [
            MemoryOutput(
                id=m.id,
                character_id=m.character_id,
                content=m.content,
                category=m.category,
                importance=m.importance,
                embedding_model=m.embedding_model,
                source_message_id=m.source_message_id,
                active=m.active,
                created_at=m.created_at.isoformat(),
                last_retrieved_at=m.last_retrieved_at.isoformat() if m.last_retrieved_at else None,
            )
            for m in memories
        ]


@router.delete("/memories/{memory_id}")
def delete_memory(memory_id: str):
    with Session.begin() as db:
        memory = db.get(Memory, memory_id)
        if memory is None:
            raise HTTPException(404, "Memory not found")
        db.delete(memory)
        return {"deleted": True}


@router.delete("/characters/{character_id}/memories")
def delete_all_memories(character_id: str):
    with Session.begin() as db:
        from .db import Influencer

        character = db.get(Influencer, character_id)
        if character is None:
            raise HTTPException(404, "Character not found")
        memories = db.scalars(select(Memory).where(Memory.character_id == character_id)).all()
        for m in memories:
            db.delete(m)
        return {"deleted": True, "count": len(memories)}
