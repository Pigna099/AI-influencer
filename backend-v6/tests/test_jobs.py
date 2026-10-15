from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app, headers={"X-API-Key": "test-key"})
PROFILE = {
    "description": "jobs test",
    "appearance": "adult woman",
    "personality_traits": "calm",
    "tone_of_voice": "warm",
    "boundaries": "adults only",
}


def make_images_dir(name: str, count: int = 6):
    from app.config import settings

    folder = settings.media_dir.parent / "lorasets" / f"jobs-{name}"
    folder.mkdir(parents=True, exist_ok=True)
    for index in range(count):
        (folder / f"{index:03}.png").write_bytes(b"fake-image")
        (folder / f"{index:03}.txt").write_text("a photo of a woman")
    return folder


def make_lora(name="Jobs LoRA"):
    character = client.post("/api/characters", json={"name": name, "profile": PROFILE}).json()
    response = client.post(f"/api/characters/{character['id']}/loras", json={"name": f"{name} lora", "family": "real"})
    assert response.status_code == 201, response.text
    lora = response.json()
    return character, lora


def queue_training(lora_id, folder):
    response = client.post(f"/api/loras/{lora_id}/training-jobs", json={"images_dir": str(folder)})
    assert response.status_code == 201, response.text
    return response.json()


def test_training_job_mirrors_into_unified_jobs():
    _, lora = make_lora("Mirror")
    folder = make_images_dir("mirror")
    job = queue_training(lora["id"], folder)

    listing = client.get("/api/jobs", params={"type": "training"}).json()
    assert len(listing) == 1
    entry = listing[0]
    assert entry["state"] == "queued" and entry["external_id"] == job["id"]
    assert entry["character_id"] == lora["character_id"]
    assert entry["queue_position"] == 1

    claimed = client.post(f"/api/training-jobs/{job['id']}/claim", json={"worker": "test-host"})
    assert claimed.status_code == 200
    entry = client.get("/api/jobs", params={"type": "training"}).json()[0]
    assert entry["state"] == "running" and entry["worker"] == "test-host"

    client.post(f"/api/training-jobs/{job['id']}/progress", json={"progress": {"step": 30, "total": 120}})
    entry = client.get(f"/api/jobs/{entry['id']}").json()
    assert entry["progress"]["current"] == 30 and entry["progress"]["total"] == 120

    events = client.get(f"/api/jobs/{entry['id']}/events").json()
    messages = [event["message"] for event in events]
    assert any("started" in message for message in messages)


def test_job_cancel_and_retry_linkage():
    _, lora = make_lora("Retry")
    folder = make_images_dir("retry")
    job = queue_training(lora["id"], folder)

    entry = client.get("/api/jobs", params={"type": "training"}).json()[0]
    canceled = client.post(f"/api/jobs/{entry['id']}/cancel")
    assert canceled.status_code == 200 and canceled.json()["cancel_requested"] is True

    done = client.post(f"/api/training-jobs/{job['id']}/cancel")
    assert done.status_code == 200
    entry = client.get(f"/api/jobs/{entry['id']}").json()
    assert entry["state"] == "canceled"

    retry = client.post(f"/api/jobs/{entry['id']}/retry")
    assert retry.status_code == 201
    retried = retry.json()
    assert retried["retry_of"] == entry["id"] and retried["state"] == "queued"

    assert client.post(f"/api/jobs/{retried['id']}/retry").status_code == 409
    assert client.get("/api/jobs/does-not-exist").status_code == 404
    assert client.post("/api/jobs/does-not-exist/cancel").status_code == 404


def test_jobs_summary_and_filters():
    _, lora = make_lora("Summary")
    folder = make_images_dir("summary")
    job = queue_training(lora["id"], folder)

    summary = client.get("/api/jobs/summary").json()
    assert summary["active_count"] >= 1
    assert any(entry["external_id"] == job["id"] for entry in summary["active"])

    active = client.get("/api/jobs", params={"state": "active"}).json()
    assert all(entry["state"] in ("queued", "running") for entry in active)

    by_character = client.get("/api/jobs", params={"character_id": lora["character_id"]}).json()
    assert by_character and all(entry["character_id"] == lora["character_id"] for entry in by_character)

    assert client.get("/api/jobs", params={"state": "succeeded"}).json() == []

def test_job_pruning_removes_old_finished_jobs():
    from datetime import UTC, datetime, timedelta

    from app.db import ExecutionJob, Session
    from app.jobs import prune_finished_jobs

    _, lora = make_lora("Prune")
    folder = make_images_dir("prune")
    job = queue_training(lora["id"], folder)
    entry = client.get("/api/jobs", params={"type": "training"}).json()[0]
    client.post(f"/api/training-jobs/{job['id']}/cancel")

    with Session.begin() as db:
        stored = db.get(ExecutionJob, entry["id"])
        stored.finished_at = datetime.now(UTC) - timedelta(days=40)
        pruned = prune_finished_jobs(db)
    assert pruned >= 1
    assert client.get(f"/api/jobs/{entry['id']}").status_code == 404


def test_video_concurrency_guard_per_character():
    from app.db import Session
    from app.jobs import create_job, start_job

    character = client.post("/api/characters", json={"name": "Video Guard", "profile": PROFILE}).json()
    with Session.begin() as db:
        running = create_job(db, type="video", character_id=character["id"], message="busy")
        start_job(db, running)

    response = client.post(
        f"/api/characters/{character['id']}/videos",
        json={"prompt": "x", "mode": "text", "length": 49},
    )
    assert response.status_code == 409
    assert "already running" in response.json()["detail"]
