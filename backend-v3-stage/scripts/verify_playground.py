"""Verify real Ollama through the running playground. Uses temporary test records only."""

import os
import time
import uuid

import httpx

base = os.environ.get("VERIFY_URL", "http://127.0.0.1:8011")
key = os.environ.get("VERIFY_KEY", "v3-preview-only")
report = []
with httpx.Client(base_url=base, headers={"X-API-Key": key}, timeout=240) as api:

    def request(method, path, **kwargs):
        response = api.request(method, path, **kwargs)
        response.raise_for_status()
        return response.json()

    character = request(
        "POST",
        "/api/characters",
        json={
            "name": "QA v3 temporary",
            "profile": {
                "description": "Nora è una fotografa immaginaria adulta di 27 anni.",
                "personality_traits": "curiosa, ironica, propositiva",
                "language": "it",
                "tone_of_voice": "caldo, giocoso, flirt leggero",
                "speech_style": "messaggi brevi, naturali",
                "boundaries": "flirt non esplicito, rispetta i no",
            },
        },
    )
    fan_a = request(
        "POST",
        "/api/fans",
        json={"name": "QA Luca", "notes": "Private test note: should never enter the prompt"},
    )
    fan_b = request("POST", "/api/fans", json={"name": "QA Sofia"})
    try:
        conversation = request(
            "POST",
            f"/api/characters/{character['id']}/conversations",
            json={"model": "llama3.1:8b", "fan_id": fan_a["id"], "auto_greet": True},
        )
        assert not conversation.get("greeting_error"), conversation
        response = request(
            "POST",
            f"/api/conversations/{conversation['id']}/messages",
            json={"content": "Mi chiamo Luca. Il mio cane si chiama Milo e adoro ascoltare jazz."},
        )
        report.append(
            {
                "check": "real_chat",
                "model": response["model"],
                "seconds": response["ollama_metrics"]["request_seconds"],
            }
        )
        for _ in range(100):
            state = request("GET", f"/api/conversations/{conversation['id']}")
            if state["memory_status"] != "pending":
                break
            time.sleep(2)
        facts = request("GET", f"/api/characters/{character['id']}/memories", params={"fan_id": fan_a["id"]})
        assert any("Milo" in fact["content"] for fact in facts), (state["memory_status"], facts)
        assert (
            request("GET", f"/api/characters/{character['id']}/memories", params={"fan_id": fan_b["id"]})
            == []
        )
        report.append({"check": "memory_isolation", "facts": len(facts)})
        new_chat = request(
            "POST",
            f"/api/characters/{character['id']}/conversations",
            json={"model": "llama3.1:8b", "fan_id": fan_a["id"], "auto_greet": False},
        )
        recalled = request(
            "POST",
            f"/api/conversations/{new_chat['id']}/messages",
            json={"content": "Come si chiama il mio cane?"},
        )
        assert recalled["ollama_metrics"]["recalled_memory_ids"], recalled
        report.append(
            {
                "check": "recall_new_chat",
                "used_milo": "milo" in recalled["content"].lower(),
                "response": recalled["content"],
            }
        )
        batch = str(uuid.uuid4())
        for model in ("llama3.1:8b", "qwen3:30b"):
            result = request(
                "POST",
                "/api/benchmarks",
                json={
                    "batch_id": batch,
                    "character_id": character["id"],
                    "fan_id": fan_b["id"],
                    "model": model,
                    "prompt": "Ciao! Ho finito di lavorare. Sorprendimi con una proposta simpatica per staccare un po'.",
                },
            )
            assert result["error"] is None, result["error"]
            report.append(
                {
                    "check": "benchmark",
                    "model": model,
                    "seconds": result["metrics"]["request_seconds"],
                    "response": result["response"],
                }
            )
        enhanced = request(
            "POST",
            "/api/character-drafts/enhance",
            json={
                "name": character["name"],
                "profile": character["profile"],
                "model": "llama3.1:8b",
                "direction": "Arricchisci interessi e stile di scrittura. Rispondi in italiano.",
            },
        )
        assert enhanced["profile"]["description"]
        assert request("GET", f"/api/characters/{character['id']}")["version"] == 1
        report.append({"check": "enhance_draft", "seconds": enhanced["seconds"]})
    finally:
        # Clean up only records created by this script, never user records.
        request("DELETE", f"/api/characters/{character['id']}")
        request("DELETE", f"/api/fans/{fan_a['id']}")
        request("DELETE", f"/api/fans/{fan_b['id']}")
for item in report:
    print(item, flush=True)
print("REAL PLAYGROUND CHECKS PASSED", flush=True)
