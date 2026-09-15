#!/usr/bin/env python3
"""Download adult SDXL checkpoints for ComfyUI (resumable, parallel).

Examples:
    uv run python scripts/download_models.py --list
    uv run python scripts/download_models.py
    uv run python scripts/download_models.py --only cyberrealistic_pony --parallel 3

PornMaster Pro is distributed by its author on Civitai. This script resolves it
through the official Civitai API (never scraping the site). NSFW downloads often
require a token: set CIVITAI_TOKEN in the environment, or pass
`--civitai-model-id` / `--civitai-version-id` copied from the model page.

    CIVITAI_TOKEN=... uv run python scripts/download_models.py --only pornmaster --civitai-model-id 123456
    uv run python scripts/download_models.py --only pornmaster --civitai-query "PornMaster Pro"
"""

import argparse
import concurrent.futures
import os
import subprocess
import sys
from pathlib import Path

import httpx

DEFAULT_DIR = os.environ.get("COMFYUI_CHECKPOINTS", "/data/data_ssd/pigni/comfyUI/ComfyUI/models/checkpoints")

MODELS = {
    "cyberrealistic_pony": {
        "filename": "CyberRealisticPony_V18.0_F16.safetensors",
        "url": "https://huggingface.co/cyberdelia/CyberRealisticPony/resolve/main/CyberRealisticPony_V18.0_F16.safetensors",
        "note": "CyberRealistic Pony V18 (author FP16) - Pony-family, explicit compositions",
    },
    "lustify": {
        "filename": "lustifySDXLNSFWSFW_v20.safetensors",
        "url": "https://huggingface.co/TheImposterImposters/LUSTIFY-v2.0/resolve/main/lustifySDXLNSFWSFW_v20.safetensors",
        "note": "LUSTIFY v2.0 (author) - photoreal SDXL baseline",
    },
    "pornmaster": {
        "civitai": True,
        "filename": None,
        "note": "PornMaster Pro SDXL (author upload on Civitai, model id 1031308) - use --civitai-model-id or --civitai-query",
    },
}


def remote_size(url: str, token: str | None = None) -> int | None:
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    try:
        response = httpx.head(url, headers=headers, follow_redirects=True, timeout=30)
        response.raise_for_status()
        return int(response.headers.get("content-length", 0)) or None
    except (httpx.HTTPError, ValueError):
        return None


def resolve_civitai(args) -> tuple[str, str, int | None] | None:
    token = os.environ.get("CIVITAI_TOKEN")
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    try:
        if args.civitai_model_id:
            response = httpx.get(
                f"https://civitai.com/api/v1/models/{args.civitai_model_id}",
                headers=headers,
                timeout=60,
            )
            response.raise_for_status()
            versions = response.json().get("modelVersions", [])
        elif args.civitai_query:
            response = httpx.get(
                "https://civitai.com/api/v1/models",
                params={"query": args.civitai_query, "limit": 20},
                headers=headers,
                timeout=60,
            )
            response.raise_for_status()
            versions = []
            for model in response.json().get("items", []):
                versions.extend(model.get("modelVersions", []))
        else:
            print(
                "  PornMaster needs --civitai-model-id (preferred) or --civitai-query.\n"
                "  Copy the numeric id from the model page URL, e.g. civitai.com/models/<id>."
            )
            return None
        if args.civitai_version_id:
            versions = [v for v in versions if str(v.get("id")) == str(args.civitai_version_id)]
            if not versions:
                print(f"  Version {args.civitai_version_id} non trovata nel modello.")
                return None
        candidates = []
        for version in versions:
            for item in version.get("files", []):
                if (item.get("type") or "").lower() != "model":
                    continue
                if not (item.get("name") or "").lower().endswith(".safetensors"):
                    continue
                if args.civitai_file and args.civitai_file.lower() not in (item.get("name") or "").lower():
                    continue
                size = int((item.get("sizeKB") or 0) * 1024)
                if size < 3_000_000_000:
                    continue
                candidates.append((version, item, size))
        if not candidates:
            token_note = "" if token else " (NSFW models may need CIVITAI_TOKEN)"
            print(f"  Nessun checkpoint SDXL trovato nei risultati{token_note}.")
            return None
        # Prefer a standard FP16 file (~7 GB) over FP32/merged variants when both exist.
        standard = [entry for entry in candidates if entry[2] <= 10_000_000_000]
        version, item, size = max(standard or candidates, key=lambda entry: entry[2])
        name = Path(item["name"]).name
        print(f"  Civitai: {version.get('name')} ({version.get('baseModel')}) -> {name} {size / 1e9:.2f} GB")
        return name, item["downloadUrl"], size
    except (httpx.HTTPError, KeyError, ValueError) as error:
        print(f"  Civitai non raggiungibile: {error}")
        return None


