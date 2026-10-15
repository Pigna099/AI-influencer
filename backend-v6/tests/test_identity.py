from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app, headers={"X-API-Key": "test-key"})
PROFILE = {
    "description": "identity test",
    "appearance": "adult woman, dark hair",
    "personality_traits": "calm",
    "tone_of_voice": "warm",
    "boundaries": "adults only",
}


def fake_edit(reference, prompt, **kwargs):
    return b"fake-identity-image", {"provider": "mock", "seed": kwargs.get("seed", 0), "model": "qwen_image_edit"}


def make_character(name="Identity"):
    response = client.post(
        "/api/characters",
        json={"name": name, "profile": PROFILE, "age": 26, "synthetic_declared": True},
    )
    assert response.status_code == 201, response.text
    character_id = response.json()["id"]
    assert client.post(f"/api/characters/{character_id}/avatar").status_code in (200, 201)
    return character_id


def test_identity_template():
    template = client.get("/api/identity-template").json()
    assert template["version"] == "1"
    assert len(template["angles"]) == 18
    assert template["canonical_min"] == 6 and template["canonical_max"] == 10


def test_identity_run_generates_candidates(monkeypatch):
    monkeypatch.setattr("app.identity_api.qwen_image_edit", fake_edit)
    character_id = make_character("Identity Run")

    response = client.post(
        f"/api/characters/{character_id}/identity-runs",
        json={"angles": ["front_neutral", "profile_left", "profile_right", "close_up_front", "three_quarter_left", "three_quarter_right", "upper_body_front", "full_body_front"], "per_angle": 1},
    )
    assert response.status_code == 201, response.text
    run = response.json()
    assert run["status"] == "finished"
    assert run["template_version"] == "1" and len(run["anchor_sha256"]) == 64
    assert len(run["candidates"]) == 8
    angles = {candidate["angle"] for candidate in run["candidates"]}
    assert "profile_left" in angles and "close_up_front" in angles

    detail = client.get(f"/api/identity-runs/{run['id']}").json()
    assert len(detail["candidates"]) == 8
    assert all(candidate["filename"] for candidate in detail["candidates"])

    listing = client.get(f"/api/characters/{character_id}/identity-runs").json()
    assert listing and listing[0]["id"] == run["id"]


def test_identity_candidate_review_and_freeze(monkeypatch):
    monkeypatch.setattr("app.identity_api.qwen_image_edit", fake_edit)
    character_id = make_character("Identity Freeze")
    run = client.post(
        f"/api/characters/{character_id}/identity-runs",
        json={"angles": ["front_neutral", "profile_left", "profile_right", "close_up_front", "three_quarter_left", "three_quarter_right", "upper_body_front", "full_body_front"]},
    ).json()

    # Freeze with nothing accepted must fail without an override.
    blocked = client.post(f"/api/identity-runs/{run['id']}/freeze", json={})
    assert blocked.status_code == 409
    assert "Unbalanced" in blocked.json()["detail"]

    for candidate in run["candidates"]:
        patched = client.patch(f"/api/identity-candidates/{candidate['id']}", json={"status": "accepted"})
        assert patched.status_code == 200, patched.text
        assert patched.json()["status"] == "accepted"

    frozen = client.post(f"/api/identity-runs/{run['id']}/freeze", json={})
    assert frozen.status_code == 200, frozen.text
    assert frozen.json()["status"] == "frozen" and frozen.json()["frozen_at"]

    # Frozen runs are immutable.
    assert client.patch(f"/api/identity-candidates/{run['candidates'][0]['id']}", json={"status": "rejected"}).status_code == 409
    assert client.post(f"/api/identity-runs/{run['id']}/freeze", json={}).status_code == 409


def test_identity_run_requires_anchor(monkeypatch):
    monkeypatch.setattr("app.identity_api.qwen_image_edit", fake_edit)
    character = client.post("/api/characters", json={"name": "No Anchor", "profile": PROFILE}).json()
    response = client.post(f"/api/characters/{character['id']}/identity-runs", json={})
    assert response.status_code == 400
    assert "profile picture" in response.json()["detail"]
