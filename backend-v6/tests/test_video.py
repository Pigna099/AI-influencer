from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app, headers={"X-API-Key": "test-key"})
PROFILE = {
    "description": "video test",
    "appearance": "adult woman, dark hair",
    "personality_traits": "calm",
    "tone_of_voice": "warm",
    "boundaries": "adults only",
}


def make_character(name="Video Character"):
    response = client.post("/api/characters", json={"name": name, "profile": PROFILE})
    assert response.status_code == 201, response.text
    return response.json()["id"]


def test_video_generate_list_file_delete():
    character_id = make_character()
    images = client.post(
        f"/api/characters/{character_id}/library/generate", json={"prompt": "studio portrait", "count": 1}
    ).json()
    assert images and images[0]["id"]

    response = client.post(
        f"/api/characters/{character_id}/videos",
        json={"prompt": "she smiles at the camera", "image_id": images[0]["id"], "length": 49, "steps": 4},
    )
    assert response.status_code == 201, response.text
    clip = response.json()
    assert clip["status"] == "ready" and clip["filename"].endswith(".webm")
    assert clip["source_image_id"] == images[0]["id"]
    assert clip["thumb_filename"] and clip["thumb_filename"].endswith(".png")
    thumb_response = client.get(f"/api/videos/{clip['id']}/thumb")
    assert thumb_response.status_code == 200 and thumb_response.content == b"MOCK-THUMB"

    listing = client.get(f"/api/characters/{character_id}/videos").json()
    assert len(listing) == 1 and listing[0]["id"] == clip["id"]

    file_response = client.get(f"/api/videos/{clip['id']}/file")
    assert file_response.status_code == 200
    assert file_response.content == b"MOCK-VIDEO"

    assert client.delete(f"/api/videos/{clip['id']}").status_code == 200
    assert client.get(f"/api/characters/{character_id}/videos").json() == []


def test_video_requires_source_image():
    character_id = make_character("No Image")
    response = client.post(f"/api/characters/{character_id}/videos", json={"prompt": "x"})
    assert response.status_code == 400


def test_video_text_mode_without_image():
    character_id = make_character("Text Mode")
    response = client.post(
        f"/api/characters/{character_id}/videos",
        json={"prompt": "a woman walking on a beach at sunset", "mode": "text", "length": 49, "steps": 4},
    )
    assert response.status_code == 201, response.text
    clip = response.json()
    assert clip["source_image_id"] is None
    assert clip["params"]["mode"] == "text"


def test_video_lora_validation():
    character_id = make_character("Lora Video")
    response = client.post(
        f"/api/characters/{character_id}/videos",
        json={"prompt": "x", "mode": "text", "loras": [{"name": "wan2.2_i2v_lightx2v_4steps_lora_v1_high_noise.safetensors"}]},
    )
    assert response.status_code == 400
    assert "automaticamente" in response.json()["detail"]
    response = client.post(
        f"/api/characters/{character_id}/videos",
        json={"prompt": "x", "mode": "text", "loras": [{"name": "missing_style.safetensors"}]},
    )
    assert response.status_code == 400
    response = client.post(
        f"/api/characters/{character_id}/videos",
        json={"prompt": "x", "mode": "text", "loras": [{"name": "ai_influencer/char.safetensors"}]},
    )
    assert response.status_code == 400
    assert "compatibile" in response.json()["detail"]


def test_wan_video_graph_modes():
    from app.integrations.comfyui import wan_video_graph

    text_graph = wan_video_graph("a cat", "bad", length=49)
    assert "11" not in text_graph
    assert "start_image" not in text_graph["12"]["inputs"]

    assert text_graph["thumb_save"]["inputs"]["images"] == ["thumb_frame", 0]
    image_graph = wan_video_graph("a cat", "bad", image_name="start.png", loras=[{"name": "wan_style.safetensors", "weight": 0.8}])
    assert image_graph["11"]["inputs"]["image"] == "start.png"
    assert image_graph["thumb_frame"]["inputs"]["image"] == ["15", 0]
    assert image_graph["12"]["inputs"]["start_image"] == ["11", 0]
    assert image_graph["lora_h1"]["inputs"]["lora_name"] == "wan_style.safetensors"
    assert image_graph["lora_l1"]["inputs"]["strength_model"] == 0.8
    assert image_graph["3"]["inputs"]["model"] == ["lora_h1", 0]
    assert image_graph["6"]["inputs"]["model"] == ["lora_l1", 0]


