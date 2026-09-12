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


@pytest.mark.parametrize(
    "capabilities, expects_think", [(["completion", "thinking"], True), (["completion"], False)]
)
def test_chat_uses_show_capabilities_and_generation_options(monkeypatch, capabilities, expects_think):
    from app.integrations.ollama import chat

    monkeypatch.setattr("app.integrations.ollama.settings.text_provider", "ollama")
    paths = []

    def fake_post(url, **kwargs):
        paths.append(url.rsplit("/", 1)[-1])
        if url.endswith("/show"):
            body = {"capabilities": capabilities}
        else:
            payload = kwargs["json"]
            assert ("think" in payload) is expects_think
            if expects_think:
                assert payload["think"] is False
            assert payload["options"] == {"temperature": 0.3, "num_predict": 512, "num_ctx": 8192}
            body = {"message": {"content": "Ciao!"}}
        return httpx.Response(200, request=httpx.Request("POST", url), json=body)

    monkeypatch.setattr("app.integrations.ollama.httpx.post", fake_post)
    assert chat("test-model", [{"role": "user", "content": "Ciao"}], 0.3)["message"]["content"] == "Ciao!"
    assert paths == ["show", "chat"]


def test_thinking_only_model_keeps_reasoning_separate(monkeypatch):
    from app.integrations.ollama import chat

    monkeypatch.setattr("app.integrations.ollama.settings.text_provider", "ollama")

    def fake_post(url, **kwargs):
        if url.endswith("/show"):
            body = {
                "capabilities": ["completion", "thinking"],
                "model_info": {"general.finetune": "Thinking"},
            }
        else:
            assert kwargs["json"]["think"] is True
            assert kwargs["json"]["options"]["num_predict"] == 2048
            body = {"message": {"content": "Ciao!", "thinking": "private reasoning"}}
        return httpx.Response(200, request=httpx.Request("POST", url), json=body)

    monkeypatch.setattr("app.integrations.ollama.httpx.post", fake_post)
    response = chat("qwen3:30b", [{"role": "user", "content": "Ciao"}], 0.7)
    assert response["playground_settings"] == {"max_tokens": 2048, "thinking": True}
    assert response["message"]["content"] == "Ciao!"
