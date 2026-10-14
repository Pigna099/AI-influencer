import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest

WORKER_PATH = Path(__file__).resolve().parents[1] / "scripts" / "trainer" / "train_worker.py"


def load_worker():
    spec = importlib.util.spec_from_file_location("train_worker", WORKER_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_worker_resolves_qwen_bf16_checkpoint(tmp_path):
    worker = load_worker()
    models = tmp_path / "models"
    (models / "diffusion_models").mkdir(parents=True)
    (models / "checkpoints").mkdir()
    (models / "diffusion_models" / "qwen_image_2512_bf16.safetensors").write_bytes(b"x")
    (models / "checkpoints" / "model.safetensors").write_bytes(b"x")
    args = SimpleNamespace(models_dir=models)

    resolved = worker.resolve_checkpoint(args, "qwen-image", "qwen_image_2512_fp8_e4m3fn.safetensors")
    assert resolved.name == "qwen_image_2512_bf16.safetensors"
    assert worker.resolve_checkpoint(args, "real", "model.safetensors").parent.name == "checkpoints"
    with pytest.raises(RuntimeError, match="bf16"):
        worker.resolve_checkpoint(args, "qwen-image", "missing_fp8_e4m3fn.safetensors")


def test_worker_builds_qwen_pipeline(tmp_path):
    worker = load_worker()
    models = tmp_path / "models"
    for folder in ("diffusion_models", "vae", "text_encoders"):
        (models / folder).mkdir(parents=True)
    (models / "diffusion_models" / "qwen_image_2512_bf16.safetensors").write_bytes(b"x")
    (models / "vae" / "qwen_image_vae.safetensors").write_bytes(b"x")
    (models / "text_encoders" / "qwen_2.5_vl_7b.safetensors").write_bytes(b"x")
    run_dir = tmp_path / "run"
    dataset_dir = run_dir / "dataset"
    (dataset_dir / "10_nikita_qwen").mkdir(parents=True)
    args = SimpleNamespace(models_dir=models, musubi_dir=tmp_path / "musubi", musubi_venv=tmp_path / "venv")
    job = {
        "params": {
            "output_stem": "nikita_qwen",
            "base_checkpoint": "qwen_image_2512_fp8_e4m3fn.safetensors",
            "rank": 32,
            "repeats": 10,
        }
    }

    commands = worker.build_qwen_commands(job, args, dataset_dir, run_dir, 4000)
    assert [label for label, _ in commands] == ["cache latents", "cache text encoder", "train"]
    train = commands[2][1]
    assert "networks.lora_qwen_image" in train
    assert "--fp8_scaled" in train and "--blocks_to_swap" in train
    assert "qwen_image_2512_bf16.safetensors" in " ".join(train)
    assert "--max_train_steps" in train and "4000" in train
    config = (run_dir / "musubi_dataset.toml").read_text()
    assert "image_directory" in config and "10_nikita_qwen" in config


def test_worker_cleanup_pending_deletes(tmp_path):
    worker = load_worker()
    loras = tmp_path / "models" / "loras" / "ai_influencer"
    loras.mkdir(parents=True)
    target = loras / "char.safetensors"
    target.write_bytes(b"x")
    data_dir = tmp_path / "data"
    pending = data_dir / "loras" / "pending_delete"
    pending.mkdir(parents=True)
    (pending / "lora-id.txt").write_text("ai_influencer/char.safetensors")
    args = SimpleNamespace(models_dir=tmp_path / "models", data_dir=data_dir)

    worker.cleanup_pending_deletes(args)
    assert not target.exists()
    assert not (pending / "lora-id.txt").exists()