def download(key: str, url: str, filename: str, expected: int | None, target_dir: Path) -> bool:
    final = target_dir / filename
    if final.is_file() and (expected is None or abs(final.stat().st_size - expected) < 1_000_000):
        print(f"[skip] {filename} già presente")
        return True
    part = target_dir / f"{filename}.part"
    print(f"[down] {filename} -> {final}")
    command = [
        "curl",
        "-L",
        "-C",
        "-",
        "--retry",
        "3",
        "--retry-delay",
        "5",
        "--fail",
        "--output",
        str(part),
        url,
    ]
    token = os.environ.get("CIVITAI_TOKEN")
    if token and "civitai.com" in url:
        command[1:1] = ["-H", f"Authorization: Bearer {token}"]
    result = subprocess.run(command, check=False)
    if result.returncode != 0:
        print(f"[fail] {filename}: curl exit {result.returncode} (file parziale in {part.name})")
        return False
    size = part.stat().st_size
    if expected and abs(size - expected) > 1_000_000:
        print(
            f"[warn] {filename}: dimensione {size / 1e9:.2f} GB diversa dall'attesa {expected / 1e9:.2f} GB"
        )
    part.replace(final)
    print(f"[ok]   {filename} ({size / 1e9:.2f} GB)")
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description="Download checkpoints for ComfyUI")
    parser.add_argument("--only", nargs="*", choices=sorted(MODELS), help="only these models")
    parser.add_argument("--list", action="store_true", help="show the catalog and exit")
    parser.add_argument("--parallel", type=int, default=2, help="parallel downloads (default 2)")
    parser.add_argument("--checkpoint-dir", default=DEFAULT_DIR)
    parser.add_argument("--civitai-model-id", type=int, default=None)
    parser.add_argument("--civitai-version-id", type=int, default=None)
    parser.add_argument("--civitai-file", default=None, help="substring of the file name to pick")
    parser.add_argument("--civitai-query", default=None)
    args = parser.parse_args()

    if args.list:
        for key, model in MODELS.items():
            print(f"{key:24} {model.get('filename') or 'civitai':<48} {model['note']}")
        return 0

    target_dir = Path(args.checkpoint_dir)
    target_dir.mkdir(parents=True, exist_ok=True)
    jobs = []
    for key in args.only or MODELS:
        model = MODELS[key]
        if model.get("civitai"):
            print(f"[info] {key}: {model['note']}")
            resolved = resolve_civitai(args)
            if resolved is None:
                continue
            filename, url, size = resolved
        else:
            filename, url = model["filename"], model["url"]
            size = remote_size(url)
        jobs.append((key, url, filename, size))

    if not jobs:
        print("Niente da scaricare.")
        return 1
    failures = 0
    with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, args.parallel)) as pool:
        futures = [pool.submit(download, key, url, name, size, target_dir) for key, url, name, size in jobs]
        for future in concurrent.futures.as_completed(futures):
            if not future.result():
                failures += 1
    if failures:
        print(f"{failures} download falliti. Rilancia lo script: riprende dal file parziale.")
        return 1
    print("Modelli pronti in", target_dir)
    return 0


if __name__ == "__main__":
    sys.exit(main())
