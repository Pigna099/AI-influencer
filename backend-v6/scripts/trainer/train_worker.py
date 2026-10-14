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
import signal
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp"}
COMFYUI_PORTS = (8188, 8189, 8190, 8191)
MIN_FREE_MIB = int(os.environ.get("TRAINER_MIN_FREE_MIB") or 16000)
STEP_RE = re.compile(r"steps:\s+\d+%\|[^|]*\|\s*(\d+)/(\d+)\s*\[")
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
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise RuntimeError(f"{method} {path} unreachable: {exc}") from exc


def free_gpus():
    try:
        out = subprocess.run(
            ["nvidia-smi", "--query-gpu=index,memory.free,pcie.link.width.current", "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=15, check=True,
        ).stdout
    except Exception:  # noqa: BLE001 - nvidia-smi may be missing or fail; treat GPUs as unknown
        return []
    result = []
    for line in out.strip().splitlines():
        index, free, width = line.split(",")
        result.append((int(index), int(free), int(width)))
    # Block-swap training is PCIe-bound: prefer the GPU with the widest link when free memory ties.
    return sorted(result, key=lambda item: (item[1], item[2]), reverse=True)


def comfyui_urls():
    raw = os.environ.get("COMFYUI_URLS") or ""
    urls = [item.strip().rstrip("/") for item in raw.split(",") if item.strip()]
    return urls or [f"http://127.0.0.1:{port}" for port in COMFYUI_PORTS]


def free_comfyuis():
    payload = json.dumps({"unload_models": True, "free_memory": True}).encode()
    for url in comfyui_urls():
        request = urllib.request.Request(url + "/free", data=payload, method="POST")
        request.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(request, timeout=30):
                pass
        except Exception as exc:  # noqa: BLE001 - instance may be down; best effort
            log(f"free {url} failed: {exc}")


def ensure_free_gpu():
    ranked = free_gpus()
    if not ranked or ranked[0][1] >= MIN_FREE_MIB:
        return ranked
    log(f"training needs {MIN_FREE_MIB} MiB free, best GPU has {ranked[0][1]}: unloading ComfyUI models")
    free_comfyuis()
    deadline = time.time() + 90
    while time.time() < deadline:
        time.sleep(5)
        ranked = free_gpus()
        if ranked and ranked[0][1] >= MIN_FREE_MIB:
            log(f"GPU {ranked[0][0]} has {ranked[0][1]} MiB free")
            return ranked
    log(f"warning: best GPU still has {ranked[0][1] if ranked else 0} MiB free, training may fail")
    return ranked


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


def pick_gpu(params, rank=None):
    if params.get("gpu") is not None:
        return str(int(params["gpu"]))
    ranked = rank if rank is not None else ensure_free_gpu()
    if not ranked:
        return "0"
    eligible = [item for item in ranked if item[1] >= MIN_FREE_MIB] or ranked
    best = max(eligible, key=lambda item: (item[2], item[1]))
    return str(best[0])


QWEN_FP8_MARKERS = ("_fp8_e4m3fn", "_fp8_scaled", "_fp8mixed", "_fp8_hq", "_nvfp4")
QWEN_BLOCKS_TO_SWAP = "20"


def resolve_checkpoint(args, family, name):
    if family == "qwen-image":
        base = args.models_dir / "diffusion_models"
        stem = name
        for marker in QWEN_FP8_MARKERS:
            if marker in stem:
                stem = stem.replace(marker, "_bf16")
                break
        candidate = base / stem
        if candidate.is_file():
            return candidate
        raise RuntimeError(
            f"Qwen training requires the bf16 weights: {stem} not found in {base} "
            "(fp8 files are not supported by musubi-tuner)"
        )
    checkpoint = args.models_dir / "checkpoints" / name
    if not checkpoint.is_file():
        raise RuntimeError(f"checkpoint not found: {checkpoint}")
    return checkpoint


def write_musubi_config(run_dir, dataset_dir, params):
    stem = params["output_stem"]
    concept = dataset_dir / f"{int(params.get('repeats') or 10)}_{stem}"
    if not concept.is_dir():
        raise RuntimeError(f"dataset folder not found: {concept}")
    cache = run_dir / "musubi_cache"
    cache.mkdir(parents=True, exist_ok=True)
    resolution = int(params.get("resolution") or 1024)
    config = run_dir / "musubi_dataset.toml"
    config.write_text(
        "[general]\n"
        f"resolution = [{resolution}, {resolution}]\n"
        'caption_extension = ".txt"\n'
        f"batch_size = {int(params.get('batch_size') or 1)}\n"
        "enable_bucket = false\n"
        "bucket_no_upscale = true\n\n"
        "[[datasets]]\n"
        f'image_directory = "{concept}"\n'
        f'cache_directory = "{cache}"\n'
        "num_repeats = 1\n"
    )
    return config


def build_qwen_commands(job, args, dataset_dir, run_dir, steps):
    params = job["params"]
    stem = params["output_stem"]
    rank = int(params.get("rank") or 32)
    if not params.get("base_checkpoint"):
        raise RuntimeError("base checkpoint not set for this LoRA")
    dit = resolve_checkpoint(args, "qwen-image", str(params["base_checkpoint"]))
    vae = args.models_dir / "vae" / "qwen_image_vae.safetensors"
    text_encoder = args.models_dir / "text_encoders" / "qwen_2.5_vl_7b.safetensors"
    for path in (vae, text_encoder):
        if not path.is_file():
            raise RuntimeError(f"missing file for Qwen training: {path}")
    config = write_musubi_config(run_dir, dataset_dir, params)
    python = str(args.musubi_venv / "bin" / "python")
    accelerate = str(args.musubi_venv / "bin" / "accelerate")
    package = args.musubi_dir / "src" / "musubi_tuner"
    learning_rate = params.get("learning_rate") or 5e-5
    save_every = int(params.get("save_every") or 500)
    return [
        ("cache latents", [
            python, str(package / "qwen_image_cache_latents.py"),
            "--dataset_config", str(config), "--vae", str(vae), "--model_version", "original",
        ]),
        ("cache text encoder", [
            python, str(package / "qwen_image_cache_text_encoder_outputs.py"),
            "--dataset_config", str(config), "--text_encoder", str(text_encoder),
            "--batch_size", "1", "--model_version", "original",
        ]),
        ("train", [
            accelerate, "launch", "--num_processes", "1", "--num_machines", "1",
            "--mixed_precision", "bf16", "--num_cpu_threads_per_process", "1",
            str(package / "qwen_image_train_network.py"),
            "--dit", str(dit), "--vae", str(vae), "--text_encoder", str(text_encoder),
            "--model_version", "original", "--dataset_config", str(config),
            "--sdpa", "--mixed_precision", "bf16",
            "--timestep_sampling", "shift", "--weighting_scheme", "none",
            "--discrete_flow_shift", "2.2",
            "--optimizer_type", "adamw8bit", "--learning_rate", str(learning_rate),
            "--gradient_checkpointing",
            "--max_data_loader_n_workers", "2", "--persistent_data_loader_workers",
            "--network_module", "networks.lora_qwen_image",
            "--network_dim", str(rank), "--network_alpha", str(max(1, rank // 2)),
            "--max_train_steps", str(steps),
            "--save_every_n_steps", str(save_every),
            "--seed", "42",
            "--output_dir", str(run_dir / "output"), "--output_name", stem,
            "--fp8_base", "--fp8_scaled", "--blocks_to_swap", QWEN_BLOCKS_TO_SWAP,
            "--use_pinned_memory_for_block_swap",
        ]),
    ]


def build_command(job, args, dataset_dir, run_dir, steps):
    params = job["params"]
    stem = params["output_stem"]
    if not params.get("base_checkpoint"):
        raise RuntimeError("base checkpoint not set for this LoRA")
    resolution = int(params.get("resolution") or 1024)
    rank = int(params.get("rank") or 32)
    checkpoint = resolve_checkpoint(args, str(params.get("family") or "real"), str(params["base_checkpoint"]))
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


def stop_process(process):
    try:
        os.killpg(os.getpgid(process.pid), signal.SIGTERM)
    except (ProcessLookupError, PermissionError):
        return
    try:
        process.wait(timeout=30)
        return
    except subprocess.TimeoutExpired:
        pass
    try:
        os.killpg(os.getpgid(process.pid), signal.SIGKILL)
    except (ProcessLookupError, PermissionError):
        pass
    try:
        process.wait(timeout=30)
    except subprocess.TimeoutExpired:
        pass


def launch_training(job_id, command, env, log_file, args, api, cwd=None):
    state = {"loss": None, "last_post": 0.0}
    canceled = False
    with open(log_file, "w") as handle:
        handle.write(" ".join(command) + "\n\n")
        handle.flush()
        process = subprocess.Popen(
            command, cwd=str(cwd or args.kohya_dir), stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, text=True, env=env, bufsize=1, start_new_session=True,
        )
        for line in process.stdout:
            handle.write(line)
            handle.flush()
            match = STEP_RE.search(line)
            if match and time.time() - state["last_post"] > 5:
                state["last_post"] = time.time()
                last_step = int(match.group(1))
                total = int(match.group(2))
                loss = LOSS_RE.search(line)
                if loss:
                    state["loss"] = float(loss.group(1))
                try:
                    response = api.call(
                        "POST", f"/api/training-jobs/{job_id}/progress",
                        {"progress": {"step": last_step, "total": total, "loss": state["loss"]},
                         "log_path": str(log_file)},
                    )
                    if response and response.get("status") == "canceled":
                        canceled = True
                        log(f"job {job_id}: cancellation detected, stopping training")
                        stop_process(process)
                        break
                except RuntimeError as exc:
                    log(f"job {job_id}: progress update failed: {exc}")
                    if "409" in str(exc):
                        try:
                            state = api.call("GET", f"/api/training-jobs/{job_id}")
                            if state and state.get("status") == "canceled":
                                canceled = True
                                log(f"job {job_id}: cancellation detected, stopping training")
                                stop_process(process)
                                break
                        except RuntimeError:
                            pass
    return process.wait(timeout=120), canceled, state["loss"]


def run_job(job, args, api):
    job_id = job["id"]
    params = job["params"]
    run_dir, dataset_dir, image_count = prepare_dataset(job, args)
    steps = int(params.get("steps") or max(200, image_count * 100))
    log_file = run_dir / "train.log"
    family = str(params.get("family") or "real")
    if family == "qwen-image":
        commands = build_qwen_commands(job, args, dataset_dir, run_dir, steps)
        workdir = args.musubi_dir
    else:
        commands = [("train", build_command(job, args, dataset_dir, run_dir, steps))]
        workdir = args.kohya_dir
    cache_dir = args.trainer_dir / "hf-cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    started = time.time()
    final_loss = None
    gpu = ""
    for label, command in commands:
        finished = False
        for attempt in range(2):
            gpu = pick_gpu(params, rank=None if attempt == 0 else ensure_free_gpu())
            env = {
                **os.environ,
                "CUDA_VISIBLE_DEVICES": gpu,
                "PYTHONUNBUFFERED": "1",
                "PYTORCH_CUDA_ALLOC_CONF": "expandable_segments:True",
                "HF_HOME": str(cache_dir),
                "HF_HUB_CACHE": str(cache_dir / "hub"),
            }
            log(f"job {job_id}: {label} ({image_count} images, {steps} steps), GPU {gpu}")
            log(f"job {job_id}: log -> {log_file}")
            code, canceled, final_loss = launch_training(job_id, command, env, log_file, args, api, workdir)
            if canceled:
                log(f"job {job_id}: canceled by user")
                return
            if code == 0:
                finished = True
                break
            tail = "".join(log_file.read_text().splitlines(keepends=True)[-12:]).strip()
            if attempt == 0 and params.get("gpu") is None and "out of memory" in tail.lower():
                log(f"job {job_id}: CUDA OOM on GPU {gpu}, freeing ComfyUI and retrying on another GPU")
                free_comfyuis()
                continue
            api.call(
                "POST", f"/api/training-jobs/{job_id}/complete",
                {"success": False, "error": f"{label} exit {code}: {tail[-1500:]}", "error_info": classify_failure(tail)},
            )
            log(f"job {job_id}: failed during {label} (exit {code})")
            return
        if not finished:
            return
    seconds = int(time.time() - started)
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


def cleanup_pending_deletes(args):
    pending = Path(args.data_dir) / "loras" / "pending_delete"
    if not pending.is_dir():
        return
    loras_root = (args.models_dir / "loras").resolve()
    for marker in pending.glob("*.txt"):
        try:
            relative = marker.read_text().strip()
            target = (loras_root / relative).resolve()
            if target.is_relative_to(loras_root) and target.is_file():
                target.unlink()
                log(f"removed deleted LoRA from ComfyUI: {relative}")
            marker.unlink(missing_ok=True)
        except OSError as exc:
            log(f"pending delete failed for {marker.name}: {exc}")


def classify_failure(message: str) -> dict:
    """Structured error for the UI: code, summary, remediation, technical details."""
    text = message.lower()
    if "checkpoint not found" in text or "checkpoint not found" in text or "richiede i pesi bf16" in text:
        code = "checkpoint_missing"
        summary = "The base checkpoint is not available on the server"
        remediation = "Install the checkpoint in the ComfyUI models folder (or choose another base checkpoint) and queue the job again."
    elif "out of memory" in text:
        code = "gpu_oom"
        summary = "The GPU ran out of memory during training"
        remediation = "Free VRAM from Home, lower resolution/rank, or pick a different GPU."
    elif "missing file for training" in text or ("not found in" in text and "text_encoder" in text):
        code = "trainer_assets_missing"
        summary = "The trainer is missing required model files"
        remediation = "Download the required weights (diffusion_models / text_encoders) and retry."
    elif "need at least 4 images" in text:
        code = "dataset_too_small"
        summary = "The dataset has fewer than 4 usable images"
        remediation = "Select at least 4 dataset images (aim for 50-70) before queueing training."
    else:
        code = "trainer_failed"
        summary = "Training failed"
        remediation = "Open the technical details and the trainer log, fix the reported issue and retry."
    return {"code": code, "summary": summary, "remediation": remediation, "technical_details": message[-1500:]}


def apply_gpu_plan(args):
    data_dir = Path(args.data_dir)
    marker = data_dir / "gpu_plan.request"
    if not marker.exists():
        return
    plan_file = data_dir / "gpu_plan.json"
    script = Path("/data/data_ssd/pigni/apply_gpu_plan.sh")
    if not script.is_file():
        log(f"GPU plan requested but {script} is missing")
        marker.unlink(missing_ok=True)
        return
    log("applying GPU plan...")
    try:
        subprocess.run([str(script), str(plan_file)], check=True, timeout=900)
    except Exception as exc:  # noqa: BLE001 - the host script reports its own errors
        log(f"GPU plan apply failed: {exc}")
    marker.unlink(missing_ok=True)


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
    parser.add_argument("--data-dir", default="/data/data_ssd/pigni/ai-influencer/backend-v6/data")
    parser.add_argument("--models-dir", default="/data/data_ssd/pigni/comfyUI/ComfyUI/models")
    parser.add_argument("--musubi-dir", default="/data/data_ssd/pigni/trainer/musubi-tuner")
    parser.add_argument("--musubi-venv", default="/data/data_ssd/pigni/trainer/musubi-venv")
    parser.add_argument("--poll-seconds", type=int, default=10)
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    args.trainer_dir = Path(args.trainer_dir)
    args.kohya_dir = Path(args.kohya_dir) if args.kohya_dir else args.trainer_dir / "sd-scripts"
    args.venv = args.trainer_dir / "venv"
    args.data_dir = Path(args.data_dir)
    args.models_dir = Path(args.models_dir)
    args.musubi_dir = Path(args.musubi_dir)
    args.musubi_venv = Path(args.musubi_venv)
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
        cleanup_pending_deletes(args)
        apply_gpu_plan(args)
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
                         {"success": False, "error": str(exc)[:1500], "error_info": classify_failure(str(exc))})
            except RuntimeError:
                pass
        if args.once:
            return 0


if __name__ == "__main__":
    sys.exit(main())
