import io
import json
import logging
import random
import threading
import time
from pathlib import Path

import httpx
from PIL import Image, ImageDraw

from ..config import settings

logger = logging.getLogger(__name__)

_probe = {"at": 0.0, "ok": False}
_pick_lock = threading.Lock()
_pick_counter = 0
PLACEHOLDERS = ("{{positive_prompt}}", "{{negative_prompt}}", "{{seed}}", "{{image_count}}")


def comfyui_targets() -> list[str]:
    """Primary ComfyUI instance plus the extra GPU instances (comma-separated COMFYUI_URLS)."""
    targets = [settings.comfyui_url.rstrip("/")]
    for url in (settings.comfyui_urls or "").split(","):
        url = url.strip().rstrip("/")
        if url and url not in targets:
            targets.append(url)
    return targets


def _queue_depth(base_url: str) -> int:
    try:
        response = httpx.get(f"{base_url}/queue", timeout=2)
        response.raise_for_status()
        data = response.json()
        return len(data.get("queue_running", [])) + len(data.get("queue_pending", []))
    except (httpx.HTTPError, ValueError, TypeError):
        return 10**6


def pick_target() -> str:
    """Least busy ComfyUI instance, rotating on ties so parallel batches spread across GPUs."""
    global _pick_counter
    targets = comfyui_targets()
    if len(targets) == 1:
        return targets[0]
    depths = [(target, _queue_depth(target)) for target in targets]
    low = min(depth for _, depth in depths)
    candidates = [target for target, depth in depths if depth == low]
    with _pick_lock:
        target = candidates[_pick_counter % len(candidates)]
        _pick_counter += 1
    return target


class ComfyUIError(Exception):
    pass


def parameterize(value, replacements):
    if isinstance(value, dict):
        return {key: parameterize(item, replacements) for key, item in value.items()}
    if isinstance(value, list):
        return [parameterize(item, replacements) for item in value]
    if isinstance(value, str) and value in replacements:
        return replacements[value]
    return value


def comfyui_available(ttl_seconds: float = 15.0) -> bool:
    """Cheap probe so chat only offers photos while at least one image service is reachable."""
    if settings.image_provider == "mock":
        return True
    now = time.monotonic()
    if now - _probe["at"] > ttl_seconds:
        ok = False
        for target in comfyui_targets():
            try:
                response = httpx.get(f"{target}/system_stats", timeout=3)
                response.raise_for_status()
                ok = True
                break
            except httpx.HTTPError:
                continue
        _probe.update(at=now, ok=ok)
    return _probe["ok"]


def free_memory() -> bool:
    """Ask every ComfyUI instance to unload models and release cached VRAM."""
    freed = False
    for target in comfyui_targets():
        try:
            response = httpx.post(
                f"{target}/free",
                json={"unload_models": True, "free_memory": True},
                timeout=15,
            )
            response.raise_for_status()
            freed = True
        except (httpx.HTTPError, OSError):
            continue
    return freed


def interrupt() -> bool:
    """Interrupt the running prompt and clear the queue on every ComfyUI instance."""
    interrupted = False
    for target in comfyui_targets():
        try:
            with httpx.Client(base_url=target, timeout=10) as client:
                client.post("/interrupt").raise_for_status()
                client.post("/queue", json={"clear": True}).raise_for_status()
            interrupted = True
        except (httpx.HTTPError, OSError):
            continue
    return interrupted


def _interrupted_message(history: dict) -> str:
    """Return a clean error when ComfyUI stopped the prompt due to /interrupt."""
    return "Generazione annullata" if "interrupt" in json.dumps(history.get("status", {})).lower() else ""


def _prompt_error(response) -> str:
    """Human readable detail when ComfyUI rejects a workflow (node errors etc.)."""
    try:
        payload = response.json()
    except ValueError:
        return response.text[:200]
    errors = payload.get("node_errors") or payload.get("error") or payload
    return json.dumps(errors)[:500]


def _submit_and_wait(workflow: dict, timeout: int, base_url: str | None = None) -> bytes:
    """Submit a workflow, wait for the first output image and return its bytes."""
    if base_url is not None:
        return _submit_on(workflow, timeout, base_url)
    targets = comfyui_targets()
    if len(targets) > 1:
        ordered = [pick_target()] + [t for t in targets if t != pick_target()]
    else:
        ordered = targets
    last_error: ComfyUIError | None = None
    for target in ordered[:2]:
        try:
            return _submit_on(workflow, timeout, target)
        except ComfyUIError as error:
            last_error = error
            if "rifiutato" not in str(error):
                raise
            logger.warning("Workflow rejected by %s, retrying on another instance", target)
    raise last_error or ComfyUIError("Nessuna istanza ComfyUI disponibile")


