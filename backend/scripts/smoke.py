"""Run from backend with uv run python scripts/smoke.py; creates demo records."""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import httpx

from app.config import settings

with httpx.Client(
    base_url="http://127.0.0.1:8010", headers={"X-API-Key": settings.api_key}, timeout=30
) as api:
    response = api.get("/health")
    response.raise_for_status()
    print("Health:", response.json())
    response = api.post(
        "/influencers",
        json={
            "name": "Demo - da personalizzare",
            "bible": {
                "description": "Personaggio anime adulto, artista di 25 anni, capelli castani e occhi verdi",
                "style": "anime illustration",
                "tone_of_voice": "cordiale, in italiano",
            },
        },
    )
    response.raise_for_status()
    influencer_id = response.json()["id"]
    response = api.post(
        "/content-jobs",
        json={
            "influencer_id": influencer_id,
            "theme": "Una passeggiata al parco",
            "outfit": "giacca azzurra",
            "scenario": "parco in primavera",
        },
    )
    response.raise_for_status()
    job_id = response.json()["id"]
    for _ in range(150):
        response = api.get(f"/content-jobs/{job_id}")
        response.raise_for_status()
        data = response.json()
        if data["job"]["status"] == "awaiting_review":
            asset = api.get(f"/assets/{data['assets'][0]['id']}/file")
            asset.raise_for_status()
            assert asset.content.startswith(b"\x89PNG")
            response = api.post(
                f"/content-jobs/{job_id}/review",
                json={"decision": "approved", "note": "Test tecnico della pipeline; non pubblicare."},
            )
            response.raise_for_status()
            print("PASS influencer:", influencer_id, "job:", job_id)
            print("Caption:", data["job"]["result"]["brief"]["caption"])
            break
        if data["job"]["status"] == "failed":
            raise RuntimeError(data["job"]["error"])
        time.sleep(2)
    else:
        raise TimeoutError("Job did not finish within five minutes")
