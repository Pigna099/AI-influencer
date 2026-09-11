from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class CharacterProfile(StrictModel):
    description: str = Field(min_length=1, max_length=5000)
    background: str = Field(default="", max_length=5000)
    personality_traits: str = Field(default="", max_length=2000)
    tone_of_voice: str = Field(default="cordiale", max_length=1000)
    speech_style: str = Field(default="", max_length=1000)
    vocabulary: str = Field(default="", max_length=1000)
    likes: str = Field(default="", max_length=2000)
    dislikes: str = Field(default="", max_length=2000)
    boundaries: str = Field(default="", max_length=2000)
    relationship_style: str = Field(default="", max_length=1000)
    language: str = Field(default="en", max_length=10)
    custom_instructions: str = Field(default="", max_length=5000)


class CharacterInput(StrictModel):
    name: str = Field(min_length=1, max_length=120)
    profile: CharacterProfile


class CharacterOutput(StrictModel):
    id: str
    name: str
    profile: CharacterProfile
    version: int
    created_at: str


class CharacterUpdate(StrictModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    profile: CharacterProfile | None = None


class ConversationInput(StrictModel):
    title: str | None = Field(default=None, max_length=200)
    model: str = Field(min_length=1, max_length=120)


class ConversationOutput(StrictModel):
    id: str
    character_id: str
    title: str
    model: str
    character_snapshot: dict
    created_at: str
    updated_at: str | None = None


class ChatMessageInput(StrictModel):
    content: str = Field(min_length=1, max_length=10000)


class ChatMessageOutput(StrictModel):
    id: str
    conversation_id: str
    role: Literal["user", "assistant"]
    content: str
    model: str | None = None
    ollama_metrics: dict | None = None
    created_at: str


class MemoryCategory(StrictModel):
    category: Literal["preference", "personal_fact", "relationship", "goal", "context"]
    importance: int = Field(ge=1, le=5)


class MemoryOutput(StrictModel):
    id: str
    character_id: str
    content: str
    category: str
    importance: int
    embedding_model: str
    source_message_id: str | None = None
    active: bool
    created_at: str
    last_retrieved_at: str | None = None


class MemoryInput(StrictModel):
    content: str = Field(min_length=1, max_length=5000)
    category: Literal["preference", "personal_fact", "relationship", "goal", "context"]
    importance: int = Field(ge=1, le=5)
    source_message_id: str | None = None