def _submit_on(workflow: dict, timeout: int, base_url: str) -> bytes:
    deadline = time.monotonic() + timeout
    try:
        with httpx.Client(base_url=base_url, timeout=30) as client:
            response = client.post("/prompt", json={"prompt": workflow})
            if response.status_code >= 400:
                raise ComfyUIError(f"ComfyUI ha rifiutato il workflow: {_prompt_error(response)}")
            response.raise_for_status()
            data = response.json()
            if data.get("node_errors") or "prompt_id" not in data:
                raise ComfyUIError(f"ComfyUI ha rifiutato il workflow: {json.dumps(data.get('node_errors'))[:400]}")
            prompt_id = data["prompt_id"]
            while time.monotonic() < deadline:
                response = client.get(f"/history/{prompt_id}")
                response.raise_for_status()
                history = response.json().get(prompt_id)
                if history:
                    if history.get("status", {}).get("status_str") == "error":
                        raise ComfyUIError(_interrupted_message(history) or "Generazione ComfyUI non riuscita")
                    for node in history.get("outputs", {}).values():
                        for asset in node.get("images", []):
                            if asset.get("type") != "output":
                                continue
                            response = client.get(
                                "/view",
                                params={
                                    key: asset[key]
                                    for key in ("filename", "subfolder", "type")
                                    if key in asset
                                },
                            )
                            response.raise_for_status()
                            return response.content
                    raise ComfyUIError("Nessuna immagine prodotta")
                time.sleep(0.5)
    except httpx.HTTPError as error:
        raise ComfyUIError(f"ComfyUI error: {error}") from error
    raise ComfyUIError("Timeout durante la generazione")


