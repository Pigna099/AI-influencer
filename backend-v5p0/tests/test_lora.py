from pathlib import Path

from fastapi.testclient import TestClient

from app.config import settings
from app.main import app

client = TestClient(app, headers={"X-API-Key": "test-key"})
public_client = TestClient(app)

PROFILE = {
    "description": "A friendly AI influencer",
    "personality_traits": "cheerful, helpful",
    "tone_of_voice": "warm",
    "boundaries": "No adult content",
}


def make_character(name="LoRA Character"):
    response = client.post("/api/characters", json={"name": name, "profile": PROFILE})
    assert response.status_code == 201
    return response.json()["id"]


def make_images_dir(name="anna"):
    path = settings.media_dir.parent / "lorasets" / name
    path.mkdir(parents=True, exist_ok=True)
    (path / "001.png").write_bytes(b"fake-image")
    (path / "001.txt").write_text("a photo of a woman")
    return path


def make_lora(character_id, name="Anna Real", family="real", trigger=None):
    body = {"name": name, "family": family}
    if trigger is not None:
        body["trigger"] = trigger
    response = client.post(f"/api/characters/{character_id}/loras", json=body)
    assert response.status_code == 201, response.text
    return response.json()


def queue_job(lora_id, images_dir):
    response = client.post(f"/api/loras/{lora_id}/training-jobs", json={"images_dir": str(images_dir)})
    assert response.status_code == 201, response.text
    return response.json()


def complete_job(job, success=True, error=None):
    body = {"success": success, "error": error}
    if success:
        artifact = settings.lora_dir / job["params"]["artifact_filename"]
        artifact.parent.mkdir(parents=True, exist_ok=True)
        artifact.write_bytes(b"fake-lora")
        body["filename"] = job["params"]["filename"]
        body["artifact_filename"] = job["params"]["artifact_filename"]
        body["metrics"] = {"final_loss": 0.08, "steps": 1200}
    response = client.post(f"/api/training-jobs/{job['id']}/complete", json=body)
    assert response.status_code == 200, response.text
    return response.json()


def test_lora_auth_required():
    assert public_client.get("/api/characters/whatever/loras").status_code == 401
    assert public_client.get("/api/training-jobs").status_code == 401


def test_create_and_list_loras():
    character_id = make_character()
    lora = make_lora(character_id)
    assert lora["status"] == "draft"
    assert lora["family"] == "real"
    assert lora["trigger"]

    listing = client.get(f"/api/characters/{character_id}/loras")
    assert listing.status_code == 200
    assert [item["id"] for item in listing.json()] == [lora["id"]]


def test_trigger_conflict():
    character_id = make_character("Trigger Test")
    make_lora(character_id, name="First", trigger="anna_abc123")
    response = client.post(
        f"/api/characters/{character_id}/loras",
        json={"name": "Second", "family": "real", "trigger": "anna_abc123"},
    )
    assert response.status_code == 409


def test_queue_claim_progress_complete():
    character_id = make_character("Full Cycle")
    lora = make_lora(character_id)
    images_dir = make_images_dir()
    job = queue_job(lora["id"], images_dir)
    assert job["status"] == "queued"
    assert job["params"]["trigger"] == lora["trigger"]
    assert job["params"]["filename"].startswith("ai_influencer/")
    assert job["lora"]["status"] == "queued"

    claimed = client.post(f"/api/training-jobs/{job['id']}/claim", json={"worker": "test-host"})
    assert claimed.status_code == 200
    assert claimed.json()["status"] == "running"
    assert claimed.json()["lora"]["status"] == "training"
    assert claimed.json()["worker"] == "test-host"

    progress = client.post(
        f"/api/training-jobs/{job['id']}/progress", json={"progress": {"step": 300, "total": 1200}}
    )
    assert progress.status_code == 200
    assert progress.json()["progress"]["step"] == 300

    done = complete_job(job)
    assert done["status"] == "succeeded"
    assert done["lora"]["status"] == "ready"
    assert done["lora"]["is_active"] is True
    assert done["lora"]["filename"] == job["params"]["filename"]
    assert done["lora"]["metrics"]["final_loss"] == 0.08


def test_second_lora_requires_activation():
    character_id = make_character("Two Versions")
    images_dir = make_images_dir("two")
    first = make_lora(character_id, name="Anna V1")
    second = make_lora(character_id, name="Anna V2")
    first_done = complete_job(queue_job(first["id"], images_dir))
    assert first_done["lora"]["is_active"] is True
    second_done = complete_job(queue_job(second["id"], images_dir))
    assert second_done["lora"]["is_active"] is False

    activated = client.post(f"/api/loras/{second['id']}/activate")
    assert activated.status_code == 200
    assert activated.json()["is_active"] is True
    refreshed = client.get(f"/api/loras/{first['id']}").json()
    assert refreshed["is_active"] is False


