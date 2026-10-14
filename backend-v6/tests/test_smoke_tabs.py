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
    ]
    failures = []
    for path in endpoints:
        response = client.get(path)
        if response.status_code != 200:
            failures.append(f"{path} -> {response.status_code}: {response.text[:120]}")
    assert not failures, "\n".join(failures)
