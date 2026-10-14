#!/usr/bin/env bash
# Resumable background download of the pose-pipeline models (SDXL OpenPose ControlNet + DWPose).
set -uo pipefail

COMFY_DIR="${COMFY_DIR:-/data/data_ssd/pigni/comfyUI/ComfyUI}"
CONTROLNET_DIR="$COMFY_DIR/models/controlnet"
CKPTS_DIR="$COMFY_DIR/custom_nodes/comfyui_controlnet_aux/ckpts/yzd-v/DWPose"
LOG_PREFIX="[pose-download $(date +%H:%M:%S)]"

mkdir -p "$CONTROLNET_DIR" "$CKPTS_DIR"

fetch() {
  local url="$1" dest="$2" name
  name="$(basename "$dest")"
  if [ -s "$dest" ]; then
    echo "$LOG_PREFIX $name already present ($(stat -c%s "$dest") bytes), skipping"
    return 0
  fi
  echo "$LOG_PREFIX downloading $name"
  if curl -L -C - --retry 10 --retry-delay 5 --retry-all-errors \
      -o "$dest.part" "$url"; then
    mv "$dest.part" "$dest"
    echo "$LOG_PREFIX $name done ($(stat -c%s "$dest") bytes)"
  else
    echo "$LOG_PREFIX $name FAILED (partial kept at $dest.part)"
    return 1
  fi
}

fetch "https://huggingface.co/xinsir/controlnet-openpose-sdxl-1.0/resolve/main/diffusion_pytorch_model.safetensors" \
  "$CONTROLNET_DIR/controlnet-openpose-sdxl.safetensors"
fetch "https://huggingface.co/yzd-v/DWPose/resolve/main/yolox_l.onnx" \
  "$CKPTS_DIR/yolox_l.onnx"
fetch "https://huggingface.co/yzd-v/DWPose/resolve/main/dw-ll_ucoco_384.onnx" \
  "$CKPTS_DIR/dw-ll_ucoco_384.onnx"

echo "$LOG_PREFIX all downloads finished"
