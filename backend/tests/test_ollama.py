import json

import httpx
import pytest
from pydantic import ValidationError

from app.integrations.ollama import generate_brief


def test_ollama_preserves_character_and_validates_json(monkeypatch):
    monkeypatch.setattr("app.integrations.ollama.settings.text_provider", "ollama")
    response = {"caption": "Una passeggiata", "positive_prompt": "sunny park", "negative_prompt": "blurry"}

    def fake_post(url, **kwargs):
        assert kwargs["json"]["stream"] is False
        assert "properties" in kwargs["json"]["format"]
        return httpx.Response(
            200, request=httpx.Request("POST", url), json={"message": {"content": json.dumps(response)}}
        )

    monkeypatch.setattr("app.integrations.ollama.httpx.post", fake_post)
    character = {"bible": {"description": "green eyes", "style": "anime", "lora_token": "my_character"}}
    request = {"theme": "walk", "outfit": "blue jacket", "scenario": "spring"}
    brief = generate_brief(character, request)
    for expected in ("my_character", "green eyes", "anime", "blue jacket", "spring", "sunny park"):
        assert expected in brief.positive_prompt
    response.pop("caption")
    with pytest.raises(ValidationError):
        generate_brief(character, request)
