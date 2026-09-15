from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app, headers={"X-API-Key": "test-key"})
public_client = TestClient(app)


def test_create_character():
    profile = {
        "description": "A friendly AI influencer",
        "personality_traits": "cheerful, helpful",
        "tone_of_voice": "warm",
        "boundaries": "No NSFW",
    }
    response = client.post("/api/characters", json={"name": "TestCharacter", "profile": profile})
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "TestCharacter"
    assert data["profile"]["description"] == "A friendly AI influencer"
    assert "id" in data
    assert "version" in data


def test_create_character_no_auth():
    profile = {
        "description": "A friendly AI influencer",
        "personality_traits": "cheerful, helpful",
        "tone_of_voice": "warm",
        "boundaries": "No NSFW",
    }
    response = public_client.post("/api/characters", json={"name": "TestCharacter", "profile": profile})
    assert response.status_code == 401


def test_list_characters():
    response = client.get("/api/characters")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)


def test_get_character():
    profile = {
        "description": "Test description",
        "personality_traits": "test",
        "tone_of_voice": "test",
        "boundaries": "test",
    }
    create_resp = client.post("/api/characters", json={"name": "GetTest", "profile": profile})
    char_id = create_resp.json()["id"]

    response = client.get(f"/api/characters/{char_id}")
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "GetTest"


def test_update_character():
    profile = {
        "description": "Original description",
        "personality_traits": "original",
        "tone_of_voice": "test",
        "boundaries": "test",
    }
    create_resp = client.post("/api/characters", json={"name": "UpdateTest", "profile": profile})
    char_id = create_resp.json()["id"]

    update_resp = client.put(
        f"/api/characters/{char_id}",
        json={"name": "UpdatedName", "profile": {"description": "Updated description"}},
    )
    assert update_resp.status_code == 200
    data = update_resp.json()
    assert data["name"] == "UpdatedName"
    assert data["profile"]["description"] == "Updated description"
    assert data["version"] == 2


def test_create_conversation():
    profile = {
        "description": "Test",
        "personality_traits": "test",
        "tone_of_voice": "test",
        "boundaries": "test",
    }
    create_resp = client.post("/api/characters", json={"name": "ConvTest", "profile": profile})
    char_id = create_resp.json()["id"]

    conv_resp = client.post(
        f"/api/characters/{char_id}/conversations",
        json={"title": "Test Conversation", "model": "llama3.1:8b"},
    )
    assert conv_resp.status_code == 201
    data = conv_resp.json()
    assert data["title"] == "Test Conversation"
    assert data["character_id"] == char_id


def test_list_character_conversations():
    profile = {
        "description": "Test",
        "personality_traits": "test",
        "tone_of_voice": "test",
        "boundaries": "test",
    }
    create_resp = client.post("/api/characters", json={"name": "ListConvTest", "profile": profile})
    char_id = create_resp.json()["id"]

    client.post(
        f"/api/characters/{char_id}/conversations",
        json={"model": "llama3.1:8b"},
    )

    response = client.get(f"/api/characters/{char_id}/conversations")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) >= 1


def test_get_conversation():
    profile = {
        "description": "Test",
        "personality_traits": "test",
        "tone_of_voice": "test",
        "boundaries": "test",
    }
    create_resp = client.post("/api/characters", json={"name": "GetConvTest", "profile": profile})
    char_id = create_resp.json()["id"]

    conv_resp = client.post(
        f"/api/characters/{char_id}/conversations",
        json={"model": "llama3.1:8b"},
    )
    conv_id = conv_resp.json()["id"]

    response = client.get(f"/api/conversations/{conv_id}")
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == conv_id


def test_patch_conversation():
    profile = {
        "description": "Test",
        "personality_traits": "test",
        "tone_of_voice": "test",
        "boundaries": "test",
    }
    create_resp = client.post("/api/characters", json={"name": "PatchConvTest", "profile": profile})
    char_id = create_resp.json()["id"]

    conv_resp = client.post(
        f"/api/characters/{char_id}/conversations",
        json={"model": "llama3.1:8b"},
    )
    conv_id = conv_resp.json()["id"]

    response = client.patch(f"/api/conversations/{conv_id}", json={"title": "New Title"})
    assert response.status_code == 200
    data = response.json()
    assert data["title"] == "New Title"


def test_send_message():
    profile = {
        "description": "Test",
        "personality_traits": "test",
        "tone_of_voice": "test",
        "boundaries": "test",
    }
    create_resp = client.post("/api/characters", json={"name": "MsgTest", "profile": profile})
    char_id = create_resp.json()["id"]

    conv_resp = client.post(
        f"/api/characters/{char_id}/conversations",
        json={"model": "llama3.1:8b"},
    )
    conv_id = conv_resp.json()["id"]

    msg_resp = client.post(f"/api/conversations/{conv_id}/messages", json={"content": "Hello!"})
    assert msg_resp.status_code == 200
    data = msg_resp.json()
    assert data["role"] == "assistant"
    assert len(data["content"]) > 0


