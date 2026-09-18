from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class CharacterProfile(StrictModel):
    description: str = Field(min_length=1, max_length=5000)
    appearance: str = Field(default="", max_length=2000)
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
    avatar_filename: str | None = None
    avatar_prompt: str | None = None
    image_checkpoint: str | None = None
    image_style: str | None = None
    ppv_enabled: bool = False
    ppv_price_cents: int = 500
    reply_delay_min_seconds: int = 8
    reply_delay_max_seconds: int = 40
    activity_enabled: bool = False
    activity_start_hour: int = 9
    activity_end_hour: int = 23
    activity_days: list[int] = Field(default_factory=lambda: list(range(7)))
    created_at: str


class ImageCheckpointInput(StrictModel):
    checkpoint: str | None = Field(default=None, max_length=200)


class AvatarInput(StrictModel):
    checkpoint: str | None = Field(default=None, max_length=200)
    style: Literal["anime", "real"] | None = None


class AvatarPromptInput(StrictModel):
    prompt: str | None = Field(default=None, max_length=4000)


class AvatarEditInput(StrictModel):
    prompt: str = Field(min_length=1, max_length=1000)
    steps: int | None = Field(default=None, ge=1, le=50)
    cfg: float | None = Field(default=None, ge=0, le=10)
    lora_weight: float = Field(default=1.0, ge=0, le=2)


class ImageStyleInput(StrictModel):
    style: Literal["anime", "real"] | None = None


class PpvInput(StrictModel):
    enabled: bool = False
    price_cents: int = Field(default=500, ge=0, le=100000)


class RealismInput(StrictModel):
    reply_delay_min_seconds: int = Field(default=8, ge=0, le=3600)
    reply_delay_max_seconds: int = Field(default=40, ge=0, le=3600)
    activity_enabled: bool = False
    activity_start_hour: int = Field(default=9, ge=0, le=23)
    activity_end_hour: int = Field(default=23, ge=0, le=23)
    activity_days: list[int] = Field(default_factory=lambda: list(range(7)), max_length=7)

    @field_validator("activity_days")
    @classmethod
    def valid_days(cls, value: list[int]) -> list[int]:
        if any(day < 0 or day > 6 for day in value):
            raise ValueError("activity_days must be between 0 (Monday) and 6 (Sunday)")
        return sorted(set(value))


class PhotoInput(StrictModel):
    scene: str | None = Field(default=None, max_length=1500)
    caption: str | None = Field(default=None, max_length=1000)
    library_id: str | None = None
    locked: bool = False
    price_cents: int | None = Field(default=None, ge=0, le=100000)


class LoraInput(StrictModel):
    name: str = Field(min_length=1, max_length=200)
    weight: float = Field(default=0.8, ge=0, le=2)
    clip_weight: float | None = Field(default=None, ge=0, le=2)
    category: Literal["character", "style", "outfit", "composition", "other"] | None = None


class LibraryGenerateInput(StrictModel):
    prompt: str = Field(min_length=1, max_length=2000)
    negative: str | None = Field(default=None, max_length=4000)
    style: Literal["anime", "real"] | None = None
    checkpoint: str | None = Field(default=None, max_length=200)
    loras: list[LoraInput] = Field(default_factory=list, max_length=8)
    pose_ids: list[str] = Field(default_factory=list, max_length=4)
    pose_strength: float = Field(default=0.8, ge=0, le=2)
    count: int = Field(default=1, ge=1, le=4)
    seed: int | None = Field(default=None, ge=0, le=2**31)
    classify: bool = True


class LibraryPatch(StrictModel):
    status: Literal["draft", "approved", "rejected"] | None = None
    rating: int | None = Field(default=None, ge=0, le=5)
    caption: str | None = Field(default=None, max_length=2000)
    tags: list[str] | None = Field(default=None, max_length=20)


class PromptAugmentInput(StrictModel):
    prompt: str = Field(min_length=1, max_length=2000)
    style: Literal["anime", "real"] = "real"
    direction: str = Field(default="", max_length=1000)


class CharacterUpdate(StrictModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    profile: CharacterProfile | None = None


class CharacterClone(StrictModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)


class ConversationInput(StrictModel):
    title: str | None = Field(default=None, max_length=200)
    model: str = Field(min_length=1, max_length=120)
    fan_id: str | None = None
    auto_greet: bool = True


class ChatMessageInput(StrictModel):
    content: str = Field(min_length=1, max_length=10000)
    scheduled: bool = False


class MemoryInput(StrictModel):
    content: str = Field(min_length=1, max_length=5000)
    category: Literal["preference", "personal_fact", "relationship", "goal", "context"]
    importance: int = Field(ge=1, le=5)
    source_message_id: str | None = None


class FanInput(StrictModel):
    name: str = Field(min_length=1, max_length=120)
    notes: str = Field(default="", max_length=3000)


class ConversationPatch(StrictModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    model: str | None = Field(default=None, min_length=1, max_length=120)
    images_enabled: bool | None = None
    human_mode: bool | None = None


class InitiateInput(StrictModel):
    kind: Literal["opener", "reengage"] = "reengage"
    absence_hours: int = Field(default=48, ge=1, le=8760)


class EnhanceInput(StrictModel):
    name: str = Field(min_length=1, max_length=120)
    profile: CharacterProfile
    model: str = Field(min_length=1, max_length=120)
    direction: str = Field(default="Rendi la personalità distintiva, giocosa e propositiva.", max_length=2000)


class BenchmarkInput(StrictModel):
    batch_id: str = Field(min_length=1, max_length=36)
    character_id: str
    fan_id: str | None = None
    model: str = Field(min_length=1, max_length=120)
    prompt: str = Field(min_length=1, max_length=4000)
    temperature: float = Field(default=0.7, ge=0, le=2)
    profile: CharacterProfile | None = None
    label: str | None = Field(default=None, max_length=120)


class MemoryExtraction(StrictModel):
    memories: list[MemoryInput] = Field(default_factory=list, max_length=8)
