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


def _run_workflow(workflow: dict, replacements: dict, expected: int, timeout: int) -> list[bytes]:
    serialized = json.dumps(workflow)
    for placeholder in PLACEHOLDERS:
        if placeholder not in serialized:
            raise ComfyUIError(f"Workflow missing placeholder: {placeholder}")
    prompt = parameterize(workflow, replacements)
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


def generate_image(
    prompt: str,
    negative_prompt: str,
    *,
    seed: int | None = None,
    reference_path: Path | None = None,
    size_label: str = "NSFW DEMO",
) -> tuple[bytes, dict]:
    """Generate one image for chat or the character avatar. Returns (png_bytes, metadata)."""
    seed = random.randrange(2**31) if seed is None else seed
    if settings.image_provider == "mock":
        image = Image.new("RGB", (512, 768), (45, 32, 55))
        ImageDraw.Draw(image).text((30, 340), f"DEMO - NOT AI GENERATED\n{size_label}", fill="white")
        output = io.BytesIO()
        image.save(output, format="PNG")
        return output.getvalue(), {"provider": "mock", "seed": seed}
    workflow = json.loads(settings.chat_workflow_path.read_text())
    replacements = {
        "{{positive_prompt}}": prompt,
        "{{negative_prompt}}": negative_prompt,
        "{{seed}}": seed,
        "{{image_count}}": 1,
    }
    if "{{reference_image}}" in json.dumps(workflow):
        # Only used by workflows that wire a reference image (for example IPAdapter).
        if reference_path is None or not reference_path.is_file():
            raise ComfyUIError("Workflow requires {{reference_image}} but the character has no picture")
        replacements["{{reference_image}}"] = upload_reference(reference_path)
    start = time.perf_counter()
    output = _run_workflow(workflow, replacements, 1, settings.generation_timeout)[0]
    return output, {
        "provider": "comfyui",
        "seed": seed,
        "seconds": time.perf_counter() - start,
    }
