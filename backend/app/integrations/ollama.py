import json

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
        timeout=180,
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
    # Keep fixed character and requested scene details even when the LLM omits them.
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