def qwen_image_edit(
    reference_path: Path,
    prompt: str,
    negative: str = "",
    *,
    seed: int | None = None,
    steps: int | None = None,
    cfg: float | None = None,
    lora_weight: float = 1.0,
    unet_name: str | None = None,
    base_url: str | None = None,
    size_label: str = "QWEN EDIT DEMO",
) -> tuple[bytes, dict]:
    """Generate a variation of the reference person with Qwen-Image-Edit (+Lightning LoRA)."""
    seed = random.randrange(2**31) if seed is None else seed
    steps = steps or settings.qwen_edit_steps
    cfg = settings.qwen_edit_cfg if cfg is None else cfg
    model = unet_name or settings.qwen_edit_unet_name
    lora = settings.qwen_edit_lora_name
    if unet_name:
        if "2511" in unet_name.lower():
            lora = "Qwen-Image-Edit-2511-Lightning-4steps-V1.0-fp32.safetensors"
        elif "2509" in unet_name.lower():
            lora = "Qwen-Image-Edit-2509-Lightning-4steps-V1.0-bf16.safetensors"
    if settings.image_provider == "mock":
        image = Image.new("RGB", (768, 1024), (40, 30, 60))
        ImageDraw.Draw(image).text((30, 470), f"DEMO - NOT AI GENERATED\n{size_label}", fill="white")
        output = io.BytesIO()
        image.save(output, format="PNG")
        return output.getvalue(), {"provider": "mock", "seed": seed, "model": "qwen_image_edit", "steps": steps, "cfg": cfg}
    if not comfyui_available():
        raise ComfyUIError("ComfyUI non è raggiungibile: avvia il servizio immagini")
    with Image.open(reference_path) as source:
        width, height = source.size
    scale = (1024 * 1024 / max(1, width * height)) ** 0.5
    width = max(512, min(1536, int(width * scale) // 8 * 8))
    height = max(512, min(1536, int(height * scale) // 8 * 8))
    base_url = base_url or pick_target()
    uploaded = upload_reference(reference_path, base_url=base_url)
    workflow = {
        "1": {"class_type": "LoadImage", "inputs": {"image": uploaded}},
        "2": {
            "class_type": "ImageScaleToTotalPixels",
            "inputs": {"image": ["1", 0], "upscale_method": "lanczos", "megapixels": 1.0, "resolution_steps": 1},
        },
        "3": {
            "class_type": "CLIPLoader",
            "inputs": {"clip_name": settings.qwen_edit_clip_name, "type": "qwen_image"},
        },
        "4": {"class_type": "VAELoader", "inputs": {"vae_name": settings.qwen_edit_vae_name}},
        "5": {
            "class_type": "UNETLoader",
            "inputs": {"unet_name": model, "weight_dtype": "default"},
        },
        "6": {
            "class_type": "LoraLoaderModelOnly",
            "inputs": {"model": ["5", 0], "lora_name": lora, "strength_model": lora_weight},
        },
        "7": {"class_type": "ModelSamplingAuraFlow", "inputs": {"model": ["6", 0], "shift": settings.qwen_edit_shift}},
        "8": {"class_type": "CFGNorm", "inputs": {"model": ["7", 0], "strength": 1.0}},
        "9": {
            "class_type": "TextEncodeQwenImageEditPlus",
            "inputs": {"clip": ["3", 0], "prompt": prompt, "vae": ["4", 0], "image1": ["2", 0]},
        },
        "10": {
            "class_type": "TextEncodeQwenImageEditPlus",
            "inputs": {"clip": ["3", 0], "prompt": negative, "vae": ["4", 0], "image1": ["2", 0]},
        },
        "11": {"class_type": "EmptySD3LatentImage", "inputs": {"width": width, "height": height, "batch_size": 1}},
        "12": {
            "class_type": "KSampler",
            "inputs": {
                "model": ["8", 0], "positive": ["9", 0], "negative": ["10", 0], "latent_image": ["11", 0],
                "seed": seed, "steps": steps, "cfg": cfg, "sampler_name": "euler", "scheduler": "simple",
                "denoise": 1.0,
            },
        },
        "13": {"class_type": "VAEDecode", "inputs": {"samples": ["12", 0], "vae": ["4", 0]}},
        "14": {"class_type": "SaveImage", "inputs": {"images": ["13", 0], "filename_prefix": "qwen_edit"}},
    }
    started = time.perf_counter()
    data = _submit_and_wait(workflow, settings.qwen_edit_timeout, base_url=base_url)
    return data, {
        "provider": "comfyui",
        "seed": seed,
        "model": model,
        "steps": steps,
        "cfg": cfg,
        "reference": True,
        "seconds": time.perf_counter() - started,
    }


def extract_pose(
    image_path: Path, resolution: int = 1024, timeout: int = 240, base_url: str | None = None
) -> bytes:
    """Run DWPose through ComfyUI and return the skeleton PNG."""
    if not comfyui_available():
        raise ComfyUIError("ComfyUI non è raggiungibile: avvia il servizio immagini")
    base_url = base_url or pick_target()
    uploaded = upload_reference(image_path, base_url=base_url)
    workflow = {
        "1": {"class_type": "LoadImage", "inputs": {"image": uploaded}},
        "2": {
            "class_type": "DWPreprocessor",
            "inputs": {
                "image": ["1", 0],
                "detect_hand": "disable",
                "detect_body": "enable",
                "detect_face": "disable",
                "resolution": resolution,
                "bbox_detector": "yolox_l.onnx",
                "pose_estimator": "dw-ll_ucoco_384.onnx",
                "scale_stick_for_xinsr_cn": "disable",
            },
        },
        "3": {
            "class_type": "SaveImage",
            "inputs": {"images": ["2", 0], "filename_prefix": "pose_skeleton"},
        },
    }
    deadline = time.monotonic() + timeout
    try:
        with httpx.Client(base_url=base_url, timeout=30) as client:
            response = client.post("/prompt", json={"prompt": workflow})
            response.raise_for_status()
            data = response.json()
            if data.get("node_errors") or "prompt_id" not in data:
                raise ComfyUIError("ComfyUI ha rifiutato il workflow posa")
            prompt_id = data["prompt_id"]
            while time.monotonic() < deadline:
                response = client.get(f"/history/{prompt_id}")
                response.raise_for_status()
                history = response.json().get(prompt_id)
                if history:
                    if history.get("status", {}).get("status_str") == "error":
                        raise ComfyUIError(_interrupted_message(history) or "Estrazione posa non riuscita")
                    for node in history.get("outputs", {}).values():
                        for asset in node.get("images", []):
                            if asset.get("type") != "output":
                                continue
                            response = client.get(
                                "/view",
                                params={
                                    key: asset[key]
                                    for key in ("filename", "subfolder", "type")
                                    if key in asset
                                },
                            )
                            response.raise_for_status()
                            image = Image.open(io.BytesIO(response.content)).convert("RGB")
                            if all(high <= 8 for _, high in image.getextrema()):
                                raise ComfyUIError("Nessuna persona rilevata nella foto")
                            output = io.BytesIO()
                            image.save(output, format="PNG")
                            return output.getvalue()
                    raise ComfyUIError("Nessuno skeleton prodotto da DWPose")
                time.sleep(0.5)
    except httpx.HTTPError as error:
        raise ComfyUIError(f"ComfyUI error: {error}") from error
    raise ComfyUIError("Timeout durante l'estrazione della posa")


def lora_family(name: str) -> str:
    """Best-effort family of a LoRA file (used to hide incompatible combinations)."""
    lower = name.lower()
    if lower.startswith("ai_influencer/"):
        for family in ("real", "pony", "anime"):
            if f"_{family}_" in lower:
                return family
        return "sdxl"
    if "qwen" in lower:
        return "qwen-image"
    if "z-image" in lower or "zimage" in lower:
        return "z-image"
    if "flux2" in lower or "flux-2" in lower:
        return "flux2"
    if "wan" in lower or "ltx" in lower:
        return "video"
    return "sdxl"


def get_loras() -> list[str]:
    """LoRA files installed in ComfyUI, for the image playground."""
    if settings.image_provider == "mock":
        return ["mock-lora.safetensors"]
    try:
        response = httpx.get(f"{settings.comfyui_url}/object_info/LoraLoader", timeout=10)
        response.raise_for_status()
        options = response.json()["LoraLoader"]["input"]["required"]["lora_name"][0]
        return list(options)
    except (httpx.HTTPError, KeyError, TypeError):
        return []


def apply_loras(workflow: dict, loras: list[dict] | None) -> dict:
    """Chain LoraLoader nodes after the checkpoint and route model/clip consumers through them."""
    if not loras:
        return workflow
    chain = []
    model_ref, clip_ref = ["4", 0], ["4", 1]
    for index, lora in enumerate(loras, start=1):
        node_id = f"lora{index}"
        weight = float(lora.get("weight", 0.8))
        clip = lora.get("clip_weight")
        clip_weight = weight if clip is None else float(clip)
        chain.append((node_id, list(model_ref), list(clip_ref), str(lora["name"]), weight, clip_weight))
        model_ref, clip_ref = [node_id, 0], [node_id, 1]
    final_model, final_clip = model_ref, clip_ref

    def rewire(value):
        if value == ["4", 0]:
            return final_model
        if value == ["4", 1]:
            return final_clip
        if isinstance(value, dict):
            return {key: rewire(item) for key, item in value.items()}
        if isinstance(value, list):
            return [rewire(item) for item in value]
        return value

    patched = rewire(json.loads(json.dumps(workflow)))
    for node_id, source_model, source_clip, name, weight, clip_weight in chain:
        patched[node_id] = {
            "class_type": "LoraLoader",
            "inputs": {
                "model": source_model,
                "clip": source_clip,
                "lora_name": name,
                "strength_model": weight,
                "strength_clip": clip_weight,
            },
            "_meta": {"title": f"LoRA {name}"},
        }
    return patched


VIDEO_HINTS = ("ltx", "wan", "hunyuan", "svd", "cosmos", "video", "animatediff")
UNSUPPORTED_HINTS = ("flux", "sd15", "sd3", "qwen", "z-image", "zimage", "chroma", "kolors", "lumina", "krea")
ANIME_HINTS = ("illustrious", "noob", "animagine", "anime")


def checkpoint_meta(name: str) -> dict:
    lower = name.lower()
    if any(hint in lower for hint in VIDEO_HINTS):
        return {"name": name, "family": "video", "usable": False}
    if "flux2" in lower or "flux-2" in lower:
        return {"name": name, "family": "flux2", "usable": True}
    if "qwen" in lower and "image" in lower:
        return {"name": name, "family": "qwen-image", "usable": True}
    if "z_image" in lower or "z-image" in lower or "zimage" in lower:
        return {"name": name, "family": "z-image", "usable": True}
    if "playground" in lower:
        return {"name": name, "family": "playground", "usable": True}
    if any(hint in lower for hint in UNSUPPORTED_HINTS):
        return {"name": name, "family": "unsupported", "usable": False}
    if "pony" in lower:
        family = "pony"
    elif any(hint in lower for hint in ANIME_HINTS):
        family = "anime"
    else:
        family = "real"
    return {"name": name, "family": family, "usable": True}


DIFFUSION_FAMILIES = ("qwen-image", "z-image", "flux2", "playground")


def get_checkpoints() -> list[dict]:
    """Checkpoints and diffusion models installed in ComfyUI, with family and usability."""
    if settings.image_provider == "mock":
        return [checkpoint_meta("mock-sdxl.safetensors")]
    result: list[dict] = []
    try:
        response = httpx.get(f"{settings.comfyui_url}/object_info/CheckpointLoaderSimple", timeout=10)
        response.raise_for_status()
        options = response.json()["CheckpointLoaderSimple"]["input"]["required"]["ckpt_name"][0]
        result += [checkpoint_meta(name) for name in options]
    except (httpx.HTTPError, KeyError, TypeError):
        pass
    try:
        response = httpx.get(f"{settings.comfyui_url}/object_info/UNETLoader", timeout=10)
        response.raise_for_status()
        options = response.json()["UNETLoader"]["input"]["required"]["unet_name"][0]
        result += [checkpoint_meta(name) for name in options]
    except (httpx.HTTPError, KeyError, TypeError):
        pass
    return result


def apply_checkpoint(workflow: dict, checkpoint: str | None) -> dict:
    """Override the checkpoint of every CheckpointLoaderSimple node in the workflow."""
    if not checkpoint:
        return workflow
    patched = json.loads(json.dumps(workflow))
    found = False
    for node in patched.values():
        if isinstance(node, dict) and node.get("class_type") == "CheckpointLoaderSimple":
            node.setdefault("inputs", {})["ckpt_name"] = checkpoint
            found = True
    if not found:
        raise ComfyUIError("Il workflow non contiene un nodo CheckpointLoaderSimple")
    return patched


def upload_reference(path: Path, base_url: str | None = None) -> str:
    """Upload the character picture to ComfyUI and return its input filename."""
    try:
        with (
            httpx.Client(base_url=base_url or pick_target(), timeout=60) as client,
            path.open("rb") as handle,
        ):
            response = client.post(
                "/upload/image",
                files={"image": (path.name, handle, "image/png")},
                data={"overwrite": "true"},
            )
        response.raise_for_status()
        data = response.json()
    except (httpx.HTTPError, OSError, KeyError) as error:
        raise ComfyUIError(f"Reference upload failed: {error}") from error
    return f"{data.get('subfolder', '')}/{data['name']}".lstrip("/")


def _run_workflow(
    workflow: dict,
    replacements: dict,
    expected: int,
    timeout: int,
    checkpoint: str | None = None,
    loras: list[dict] | None = None,
    base_url: str | None = None,
) -> list[bytes]:
    serialized = json.dumps(workflow)
    for placeholder in PLACEHOLDERS:
        if placeholder not in serialized:
            raise ComfyUIError(f"Workflow missing placeholder: {placeholder}")
    prompt = parameterize(apply_loras(apply_checkpoint(workflow, checkpoint), loras), replacements)
    deadline = time.monotonic() + timeout
    try:
        with httpx.Client(base_url=base_url or pick_target(), timeout=30) as client:
            response = client.post("/prompt", json={"prompt": prompt})
            if response.status_code >= 400:
                raise ComfyUIError(f"ComfyUI ha rifiutato il workflow: {_prompt_error(response)}")
            response.raise_for_status()
            data = response.json()
            if data.get("node_errors") or "prompt_id" not in data:
                raise ComfyUIError(f"ComfyUI ha rifiutato il workflow: {json.dumps(data.get('node_errors'))[:400]}")
            prompt_id = data["prompt_id"]
            while time.monotonic() < deadline:
                response = client.get(f"/history/{prompt_id}")
                response.raise_for_status()
                history = response.json().get(prompt_id)
                if history:
                    if history.get("status", {}).get("status_str") == "error":
                        raise ComfyUIError(_interrupted_message(history) or "ComfyUI generation failed")
                    outputs = []
                    for node in history.get("outputs", {}).values():
                        for asset in node.get("images", []):
                            if asset.get("type") != "output":
                                continue
                            response = client.get(
                                "/view",
                                params={
                                    key: asset[key]
                                    for key in ("filename", "subfolder", "type")
                                    if key in asset
                                },
                            )
                            response.raise_for_status()
                            # Decode and re-encode to ensure stored media is a real PNG.
                            image = Image.open(io.BytesIO(response.content))
                            output = io.BytesIO()
                            image.save(output, format="PNG")
                            outputs.append(output.getvalue())
                    if len(outputs) != expected:
                        raise ComfyUIError("Unexpected image count: use one SaveImage output node")
                    return outputs
                time.sleep(2)
    except httpx.HTTPError as error:
        raise ComfyUIError(f"ComfyUI request failed: {error}") from error
    except OSError as error:
        raise ComfyUIError(f"Image decoding failed: {error}") from error
    raise ComfyUIError(
        "ComfyUI timeout; remote generation may still be running. Check ComfyUI before retrying."
    )


def generate_images(brief, request):
    if settings.image_provider == "mock":
        outputs = []
        for index in range(request["image_count"]):
            image = Image.new("RGB", (512, 512), (35, 42, 65))
            ImageDraw.Draw(image).text((35, 220), f"DEMO - NOT AI GENERATED\nImage {index + 1}", fill="white")
            output = io.BytesIO()
            image.save(output, format="PNG")
            outputs.append(output.getvalue())
        return outputs, {"provider": "mock"}
    workflow = json.loads(settings.workflow_path.read_text())
    outputs = _run_workflow(
        workflow,
        {
            "{{positive_prompt}}": brief.positive_prompt,
            "{{negative_prompt}}": brief.negative_prompt,
            "{{seed}}": request["seed"],
            "{{image_count}}": request["image_count"],
        },
        request["image_count"],
        settings.generation_timeout,
    )
    return outputs, {"provider": "comfyui", "workflow": "default"}


def _style_workflows(style: str, family: str | None = None) -> tuple[Path, Path]:
    """Plain and reference workflow for the requested family/style, with legacy fallback."""
    family = family or style
    if family == "pony":
        plain, reference = settings.chat_pony_workflow_path, settings.chat_pony_reference_workflow_path
    elif family == "anime":
        plain, reference = settings.chat_anime_workflow_path, settings.chat_anime_reference_workflow_path
    else:
        plain, reference = settings.chat_real_workflow_path, settings.chat_real_reference_workflow_path
    if not plain.is_file():
        return settings.chat_workflow_path, settings.chat_reference_workflow_path
    return plain, reference


def _diffusion_graph(
    family: str,
    checkpoint: str,
    prompt: str,
    negative: str,
    seed: int,
    loras: list[dict] | None = None,
    reference_name: str | None = None,
    pose_name: str | None = None,
    pose_strength: float = 0.8,
) -> dict:
    """Programmatic graph for the non-SDXL families. Playground (SDXL-based) supports IPAdapter and OpenPose."""
    width = height = 1024
    if family == "playground":
        graph = {
            "1": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": checkpoint}},
            "4": {"class_type": "EmptyLatentImage", "inputs": {"width": width, "height": height, "batch_size": 1}},
            "7": {"class_type": "VAEDecode", "inputs": {"samples": ["6", 0], "vae": ["1", 2]}},
            "8": {"class_type": "SaveImage", "inputs": {"images": ["7", 0], "filename_prefix": "playground25"}},
        }
        model_ref, clip_ref = ["1", 0], ["1", 1]
        for index, lora in enumerate(loras or [], start=1):
            node_id = f"lora{index}"
            weight = float(lora.get("weight", 0.8))
            clip = lora.get("clip_weight")
            graph[node_id] = {
                "class_type": "LoraLoader",
                "inputs": {
                    "model": model_ref, "clip": clip_ref, "lora_name": str(lora["name"]),
                    "strength_model": weight, "strength_clip": weight if clip is None else float(clip),
                },
            }
            model_ref, clip_ref = [node_id, 0], [node_id, 1]
        if reference_name:
            graph["12"] = {"class_type": "LoadImage", "inputs": {"image": reference_name, "upload": "image"}}
            graph["11"] = {
                "class_type": "easy ipadapterApplyADV",
                "inputs": {
                    "model": model_ref, "image": ["12", 0], "preset": "PLUS (high strength)",
                    "lora_strength": 0.6, "provider": "CUDA", "weight": 0.6, "weight_faceidv2": 1.0,
                    "weight_type": "ease in-out", "combine_embeds": "concat", "start_at": 0.0,
                    "end_at": 1.0, "embeds_scaling": "K+V", "cache_mode": "all", "use_tiled": False,
                    "use_batch": False, "sharpening": 0.0,
                },
            }
            model_ref = ["11", 0]
        graph["2"] = {"class_type": "CLIPTextEncode", "inputs": {"clip": clip_ref, "text": prompt}}
        graph["3"] = {"class_type": "CLIPTextEncode", "inputs": {"clip": clip_ref, "text": negative}}
        positive_ref, negative_ref = ["2", 0], ["3", 0]
        if pose_name:
            graph["30"] = {"class_type": "ControlNetLoader", "inputs": {"control_net_name": settings.pose_controlnet_name}}
            graph["31"] = {"class_type": "LoadImage", "inputs": {"image": pose_name, "upload": "image"}}
            graph["32"] = {
                "class_type": "ControlNetApplyAdvanced",
                "inputs": {
                    "positive": positive_ref, "negative": negative_ref, "control_net": ["30", 0],
                    "image": ["31", 0], "strength": float(pose_strength),
                    "start_percent": 0.0, "end_percent": 0.85,
                },
            }
            positive_ref, negative_ref = ["32", 0], ["32", 1]
        graph["5"] = {
            "class_type": "ModelSamplingContinuousEDM",
            "inputs": {
                "model": model_ref, "sampling": "edm",
                "sigma_max": settings.playground_sigma_max, "sigma_min": settings.playground_sigma_min,
            },
        }
        graph["6"] = {
            "class_type": "KSampler",
            "inputs": {
                "model": ["5", 0], "positive": positive_ref, "negative": negative_ref, "latent_image": ["4", 0],
                "seed": seed, "steps": settings.playground_steps, "cfg": settings.playground_cfg,
                "sampler_name": "dpmpp_2m", "scheduler": "sgm_uniform", "denoise": 1.0,
            },
        }
        return graph
    if family == "qwen-image":
        return {
            "1": {"class_type": "UNETLoader", "inputs": {"unet_name": checkpoint or settings.qwen_image_unet_name, "weight_dtype": "default"}},
            "2": {"class_type": "CLIPLoader", "inputs": {"clip_name": settings.qwen_image_clip_name, "type": "qwen_image"}},
            "3": {"class_type": "VAELoader", "inputs": {"vae_name": settings.qwen_edit_vae_name}},
            "4": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["2", 0], "text": prompt}},
            "5": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["2", 0], "text": negative}},
            "6": {"class_type": "ModelSamplingAuraFlow", "inputs": {"model": ["1", 0], "shift": settings.qwen_image_shift}},
            "7": {"class_type": "CFGNorm", "inputs": {"model": ["6", 0], "strength": 1.0}},
            "8": {"class_type": "EmptySD3LatentImage", "inputs": {"width": width, "height": height, "batch_size": 1}},
            "9": {
                "class_type": "KSampler",
                "inputs": {
                    "model": ["7", 0], "positive": ["4", 0], "negative": ["5", 0], "latent_image": ["8", 0],
                    "seed": seed, "steps": settings.qwen_image_steps, "cfg": settings.qwen_image_cfg,
                    "sampler_name": "euler", "scheduler": "simple", "denoise": 1.0,
                },
            },
            "10": {"class_type": "VAEDecode", "inputs": {"samples": ["9", 0], "vae": ["3", 0]}},
            "11": {"class_type": "SaveImage", "inputs": {"images": ["10", 0], "filename_prefix": "qwen_image"}},
        }
    if family == "z-image":
        model = checkpoint or settings.z_image_unet_name
        turbo = "turbo" in model.lower()
        return {
            "1": {"class_type": "UNETLoader", "inputs": {"unet_name": model, "weight_dtype": "default"}},
            "2": {"class_type": "CLIPLoader", "inputs": {"clip_name": settings.z_image_clip_name, "type": "lumina2"}},
            "3": {"class_type": "VAELoader", "inputs": {"vae_name": settings.z_image_vae_name}},
            "4": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["2", 0], "text": prompt}},
            "5": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["2", 0], "text": negative}},
            "6": {"class_type": "ModelSamplingAuraFlow", "inputs": {"model": ["1", 0], "shift": settings.z_image_shift}},
            "7": {"class_type": "EmptySD3LatentImage", "inputs": {"width": width, "height": height, "batch_size": 1}},
            "8": {
                "class_type": "KSampler",
                "inputs": {
                    "model": ["6", 0], "positive": ["4", 0], "negative": ["5", 0], "latent_image": ["7", 0],
                    "seed": seed, "steps": 4 if turbo else 30, "cfg": 1.0 if turbo else 4.0,
                    "sampler_name": "res_multistep", "scheduler": "simple", "denoise": 1.0,
                },
            },
            "9": {"class_type": "VAEDecode", "inputs": {"samples": ["8", 0], "vae": ["3", 0]}},
            "10": {"class_type": "SaveImage", "inputs": {"images": ["9", 0], "filename_prefix": "z_image"}},
        }
    model = checkpoint or settings.flux2_unet_name
    guider_model = ["2", 0] if settings.flux2_lora_name else ["1", 0]
    graph = {
        "1": {"class_type": "UNETLoader", "inputs": {"unet_name": model, "weight_dtype": "default"}},
        "3": {"class_type": "CLIPLoader", "inputs": {"clip_name": settings.flux2_clip_name, "type": "flux2"}},
        "4": {"class_type": "VAELoader", "inputs": {"vae_name": settings.flux2_vae_name}},
        "5": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["3", 0], "text": prompt}},
        "6": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["3", 0], "text": negative}},
        "7": {"class_type": "CFGGuider", "inputs": {"model": guider_model, "positive": ["5", 0], "negative": ["6", 0], "cfg": settings.flux2_cfg}},
        "8": {"class_type": "RandomNoise", "inputs": {"noise_seed": seed}},
        "9": {"class_type": "KSamplerSelect", "inputs": {"sampler_name": "euler"}},
        "10": {"class_type": "Flux2Scheduler", "inputs": {"steps": settings.flux2_steps, "width": width, "height": height}},
        "11": {"class_type": "EmptyFlux2LatentImage", "inputs": {"width": width, "height": height, "batch_size": 1}},
        "12": {
            "class_type": "SamplerCustomAdvanced",
            "inputs": {"noise": ["8", 0], "guider": ["7", 0], "sampler": ["9", 0], "sigmas": ["10", 0], "latent_image": ["11", 0]},
        },
        "13": {"class_type": "VAEDecode", "inputs": {"samples": ["12", 0], "vae": ["4", 0]}},
        "14": {"class_type": "SaveImage", "inputs": {"images": ["13", 0], "filename_prefix": "flux2"}},
    }
    if settings.flux2_lora_name:
        graph["2"] = {
            "class_type": "LoraLoaderModelOnly",
            "inputs": {"model": ["1", 0], "lora_name": settings.flux2_lora_name, "strength_model": 1.0},
        }
    return graph