def test_ltx_video_graph_modes():
    from app.integrations.comfyui import ltx_video_graph

    graph = ltx_video_graph("a cat", "bad", length=49, steps=5)
    assert graph["1"]["inputs"]["ckpt_name"].startswith("ltx-2.3")
    assert graph["8"]["inputs"]["frames_number"] == 49
    assert graph["15"]["inputs"]["sigmas"].endswith("0.0")
    assert "9" not in graph and "10" not in graph
    assert graph["11"]["inputs"]["video_latent"] == ["6", 0]

    image_graph = ltx_video_graph("a cat", "bad", image_name="start.png", loras=[{"name": "ltx-style.safetensors", "weight": 0.7}])
    assert image_graph["10"]["inputs"]["image"] == ["9", 0]
    assert image_graph["11"]["inputs"]["video_latent"] == ["10", 0]
    assert image_graph["lora1"]["inputs"]["strength_model"] == 0.7
    assert image_graph["13"]["inputs"]["model"] == ["lora1", 0]


def test_ltx_model_select_and_lora_family():
    character_id = make_character("LTX Video")
    response = client.post(
        f"/api/characters/{character_id}/videos",
        json={"prompt": "x", "mode": "text", "model": "ltx-distilled", "width": 800, "height": 500, "length": 51},
    )
    assert response.status_code == 201, response.text
    clip = response.json()
    assert clip["model"].startswith("ltx-2.3")
    assert clip["params"]["width"] == 800 and clip["params"]["height"] == 480
    assert clip["params"]["length"] == 49

    response = client.post(
        f"/api/characters/{character_id}/videos",
        json={"prompt": "x", "mode": "text", "model": "ltx-distilled", "loras": [{"name": "wan_style.safetensors"}]},
    )
    assert response.status_code == 400
    assert "compatibile" in response.json()["detail"]


def test_hunyuan_video_graph_modes():
    from app.integrations.comfyui import hunyuan_video_graph

    graph = hunyuan_video_graph("a cat", "bad", length=49)
    assert graph["2"]["inputs"]["type"] == "hunyuan_video_15"
    assert graph["2"]["inputs"]["clip_name2"] == "byt5_small_glyphxl_fp16.safetensors"
    assert graph["1"]["inputs"]["unet_name"].endswith("t2v_cfg_distilled_fp8_scaled.safetensors")
    assert graph["15"]["class_type"] == "EmptyHunyuanVideo15Latent"
    assert "23" not in graph
    assert graph["thumb_frame"]["inputs"]["image"] == ["12", 0]

    image_graph = hunyuan_video_graph("a cat", "bad", image_name="start.png", loras=[{"name": "hunyuan/style.safetensors", "weight": 0.6}])
    assert image_graph["1"]["inputs"]["unet_name"].endswith("i2v_cfg_distilled_fp8_scaled.safetensors")
    assert image_graph["20"]["inputs"]["image"] == "start.png"
    assert image_graph["23"]["inputs"]["clip_vision_output"] == ["22", 0]
    assert image_graph["10"]["inputs"]["positive"] == ["23", 0]
    assert image_graph["lora1"]["inputs"]["strength_model"] == 0.6
    assert image_graph["6"]["inputs"]["model"] == ["lora1", 0]


def test_hunyuan_model_via_api():
    character_id = make_character("Hunyuan Video")
    response = client.post(
        f"/api/characters/{character_id}/videos",
        json={"prompt": "a woman walking in the snow", "mode": "text", "model": "hunyuan", "width": 832, "height": 480, "length": 49, "steps": 8},
    )
    assert response.status_code == 201, response.text
    clip = response.json()
    assert "hunyuanvideo1.5" in clip["model"]
    assert clip["params"]["length"] == 49
    response = client.post(
        f"/api/characters/{character_id}/videos",
        json={"prompt": "x", "mode": "text", "model": "hunyuan", "loras": [{"name": "wan_style.safetensors"}]},
    )
    assert response.status_code == 400
    assert "compatibile" in response.json()["detail"]
