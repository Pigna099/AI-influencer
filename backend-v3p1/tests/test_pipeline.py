from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

from fastapi.testclient import TestClient
from sqlalchemy import update

from app.db import Job, Session, now
from app.integrations.comfyui import parameterize
from app.main import app
from app.worker import claim_job, process_job

client = TestClient(app, headers={"X-API-Key": "test-key"})


def create():
    result = client.post(
        "/influencers", json={"name": "Demo", "bible": {"description": "Adult anime artist"}}
    )
    assert result.status_code == 201
    influencer = result.json()
    result = client.post(
        "/content-jobs", json={"influencer_id": influencer["id"], "theme": "A walk", "image_count": 2}
    )
    assert result.status_code == 202
    return influencer, result.json()


def test_pipeline_review_and_history():
    influencer, job = create()
    assert client.post(f"/content-jobs/{job['id']}/review", json={"decision": "approved"}).status_code == 409
    result = client.put(f"/influencers/{influencer['id']}/bible", json={"description": "Changed"})
    assert result.json()["version"] == 2
    assert len(client.get(f"/influencers/{influencer['id']}/versions").json()) == 2
    assert claim_job() == job["id"]
    assert claim_job() is None
    process_job(job["id"])
    data = client.get(f"/content-jobs/{job['id']}").json()
    assert data["job"]["status"] == "awaiting_review"
    assert data["job"]["character_snapshot"]["version"] == 1
    assert len(data["assets"]) == 2
    asset = client.get(f"/assets/{data['assets'][0]['id']}/file")
    assert asset.content.startswith(b"\x89PNG")
    assert client.post(f"/content-jobs/{job['id']}/review", json={"decision": "approved"}).status_code == 200
    assert client.post(f"/content-jobs/{job['id']}/review", json={"decision": "rejected"}).status_code == 409
    regenerated = client.post(f"/content-jobs/{job['id']}/regenerate").json()
    assert regenerated["id"] != job["id"]
    assert regenerated["character_snapshot"]["version"] == 1
    assert regenerated["request"]["seed"] == job["request"]["seed"] + 1


def test_auth_validation():
    assert TestClient(app).get("/influencers").status_code == 401
    assert client.post("/content-jobs", json={"influencer_id": "missing", "theme": "a"}).status_code == 404
    assert (
        client.post(
            "/content-jobs", json={"influencer_id": "missing", "theme": "a", "image_count": 5}
        ).status_code
        == 422
    )


def test_concurrent_claim():
    _, job = create()
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: claim_job(), range(2)))
    assert results.count(job["id"]) == 1


def test_error_and_stale_recovery(monkeypatch):
    _, job = create()
    claim_job()

    def fail(*args):
        raise RuntimeError("provider offline")

    monkeypatch.setattr("app.worker.generate_brief", fail)
    process_job(job["id"])
    assert client.get(f"/content-jobs/{job['id']}").json()["job"]["status"] == "failed"
    _, second = create()
    claim_job()
    with Session.begin() as db:
        db.execute(update(Job).where(Job.id == second["id"]).values(started_at=now() - timedelta(hours=1)))
    assert claim_job() is None
    assert client.get(f"/content-jobs/{second['id']}").json()["job"]["status"] == "failed"


def test_workflow_parameter_types():
    assert parameterize(
        {"inputs": ["{{seed}}", "{{positive_prompt}}"]},
        {"{{seed}}": 42, "{{positive_prompt}}": 'quotes " and \\ are safe'},
    ) == {"inputs": [42, 'quotes " and \\ are safe']}
