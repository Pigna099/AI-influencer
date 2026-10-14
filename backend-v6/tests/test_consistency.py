import io

from fastapi.testclient import TestClient
from PIL import Image

from app.main import app

client = TestClient(app, headers={"X-API-Key": "test-key"})
PROFILE = {
    "description": "consistency test",
    "appearance": "adult woman, dark hair",
    "personality_traits": "calm",
    "tone_of_voice": "warm",
    "boundaries": "adults only",
}


def png_data():
    buffer = io.BytesIO()
    Image.new("RGB", (64, 64), (120, 80, 60)).save(buffer, format="PNG")
    return buffer.getvalue()


def test_consistency_check_flags_outliers(monkeypatch):
    character_id = client.post("/api/characters", json={"name": "Consistency", "profile": PROFILE}).json()["id"]
    assert client.post(f"/api/characters/{character_id}/avatar").status_code in (200, 201)
    generated = client.post(
        f"/api/characters/{character_id}/library/generate", json={"prompt": "studio", "count": 3}
    ).json()
    assert len(generated) == 3

    calls = {"n": 0}

    def fake_vision(model, prompt, images, *, schema=None, max_tokens=400):
        calls["n"] += 1
        if calls["n"] == 1:
            return {"score": 92, "same_person": True, "reason": "same face"}
        if calls["n"] == 2:
            return {"score": 40, "same_person": False, "reason": "different person"}
        return {"score": 61, "same_person": True, "reason": "close enough"}

    monkeypatch.setattr("app.consistency_api.vision_json", fake_vision)
    response = client.post(
        f"/api/characters/{character_id}/consistency-check",
        json={"limit": 5, "threshold": 60},
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["checked"] == 3
    assert payload["flagged_count"] == 1
    assert payload["results"][0]["score"] == 40
    assert payload["results"][0]["same_person"] is False
    assert payload["reference"] == "profile picture"


def test_resize_jpeg_downscales():
    from app.consistency_api import resize_jpeg

    encoded = resize_jpeg(png_data(), max_side=32)
    import base64

    with Image.open(io.BytesIO(base64.b64decode(encoded))) as image:
        assert max(image.size) <= 32
