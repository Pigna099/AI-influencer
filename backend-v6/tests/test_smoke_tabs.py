"""Smoke test: the main API surface used by every tab answers successfully."""

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app, headers={"X-API-Key": "test-key"})
PROFILE = {"description": "smoke", "appearance": "adult woman", "personality_traits": "calm", "tone_of_voice": "warm", "boundaries": "adults only"}


def test_every_tab_main_endpoints():
    character = client.post("/api/characters", json={"name": "Smoke", "profile": PROFILE}).json()
    character_id = character["id"]

    endpoints = [
        # Home
        "/health", "/api/system/gpus", "/api/settings/defaults", "/api/settings/gpu-plan",
        "/api/ollama/models", "/api/images/checkpoints", "/api/images/loras",
        # Chat
        f"/api/characters/{character_id}/conversations", "/api/fans",
        # Images
        f"/api/characters/{character_id}/library", "/api/presets", "/api/poses",
        f"/api/characters/{character_id}/loras",
        # Video
        f"/api/characters/{character_id}/videos",
        # Dataset
        "/api/dataset/sources", "/api/dataset/images",
        # LoRA
        f"/api/characters/{character_id}/datasets", "/api/training-jobs",
        # Home
        "/api/overview", "/api/metrics", "/api/alerts",
    ]
    failures = []
    for path in endpoints:
        response = client.get(path)
        if response.status_code != 200:
            failures.append(f"{path} -> {response.status_code}: {response.text[:120]}")
    assert not failures, "\n".join(failures)

def test_failed_attempt_limiter():
    from app.auth import reset_limits

    reset_limits()
    bad = TestClient(app, headers={"X-API-Key": "wrong-key"})
    for _ in range(31):
        assert bad.get("/api/characters").status_code == 401
    assert bad.get("/api/characters").status_code == 429
    # The block is per client IP: even a valid key from that IP is rejected until it expires.
    assert client.get("/api/characters").status_code == 429
    reset_limits()
    assert client.get("/api/characters").status_code == 200

def test_api_key_rotation_accepts_previous_key():
    from app.auth import reset_limits
    from app.config import settings

    reset_limits()
    original = settings.api_key_previous
    settings.api_key_previous = "rotated-out-key"
    try:
        rotated = TestClient(app, headers={"X-API-Key": "rotated-out-key"})
        assert rotated.get("/api/characters").status_code == 200
        assert TestClient(app, headers={"X-API-Key": "still-wrong"}).get("/api/characters").status_code == 401
    finally:
        settings.api_key_previous = original
        reset_limits()