def test_activate_requires_ready():
    character_id = make_character("Not Ready")
    lora = make_lora(character_id)
    assert client.post(f"/api/loras/{lora['id']}/activate").status_code == 409


def test_queue_conflict_and_cancel():
    character_id = make_character("Cancel Flow")
    lora = make_lora(character_id)
    job = queue_job(lora["id"], make_images_dir("cancel"))
    conflict = client.post(f"/api/loras/{lora['id']}/training-jobs", json={"images_dir": str(make_images_dir("cancel"))})
    assert conflict.status_code == 409

    canceled = client.post(f"/api/training-jobs/{job['id']}/cancel")
    assert canceled.status_code == 200
    assert canceled.json()["status"] == "canceled"
    assert canceled.json()["lora"]["status"] == "draft"


def test_complete_failure_marks_lora_failed():
    character_id = make_character("Failure Flow")
    lora = make_lora(character_id)
    job = queue_job(lora["id"], make_images_dir("failure"))
    client.post(f"/api/training-jobs/{job['id']}/claim", json={"worker": "test-host"})
    failed = complete_job(job, success=False, error="CUDA out of memory")
    assert failed["status"] == "failed"
    assert failed["lora"]["status"] == "failed"
    assert failed["lora"]["error"] == "CUDA out of memory"


def test_delete_lora_keeps_job_history():
    character_id = make_character("Delete Flow")
    lora = make_lora(character_id)
    job = queue_job(lora["id"], make_images_dir("delete"))
    client.post(f"/api/training-jobs/{job['id']}/cancel")
    assert client.delete(f"/api/loras/{lora['id']}").status_code == 200
    assert client.get(f"/api/loras/{lora['id']}").status_code == 404
    history = client.get(f"/api/training-jobs/{job['id']}").json()
    assert history["lora_id"] is None
    assert history["lora"] is None
    assert history["character"]["id"] == character_id


def test_queue_rejects_bad_images_dir():
    character_id = make_character("Bad Dir")
    lora = make_lora(character_id)
    response = client.post(f"/api/loras/{lora['id']}/training-jobs", json={"images_dir": "/tmp/not-allowed"})
    assert response.status_code == 400
    response = client.post(
        f"/api/loras/{lora['id']}/training-jobs", json={"images_dir": "data/does-not-exist"}
    )
    assert response.status_code == 400


def test_job_listing_filters_by_status():
    character_id = make_character("Listing")
    lora = make_lora(character_id)
    job = queue_job(lora["id"], make_images_dir("listing"))
    queued = client.get("/api/training-jobs", params={"status": "queued", "character_id": character_id})
    assert queued.status_code == 200
    assert [item["id"] for item in queued.json()] == [job["id"]]
    assert client.get("/api/training-jobs", params={"status": "succeeded"}).json() == []


def test_delete_character_with_lora_cleans_artifact():
    character_id = make_character("Delete With LoRA")
    lora = make_lora(character_id)
    job = queue_job(lora["id"], make_images_dir("delete-lora"))
    complete_job(job)
    artifact = settings.lora_dir / job["params"]["artifact_filename"]
    assert artifact.is_file()

    assert client.delete(f"/api/characters/{character_id}").status_code == 200
    assert client.get(f"/api/loras/{lora['id']}").status_code == 404
    assert client.get(f"/api/training-jobs/{job['id']}").status_code == 404
    assert not artifact.exists()


def test_delete_character_blocked_while_training():
    character_id = make_character("Delete Busy")
    lora = make_lora(character_id)
    queue_job(lora["id"], make_images_dir("delete-busy"))
    response = client.delete(f"/api/characters/{character_id}")
    assert response.status_code == 409


def png_bytes():
    from io import BytesIO

    from PIL import Image

    buffer = BytesIO()
    Image.new("RGB", (48, 64), (30, 40, 50)).save(buffer, format="PNG")
    return buffer.getvalue()


def fake_generate(prompt, negative, **kwargs):
    return png_bytes(), {"seed": kwargs.get("seed", 1), "checkpoint": kwargs.get("checkpoint")}


