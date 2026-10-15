from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app, headers={"X-API-Key": "test-key"})
PROFILE = {
    "description": "ppv video test",
    "appearance": "adult woman, dark hair",
    "personality_traits": "playful",
    "tone_of_voice": "warm",
    "boundaries": "adults only",
}


def test_extract_video_request():
    from app.chat_service import extract_video_request

    text, scene = extract_video_request("Guarda qua 😏\n[PPV-VIDEO: she dances in the rain]")
    assert scene == "she dances in the rain"
    assert "[PPV-VIDEO" not in text
    clean, scene = extract_video_request("nessun marker qui")
    assert scene is None and clean == "nessun marker qui"


def test_chat_ppv_video_flow(monkeypatch):
    character_id = client.post("/api/characters", json={"name": "PPV Video", "profile": PROFILE}).json()["id"]
    ppv = client.put(f"/api/characters/{character_id}/ppv", json={"enabled": True, "price_cents": 500})
    assert ppv.status_code == 200, ppv.text

    clip = client.post(
        f"/api/characters/{character_id}/videos",
        json={"prompt": "she dances in the rain", "mode": "text"},
    ).json()
    assert clip["status"] == "ready"

    conversation = client.post(
        f"/api/characters/{character_id}/conversations",
        json={"title": "PPV Video Chat", "model": "llama3.1:8b"},
    ).json()

    def fake_reply(conversation, content, kind="reply", absence_hours=48):
        return "Ecco il video esclusivo 😏", {"video_scene": "she dances in the rain", "video_requested": True}

    monkeypatch.setattr("app.characters.generate_reply", fake_reply)
    response = client.post(f"/api/conversations/{conversation['id']}/messages", json={"content": "mandami un video"})
    assert response.status_code == 200, response.text

    messages = client.get(f"/api/conversations/{conversation['id']}/messages").json()
    assistant = [message for message in messages if message["role"] == "assistant"][-1]
    assert assistant["videos"], assistant
    video = assistant["videos"][0]
    assert video["price_cents"] == 500 and video["unlocked"] is False
    assert video["video_id"] == clip["id"]

    locked = client.get(f"/api/chat-videos/{video['id']}/file")
    assert locked.status_code == 403

    unlocked = client.post(f"/api/chat-videos/{video['id']}/unlock")
    assert unlocked.status_code == 200
    payload = unlocked.json()
    assert payload["unlocked"] is True
    assert payload["payment"]["amount_cents"] == 500 and payload["payment"]["simulated"] is True

    playable = client.get(f"/api/chat-videos/{video['id']}/file")
    assert playable.status_code == 200 and playable.content == b"MOCK-VIDEO"


def test_chat_video_no_clips_falls_back(monkeypatch):
    character_id = client.post("/api/characters", json={"name": "No Clips", "profile": PROFILE}).json()["id"]
    client.put(f"/api/characters/{character_id}/ppv", json={"enabled": True, "price_cents": 500})
    conversation = client.post(
        f"/api/characters/{character_id}/conversations",
        json={"title": "Empty", "model": "llama3.1:8b"},
    ).json()

    def fake_reply(conversation, content, kind="reply", absence_hours=48):
        return "Niente video stavolta", {"video_scene": "she dances", "video_requested": True}

    monkeypatch.setattr("app.characters.generate_reply", fake_reply)
    response = client.post(f"/api/conversations/{conversation['id']}/messages", json={"content": "video?"})
    assert response.status_code == 200
    messages = client.get(f"/api/conversations/{conversation['id']}/messages").json()
    assistant = [message for message in messages if message["role"] == "assistant"][-1]
    assert assistant["videos"] == []

def test_manual_video_from_library(monkeypatch):

    character_id = client.post("/api/characters", json={"name": "Manual Video", "profile": PROFILE}).json()["id"]
    images = client.post(
        f"/api/characters/{character_id}/library/generate", json={"prompt": "x", "count": 1}
    ).json()
    clip = client.post(
        f"/api/characters/{character_id}/videos",
        json={"prompt": "x", "image_id": images[0]["id"], "length": 49},
    ).json()
    client.patch(f"/api/videos/{clip['id']}", json={"review_status": "approved"})
    conversation = client.post(
        f"/api/characters/{character_id}/conversations",
        json={"fan_id": client.post("/api/fans", json={"name": "Video Fan"}).json()["id"], "model": "test-model"},
    ).json()

    sent = client.post(
        f"/api/conversations/{conversation['id']}/video",
        json={"video_id": clip["id"], "caption": "Guarda che clip 😏", "locked": True, "price_cents": 400},
    )
    assert sent.status_code == 201, sent.text
    body = sent.json()
    assert body["content"] == "Guarda che clip 😏"
    assert body["videos"][0]["price_cents"] == 400
    assert body["ollama_metrics"]["video_sent"] is True

    unlock = client.post(f"/api/chat-videos/{body['videos'][0]['id']}/unlock")
    assert unlock.status_code == 200

    other = client.post("/api/characters", json={"name": "Other", "profile": {"description": "x"}}).json()
    other_conv = client.post(
        f"/api/characters/{other['id']}/conversations",
        json={"fan_id": client.post("/api/fans", json={"name": "Other Fan"}).json()["id"], "model": "test-model"},
    ).json()
    assert client.post(
        f"/api/conversations/{other_conv['id']}/video", json={"video_id": clip["id"]}
    ).status_code == 404
