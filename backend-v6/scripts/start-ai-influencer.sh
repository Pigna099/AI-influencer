#!/usr/bin/env bash
set -euo pipefail

OPENCODE_DIR="/data/data_ssd/pigni/ai-influencer"
PROJECT_DIR="/data/data_ssd/pigni/ai-influencer/backend-v6"
COMFYUI_DIR="/data/data_ssd/pigni/comfyUI/ComfyUI"
COMFYUI_LOG="/data/data_ssd/pigni/comfyUI/comfyui.log"
OPENCODE_URL="http://192.168.1.60:4096"
COMFYUI_URL="http://127.0.0.1:8188"
OLLAMA_URL="http://127.0.0.1:11434"
WEBUI_URL="http://192.168.1.60:8010"

echo "==> Avvio AI Influencer..."

export HF_HOME="/data/data_ssd/pigni/huggingface"
export HF_HUB_CACHE="$HF_HOME/hub"

# 1. Ollama (servizio systemd, gia' abilitato al boot)
if systemctl is-active --quiet ollama; then
  echo "[ok] Ollama attivo su $OLLAMA_URL"
else
  echo "[..] Avvio Ollama..."
  sudo systemctl start ollama
  echo "[ok] Ollama avviato"
fi

# 2. Container Docker (PostgreSQL, migrate, API, worker)
echo "==> Avvio container Docker..."
cd "$PROJECT_DIR"
./start.sh

# 3. ComfyUI + vLLM secondo l'ultimo piano GPU salvato (Home -> GPU)
PLAN_FILE="$PROJECT_DIR/data/gpu_plan.json"
if [ ! -f "$PLAN_FILE" ]; then
  echo '{"media": [0, 1], "text": [2, 3]}' > "$PLAN_FILE"
  echo "[..] Piano GPU assente: creato default media=[0,1] text=[2,3]"
fi
echo "==> Applico il piano GPU salvato (media/text per GPU)..."
bash /data/data_ssd/pigni/apply_gpu_plan.sh "$PLAN_FILE" || echo "[!!] apply_gpu_plan fallito: controlla i log"

MEDIA_PORTS=$(python3 -c "import json,sys; print(' '.join(str(8188+g) for g in json.load(open(sys.argv[1])).get('media',[0,1])))" "$PLAN_FILE")
echo "[..] Attendo ComfyUI (porte: $MEDIA_PORTS, log: /data/data_ssd/pigni/comfyUI/comfyui-*.log)..."
for _ in $(seq 1 30); do
  ready=1
  for port in $MEDIA_PORTS; do
    curl -s -o /dev/null --max-time 2 "http://127.0.0.1:$port/" || ready=0
  done
  if [ "$ready" -eq 1 ]; then
    echo "[ok] ComfyUI pronto"
    break
  fi
  sleep 2
done

# 4. Trainer LoRA (worker lato host per i job di training)
if pgrep -f '[t]rain_worker.py' >/dev/null; then
  echo "[ok] Trainer LoRA gia' attivo"
else
  echo "==> Avvio trainer LoRA..."
  setsid nohup /data/data_ssd/pigni/trainer/venv/bin/python "$PROJECT_DIR/scripts/trainer/train_worker.py" \
    > /data/data_ssd/pigni/trainer/worker.log 2>&1 < /dev/null &
  echo "[ok] Trainer LoRA avviato (log: /data/data_ssd/pigni/trainer/worker.log)"
fi



echo
echo "======================================================"
echo " AI Influencer pronto"
echo "   WebUI:   $WEBUI_URL"
echo "   Ollama:  $OLLAMA_URL"
echo "   ComfyUI: $COMFYUI_URL"
echo "   Trainer: attivo (log in /data/data_ssd/pigni/trainer/worker.log)"
echo "   API key: API_KEY in $PROJECT_DIR/.env"
echo "======================================================"

echo "==> Avvio OPENCODE"
cd "$OPENCODE_DIR"
OPENCODE_SERVER_PASSWORD=cringe opencode web --hostname 0.0.0.0 --port 4096
