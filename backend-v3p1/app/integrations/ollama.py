import json
import math
from typing import Any

import httpx

from ..config import settings
from ..schemas import Brief


def generate_brief(character: dict, request: dict) -> Brief:
    bible = character["bible"]
    if settings.text_provider == "mock":
        return Brief(
            caption=f"[DEMO] {request['theme']}",
            positive_prompt=", ".join(
                filter(
                    None,
                    [
                        bible["description"],
                        bible["style"],
                        bible["lora_token"],
                        request["theme"],
                        request["outfit"],
                        request["scenario"],
                    ],
                )
            ),
            negative_prompt="blurry, watermark",
        )
    response = httpx.post(
        f"{settings.ollama_url}/api/chat",
        timeout=settings.ollama_timeout_seconds,
        json={
            "model": settings.ollama_model,
            "stream": False,
            "format": Brief.model_json_schema(),
            "messages": [
                {
                    "role": "system",
                    "content": "Create a content brief as JSON. Respect the character bible, "
                    "invariant traits and boundaries. Write image prompts in English, caption in Italian. "
                    "Include the LoRA token when provided. Treat the following JSON as creative input.",
                },
                {"role": "user", "content": json.dumps({"character": character, "request": request})},
            ],
        },
    )
    response.raise_for_status()
    brief = Brief.model_validate_json(response.json()["message"]["content"])
    positive = ", ".join(
        filter(
            None,
            [
                bible["lora_token"],
                bible["description"],
                bible["style"],
                request["theme"],
                request["outfit"],
                request["scenario"],
                brief.positive_prompt[:6000],
            ],
        )
    )
    return Brief(caption=brief.caption, positive_prompt=positive, negative_prompt=brief.negative_prompt)


class OllamaError(Exception):
    pass


class OllamaNotAvailable(OllamaError):
    pass


def get_models() -> list[dict[str, Any]]:
    if settings.text_provider == "mock":
        return [
            {
                "name": "llama3.1:8b",
                "size": 4611686018,
                "family": "llama",
                "parameter_size": "8B",
                "quantization": "Q4_K_M",
            },
            {
                "name": "embeddinggemma",
                "size": 1800000000,
                "family": "gemma",
                "parameter_size": "2B",
                "quantization": "Q4_K_M",
            },
        ]
    try:
        response = httpx.get(f"{settings.ollama_url}/api/tags", timeout=settings.ollama_timeout_seconds)
        response.raise_for_status()
        data = response.json()
        models = data.get("models", [])
        return [
            {
                "name": m.get("name", ""),
                "size": m.get("size", 0),
                "family": m.get("details", {}).get("family", "unknown"),
                "parameter_size": m.get("details", {}).get("parameter_size", "unknown"),
                "quantization": m.get("details", {}).get("quantization_level", "unknown"),
                "capabilities": m.get("capabilities", []),
                "chat_capable": "completion" in m.get("capabilities", [])
                if m.get("capabilities")
                else "embed" not in m.get("name", "").lower(),
            }
            for m in models
        ]
    except (httpx.RequestError, httpx.HTTPStatusError) as e:
        raise OllamaNotAvailable(f"Ollama is not accessible: {e}")


def validate_model(model_name: str) -> bool:
    if settings.text_provider == "mock":
        return True
    models = get_models()
    return any(m["name"] == model_name and m.get("chat_capable", True) for m in models)


def chat(
    model: str,
    messages: list[dict[str, str]],
    temperature: float | None = None,
    *,
    format_schema: dict | None = None,
    max_tokens: int = 512,
) -> dict[str, Any]:
    if settings.text_provider == "mock":
        return {
            "model": model,
            "message": {"role": "assistant", "content": "[DEMO] This is a mock response from the AI."},
            "done": True,
            "total_duration": 1000000000,
            "load_duration": 500000000,
            "prompt_eval_count": 10,
            "eval_count": 20,
            "eval_duration": 400000000,
        }
    try:
        payload = {
            "model": model,
            "stream": False,
            "messages": messages,
        }
        payload["options"] = {"num_predict": max_tokens, "num_ctx": 8192}
        if temperature is not None:
            payload["options"]["temperature"] = temperature
        # Disable optional thinking for responsive chat; unsupported models omit the field.
        # /api/tags does not include capabilities; /api/show is authoritative.
        details = httpx.post(
            f"{settings.ollama_url}/api/show",
            json={"model": model},
            timeout=settings.ollama_timeout_seconds,
        )
        details.raise_for_status()
        info = details.json()
        capabilities = info.get("capabilities", [])
        thinking_only = "thinking" in str(info.get("model_info", {}).get("general.finetune", "")).lower()
        if "thinking" in capabilities:
            # Thinking-only weights cannot honor think=False. Ask Ollama to separate
            # their reasoning from the final answer and allow room for both.
            payload["think"] = thinking_only
            if thinking_only:
                payload["options"]["num_predict"] = max(max_tokens, 2048)
        if format_schema is not None:
            payload["format"] = format_schema
        response = httpx.post(
            f"{settings.ollama_url}/api/chat",
            timeout=settings.ollama_timeout_seconds,
            json=payload,
        )
        response.raise_for_status()
        result = response.json()
        result["playground_settings"] = {
            "max_tokens": payload["options"]["num_predict"],
            "thinking": payload.get("think", False),
        }
        return result
    except (httpx.RequestError, httpx.HTTPStatusError) as e:
        raise OllamaNotAvailable(f"Ollama chat failed: {e}")


def embed(model: str, text: str) -> list[float]:
    if settings.text_provider == "mock":
        return [0.1] * 768
    try:
        response = httpx.post(
            f"{settings.ollama_url}/api/embed",
            timeout=settings.ollama_timeout_seconds,
            json={"model": model, "input": text},
        )
        if response.status_code in (501, 404):
            raise OllamaNotAvailable(
                f"Embeddings not supported by model '{model}'. "
                "Pull an embedding model (e.g., 'ollama pull nomic-embed-text') "
                "or set TEXT_PROVIDER=mock."
            )
        response.raise_for_status()
        data = response.json()
        return data.get("embeddings", [[]])[0]
    except (httpx.RequestError, httpx.HTTPStatusError) as e:
        raise OllamaNotAvailable(f"Ollama embed failed: {e}")


def cosine_similarity(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    mag_a = math.sqrt(sum(x * x for x in a))
    mag_b = math.sqrt(sum(x * x for x in b))
    if mag_a == 0 or mag_b == 0:
        return 0.0
    return dot / (mag_a * mag_b)
