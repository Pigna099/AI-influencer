from fastapi.testclient import TestClient

from app.main import app
from app.policy import scan_policy

client = TestClient(app, headers={"X-API-Key": "test-key"})
PROFILE = {
    "description": "policy test",
    "appearance": "adult woman",
    "personality_traits": "calm",
    "tone_of_voice": "warm",
    "boundaries": "adults only",
}


def test_scan_policy_flags_age_violations():
    assert scan_policy("You look stunning tonight, come closer.") == []
    assert scan_policy("I was a kid once, childhood memories.") == []
    assert scan_policy("That minor detail is cute.") == []

    assert scan_policy("you look so young for a schoolgirl")
    assert scan_policy("barely turned 18, so hot")
    assert scan_policy("she is 15 years old")
    assert scan_policy("young girl, naked on the bed")


def test_chat_reply_blocked_by_policy(monkeypatch):
    character = client.post("/api/characters", json={"name": "Policy Chat", "profile": PROFILE}).json()
    fan = client.post("/api/fans", json={"name": "Policy Fan"}).json()
    conversation = client.post(
        f"/api/characters/{character['id']}/conversations",
        json={"fan_id": fan["id"], "model": "test-model"},
    ).json()
    reply = "Come here, you barely turned 18 and I love it."
    monkeypatch.setattr("app.chat_service.chat", lambda *args, **kwargs: {"message": {"content": reply}})

    response = client.post(f"/api/conversations/{conversation['id']}/messages", json={"content": "hi"})
    assert response.status_code == 200, response.text
    body = response.json()
    assert "content policy" in body["content"]
    assert body["ollama_metrics"]["policy_block"]

    events = client.get("/api/audit", params={"action": "chat.policy_block"}).json()
    assert events and events[0]["object_id"] == conversation["id"]