def generate_image(
    prompt: str,
    negative_prompt: str,
    *,
    seed: int | None = None,
    reference_path: Path | None = None,
    checkpoint: str | None = None,
    style: str = "real",
    family: str | None = None,
    loras: list[dict] | None = None,
    pose_path: Path | None = None,
    pose_strength: float = 0.8,
    base_url: str | None = None,
    size_label: str = "NSFW DEMO",
) -> tuple[bytes, dict]:
    """Generate one image for chat or the character avatar. Returns (png_bytes, metadata).

    The style picks the workflow pair (`chat_real*` or `chat_anime*`). When the
    character has a picture and a reference workflow is configured (IPAdapter),
    that workflow is used with the picture uploaded to ComfyUI. Otherwise the plain
    text-to-image workflow is used as a fallback.
    """
    seed = random.randrange(2**31) if seed is None else seed
    if settings.image_provider == "mock":
        image = Image.new("RGB", (512, 768), (45, 32, 55))
        ImageDraw.Draw(image).text((30, 340), f"DEMO - NOT AI GENERATED\n{size_label}", fill="white")
        output = io.BytesIO()
        image.save(output, format="PNG")
        return output.getvalue(), {
            "provider": "mock",
            "seed": seed,
            "checkpoint": checkpoint,
            "style": style,
            "family": family or style,
            "loras": loras or [],
            "pose": bool(pose_path),
        }
    family = family or style
    base_url = base_url or pick_target()
    if family in DIFFUSION_FAMILIES:
        reference_name = None
        pose_name = None
        if family == "playground":
            if reference_path is not None and reference_path.is_file():
                reference_name = upload_reference(reference_path, base_url=base_url)
            if pose_path is not None:
                if not pose_path.is_file():
                    raise ComfyUIError("Skeleton di posa non trovato")
                pose_name = upload_reference(pose_path, base_url=base_url)
        workflow = _diffusion_graph(
            family, checkpoint or "", prompt, negative_prompt, seed, loras=loras,
            reference_name=reference_name, pose_name=pose_name, pose_strength=pose_strength,
        )
        started = time.perf_counter()
        data = _submit_and_wait(workflow, settings.generation_timeout, base_url=base_url)
        return data, {
            "provider": "comfyui",
            "seed": seed,
            "checkpoint": checkpoint,
            "style": style,
            "family": family,
            "loras": [],
            "reference": bool(reference_name),
            "pose": bool(pose_name),
            "seconds": time.perf_counter() - started,
        }
    plain_path, reference_setting = _style_workflows(style, family)
    has_reference = reference_path is not None and reference_path.is_file()
    workflow_path = plain_path
    if has_reference and reference_setting.is_file():
        workflow_path = reference_setting
    use_pose = pose_path is not None
    if use_pose and not pose_path.is_file():
        raise ComfyUIError("Skeleton di posa non trovato")
    if use_pose:
        if (family or style) != "real":
            raise ComfyUIError("Il controllo posa è disponibile solo per la famiglia real")
        workflow_path = (
            settings.chat_real_pose_reference_workflow_path
            if has_reference
            else settings.chat_real_pose_workflow_path
        )
        if not workflow_path.is_file():
            raise ComfyUIError("Workflow posa non trovato")
    workflow = json.loads(workflow_path.read_text())
    replacements = {
        "{{positive_prompt}}": prompt,
        "{{negative_prompt}}": negative_prompt,
        "{{seed}}": seed,
        "{{image_count}}": 1,
    }
    if use_pose:
        replacements["{{pose_image}}"] = upload_reference(pose_path, base_url=base_url)
        replacements["{{pose_strength}}"] = float(pose_strength)
        replacements["{{controlnet_name}}"] = settings.pose_controlnet_name
    used_reference = False
    if "{{reference_image}}" in json.dumps(workflow):
        if not has_reference:
            # Reference node present but the character has no picture: fall back to text-to-image.
            workflow = json.loads(plain_path.read_text())
            if "{{reference_image}}" in json.dumps(workflow):
                raise ComfyUIError("Workflow requires {{reference_image}} but the character has no picture")
        else:
            replacements["{{reference_image}}"] = upload_reference(reference_path, base_url=base_url)
            used_reference = True
    start = time.perf_counter()
    output = _run_workflow(
        workflow, replacements, 1, settings.generation_timeout, checkpoint=checkpoint, loras=loras, base_url=base_url
    )[0]
    return output, {
        "provider": "comfyui",
        "seed": seed,
        "checkpoint": checkpoint,
        "style": style,
        "family": family or style,
        "loras": loras or [],
        "reference": used_reference,
        "pose": use_pose,
        "seconds": time.perf_counter() - start,
    }
