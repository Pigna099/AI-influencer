from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app, headers={"X-API-Key": "test-key"})
public_client = TestClient(app)

PAYLOAD = {
    "checkpoint": "pornmasterProSDXL_sdxlV2VAE_1072864.safetensors",
    "style": "real",
    "negative": "",
    "count": 2,
    "loras": [{"name": "ai_influencer/nikita_real_v1.safetensors", "weight": 0.85, "category": "character"}],
    "pose_ids": [],
    "pose_strength": 0.8,
}


def test_presets_crud():
    assert public_client.get("/api/presets").status_code == 401

    created = client.post("/api/presets", json={"name": "Instagram casual", "payload": PAYLOAD})
    assert created.status_code == 201, created.text
    preset = created.json()
    assert preset["name"] == "Instagram casual"
    assert preset["payload"]["loras"][0]["category"] == "character"

    listing = client.get("/api/presets").json()
    assert [item["id"] for item in listing] == [preset["id"]]

    patched = client.patch(f"/api/presets/{preset['id']}", json={"name": "Instagram"})
    assert patched.status_code == 200 and patched.json()["name"] == "Instagram"

    assert client.delete(f"/api/presets/{preset['id']}").json()["deleted"] is True
    assert client.get("/api/presets").json() == []


def test_presets_validation_and_404():
    assert client.post("/api/presets", json={"name": "", "payload": {}}).status_code == 422
    assert client.patch("/api/presets/missing", json={"name": "x"}).status_code == 404
    assert client.delete("/api/presets/missing").status_code == 404
