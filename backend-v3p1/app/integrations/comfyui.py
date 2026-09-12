import io
import json
import random
import time
from pathlib import Path

import httpx
from PIL import Image, ImageDraw

from ..config import settings

_probe = {"at": 0.0, "ok": False}
PLACEHOLDERS = ("{{positive_prompt}}", "{{negative_prompt}}", "{{seed}}", "{{image_count}}")


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
    """Cheap probe so chat only offers photos while the image service is reachable."""
    if settings.image_provider == "mock":
        return True
    now = time.monotonic()
    if now - _probe["at"] > ttl_seconds:
        try:
            response = httpx.get(f"{settings.comfyui_url}/system_stats", timeout=3)
            response.raise_for_status()
            _probe.update(at=now, ok=True)
        except httpx.HTTPError:
            _probe.update(at=now, ok=False)
    return _probe["ok"]


def get_checkpoints() -> list[str]:
    """Checkpoints installed in ComfyUI, for the per-character selector."""
    if settings.image_provider == "mock":
        return ["mock-sdxl.safetensors"]
    try:
        response = httpx.get(f"{settings.comfyui_url}/object_info/CheckpointLoaderSimple", timeout=10)
        response.raise_for_status()
        options = response.json()["CheckpointLoaderSimple"]["input"]["required"]["ckpt_name"][0]
        return list(options)
    except (httpx.HTTPError, KeyError, TypeError):
        return []


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


def upload_reference(path: Path) -> str:
    """Upload the character picture to ComfyUI and return its input filename."""
    try:
        with (
            httpx.Client(base_url=settings.comfyui_url, timeout=60) as client,
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
    workflow: dict, replacements: dict, expected: int, timeout: int, checkpoint: str | None = None
) -> list[bytes]:
    serialized = json.dumps(workflow)
    for placeholder in PLACEHOLDERS:
        if placeholder not in serialized:
            raise ComfyUIError(f"Workflow missing placeholder: {placeholder}")
    prompt = parameterize(apply_checkpoint(workflow, checkpoint), replacements)
    deadline = time.monotonic() + timeout
    try:
        with httpx.Client(base_url=settings.comfyui_url, timeout=30) as client:
            response = client.post("/prompt", json={"prompt": prompt})
            response.raise_for_status()
            data = response.json()
            if data.get("node_errors") or "prompt_id" not in data:
                raise ComfyUIError("ComfyUI rejected workflow")
            prompt_id = data["prompt_id"]
            while time.monotonic() < deadline:
                response = client.get(f"/history/{prompt_id}")
                response.raise_for_status()
                history = response.json().get(prompt_id)
                if history:
                    if history.get("status", {}).get("status_str") == "error":
                        raise ComfyUIError("ComfyUI generation failed")
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


def _style_workflows(style: str) -> tuple[Path, Path]:
    """Plain and reference workflow for the requested style, with legacy fallback."""
    if style == "anime":
        plain, reference = settings.chat_anime_workflow_path, settings.chat_anime_reference_workflow_path
    else:
        plain, reference = settings.chat_real_workflow_path, settings.chat_real_reference_workflow_path
    if not plain.is_file():
        return settings.chat_workflow_path, settings.chat_reference_workflow_path
    return plain, reference


def generate_image(
    prompt: str,
    negative_prompt: str,
    *,
    seed: int | None = None,
    reference_path: Path | None = None,
    checkpoint: str | None = None,
    style: str = "real",
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
        return output.getvalue(), {"provider": "mock", "seed": seed, "checkpoint": checkpoint, "style": style}
    plain_path, reference_setting = _style_workflows(style)
    has_reference = reference_path is not None and reference_path.is_file()
    workflow_path = plain_path
    if has_reference and reference_setting.is_file():
        workflow_path = reference_setting
    workflow = json.loads(workflow_path.read_text())
    replacements = {
        "{{positive_prompt}}": prompt,
        "{{negative_prompt}}": negative_prompt,
        "{{seed}}": seed,
        "{{image_count}}": 1,
    }
    used_reference = False
    if "{{reference_image}}" in json.dumps(workflow):
        if not has_reference:
            # Reference node present but the character has no picture: fall back to text-to-image.
            workflow = json.loads(plain_path.read_text())
            if "{{reference_image}}" in json.dumps(workflow):
                raise ComfyUIError("Workflow requires {{reference_image}} but the character has no picture")
        else:
            replacements["{{reference_image}}"] = upload_reference(reference_path)
            used_reference = True
    start = time.perf_counter()
    output = _run_workflow(workflow, replacements, 1, settings.generation_timeout, checkpoint=checkpoint)[0]
    return output, {
        "provider": "comfyui",
        "seed": seed,
        "checkpoint": checkpoint,
        "style": style,
        "reference": used_reference,
        "seconds": time.perf_counter() - start,
    }
