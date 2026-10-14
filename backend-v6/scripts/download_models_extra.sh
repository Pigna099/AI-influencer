#!/usr/bin/env bash
# Resumable background download of the missing image-model assets:
# LUSTIFY (SDXL realistic), Qwen-Image base, FLUX.2 (model + text encoder + VAE + turbo LoRA).
set -uo pipefail

MODELS="${COMFY_MODELS:-/data/data_ssd/pigni/comfyUI/ComfyUI/models}"
LOG_PREFIX="[models-download $(date +%H:%M:%S)]"

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

fetch "https://huggingface.co/TheImposterImposters/LUSTIFY-v2.0/resolve/main/lustifySDXLNSFWSFW_v20.safetensors" \
  "$MODELS/checkpoints/lustifySDXLNSFWSFW_v20.safetensors"

fetch "https://huggingface.co/Comfy-Org/Qwen-Image_ComfyUI/resolve/main/split_files/diffusion_models/qwen_image_fp8_e4m3fn.safetensors" \
  "$MODELS/diffusion_models/qwen_image_fp8_e4m3fn.safetensors"

fetch "https://huggingface.co/Comfy-Org/flux2-dev/resolve/main/split_files/diffusion_models/flux2_dev_fp8mixed.safetensors" \
  "$MODELS/diffusion_models/flux2_dev_fp8mixed.safetensors"

fetch "https://huggingface.co/Comfy-Org/flux2-dev/resolve/main/split_files/text_encoders/mistral_3_small_flux2_fp8.safetensors" \
  "$MODELS/text_encoders/mistral_3_small_flux2_fp8.safetensors"

fetch "https://huggingface.co/Comfy-Org/flux2-dev/resolve/main/split_files/vae/flux2-vae.safetensors" \
  "$MODELS/vae/flux2-vae.safetensors"

fetch "https://huggingface.co/Comfy-Org/flux2-dev/resolve/main/split_files/loras/Flux2TurboComfyv2.safetensors" \
  "$MODELS/loras/flux2_turbo.safetensors"

echo "$LOG_PREFIX all downloads finished"
