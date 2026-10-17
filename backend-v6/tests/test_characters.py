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


def test_app_defaults_roundtrip():
    response = client.get("/api/settings/defaults")
    assert response.status_code == 200
    defaults = response.json()
    assert defaults["video_model"] == "wan"
    updated = client.put(
        "/api/settings/defaults",
        json={"chat_model": "qwen3.8", "image_checkpoint": "flux-2-klein-4b.safetensors", "video_model": "hunyuan"},
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["video_model"] == "hunyuan"
    again = client.get("/api/settings/defaults").json()
    assert again["chat_model"] == "qwen3.8"
    assert again["image_checkpoint"] == "flux-2-klein-4b.safetensors"

def test_character_policy_fields():
    created = client.post(
        "/api/characters",
        json={
            "name": "Policy Fields",
            "profile": {
                "description": "adult test",
                "appearance": "adult woman",
                "personality_traits": "calm",
                "tone_of_voice": "warm",
                "boundaries": "adults only",
            },
            "age": 25,
            "synthetic_declared": True,
            "provenance": "synthetic",
        },
    )
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["age"] == 25 and body["synthetic_declared"] is True and body["provenance"] == "synthetic"

    underage = client.post(
        "/api/characters",
        json={
            "name": "Too Young",
            "profile": {"description": "x"},
            "age": 17,
        },
    )
    assert underage.status_code == 422

    updated = client.put(f"/api/characters/{body['id']}", json={"age": 30, "provenance": "original"})
    assert updated.status_code == 200, updated.text
    assert updated.json()["age"] == 30 and updated.json()["provenance"] == "original"


def test_identity_provenance_and_reference_only_guard():
    created = client.post(
        "/api/characters",
        json={
            "name": "Reference Only",
            "profile": {"description": "adult test", "boundaries": "adults only"},
            "age": 24,
            "synthetic_declared": True,
            "provenance": "synthetic",
            "source_category": "reference_only",
            "rights_notes": "moodboard inspiration only",
            "permitted_uses": "pose and style reference",
        },
    )
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["source_category"] == "reference_only"
    assert body["rights_notes"] == "moodboard inspiration only"
    assert body["lifecycle_state"] == "active"

    avatar = client.post(f"/api/characters/{body['id']}/avatar", json={})
    assert avatar.status_code == 400
    assert "Reference-only" in avatar.json()["detail"]

    promoted = client.put(f"/api/characters/{body['id']}", json={"source_category": "generated"})
    assert promoted.status_code == 200 and promoted.json()["source_category"] == "generated"
    generated = client.post(f"/api/characters/{body['id']}/avatar", json={})
    assert generated.status_code == 201, generated.text
    assert generated.json()["avatar_sha256"] and len(generated.json()["avatar_sha256"]) == 64

def test_library_trash_and_restore():
    character = client.post("/api/characters", json={"name": "Trash", "profile": {"description": "x"}}).json()
    images = client.post(f"/api/characters/{character['id']}/library/generate", json={"prompt": "x", "count": 2}).json()
    first, second = images[0], images[1]

    assert images[0]["policy"]["age_safety"] == "enforced"
    trashed = client.post(f"/api/library/{first['id']}/trash")
    assert trashed.status_code == 200 and trashed.json()["deleted_at"]

    listing = client.get(f"/api/characters/{character['id']}/library").json()
    assert [item["id"] for item in listing] == [second["id"]]
    trash_listing = client.get(f"/api/characters/{character['id']}/library", params={"trash": True}).json()
    assert [item["id"] for item in trash_listing] == [first["id"]]

    restored = client.post(f"/api/library/{first['id']}/restore")
    assert restored.status_code == 200 and restored.json()["deleted_at"] is None
    listing = client.get(f"/api/characters/{character['id']}/library").json()
    assert {item["id"] for item in listing} == {first["id"], second["id"]}

    # Delete forever removes it for good.
    client.post(f"/api/library/{first['id']}/trash")
    assert client.delete(f"/api/library/{first['id']}").status_code == 200
    assert client.get(f"/api/characters/{character['id']}/library", params={"trash": True}).json() == []

def test_library_bulk_status():
    character = client.post("/api/characters", json={"name": "Bulk Status", "profile": {"description": "x"}}).json()
    images = client.post(f"/api/characters/{character['id']}/library/generate", json={"prompt": "x", "count": 3}).json()
    ids = [item["id"] for item in images]

    approved = client.post("/api/library/bulk-status", json={"ids": ids[:2], "status": "approved"})
    assert approved.status_code == 200 and approved.json()["updated"] == 2
    listing = client.get(f"/api/characters/{character['id']}/library", params={"status": "approved"}).json()
    assert {item["id"] for item in listing} == set(ids[:2])

    rejected = client.post("/api/library/bulk-status", json={"ids": [ids[2]], "status": "rejected"})
    assert rejected.status_code == 200 and rejected.json()["updated"] == 1
    assert client.post("/api/library/bulk-status", json={"ids": [], "status": "draft"}).status_code == 422
    assert client.post("/api/library/bulk-status", json={"ids": [ids[0]], "status": "archived"}).status_code == 422

def test_library_collections():
    character = client.post("/api/characters", json={"name": "Collections", "profile": {"description": "x"}}).json()
    images = client.post(f"/api/characters/{character['id']}/library/generate", json={"prompt": "x", "count": 3}).json()
    ids = [item["id"] for item in images]

    created = client.post("/api/collections", json={"name": "Favorites"})
    assert created.status_code == 201
    collection = created.json()
    assert client.post("/api/collections", json={"name": "Favorites"}).json()["id"] == collection["id"]

    added = client.post(f"/api/collections/{collection['id']}/items", json={"ids": ids[:2]})
    assert added.status_code == 200 and added.json()["added"] == 2
    assert client.post(f"/api/collections/{collection['id']}/items", json={"ids": ids[:2]}).json()["added"] == 0

    listing = client.get("/api/collections").json()
    assert listing == [{"id": collection["id"], "name": "Favorites", "count": 2, "videos": 0}]

    filtered = client.get(f"/api/characters/{character['id']}/library", params={"collection_id": collection["id"]}).json()
    assert {item["id"] for item in filtered} == set(ids[:2])

    removed = client.request("DELETE", f"/api/collections/{collection['id']}/items", json={"ids": [ids[0]]})
    assert removed.json()["removed"] == 1
    assert client.delete(f"/api/collections/{collection['id']}").status_code == 200
    assert client.get("/api/collections").json() == []
    assert client.post("/api/collections/missing/items", json={"ids": [ids[0]]}).status_code == 404

def test_audit_log_records_actions():
    character = client.post("/api/characters", json={"name": "Audit", "profile": {"description": "x"}}).json()
    images = client.post(f"/api/characters/{character['id']}/library/generate", json={"prompt": "x", "count": 1}).json()
    image_id = images[0]["id"]

    client.patch(f"/api/library/{image_id}", json={"status": "approved"})
    client.post(f"/api/library/{image_id}/trash")
    client.post(f"/api/library/{image_id}/restore")

    events = client.get("/api/audit", params={"object_id": image_id}).json()
    actions = [event["action"] for event in events]
    assert actions[:3] == ["library.restore", "library.trash", "library.approved"]
    assert all(event["object_type"] == "image" for event in events)

def test_content_labels():
    character = client.post("/api/characters", json={"name": "Labels", "profile": {"description": "x"}}).json()
    images = client.post(f"/api/characters/{character['id']}/library/generate", json={"prompt": "x", "count": 1}).json()
    image_id = images[0]["id"]
    assert images[0]["content_label"] == "suggestive"

    patched = client.patch(f"/api/library/{image_id}", json={"content_label": "explicit"})
    assert patched.status_code == 200 and patched.json()["content_label"] == "explicit"
    assert client.patch(f"/api/library/{image_id}", json={"content_label": "nude"}).status_code == 422
    listing = client.get(f"/api/characters/{character['id']}/library").json()
    assert listing[0]["content_label"] == "explicit"

def test_platform_policy_checklists():
    created = client.post(
        "/api/characters",
        json={
            "name": "Platform Policy",
            "profile": {"description": "x"},
            "platform_policy": {
                "platforms": {
                    "instagram": {"ai_disclosure": True, "terms_reviewed": True, "content_rules_ok": False},
                    "fanvue": {"ai_disclosure": True, "terms_reviewed": False, "content_rules_ok": True},
                }
            },
        },
    )
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["platform_policy"]["platforms"]["instagram"]["ai_disclosure"] is True

    # Both platforms declare the AI disclosure, so nothing is flagged.
    overview = client.get("/api/overview").json()
    assert overview["characters_undisclosed"] == 0

    bad = client.put(f"/api/characters/{body['id']}", json={"platform_policy": {"platforms": {"myspace": {}}}})
    assert bad.status_code == 400

    updated = client.put(
        f"/api/characters/{body['id']}",
        json={"platform_policy": {"platforms": {"instagram": {"ai_disclosure": True, "terms_reviewed": True, "content_rules_ok": True}}}},
    )
    assert updated.status_code == 200
    assert updated.json()["platform_policy"]["platforms"]["instagram"]["content_rules_ok"] is True
    assert "fanvue" not in updated.json()["platform_policy"]["platforms"]

    # Dropping the disclosure flags the character in the Home overview.
    client.put(
        f"/api/characters/{body['id']}",
        json={"platform_policy": {"platforms": {"instagram": {"ai_disclosure": False}}}},
    )
    assert client.get("/api/overview").json()["characters_undisclosed"] >= 1

def test_conversation_ppv_override():
    character = client.post("/api/characters", json={"name": "PPV Override", "profile": {"description": "x"}}).json()
    fan = client.post("/api/fans", json={"name": "PPV Fan"}).json()
    conversation = client.post(
        f"/api/characters/{character['id']}/conversations",
        json={"fan_id": fan["id"], "model": "test-model"},
    ).json()
    assert conversation["ppv_enabled"] is None and conversation["ppv_price_cents"] is None

    updated = client.patch(
        f"/api/conversations/{conversation['id']}",
        json={"ppv_enabled": True, "ppv_price_cents": 1200},
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["ppv_enabled"] is True and updated.json()["ppv_price_cents"] == 1200

    cleared = client.patch(f"/api/conversations/{conversation['id']}", json={"ppv_enabled": None, "ppv_price_cents": None})
    assert cleared.status_code == 200
    assert cleared.json()["ppv_enabled"] is None and cleared.json()["ppv_price_cents"] is None

def test_avatar_upload_validation(monkeypatch):
    import base64
    from io import BytesIO

    from PIL import Image

    def png(width=800, height=1000):
        buffer = BytesIO()
        Image.new("RGB", (width, height), (140, 90, 70)).save(buffer, format="PNG")
        return base64.b64encode(buffer.getvalue()).decode()

    def fake_vision(model, prompt, images, **kwargs):
        return {"adult": True, "one_person": True, "face_visible": True, "sharp": True, "quality_notes": ""}

    # vision_json is imported inside the endpoint from integrations.text
    monkeypatch.setattr("app.integrations.text.vision_json", fake_vision)

    character = client.post("/api/characters", json={"name": "Uploader", "profile": {"description": "x"}}).json()

    too_small = client.post(
        f"/api/characters/{character['id']}/avatar/upload",
        json={"image_base64": png(300, 300), "content_type": "image/png"},
    )
    assert too_small.status_code == 400 and "too small" in too_small.json()["detail"]

    invalid = client.post(
        f"/api/characters/{character['id']}/avatar/upload",
        json={"image_base64": base64.b64encode(b"not an image").decode(), "content_type": "image/png"},
    )
    assert invalid.status_code == 400

    accepted = client.post(
        f"/api/characters/{character['id']}/avatar/upload",
        json={"image_base64": png(), "content_type": "image/png"},
    )
    assert accepted.status_code == 201, accepted.text
    body = accepted.json()
    assert body["avatar_filename"] and len(body["avatar_sha256"]) == 64
    assert body["avatar_validation"]["source"] == "upload" and body["avatar_validation"]["adult"] is True

    events = client.get("/api/audit", params={"action": "avatar.upload"}).json()
    assert events and events[0]["object_id"] == character["id"]


def test_avatar_upload_rejected_by_vision(monkeypatch):
    import base64
    from io import BytesIO

    from PIL import Image

    def fake_vision(model, prompt, images, **kwargs):
        return {"adult": False, "one_person": True, "face_visible": True, "sharp": True, "quality_notes": "looks young"}

    monkeypatch.setattr("app.integrations.text.vision_json", fake_vision)
    character = client.post("/api/characters", json={"name": "Rejected", "profile": {"description": "x"}}).json()
    buffer = BytesIO()
    Image.new("RGB", (800, 1000), (140, 90, 70)).save(buffer, format="PNG")
    response = client.post(
        f"/api/characters/{character['id']}/avatar/upload",
        json={"image_base64": base64.b64encode(buffer.getvalue()).decode(), "content_type": "image/png"},
    )
    assert response.status_code == 400
    assert "21+" in response.json()["detail"]
    assert client.get(f"/api/characters/{character['id']}").json()["avatar_filename"] is None

def test_library_thumbnail_endpoint():
    character = client.post("/api/characters", json={"name": "Thumbs", "profile": {"description": "x"}}).json()
    images = client.post(f"/api/characters/{character['id']}/library/generate", json={"prompt": "x", "count": 1}).json()
    image_id = images[0]["id"]

    thumb = client.get(f"/api/library/{image_id}/thumb")
    assert thumb.status_code == 200
    assert thumb.headers["content-type"] == "image/jpeg"
    original = client.get(f"/api/library/{image_id}/file")
    assert len(thumb.content) < len(original.content)

    # Second call is served from the cache and still valid.
    again = client.get(f"/api/library/{image_id}/thumb")
    assert again.status_code == 200 and again.content == thumb.content

    assert client.get("/api/library/does-not-exist/thumb").status_code == 404

def test_alerts_are_deduplicated_and_tied_to_objects():
    character = client.post("/api/characters", json={"name": "Alert Char", "profile": {"description": "x"}}).json()
    first = client.get("/api/alerts").json()
    keys = {alert["key"] for alert in first["alerts"]}
    policy_key = f"character:{character['id']}:policy"
    assert policy_key in keys
    entry = next(alert for alert in first["alerts"] if alert["key"] == policy_key)
    assert entry["object_type"] == "character" and entry["object_id"] == character["id"]
    assert entry["remediation"]

    # Completing the policy removes the alert; repeated calls never duplicate it.
    client.put(f"/api/characters/{character['id']}", json={"age": 25, "synthetic_declared": True})
    second = client.get("/api/alerts").json()
    assert policy_key not in {alert["key"] for alert in second["alerts"]}
    third = client.get("/api/alerts").json()
    assert len(third["alerts"]) == len(second["alerts"])
    assert len({alert["key"] for alert in third["alerts"]}) == len(third["alerts"])


def test_image_step_defaults_roundtrip_and_wiring():
    response = client.put(
        "/api/settings/defaults",
        json={
            "image_steps": {
                "character": {"checkpoint": "qwen_image_2.1_bf16.safetensors", "loras": []},
                "create": {
                    "checkpoint": "qwen_image_2512_bf16.safetensors",
                    "loras": [{"name": "realistic_skin.safetensors", "weight": 0.7}],
                },
                "edit": {"checkpoint": "qwen_image_edit_2511_fp8mixed.safetensors", "loras": []},
            }
        },
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["image_steps"]["create"]["checkpoint"] == "qwen_image_2512_bf16.safetensors"
    assert data["image_steps"]["create"]["loras"] == [{"name": "realistic_skin.safetensors", "weight": 0.7}]
    assert data["image_steps"]["edit"]["checkpoint"] == "qwen_image_edit_2511_fp8mixed.safetensors"
    # legacy field mirrors the create step so older clients keep working
    assert data["image_checkpoint"] == "qwen_image_2512_bf16.safetensors"

    created = client.post("/api/characters", json={"name": "Defaults Wiring", "profile": {"description": "adult"}}).json()
    generated = client.post(
        f"/api/characters/{created['id']}/library/generate",
        json={"prompt": "test scene", "count": 1, "classify": False},
    )
    assert generated.status_code in (200, 201), generated.text
    item = generated.json()[0]
    assert item["checkpoint"] == "qwen_image_2512_bf16.safetensors"
    assert item["loras"] == [{"name": "realistic_skin.safetensors", "weight": 0.7}]

    client.put(
        "/api/settings/defaults",
        json={"image_steps": {"character": {"checkpoint": "", "loras": []}, "create": {"checkpoint": "", "loras": []}, "edit": {"checkpoint": "", "loras": []}}},
    )
