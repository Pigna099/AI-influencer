from datetime import timedelta

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.chat_service import build_context
from app.db import BenchmarkSample, ChatMessage, Conversation, Memory, Session, now
from app.integrations.ollama import OllamaNotAvailable
from app.main import app

client = TestClient(app, headers={"X-API-Key": "test-key"})


def setup_pair():
    character = client.post(
        "/api/characters",
        json={
            "name": "Nora",
            "profile": {
                "description": "Adult fictional photographer",
                "language": "it",
                "vocabulary": "test-voice",
            },
        },
    ).json()
    fan_a = client.post("/api/fans", json={"name": "Luca", "notes": "SECRET-ANSWER-KEY"}).json()
    fan_b = client.post("/api/fans", json={"name": "Sofia"}).json()
    return character, fan_a, fan_b


def conversation(character, fan):
    result = client.post(
        f"/api/characters/{character['id']}/conversations",
        json={"model": "llama3.1:8b", "fan_id": fan["id"], "auto_greet": False},
    )
    assert result.status_code == 201, result.text
    return result.json()


def add_memory(character, fan, content):
    result = client.post(
        f"/api/characters/{character['id']}/memories?fan_id={fan['id']}",
        json={"content": content, "category": "personal_fact", "importance": 4},
    )
    assert result.status_code == 201
    return result.json()


def test_memory_isolation_across_fans_characters_and_new_chats():
    char, a, b = setup_pair()
    add_memory(char, a, "Luca's dog is Milo")
    add_memory(char, b, "Sofia's cat is Nori")
    conv_a = conversation(char, a)
    conv_b = conversation(char, b)
    with Session() as db:
        prompt_a, _ = build_context(db.get(Conversation, conv_a["id"]), "pet")
        prompt_b, _ = build_context(db.get(Conversation, conv_b["id"]), "pet")
    assert "Milo" in prompt_a[0]["content"] and "Nori" not in prompt_a[0]["content"]
    assert "Nori" in prompt_b[0]["content"] and "Milo" not in prompt_b[0]["content"]
    assert "SECRET-ANSWER-KEY" not in prompt_a[0]["content"]
    assert "test-voice" in prompt_a[0]["content"]
    char2 = client.post(
        "/api/characters", json={"name": "Another", "profile": {"description": "Adult"}}
    ).json()
    other = conversation(char2, a)
    with Session() as db:
        context, _ = build_context(db.get(Conversation, other["id"]), "pet")
    assert "Milo" not in context[0]["content"]
    assert len(client.get(f"/api/characters/{char['id']}/conversations?fan_id={a['id']}").json()) == 1
    client.delete(f"/api/characters/{char['id']}/memories?fan_id={a['id']}")
    assert len(client.get(f"/api/characters/{char['id']}/memories?fan_id={b['id']}").json()) == 1


def test_reply_persistence_failure_retry_and_lease(monkeypatch):
    char, a, _ = setup_pair()
    conv = conversation(char, a)

    def failure(*args, **kwargs):
        raise OllamaNotAvailable("offline")

    monkeypatch.setattr("app.characters.generate_reply", failure)
    response = client.post(f"/api/conversations/{conv['id']}/messages", json={"content": "hello"})
    assert response.status_code == 503
    assert client.get(f"/api/conversations/{conv['id']}/messages").json() == []
    assert client.get(f"/api/conversations/{conv['id']}").json()["busy_until"] is None
    monkeypatch.setattr(
        "app.characters.generate_reply",
        lambda *args, **kwargs: ("Hi", {"request_seconds": 1.2, "kind": "reply"}),
    )
    assert (
        client.post(f"/api/conversations/{conv['id']}/messages", json={"content": "hello"}).status_code == 200
    )
    messages = client.get(f"/api/conversations/{conv['id']}/messages").json()
    assert [m["role"] for m in messages] == ["user", "assistant"]
    assert messages[0]["created_at"].endswith("+00:00") or messages[0]["created_at"].endswith("Z")
    with Session.begin() as db:
        db.get(Conversation, conv["id"]).busy_until = now() + timedelta(minutes=2)
    assert (
        client.post(f"/api/conversations/{conv['id']}/messages", json={"content": "another"}).status_code
        == 409
    )
    assert client.delete(f"/api/characters/{char['id']}").status_code == 409


