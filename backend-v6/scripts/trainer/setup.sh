#!/usr/bin/env bash
# Installs kohya sd-scripts with its own Python 3.12 venv and CUDA torch.
set -euo pipefail

TRAINER_DIR="${TRAINER_DIR:-/data/data_ssd/pigni/trainer}"
KOHYA_DIR="${KOHYA_DIR:-$TRAINER_DIR/sd-scripts}"
VENV="$TRAINER_DIR/venv"
TORCH_VERSION="${TORCH_VERSION:-2.6.0}"
TORCHVISION_VERSION="${TORCHVISION_VERSION:-0.21.0}"
CUDA_INDEX="${CUDA_INDEX:-https://download.pytorch.org/whl/cu124}"

mkdir -p "$TRAINER_DIR"

if [ ! -d "$KOHYA_DIR/.git" ]; then
  git clone --depth 1 https://github.com/kohya-ss/sd-scripts "$KOHYA_DIR"
fi

if [ ! -x "$VENV/bin/python" ]; then
  uv venv --python 3.12 "$VENV"
fi
PY="$VENV/bin/python"

uv pip install --python "$PY" --upgrade pip wheel
uv pip install --python "$PY" "torch==$TORCH_VERSION" "torchvision==$TORCHVISION_VERSION" --index-url "$CUDA_INDEX"
cd "$KOHYA_DIR"
uv pip install --python "$PY" -r "$KOHYA_DIR/requirements.txt"
uv pip install --python "$PY" bitsandbytes

"$PY" - <<'PY'
import torch
print(f"torch {torch.__version__} cuda={torch.cuda.is_available()} devices={torch.cuda.device_count()}")
PY

echo "Trainer ready in $TRAINER_DIR"
