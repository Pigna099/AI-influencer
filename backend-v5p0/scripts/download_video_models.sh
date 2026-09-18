#!/usr/bin/env bash
# Resumable background download of the LTX 2.3 video models (checkpoints + distilled LoRA).
set -uo pipefail

MODELS="${COMFY_MODELS:-/data/data_ssd/pigni/comfyUI/ComfyUI/models}"
LOG_PREFIX="[video-download $(date +%H:%M:%S)]"

fetch() {
  local url="$1" dest="$2" name
  name="$(basename "$dest")"
  mkdir -p "$(dirname "$dest")"
  if [ -s "$dest" ]; then
    echo "$LOG_PREFIX $name already present ($(stat -c%s "$dest") bytes), skipping"
    return 0
  fi
  echo "$LOG_PREFIX downloading $name"
  if curl -L -C - --retry 20 --retry-delay 5 --retry-all-errors --connect-timeout 30 \
      -o "$dest.part" "$url"; then
    mv "$dest.part" "$dest"
    echo "$LOG_PREFIX $name done ($(stat -c%s "$dest") bytes)"
  else
    echo "$LOG_PREFIX $name FAILED (partial kept at $dest.part)"
    return 1
  fi
}

fetch "https://huggingface.co/Lightricks/LTX-2.3-fp8/resolve/main/ltx-2.3-22b-dev-fp8.safetensors" \
  "$MODELS/checkpoints/ltx-2.3-22b-dev-fp8.safetensors"

fetch "https://huggingface.co/Lightricks/LTX-2.3-fp8/resolve/main/ltx-2.3-22b-distilled-fp8.safetensors" \
  "$MODELS/checkpoints/ltx-2.3-22b-distilled-fp8.safetensors"

fetch "https://huggingface.co/Lightricks/LTX-2.3/resolve/main/ltx-2.3-22b-distilled-lora-384.safetensors" \
  "$MODELS/loras/ltx-2.3-22b-distilled-lora-384.safetensors"

echo "$LOG_PREFIX all downloads finished"
