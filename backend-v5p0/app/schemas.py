from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class Bible(StrictModel):
    description: str = Field(min_length=1, max_length=5000)
    style: str = Field(default="anime", max_length=1000)
    tone_of_voice: str = Field(default="cordiale", max_length=1000)
    boundaries: str = Field(default="", max_length=2000)
    lora_token: str = Field(default="", max_length=200)


class InfluencerInput(StrictModel):
    name: str = Field(min_length=1, max_length=120)
    bible: Bible


class JobInput(StrictModel):
    influencer_id: str
    theme: str = Field(min_length=1, max_length=1500)
    outfit: str = Field(default="", max_length=500)
    scenario: str = Field(default="", max_length=1000)
    image_count: int = Field(default=1, ge=1, le=4)
    seed: int = Field(default=42, ge=0, le=2**32 - 5)


class Brief(StrictModel):
    caption: str = Field(min_length=1, max_length=3000)
    positive_prompt: str = Field(min_length=1, max_length=20000)
    negative_prompt: str = Field(max_length=3000)


class ReviewInput(StrictModel):
    decision: Literal["approved", "rejected"]
    note: str = Field(default="", max_length=3000)
