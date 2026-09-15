from io import BytesIO

from fastapi.testclient import TestClient
from PIL import Image

from app.config import settings
from app.main import app

client = TestClient(app, headers={"X-API-Key": "test-key"})
public_client = TestClient(app)


def png_bytes():
    buffer = BytesIO()
    Image.new("RGB", (48, 64), (20, 30, 40)).save(buffer, format="PNG")
    return buffer.getvalue()


def seed_dataset_image(monkeypatch, name="Pose dataset"):
    data = png_bytes()
    monkeypatch.setattr("app.dataset.download_image", lambda url: (data, ".png"))
    created = client.post(
        "/api/dataset/sources",
        json={
            "name": name,
            "kind": "urls",
            "reference": "https://example.com/a.png",
            "limit": 10,
            "classify": False,
        },
    )
    source_id = created.json()["id"]
    images = client.get(f"/api/dataset/images?source_id={source_id}").json()
    return source_id, images[0]["id"]


def test_poses_require_auth():
    assert public_client.get("/api/poses").status_code == 401
    assert public_client.post("/api/poses/extract", json={}).status_code == 401


def test_pose_extract_list_patch_delete(monkeypatch):
    monkeypatch.setattr("app.pose_api.extract_pose", lambda path, resolution=1024: png_bytes())
    _, image_id = seed_dataset_image(monkeypatch)
    created = client.post(
        "/api/poses/extract",
        json={
            "source": "dataset",
            "source_image_id": image_id,
            "name": "Standing",
            "tags": ["Standing", " front "],
        },
    )
    assert created.status_code == 201, created.text
    pose = created.json()
    assert pose["name"] == "Standing"
    assert pose["tags"] == ["standing", "front"]
    assert pose["active"] is True and pose["keypoint_count"] == 0

    skeleton = settings.pose_dir / pose["skeleton_filename"]
    assert skeleton.is_file()

    listing = client.get("/api/poses").json()
    assert [item["id"] for item in listing] == [pose["id"]]
    assert client.get("/api/poses", params={"tag": "front"}).json()[0]["id"] == pose["id"]
    assert client.get("/api/poses", params={"tag": "missing"}).json() == []

    served = client.get(f"/api/poses/{pose['id']}/skeleton")
    assert served.status_code == 200 and served.content.startswith(b"\x89PNG")
    source = client.get(f"/api/poses/{pose['id']}/source")
    assert source.status_code == 200 and source.content.startswith(b"\x89PNG")

    patched = client.patch(
        f"/api/poses/{pose['id']}", json={"name": "Standing pose", "active": False}
    ).json()
    assert patched["name"] == "Standing pose" and patched["active"] is False
    assert client.get("/api/poses", params={"active_only": True}).json() == []

    assert client.delete(f"/api/poses/{pose['id']}").json()["deleted"] is True
    assert not skeleton.exists()
    assert client.get(f"/api/poses/{pose['id']}").status_code == 404


def test_pose_extract_unknown_image(monkeypatch):
    monkeypatch.setattr("app.pose_api.extract_pose", lambda path, resolution=1024: png_bytes())
    response = client.post(
        "/api/poses/extract", json={"source": "dataset", "source_image_id": "missing"}
    )
    assert response.status_code == 404


def test_pose_extract_comfyui_failure(monkeypatch):
    from app.integrations.comfyui import ComfyUIError

    def boom(path, resolution=1024):
        raise ComfyUIError("ComfyUI non è raggiungibile: avvia il servizio immagini")

    monkeypatch.setattr("app.pose_api.extract_pose", boom)
    _, image_id = seed_dataset_image(monkeypatch, name="Pose failure")
    response = client.post(
        "/api/poses/extract", json={"source": "dataset", "source_image_id": image_id}
    )
    assert response.status_code == 502
    assert "Estrazione posa non riuscita" in response.json()["detail"]


def test_library_generate_with_pose(monkeypatch):
    monkeypatch.setattr("app.pose_api.extract_pose", lambda path, resolution=1024: png_bytes())
    _, image_id = seed_dataset_image(monkeypatch, name="Pose gen")
    pose = client.post(
        "/api/poses/extract", json={"source": "dataset", "source_image_id": image_id}
    ).json()
    profile = {"description": "d", "personality_traits": "t", "tone_of_voice": "t", "boundaries": "b"}
    character = client.post("/api/characters", json={"name": "PoseGen", "profile": profile}).json()

    response = client.post(
        f"/api/characters/{character['id']}/library/generate",
        json={"prompt": "standing", "count": 1, "pose_ids": [pose["id"]], "classify": False},
    )
    assert response.status_code == 201, response.text
    assert response.json()[0]["status"] == "draft"

    missing = client.post(
        f"/api/characters/{character['id']}/library/generate",
        json={"prompt": "standing", "count": 1, "pose_ids": ["missing"], "classify": False},
    )
    assert missing.status_code == 404