def make_dataset(character_id, trigger="qa_ds"):
    response = client.post(
        f"/api/characters/{character_id}/datasets",
        json={"family": "real", "trigger": trigger, "base_checkpoint": "model.safetensors"},
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_dataset_generate_curate_and_retrain_gate(monkeypatch):
    character_id = make_character("Dataset Flow")
    dataset = make_dataset(character_id)
    monkeypatch.setattr("app.lora_api.generate_image", fake_generate)

    generated = client.post(f"/api/datasets/{dataset['id']}/generate", json={"prompt": "portrait", "count": 2})
    assert generated.status_code == 201, generated.text
    items = generated.json()
    assert len(items) == 2 and items[0]["filename"]

    for item in items:
        patched = client.patch(
            f"/api/dataset-items/{item['id']}", json={"selected": True, "caption": "portrait"}
        ).json()
        assert patched["selected"] is True

    detail = client.get(f"/api/datasets/{dataset['id']}").json()
    assert detail["item_count"] == 2 and detail["selected_count"] == 2

    lora = make_lora(character_id)
    too_few = client.post(f"/api/loras/{lora['id']}/training-jobs", json={"dataset_id": dataset["id"]})
    assert too_few.status_code == 400


def test_training_from_dataset_materializes(monkeypatch):
    character_id = make_character("Dataset Train")
    dataset = make_dataset(character_id, trigger="trg_ds")
    monkeypatch.setattr("app.lora_api.generate_image", fake_generate)
    items = client.post(
        f"/api/datasets/{dataset['id']}/generate", json={"prompt": "portrait", "count": 4}
    ).json()
    for item in items:
        client.patch(f"/api/dataset-items/{item['id']}", json={"selected": True})

    lora = make_lora(character_id)
    job = client.post(f"/api/loras/{lora['id']}/training-jobs", json={"dataset_id": dataset["id"]}).json()
    folder = Path(job["params"]["images_dir"])
    assert folder.is_dir()
    assert len(list(folder.glob("*.png"))) == 4
    texts = [path.read_text() for path in folder.glob("*.txt")]
    assert len(texts) == 4 and all("trg_ds" in text for text in texts)


def test_dataset_generate_comfyui_failure(monkeypatch):
    from app.integrations.comfyui import ComfyUIError

    character_id = make_character("Dataset Failure")
    dataset = make_dataset(character_id)

    def boom(prompt, negative, **kwargs):
        raise ComfyUIError("ComfyUI non è raggiungibile")

    monkeypatch.setattr("app.lora_api.generate_image", boom)
    response = client.post(f"/api/datasets/{dataset['id']}/generate", json={"prompt": "portrait", "count": 1})
    assert response.status_code == 502
    assert "Generazione dataset non riuscita" in response.json()["detail"]


def fake_variation(reference, prompt, negative="", **kwargs):
    return png_bytes(), {"seed": kwargs.get("seed", 1), "model": "qwen_image_edit_2509"}


def test_dataset_variations(monkeypatch):
    monkeypatch.setattr("app.lora_api.qwen_image_edit", fake_variation)
    character_id = make_character("Variations")
    assert client.post(f"/api/characters/{character_id}/avatar").status_code in (200, 201)
    dataset = make_dataset(character_id)
    response = client.post(
        f"/api/datasets/{dataset['id']}/variations",
        json={"prompts": ["same person, standing in a sunny street", "same person, close-up portrait"], "count": 2},
    )
    assert response.status_code == 201, response.text
    items = response.json()
    assert len(items) == 4
    assert all(item["filename"] for item in items)
    detail = client.get(f"/api/datasets/{dataset['id']}").json()
    assert detail["item_count"] == 4


def test_dataset_variations_need_anchor(monkeypatch):
    monkeypatch.setattr("app.lora_api.qwen_image_edit", fake_variation)
    character_id = make_character("No Anchor")
    dataset = make_dataset(character_id)
    response = client.post(
        f"/api/datasets/{dataset['id']}/variations", json={"prompts": ["same person"], "count": 1}
    )
    assert response.status_code == 400


def test_dataset_analysis(monkeypatch):
    monkeypatch.setattr("app.lora_api.generate_image", fake_generate)
    character_id = make_character("Analysis")
    dataset = make_dataset(character_id)
    items = client.post(
        f"/api/datasets/{dataset['id']}/generate", json={"prompt": "same person, standing", "count": 4}
    ).json()
    for item in items:
        client.patch(f"/api/dataset-items/{item['id']}", json={"selected": True})

    analysis = client.get(f"/api/datasets/{dataset['id']}/analysis").json()
    assert analysis["total"] == 4 and analysis["selected"] == 4 and analysis["target"] == 60
    codes = {warning["code"] for warning in analysis["warnings"]}
    assert "select_more" in codes
    assert "duplicates" in codes and analysis["duplicates"] == 3
    assert analysis["keywords"]["standing"] == 4


def test_delete_dataset_item(monkeypatch):
    monkeypatch.setattr("app.lora_api.generate_image", fake_generate)
    character_id = make_character("Delete Item")
    dataset = make_dataset(character_id)
    items = client.post(
        f"/api/datasets/{dataset['id']}/generate", json={"prompt": "same person, standing", "count": 1}
    ).json()
    item = items[0]
    response = client.delete(f"/api/dataset-items/{item['id']}")
    assert response.status_code == 200, response.text
    detail = client.get(f"/api/datasets/{dataset['id']}").json()
    assert detail["item_count"] == 0
    assert client.get(f"/api/library/{item['image_id']}/file").status_code == 404


def test_delete_library_item_in_dataset(monkeypatch):
    monkeypatch.setattr("app.lora_api.generate_image", fake_generate)
    character_id = make_character("Delete Library")
    dataset = make_dataset(character_id)
    items = client.post(
        f"/api/datasets/{dataset['id']}/generate", json={"prompt": "same person, sitting", "count": 1}
    ).json()
    image_id = items[0]["image_id"]
    assert client.delete(f"/api/library/{image_id}").status_code == 200
    detail = client.get(f"/api/datasets/{dataset['id']}").json()
    assert detail["item_count"] == 0


def test_delete_dataset_with_images(monkeypatch):
    monkeypatch.setattr("app.lora_api.generate_image", fake_generate)
    character_id = make_character("Delete Dataset")
    dataset = make_dataset(character_id)
    items = client.post(
        f"/api/datasets/{dataset['id']}/generate", json={"prompt": "same person", "count": 2}
    ).json()
    response = client.delete(f"/api/datasets/{dataset['id']}")
    assert response.status_code == 200, response.text
    assert client.get(f"/api/datasets/{dataset['id']}").status_code == 404
    assert client.get(f"/api/characters/{character_id}/datasets").json() == []
    assert client.get(f"/api/library/{items[0]['image_id']}/file").status_code == 404


def test_dataset_reference_roles(monkeypatch):
    monkeypatch.setattr("app.lora_api.generate_image", fake_generate)
    character_id = make_character("References")
    dataset = make_dataset(character_id)
    items = client.post(
        f"/api/datasets/{dataset['id']}/generate", json={"prompt": "portrait", "count": 2}
    ).json()
    patched = client.patch(
        f"/api/dataset-items/{items[0]['id']}", json={"reference_role": "close_face"}
    )
    assert patched.status_code == 200
    assert patched.json()["reference_role"] == "close_face"
    invalid = client.patch(
        f"/api/dataset-items/{items[1]['id']}", json={"reference_role": "nope"}
    )
    assert invalid.status_code == 400
    cleared = client.patch(f"/api/dataset-items/{items[0]['id']}", json={"reference_role": ""}).json()
    assert cleared["reference_role"] is None

    client.patch(f"/api/dataset-items/{items[0]['id']}", json={"reference_role": "profile"})
    analysis = client.get(f"/api/datasets/{dataset['id']}/analysis").json()
    assert analysis["reference_counts"] == {"profile": 1}
    assert any(warning["code"] == "few_references" for warning in analysis["warnings"])


def test_candidates_use_canonical_references(monkeypatch):
    monkeypatch.setattr("app.lora_api.generate_image", fake_generate)
    character_id = make_character("RefCandidates")
    dataset = make_dataset(character_id)
    first = client.post(
        f"/api/datasets/{dataset['id']}/generate", json={"prompt": "portrait", "count": 1}
    ).json()[0]
    client.patch(f"/api/dataset-items/{first['id']}", json={"reference_role": "front_full_body"})

    captured = []

    def spy(prompt, negative, **kwargs):
        captured.append(kwargs.get("reference_path"))
        return png_bytes(), {"seed": kwargs.get("seed", 1)}

    monkeypatch.setattr("app.lora_api.generate_image", spy)
    client.post(f"/api/datasets/{dataset['id']}/generate", json={"prompt": "standing", "count": 2})
    assert len(captured) == 2
    assert all(path is not None and path.name == first["filename"] for path in captured)


def test_variations_use_canonical_references(monkeypatch):
    monkeypatch.setattr("app.lora_api.generate_image", fake_generate)
    character_id = make_character("RefVariations")
    assert client.post(f"/api/characters/{character_id}/avatar").status_code in (200, 201)
    dataset = make_dataset(character_id)
    reference = client.post(
        f"/api/datasets/{dataset['id']}/generate", json={"prompt": "portrait", "count": 1}
    ).json()[0]
    client.patch(f"/api/dataset-items/{reference['id']}", json={"reference_role": "upper_body"})

    captured = []

    def spy(reference_path, prompt, negative="", **kwargs):
        captured.append(reference_path)
        return png_bytes(), {"seed": kwargs.get("seed", 1)}

    monkeypatch.setattr("app.lora_api.qwen_image_edit", spy)
    client.post(f"/api/datasets/{dataset['id']}/variations", json={"prompts": ["same person, cafe"], "count": 1})
    assert len(captured) == 1 and captured[0].name == reference["filename"]


def test_candidates_family_follows_checkpoint(monkeypatch):
    monkeypatch.setattr("app.lora_api.generate_image", fake_generate)
    character_id = make_character("Family Follow")
    dataset = make_dataset(character_id)
    captured = {}

    def spy(prompt, negative, **kwargs):
        captured.update(kwargs)
        return png_bytes(), {"seed": kwargs.get("seed", 1)}

    monkeypatch.setattr("app.lora_api.generate_image", spy)
    client.post(
        f"/api/datasets/{dataset['id']}/generate",
        json={"prompt": "portrait", "checkpoint": "qwen_image_2512_fp8_e4m3fn.safetensors", "pose_ids": [], "count": 1},
    )
    assert captured["family"] == "qwen-image"
    assert captured["checkpoint"] == "qwen_image_2512_fp8_e4m3fn.safetensors"


def test_character_prompt_flows_into_candidates(monkeypatch):
    profile = {
        "description": "d",
        "appearance": "asian woman with black hair and green eyes",
        "personality_traits": "t",
        "tone_of_voice": "t",
        "boundaries": "b",
    }
    character_id = client.post("/api/characters", json={"name": "Identity Prompt", "profile": profile}).json()["id"]
    assert client.post(f"/api/characters/{character_id}/avatar").status_code in (200, 201)
    character = client.get(f"/api/characters/{character_id}").json()
    assert "asian" in (character["avatar_prompt"] or "").lower()

    updated = client.put(
        f"/api/characters/{character_id}/avatar-prompt",
        json={"prompt": "asian woman, long black hair, green eyes"},
    ).json()
    assert updated["avatar_prompt"] == "asian woman, long black hair, green eyes"

    dataset = make_dataset(character_id)
    captured = {}

    def spy(prompt, negative, **kwargs):
        captured["prompt"] = prompt
        return png_bytes(), {"seed": 1}

    monkeypatch.setattr("app.lora_api.generate_image", spy)
    client.post(
        f"/api/datasets/{dataset['id']}/generate",
        json={"prompt": "standing in a park", "pose_ids": [], "count": 1},
    )
    assert "asian woman" in captured["prompt"]
    assert "standing in a park" in captured["prompt"]

    cleared = client.put(f"/api/characters/{character_id}/avatar-prompt", json={"prompt": None}).json()
    assert cleared["avatar_prompt"] is None


def test_bulk_delete_library_and_dataset_items(monkeypatch):
    monkeypatch.setattr("app.lora_api.generate_image", fake_generate)
    monkeypatch.setattr("app.characters.generate_image", fake_generate)
    character_id = make_character("Bulk Delete")
    dataset = make_dataset(character_id, trigger="bulk_ds")
    items = client.post(
        f"/api/datasets/{dataset['id']}/generate", json={"prompt": "portrait", "count": 2}
    ).json()
    assert len(items) == 2

    response = client.post(
        "/api/loras/dataset-items/bulk-delete", json={"ids": [item["id"] for item in items]}
    )
    assert response.status_code == 200 and response.json()["deleted"] == 2
    detail = client.get(f"/api/datasets/{dataset['id']}").json()
    assert detail["item_count"] == 0
    for item in items:
        assert not (settings.media_dir / item["filename"]).exists()

    generated = client.post(
        f"/api/characters/{character_id}/library/generate", json={"prompt": "studio", "count": 2}
    ).json()
    assert len(generated) == 2
    response = client.post(
        "/api/library/bulk-delete", json={"ids": [item["id"] for item in generated]}
    )
    assert response.status_code == 200 and response.json()["deleted"] == 2
    assert client.get(f"/api/characters/{character_id}/library").json() == []
    for item in generated:
        assert not (settings.media_dir / item["filename"]).exists()
