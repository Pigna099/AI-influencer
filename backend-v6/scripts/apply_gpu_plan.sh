#!/usr/bin/env bash
# Apply the GPU reservation plan: media GPUs (ComfyUI) and text GPUs (vLLM).
# Called by the trainer worker when data/gpu_plan.request appears.
set -uo pipefail

PLAN_FILE=${1:-/data/data_ssd/pigni/ai-influencer/backend-v6/data/gpu_plan.json}
COMFY=/data/data_ssd/pigni/comfyUI/ComfyUI
COMFY_LOG_DIR=/data/data_ssd/pigni/comfyUI
VLLM_START=/data/data_ssd/pigni/vllm_start.sh
APPLIED_FILE="$(dirname "$PLAN_FILE")/gpu_plan.applied.json"

if [ ! -f "$PLAN_FILE" ]; then
  echo "plan file not found: $PLAN_FILE" >&2
  exit 1
fi

eval "$(python3 - "$PLAN_FILE" <<'PY'
import json
import shlex
import sys

plan = json.load(open(sys.argv[1]))
media = [int(g) for g in plan.get("media", [0, 1])]
text = [int(g) for g in plan.get("text", [2, 3])]
print("MEDIA=" + shlex.quote(",".join(map(str, media))))
print("TEXT=" + shlex.quote(",".join(map(str, text))))
PY
)"

echo "==> GPU plan: media=[$MEDIA] text=[$TEXT]"

# 1. Stop ComfyUI instances (free VRAM first, then terminate).
for pid in $(pgrep -f 'main\.py --listen 127\.0\.0\.1 --port'); do
  port=$(tr '\0' ' ' < "/proc/$pid/cmdline" | grep -o 'port [0-9]*' | awk '{print $2}')
  [ -n "$port" ] && curl -s -X POST -H 'Content-Type: application/json' \
    -d '{"unload_models":true,"free_memory":true}' "http://127.0.0.1:$port/free" -o /dev/null
done
for pid in $(pgrep -f 'main\.py --listen 127\.0\.0\.1 --port'); do kill "$pid"; done
sleep 5

# 2. vLLM: stop it; start again only when the plan reserves exactly two text GPUs.
if [ -z "$TEXT" ]; then
  for pid in $(pgrep -f '[v]llm serve'); do kill "$pid"; done
  sleep 3
else
  count=$(echo "$TEXT" | tr ',' '\n' | grep -c .)
  if [ "$count" -ge 2 ]; then
    previous_text=""
    if [ -f "$APPLIED_FILE" ]; then
      previous_text=$(python3 -c "import json,sys; print(','.join(map(str, json.load(open(sys.argv[1])).get('text', []))))" "$APPLIED_FILE" 2>/dev/null || echo "")
    fi
    if [ "$previous_text" = "$TEXT" ] && pgrep -f '[v]llm serve' >/dev/null; then
      echo "[ok] vLLM gia' attivo sulle GPU $TEXT"
    else
      for pid in $(pgrep -f '[v]llm serve'); do kill "$pid"; done
      for _ in $(seq 1 30); do pgrep -f '[v]llm serve' >/dev/null || break; sleep 1; done
      VLLM_GPUS="$TEXT" "$VLLM_START" || echo "warning: vLLM did not start"
    fi
  fi
fi

# 3. Start one ComfyUI instance per media GPU (port = 8188 + GPU index).
cd "$COMFY" || exit 1
export HF_HOME=/data/data_ssd/pigni/huggingface HF_HUB_CACHE=/data/data_ssd/pigni/huggingface/hub
for gpu in ${MEDIA//,/ }; do
  port=$((8188 + gpu))
  if curl -s -o /dev/null --max-time 2 "http://127.0.0.1:$port/"; then
    echo "[ok] ComfyUI $port gia' attivo"
    continue
  fi
  echo "==> Avvio ComfyUI $port (GPU $gpu)"
  CUDA_VISIBLE_DEVICES=$gpu setsid nohup ./venv/bin/python main.py --listen 127.0.0.1 --port "$port" \
    --database-url "sqlite:///$COMFY/user/comfyui_$port.db" \
    > "$COMFY_LOG_DIR/comfyui-$port.log" 2>&1 < /dev/null &
done

# 4. Record the applied plan for the Home page.
python3 - "$APPLIED_FILE" "$MEDIA" "$TEXT" <<'PY'
import datetime
import json
import sys

path, media, text = sys.argv[1], sys.argv[2], sys.argv[3]
payload = {
    "media": [int(g) for g in media.split(",") if g],
    "text": [int(g) for g in text.split(",") if g],
    "applied_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
}
with open(path, "w") as handle:
    json.dump(payload, handle)
PY
echo "==> GPU plan applied"
