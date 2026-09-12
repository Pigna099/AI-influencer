from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    database_url: str = "sqlite:///./data/backend.db"
    media_dir: Path = Path("data/media")
    api_key: str = ""
    text_provider: Literal["mock", "ollama"] = "mock"
    image_provider: Literal["mock", "comfyui"] = "mock"
    ollama_url: str = "http://127.0.0.1:11434"
    ollama_model: str = "llama3.1:8b"
    ollama_timeout_seconds: int = 120
    ollama_embedding_model: str = "embeddinggemma"
    chat_temperature: float = 0.7
    cors_origins: str = "http://localhost:3000"
    comfyui_url: str = "http://127.0.0.1:8188"
    workflow_path: Path = Path("workflows/default.json")
    generation_timeout: int = 900
    worker_lease_seconds: int = 1200
    chat_image_enabled: bool = True
    chat_image_nsfw: bool = True
    chat_image_style: str = (
        "score_9, score_8_up, score_7_up, source_photo, rating_explicit, NSFW, explicit adult content, "
        "seductive, highly detailed skin, photorealistic, sharp focus, 8k"
    )
    chat_image_negative: str = (
        "score_4, score_5, score_6, source_anime, source_cartoon, rating_safe, worst quality, low quality, "
        "bad anatomy, extra fingers, deformed hands, watermark, text, logo"
    )
    chat_image_cooldown_seconds: int = 300
    chat_workflow_path: Path = Path("workflows/chat_default.json")


settings = Settings()