def test_list_conversation_messages():
    profile = {
        "description": "Test",
        "personality_traits": "test",
        "tone_of_voice": "test",
        "boundaries": "test",
    }
    create_resp = client.post("/api/characters", json={"name": "ListMsgTest", "profile": profile})
    char_id = create_resp.json()["id"]

    conv_resp = client.post(
        f"/api/characters/{char_id}/conversations",
        json={"model": "llama3.1:8b"},
    )
    conv_id = conv_resp.json()["id"]

    client.post(f"/api/conversations/{conv_id}/messages", json={"content": "First message"})

    response = client.get(f"/api/conversations/{conv_id}/messages")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) >= 1


def test_list_memories():
    profile = {
        "description": "Test",
        "personality_traits": "test",
        "tone_of_voice": "test",
        "boundaries": "test",
    }
    create_resp = client.post("/api/characters", json={"name": "MemTest", "profile": profile})
    char_id = create_resp.json()["id"]

    response = client.get(f"/api/characters/{char_id}/memories")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)


def test_delete_all_memories():
    profile = {
        "description": "Test",
        "personality_traits": "test",
        "tone_of_voice": "test",
        "boundaries": "test",
    }
    create_resp = client.post("/api/characters", json={"name": "DelMemTest", "profile": profile})
    char_id = create_resp.json()["id"]

    response = client.delete(f"/api/characters/{char_id}/memories")
    assert response.status_code == 200
    data = response.json()
    assert "deleted" in data
    assert "count" in data


def test_legacy_bible_compatibility():
    from app.db import Influencer, Session

    with Session.begin() as db:
        item = Influencer(
            name="LegacyChar",
            bible={
                "description": "Legacy profile description",
                "style": "anime",
                "tone_of_voice": "formal",
                "boundaries": "No NSFW",
            },
        )
        db.add(item)

    response = client.get(f"/api/characters/{item.id}")
    assert response.status_code == 200
    data = response.json()
    assert data["profile"]["description"] == "Legacy profile description"
    assert data["profile"]["personality_traits"] == ""
    assert data["profile"]["tone_of_voice"] == "formal"


def test_system_health():
    response = public_client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"


def test_system_ping():
    response = public_client.get("/ping")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"


def test_delete_character():
    profile = {
        "description": "Test",
        "personality_traits": "test",
        "tone_of_voice": "test",
        "boundaries": "test",
    }
    create_resp = client.post("/api/characters", json={"name": "DelTest", "profile": profile})
    char_id = create_resp.json()["id"]

    response = client.delete(f"/api/characters/{char_id}")
    assert response.status_code == 200
    data = response.json()
    assert data["deleted"] == True
    assert data["id"] == char_id

    # Verify character is gone
    get_resp = client.get(f"/api/characters/{char_id}")
    assert get_resp.status_code == 404

    # Verify list is updated
    list_resp = client.get("/api/characters")
    assert all(c["id"] != char_id for c in list_resp.json())


def test_delete_character_with_conversation():
    profile = {
        "description": "Test",
        "personality_traits": "test",
        "tone_of_voice": "test",
        "boundaries": "test",
    }
    create_resp = client.post("/api/characters", json={"name": "ConvDelTest", "profile": profile})
    char_id = create_resp.json()["id"]

    # Create a conversation
    conv_resp = client.post(
        f"/api/characters/{char_id}/conversations",
        json={"model": "llama3.1:8b"},
    )
    conv_id = conv_resp.json()["id"]

    # Delete the character
    response = client.delete(f"/api/characters/{char_id}")
    assert response.status_code == 200

    # Verify conversation is gone
    get_conv_resp = client.get(f"/api/conversations/{conv_id}")
    assert get_conv_resp.status_code == 404


def test_delete_character_with_memories():
    profile = {
        "description": "Test",
        "personality_traits": "test",
        "tone_of_voice": "test",
        "boundaries": "test",
    }
    create_resp = client.post("/api/characters", json={"name": "MemDelTest", "profile": profile})
    char_id = create_resp.json()["id"]

    # Create a conversation and send messages to generate memories
    conv_resp = client.post(
        f"/api/characters/{char_id}/conversations",
        json={"model": "llama3.1:8b"},
    )
    assert conv_resp.status_code == 201

    # We need to wait for background tasks to complete
    # For now, just delete directly

    # Delete the character
    response = client.delete(f"/api/characters/{char_id}")
    assert response.status_code == 200

    # Verify memories are gone
    get_mem_resp = client.get(f"/api/characters/{char_id}/memories")
    assert get_mem_resp.status_code == 404


