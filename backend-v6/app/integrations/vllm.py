"""OpenAI-compatible client for a local vLLM server (fast text inference)."""

import time

import httpx

from ..config import settings


class VllmNotAvailable(RuntimeError):
    """The vLLM server is down, the model is not served, or the request failed."""


def _headers() -> dict:
    return {"Authorization": f"Bearer {settings.vllm_api_key}"} if settings.vllm_api_key else {}


def available(timeout: float = 3.0) -> bool:
    try:
        response = httpx.get(f"{settings.vllm_url}/v1/models", headers=_headers(), timeout=timeout)
        return response.status_code == 200
    except httpx.HTTPError:
        return False


def get_models() -> list[dict]:
    response = httpx.get(f"{settings.vllm_url}/v1/models", headers=_headers(), timeout=10)
    response.raise_for_status()
    return [
        {
            "name": item.get("id", ""),
            "model": item.get("id", ""),
            "size": "vLLM",
            "parameter_size": "",
            "quantization_level": "",
            "kind": "chat",
            "chat_capable": True,
        }
        for item in response.json().get("data", [])
    ]


def normalize_messages(messages: list[dict[str, str]]) -> list[dict[str, str]]:
    """Qwen templates require all system messages first and at least one user query."""
    systems = [message.get("content", "") for message in messages if message.get("role") == "system"]
    rest = [message for message in messages if message.get("role") != "system"]
    normalized: list[dict[str, str]] = []
    if systems:
        normalized.append({"role": "system", "content": "\n\n".join(part for part in systems if part)})
    normalized.extend(rest)
    if not any(message.get("role") == "user" for message in normalized):
        normalized.append({"role": "user", "content": "Reply following the instructions above."})
    return normalized


def chat(
    model: str,
    messages: list[dict[str, str]],
    temperature: float | None = None,
    *,
    format_schema: dict | None = None,
    max_tokens: int = 512,
) -> dict:
    payload: dict = {
        "model": model,
        "messages": normalize_messages(messages),
        "max_tokens": max_tokens,
        "stream": False,
        # Hybrid reasoning models (Qwen3.x): keep chat replies fast and direct.
        "chat_template_kwargs": {"enable_thinking": False},
    }
    if temperature is not None:
        payload["temperature"] = temperature
    if format_schema is not None:
        # vLLM reads guided_json from the request body (extra field) and also accepts response_format.
        payload["guided_json"] = format_schema
        payload["response_format"] = {"type": "json_object"}
    started = time.perf_counter()
    try:
        response = httpx.post(
            f"{settings.vllm_url}/v1/chat/completions",
            json=payload,
            headers=_headers(),
            timeout=settings.vllm_timeout_seconds,
        )
    except httpx.HTTPError as error:
        raise VllmNotAvailable(f"vLLM unreachable: {error}") from error
    if response.status_code == 404:
        raise VllmNotAvailable(f"Model not served by vLLM: {model}")
    if response.status_code >= 400:
        raise VllmNotAvailable(f"vLLM error {response.status_code}: {response.text[:300]}")
    data = response.json()
    elapsed_ns = int((time.perf_counter() - started) * 1e9)
    usage = data.get("usage") or {}
    choice = (data.get("choices") or [{}])[0]
    message = choice.get("message") or {}
    return {
        "model": data.get("model", model),
        "message": {"role": "assistant", "content": message.get("content") or ""},
        "thinking": message.get("reasoning_content") or message.get("reasoning") or "",
        "done": True,
        "done_reason": choice.get("finish_reason") or "stop",
        "total_duration": elapsed_ns,
        "load_duration": 0,
        "prompt_eval_count": usage.get("prompt_tokens") or 0,
        "prompt_eval_duration": 0,
        "eval_count": usage.get("completion_tokens") or 0,
        "eval_duration": elapsed_ns,
    }


def vision_json(
    model: str,
    prompt: str,
    images: list[str],
    *,
    schema: dict | None = None,
    max_tokens: int = 400,
) -> dict:
    """One-shot vision request: images are base64 JPEG/PNG strings; returns parsed JSON."""
    import json as jsonlib

    content: list[dict] = [{"type": "text", "text": prompt}]
    for image in images:
        content.append({"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image}"}})
    payload: dict = {
        "model": model,
        "messages": [{"role": "user", "content": content}],
        "max_tokens": max_tokens,
        "temperature": 0.1,
        "chat_template_kwargs": {"enable_thinking": False},
    }
    if schema is not None:
        payload["guided_json"] = schema
        payload["response_format"] = {"type": "json_object"}
    try:
        response = httpx.post(
            f"{settings.vllm_url}/v1/chat/completions",
            json=payload,
            headers=_headers(),
            timeout=settings.vllm_timeout_seconds,
        )
    except httpx.HTTPError as error:
        raise VllmNotAvailable(f"vLLM unreachable: {error}") from error
    if response.status_code >= 400:
        raise VllmNotAvailable(f"vLLM error {response.status_code}: {response.text[:200]}")
    text_content = ((response.json().get("choices") or [{}])[0].get("message") or {}).get("content") or ""
    try:
        return jsonlib.loads(text_content)
    except ValueError as error:
        raise VllmNotAvailable(f"Invalid vision response: {text_content[:160]}") from error
