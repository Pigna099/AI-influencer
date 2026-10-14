"""Text generation provider switch: vLLM when configured, Ollama as fallback/backup."""

import logging

from ..config import settings
from . import ollama, vllm
from .ollama import OllamaNotAvailable

logger = logging.getLogger(__name__)

__all__ = ["OllamaNotAvailable", "chat", "get_models", "validate_model"]


def chat(
    model: str,
    messages: list[dict[str, str]],
    temperature: float | None = None,
    *,
    format_schema: dict | None = None,
    max_tokens: int = 512,
) -> dict:
    if settings.text_provider == "vllm":
        try:
            return vllm.chat(model, messages, temperature, format_schema=format_schema, max_tokens=max_tokens)
        except vllm.VllmNotAvailable as error:
            logger.warning("vLLM non disponibile, fallback su Ollama: %s", error)
    return ollama.chat(model, messages, temperature, format_schema=format_schema, max_tokens=max_tokens)


def get_models() -> list[dict]:
    if settings.text_provider == "vllm":
        try:
            models = vllm.get_models()
            if models:
                return models
        except Exception as error:  # noqa: BLE001 - fall back to the Ollama list when vLLM is down
            logger.warning("Lista modelli vLLM non disponibile, fallback su Ollama: %s", error)
    return ollama.get_models()


def validate_model(model_name: str) -> bool:
    if settings.text_provider == "vllm":
        try:
            if any(item["name"] == model_name for item in vllm.get_models()):
                return True
        except Exception as error:  # noqa: BLE001 - validation must not raise when vLLM is down
            logger.warning("Validazione modello vLLM non disponibile: %s", error)
    return ollama.validate_model(model_name)


def vision_json(model: str, prompt: str, images: list[str], *, schema: dict | None = None, max_tokens: int = 400) -> dict:
    """Vision JSON with vLLM first (when configured) and Ollama as fallback."""
    if settings.text_provider == "vllm" and model == settings.vllm_chat_model:
        try:
            return vllm.vision_json(model, prompt, images, schema=schema, max_tokens=max_tokens)
        except vllm.VllmNotAvailable as error:
            logger.warning("vLLM vision non disponibile, fallback su Ollama: %s", error)
    return ollama.vision_json(model if model != settings.vllm_chat_model else settings.image_tag_model, prompt, images, schema=schema, max_tokens=max_tokens)
