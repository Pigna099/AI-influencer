#!/usr/bin/env python3
"""Host-side LoRA training worker for the AI influencer pipeline.

Polls the backend for queued training jobs, runs kohya sd-scripts on a free GPU,
streams progress back to the API and publishes the trained LoRA to ComfyUI.
"""

import argparse
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp"}
STEP_RE = re.compile(r"(\d+)/(\d+)\s*\[")
LOSS_RE = re.compile(r"loss=([0-9.]+)")


def log(message):
    print(f"[{time.strftime('%H:%M:%S')}] {message}", flush=True)


def read_env(path):
    data = {}
    file = Path(path)
    if not file.is_file():
        return data
    for line in file.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        data[key.strip()] = value.strip().strip('"').strip("'")
    return data


class Api:
    def __init__(self, base_url, api_key):
        self.base = base_url.rstrip("/")
        self.key = api_key

    def call(self, method, path, body=None):
        data = json.dumps(body).encode() if body is not None else None
        request = urllib.request.Request(self.base + path, data=data, method=method)
        request.add_header("X-API-Key", self.key)
        request.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                payload = response.read()
                return json.loads(payload) if payload else None
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode(errors="replace")
            raise RuntimeError(f"{method} {path} failed: {exc.code} {detail[:300]}") from exc


