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
    chat_image_cooldown_seconds: int = 300
    chat_workflow_path: Path = Path("workflows/chat_default.json")
    chat_reference_workflow_path: Path = Path("workflows/chat_reference.json")
    chat_real_workflow_path: Path = Path("workflows/chat_real.json")
    chat_real_reference_workflow_path: Path = Path("workflows/chat_real_reference.json")
    chat_anime_workflow_path: Path = Path("workflows/chat_anime.json")
    chat_anime_reference_workflow_path: Path = Path("workflows/chat_anime_reference.json")
    chat_real_style: str = (
        "nsfw, explicit adult content, seductive, realistic skin texture, detailed anatomy, "
        "photorealistic, 8k uhd, dslr, soft lighting, film grain, sharp focus"
    )
    chat_real_negative: str = (
        "child, minor, teen, underage, cartoon, anime, illustration, painting, cgi, 3d render, "
        "plastic skin, bad anatomy, extra fingers, fused fingers, extra limbs, watermark, text, logo"
    )
    chat_anime_style: str = (
        "nsfw, explicit, detailed anatomy, beautiful detailed eyes, detailed face, cinematic lighting, "
        "depth of field, high contrast"
    )
    chat_anime_negative: str = (
        "bad quality, worst quality, worst detail, sketch, censor, bad anatomy, bad hands, extra digits, "
        "fewer digits, missing fingers, jpeg artifacts, signature, watermark, username, child, minor, "
        "teen, underage, loli, shota"
    )
    chat_pony_workflow_path: Path = Path("workflows/chat_pony.json")
    chat_pony_reference_workflow_path: Path = Path("workflows/chat_pony_reference.json")
    chat_pony_style: str = (
        "rating_explicit, nsfw, explicit adult content, realistic skin texture, detailed anatomy, "
        "photorealistic, sharp focus"
    )
    chat_pony_negative: str = (
        "score_4, score_5, score_6, source_anime, source_cartoon, source_furry, worst quality, "
        "low quality, bad anatomy, extra fingers, fused fingers, deformed hands, watermark, text, logo"
    )
    # Uncensored enough to translate explicit scenes into English image tags.
    image_prompt_model: str = "mistral-small3.2:latest"
    # Multimodal model used to caption/tag generated images for the library (empty disables it).
    image_tag_model: str = "gemma3:27b"
    # Similarity threshold for reusing an approved library image instead of generating.
    image_match_threshold: float = 0.55
    # Maximum images in a single playground batch request.
    image_library_batch_max: int = 4
    dataset_dir: Path = Path("data/dataset")
    dataset_import_dir: Path = Path("data/imports")
    dataset_max_images: int = 2000
    dataset_download_max_bytes: int = 20 * 1024 * 1024
    dataset_video_max_bytes: int = 200 * 1024 * 1024
    # Simulated pay-per-view for chat photos (no real payments).
    ppv_enabled: bool = True


settings = Settings()