def test_proactive_and_actual_cascade_deletion():
    char, a, _ = setup_pair()
    conv = conversation(char, a)
    add_memory(char, a, "Likes jazz")
    result = client.post(
        f"/api/conversations/{conv['id']}/initiate", json={"kind": "reengage", "absence_hours": 48}
    )
    assert result.status_code == 200
    assert result.json()["ollama_metrics"]["kind"] == "reengage"
    assert len(client.get(f"/api/conversations/{conv['id']}/messages").json()) == 1
    assert client.delete(f"/api/characters/{char['id']}").status_code == 200
    with Session() as db:
        assert list(db.scalars(select(ChatMessage))) == []
        assert list(db.scalars(select(Memory))) == []
        assert list(db.scalars(select(Conversation))) == []


def test_extraction_tracks_user_source_and_scopes(monkeypatch):
    char, a, b = setup_pair()
    conv = conversation(char, a)
    from app.chat_service import extract_memories
    from app.config import settings

    with Session.begin() as db:
        source = ChatMessage(conversation_id=conv["id"], role="user", content="I have a dog named Milo")
        db.add(source)
        db.flush()
    monkeypatch.setattr(settings, "text_provider", "ollama")
    monkeypatch.setattr(
        "app.chat_service.chat",
        lambda *args, **kwargs: {
            "message": {
                "content": '{"memories":[{"content":"Dog named Milo","category":"personal_fact","importance":4}]}'
            }
        },
    )
    extract_memories(conv["id"], source.id)
    new_a = conversation(char, a)
    new_b = conversation(char, b)
    with Session() as db:
        prompt_a, _ = build_context(db.get(Conversation, new_a["id"]), "pet")
        prompt_b, _ = build_context(db.get(Conversation, new_b["id"]), "pet")
    assert "I have a dog named Milo" in prompt_a[0]["content"]
    assert "I have a dog named Milo" not in prompt_b[0]["content"]
    memories = client.get(f"/api/characters/{char['id']}/memories?fan_id={a['id']}").json()
    assert len(memories) == 1 and memories[0]["source_message_id"] == source.id
    assert client.get(f"/api/characters/{char['id']}/memories?fan_id={b['id']}").json() == []


def test_benchmark_freezes_context_and_keeps_chat_clean(monkeypatch):
    char, a, _ = setup_pair()
    body = {
        "batch_id": "batch-a",
        "character_id": char["id"],
        "fan_id": a["id"],
        "model": "llama3.1:8b",
        "prompt": "Hello",
        "temperature": 0.7,
    }
    first = client.post("/api/benchmarks", json=body)
    assert first.status_code == 201, first.text
    add_memory(char, a, "new fact after benchmark started")
    second = client.post("/api/benchmarks", json=body)
    assert second.json()["metrics"]["context_messages"] == first.json()["metrics"]["context_messages"]
    assert client.post("/api/benchmarks", json={**body, "prompt": "different"}).status_code == 409
    assert client.get(f"/api/characters/{char['id']}/conversations").json() == []

    def failure(*args, **kwargs):
        raise OllamaNotAvailable("offline")

    monkeypatch.setattr("app.characters.measured_chat", failure)
    third = client.post("/api/benchmarks", json=body)
    assert third.status_code == 201 and third.json()["error"] == "offline"
    with Session() as db:
        assert len(list(db.scalars(select(BenchmarkSample)))) == 3


def test_enhance_draft_does_not_save_and_auth():
    char, _, _ = setup_pair()
    result = client.post(
        "/api/character-drafts/enhance",
        json={"name": char["name"], "profile": char["profile"], "model": "llama3.1:8b"},
    )
    assert result.status_code == 200
    assert client.get(f"/api/characters/{char['id']}").json()["version"] == 1
    assert (
        TestClient(app)
        .post("/influencers", json={"name": "test", "bible": {"description": "test"}})
        .status_code
        == 401
    )
    assert TestClient(app).get("/api/fans").status_code == 401