def free_gpus():
    try:
        out = subprocess.run(
            ["nvidia-smi", "--query-gpu=index,memory.free", "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=15, check=True,
        ).stdout
    except Exception:  # noqa: BLE001 - nvidia-smi may be missing or fail; treat GPUs as unknown
        return []
    result = []
    for line in out.strip().splitlines():
        index, free = line.split(",")
        result.append((int(index), int(free)))
    return sorted(result, key=lambda item: item[1], reverse=True)


def host_path(value, data_dir):
    text = str(value)
    if text.startswith("/app/data"):
        return Path(str(data_dir) + text[len("/app/data"):])
    return Path(text)


def prepare_dataset(job, args):
    params = job["params"]
    source = host_path(params["images_dir"], args.data_dir)
    if not source.is_dir():
        raise RuntimeError(f"images folder not found on host: {source}")
    stem = params["output_stem"]
    repeats = int(params.get("repeats") or 10)
    trigger = params.get("trigger") or ""
    prefix = params.get("caption_prefix") or ""
    run_dir = args.trainer_dir / "runs" / job["id"]
    concept = run_dir / "dataset" / f"{repeats}_{stem}"
    if concept.exists():
        shutil.rmtree(concept)
    concept.mkdir(parents=True)
    images = sorted(p for p in source.iterdir() if p.suffix.lower() in IMAGE_SUFFIXES)
    if len(images) < 4:
        raise RuntimeError(f"need at least 4 images, found {len(images)} in {source}")
    for image in images:
        shutil.copy2(image, concept / image.name)
        sidecar = image.with_suffix(".txt")
        caption = sidecar.read_text().strip() if sidecar.is_file() else ""
        if prefix:
            caption = f"{prefix.rstrip()}{(' ' + caption) if caption else ''}"
        if trigger and trigger not in caption:
            caption = f"{trigger}, {caption}".strip(", ")
        (concept / f"{image.stem}.txt").write_text(caption or trigger or image.stem)
    return run_dir, run_dir / "dataset", len(images)


def pick_gpu(params):
    if params.get("gpu") is not None:
        return str(int(params["gpu"]))
    ranked = free_gpus()
    return str(ranked[0][0]) if ranked else "0"


def build_command(job, args, dataset_dir, run_dir, steps):
    params = job["params"]
    stem = params["output_stem"]
    if not params.get("base_checkpoint"):
        raise RuntimeError("base checkpoint not set for this LoRA")
    resolution = int(params.get("resolution") or 1024)
    rank = int(params.get("rank") or 32)
    checkpoint = args.models_dir / "checkpoints" / str(params["base_checkpoint"])
    if not checkpoint.is_file():
        raise RuntimeError(f"checkpoint not found: {checkpoint}")
    command = [
        str(args.venv / "bin" / "accelerate"), "launch",
        "--num_processes", "1", "--num_machines", "1",
        "--mixed_precision", "bf16", "--dynamo_backend", "no",
        "--num_cpu_threads_per_process", "4",
        "sdxl_train_network.py",
        "--pretrained_model_name_or_path", str(checkpoint),
        "--train_data_dir", str(dataset_dir),
        "--output_dir", str(run_dir / "output"),
        "--output_name", stem,
        "--logging_dir", str(run_dir / "logs"),
        "--network_module", "networks.lora",
        "--network_dim", str(rank),
        "--network_alpha", str(max(1, rank // 2)),
        "--resolution", f"{resolution},{resolution}",
        "--train_batch_size", str(int(params.get("batch_size") or 1)),
        "--max_train_steps", str(steps),
        "--learning_rate", str(params.get("learning_rate") or 1e-4),
        "--optimizer_type", "AdamW8bit",
        "--lr_scheduler", "cosine",
        "--lr_warmup_steps", "50",
        "--mixed_precision", "bf16",
        "--save_precision", "bf16",
        "--save_model_as", "safetensors",
        "--save_every_n_steps", str(int(params.get("save_every") or 500)),
        "--gradient_checkpointing",
        "--sdpa",
        "--cache_latents",
        "--cache_latents_to_disk",
        "--max_data_loader_n_workers", "2",
        "--persistent_data_loader_workers",
        "--caption_extension", ".txt",
        "--shuffle_caption",
        "--seed", "42",
        "--min_snr_gamma", "5",
        "--no_half_vae",
    ]
    if params.get("family") == "real":
        command += ["--noise_offset", "0.05"]
    return command


def run_job(job, args, api):
    job_id = job["id"]
    params = job["params"]
    run_dir, dataset_dir, image_count = prepare_dataset(job, args)
    steps = int(params.get("steps") or max(200, image_count * 100))
    gpu = pick_gpu(params)
    log_file = run_dir / "train.log"
    command = build_command(job, args, dataset_dir, run_dir, steps)
    cache_dir = args.trainer_dir / "hf-cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    env = {
        **os.environ,
        "CUDA_VISIBLE_DEVICES": gpu,
        "PYTHONUNBUFFERED": "1",
        "HF_HOME": str(cache_dir),
        "HF_HUB_CACHE": str(cache_dir / "hub"),
    }
    log(f"job {job_id}: {image_count} images, {steps} steps, rank {params.get('rank')}, GPU {gpu}")
    log(f"job {job_id}: log -> {log_file}")
    started = time.time()
    final_loss = None
    last_post = 0.0
    canceled = False
    code = 1
    with open(log_file, "w") as handle:
        handle.write(" ".join(command) + "\n\n")
        handle.flush()
        process = subprocess.Popen(
            command, cwd=str(args.kohya_dir), stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, text=True, env=env, bufsize=1,
        )
        for line in process.stdout:
            handle.write(line)
            handle.flush()
            match = STEP_RE.search(line)
            if match and time.time() - last_post > 5:
                last_post = time.time()
                last_step = int(match.group(1))
                total = int(match.group(2))
                loss = LOSS_RE.search(line)
                if loss:
                    final_loss = float(loss.group(1))
                try:
                    response = api.call(
                        "POST", f"/api/training-jobs/{job_id}/progress",
                        {"progress": {"step": last_step, "total": total, "loss": final_loss},
                         "log_path": str(log_file)},
                    )
                    if response and response.get("status") == "canceled":
                        canceled = True
                        process.terminate()
                except RuntimeError as exc:
                    log(f"job {job_id}: progress update failed: {exc}")
        code = process.wait(timeout=120)
    seconds = int(time.time() - started)
    if canceled:
        log(f"job {job_id}: canceled by user")
        return
    if code != 0:
        tail = "".join(log_file.read_text().splitlines(keepends=True)[-12:]).strip()
        api.call(
            "POST", f"/api/training-jobs/{job_id}/complete",
            {"success": False, "error": f"kohya exit {code}: {tail[-1500:]}"},
        )
        log(f"job {job_id}: failed (exit {code})")
        return
    output = sorted((run_dir / "output").glob("*.safetensors"))
    if not output:
        api.call("POST", f"/api/training-jobs/{job_id}/complete",
                 {"success": False, "error": "no safetensors produced"})
        return
    trained = output[-1]
    comfy_target = args.models_dir / "loras" / params["filename"]
    comfy_target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(trained, comfy_target)
    artifact = Path(args.data_dir) / "loras" / params["artifact_filename"]
    artifact.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(trained, artifact)
    metrics = {
        "images": image_count, "steps": steps, "final_loss": final_loss, "seconds": seconds,
        "gpu": gpu, "rank": params.get("rank"), "log_path": str(log_file),
    }
    api.call(
        "POST", f"/api/training-jobs/{job_id}/complete",
        {"success": True, "filename": params["filename"],
         "artifact_filename": params["artifact_filename"], "metrics": metrics},
    )
    log(f"job {job_id}: done in {seconds}s -> {comfy_target}")


def recover_stale(api, max_idle_minutes=15):
    try:
        running = api.call("GET", "/api/training-jobs?status=running&limit=20")
    except RuntimeError as exc:
        log(f"recovery scan failed: {exc}")
        return
    for job in running:
        stamp = job.get("heartbeat_at") or job.get("started_at")
        if not stamp:
            continue
        try:
            age = time.time() - datetime.fromisoformat(stamp).timestamp()
        except ValueError:
            continue
        if age > max_idle_minutes * 60:
            log(f"marking stale job {job['id']} as failed (idle {int(age / 60)} min)")
            try:
                api.call("POST", f"/api/training-jobs/{job['id']}/complete",
                         {"success": False, "error": f"worker lost: no heartbeat for {int(age / 60)} min"})
            except RuntimeError as exc:
                log(f"could not close stale job {job['id']}: {exc}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api-url", default="http://127.0.0.1:8010")
    parser.add_argument("--env-file", default=str(Path(__file__).resolve().parents[2] / ".env"))
    parser.add_argument("--api-key", default="")
    parser.add_argument("--trainer-dir", default="/data/data_ssd/pigni/trainer")
    parser.add_argument("--kohya-dir", default="")
    parser.add_argument("--data-dir", default="/data/data_ssd/pigni/ai-influencer/backend-v4p1/data")
    parser.add_argument("--models-dir", default="/data/data_ssd/pigni/comfyUI/ComfyUI/models")
    parser.add_argument("--poll-seconds", type=int, default=10)
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    args.trainer_dir = Path(args.trainer_dir)
    args.kohya_dir = Path(args.kohya_dir) if args.kohya_dir else args.trainer_dir / "sd-scripts"
    args.venv = args.trainer_dir / "venv"
    args.data_dir = Path(args.data_dir)
    args.models_dir = Path(args.models_dir)
    env = read_env(args.env_file)
    api_key = args.api_key or env.get("API_KEY") or ""
    if not api_key:
        print("missing API_KEY (use --api-key or --env-file)", file=sys.stderr)
        return 1
    api = Api(args.api_url, api_key)
    worker = socket.gethostname()
    log(f"trainer worker {worker} polling {args.api_url}")
    recover_stale(api)
    while True:
        try:
            jobs = api.call("GET", "/api/training-jobs?status=queued&limit=1")
        except RuntimeError as exc:
            log(f"poll failed: {exc}")
            time.sleep(args.poll_seconds)
            continue
        if not jobs:
            if args.once:
                return 0
            time.sleep(args.poll_seconds)
            continue
        job = jobs[0]
        try:
            claimed = api.call("POST", f"/api/training-jobs/{job['id']}/claim", {"worker": worker})
        except RuntimeError as exc:
            log(f"claim failed: {exc}")
            time.sleep(args.poll_seconds)
            continue
        try:
            run_job(claimed, args, api)
        except Exception as exc:  # noqa: BLE001 - a crashed job must be reported and the worker kept alive
            log(f"job {job['id']} crashed: {exc}")
            try:
                api.call("POST", f"/api/training-jobs/{job['id']}/complete",
                         {"success": False, "error": str(exc)[:1500]})
            except RuntimeError:
                pass
        if args.once:
            return 0


if __name__ == "__main__":
    sys.exit(main())
