import os
from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient

from app.config import settings
from app.main import app

client = TestClient(app, headers={"X-API-Key": "test-key"})
PROFILE = {
    "description": "reconcile test",
    "appearance": "adult woman",
    "personality_traits": "calm",
    "tone_of_voice": "warm",
    "boundaries": "adults only",
}


def _old_file(name: str) -> None:
    path = settings.media_dir / name
    path.write_bytes(b"orphan")
    old = (datetime.now(UTC) - timedelta(days=2)).timestamp()
    os.utime(path, (old, old))


def test_reconcile_reports_and_deletes_orphans():
    from app.db import ImageLibrary, Session

    character = client.post("/api/characters", json={"name": "Reconcile", "profile": PROFILE}).json()
    images = client.post(f"/api/characters/{character['id']}/library/generate", json={"prompt": "x", "count": 1}).json()
    assert images and images[0]["id"]

    # Fresh unreferenced file: too new to be treated as orphan.
    _old_file("recent-orphan.png")
    path = settings.media_dir / "recent-orphan.png"
    os.utime(path, None)

    # Old unreferenced file: an orphan.
    _old_file("old-orphan.png")

    # Old file referenced by a record: not an orphan.
    with Session.begin() as db:
        db.add(ImageLibrary(character_id=character["id"], filename="kept.png", sha256="kept-hash", status="draft", prompt="kept"))
    _old_file("kept.png")

    report = client.post("/api/system/reconcile").json()
    assert report["orphans"] == 1
    assert report["sample"] == ["old-orphan.png"]
    assert (settings.media_dir / "old-orphan.png").is_file()

    deleted = client.post("/api/system/reconcile", params={"delete": True}).json()
    assert deleted["removed"] == 1 and deleted["freed_bytes"] > 0
    assert not (settings.media_dir / "old-orphan.png").is_file()
    assert (settings.media_dir / "kept.png").is_file()
    assert (settings.media_dir / "recent-orphan.png").is_file()
