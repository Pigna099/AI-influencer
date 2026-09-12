import io
import json
import time

import httpx
from PIL import Image, ImageDraw

from ..config import settings


def parameterize(value, replacements):
    if isinstance(value, dict):
        return {key: parameterize(item, replacements) for key, item in value.items()}
    if isinstance(value, list):
        return [parameterize(item, replacements) for item in value]
    if isinstance(value, str) and value in replacements:
        return replacements[value]
    return value


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
    serialized = json.dumps(workflow)
    for placeholder in ("{{positive_prompt}}", "{{negative_prompt}}", "{{seed}}", "{{image_count}}"):
        if placeholder not in serialized:
            raise ValueError(f"Workflow missing placeholder: {placeholder}")
    prompt = parameterize(
        workflow,
        {
            "{{positive_prompt}}": brief.positive_prompt,
            "{{negative_prompt}}": brief.negative_prompt,
            "{{seed}}": request["seed"],
            "{{image_count}}": request["image_count"],
        },
    )
    deadline = time.monotonic() + settings.generation_timeout
    with httpx.Client(base_url=settings.comfyui_url, timeout=30) as client:
        response = client.post("/prompt", json={"prompt": prompt})
        response.raise_for_status()
        data = response.json()
        if data.get("node_errors") or "prompt_id" not in data:
            raise ValueError("ComfyUI rejected workflow")
        prompt_id = data["prompt_id"]
        while time.monotonic() < deadline:
            response = client.get(f"/history/{prompt_id}")
            response.raise_for_status()
            history = response.json().get(prompt_id)
            if history:
                if history.get("status", {}).get("status_str") == "error":
                    raise RuntimeError("ComfyUI generation failed")
                outputs = []
                for node in history.get("outputs", {}).values():
                    for asset in node.get("images", []):
                        if asset.get("type") != "output":
                            continue
                        response = client.get(
                            "/view",
                            params={
                                key: asset[key] for key in ("filename", "subfolder", "type") if key in asset
                            },
                        )
                        response.raise_for_status()
                        # Decode and re-encode to ensure stored media is a real PNG.
                        image = Image.open(io.BytesIO(response.content))
                        output = io.BytesIO()
                        image.save(output, format="PNG")
                        outputs.append(output.getvalue())
                if len(outputs) != request["image_count"]:
                    raise ValueError("Unexpected image count: use one SaveImage output node")
                return outputs, {"provider": "comfyui", "prompt_id": prompt_id, "workflow": prompt}
            time.sleep(2)
    raise TimeoutError(
        "ComfyUI timeout; remote generation may still be running. Check ComfyUI before retrying."
    )