def test_delete_nonexistent_character():
    response = client.delete("/api/characters/00000000-0000-0000-0000-000000000000")
    assert response.status_code == 404


def _character_and_conversation(name):
    profile = {
        "description": "Test",
        "personality_traits": "test",
        "tone_of_voice": "test",
        "boundaries": "test",
    }
    char_id = client.post("/api/characters", json={"name": name, "profile": profile}).json()["id"]
    conversation = client.post(
        f"/api/characters/{char_id}/conversations",
        json={"model": "llama3.1:8b", "auto_greet": False},
    ).json()
    return char_id, conversation["id"]


def test_conversation_human_mode_toggle():
    _, conv_id = _character_and_conversation("HumanToggle")
    assert client.get(f"/api/conversations/{conv_id}").json()["human_mode"] is False
    patched = client.patch(f"/api/conversations/{conv_id}", json={"human_mode": True}).json()
    assert patched["human_mode"] is True


def test_human_mode_splits_reply_into_bursts(monkeypatch):
    _, conv_id = _character_and_conversation("HumanBursts")
    client.patch(f"/api/conversations/{conv_id}", json={"human_mode": True})
    long_answer = (
        "I could not stop thinking about you today. The city was loud and full of light. "
        "I walked home slowly and smiled the whole way. Tell me about your day, I want every detail."
    )
    monkeypatch.setattr("app.characters.generate_reply", lambda *args, **kwargs: (long_answer, {}))

    response = client.post(f"/api/conversations/{conv_id}/messages", json={"content": "Hey!"})
    assert response.status_code == 200, response.text
    payload = response.json()
    assert "burst" in payload and len(payload["burst"]) >= 2
    messages = client.get(f"/api/conversations/{conv_id}/messages").json()
    assistant = [message for message in messages if message["role"] == "assistant"]
    assert len(assistant) >= 2
    assert messages[-1]["id"] == payload["id"]


def test_human_mode_schedules_proactive(monkeypatch):
    _, conv_id = _character_and_conversation("HumanProactive")
    client.patch(f"/api/conversations/{conv_id}", json={"human_mode": True})
    monkeypatch.setattr("app.characters.generate_reply", lambda *args, **kwargs: ("Short answer.", {}))
    client.post(f"/api/conversations/{conv_id}/messages", json={"content": "Hi"})
    conversation = client.get(f"/api/conversations/{conv_id}").json()
    assert conversation["pending_replies"] >= 1


def test_human_bursts_unit():
    from app.chat_service import human_bursts

    class Rng:
        def random(self):
            return 0.0

        def randrange(self, *args):
            if len(args) == 2:
                return args[0]
            return min(1, args[0] - 1)

    text = (
        "First sentence about something nice. Second sentence with more detail. "
        "Third sentence to close the thought. Fourth sentence for good measure."
    )
    bursts = human_bursts(text, Rng())
    assert 2 <= len(bursts) <= 4
    assert any(item.startswith("*") for item in bursts)


def _avatar_png():
    from io import BytesIO

    from PIL import Image

    buffer = BytesIO()
    Image.new("RGB", (48, 64), (30, 20, 40)).save(buffer, format="PNG")
    return buffer.getvalue()


def test_avatar_can_choose_checkpoint():
    profile = {"description": "Test", "personality_traits": "test", "tone_of_voice": "test", "boundaries": "test"}
    char = client.post("/api/characters", json={"name": "AvatarModel", "profile": profile}).json()
    response = client.post(f"/api/characters/{char['id']}/avatar", json={"checkpoint": "pornmaster.safetensors"})
    assert response.status_code in (200, 201)
    assert response.json()["avatar_filename"]


def test_avatar_edit_with_qwen(monkeypatch):
    profile = {"description": "Test", "personality_traits": "test", "tone_of_voice": "test", "boundaries": "test"}
    char = client.post("/api/characters", json={"name": "AvatarEdit", "profile": profile}).json()
    assert client.post(f"/api/characters/{char['id']}/avatar").status_code in (200, 201)
    before = client.get(f"/api/characters/{char['id']}").json()["avatar_filename"]
    monkeypatch.setattr("app.characters.qwen_image_edit", lambda path, prompt, **kwargs: (_avatar_png(), {}))
    response = client.post(
        f"/api/characters/{char['id']}/avatar/edit", json={"prompt": "same person, studio portrait"}
    )
    assert response.status_code in (200, 201), response.text
    after = response.json()["avatar_filename"]
    assert after and after != before


def test_avatar_edit_requires_avatar():
    profile = {"description": "Test", "personality_traits": "test", "tone_of_voice": "test", "boundaries": "test"}
    char = client.post("/api/characters", json={"name": "NoAvatar", "profile": profile}).json()
    response = client.post(f"/api/characters/{char['id']}/avatar/edit", json={"prompt": "x"})
    assert response.status_code == 400
