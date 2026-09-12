#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")"
docker info >/dev/null
docker compose version >/dev/null
if [[ ! -f .env ]]; then
  docker run --rm --user "$(id -u):$(id -g)" -v "$PWD:/workspace" python:3.12-slim python /workspace/scripts/init_env.py
fi
mkdir -p data/media
docker compose up -d --build --wait --wait-timeout 180
printf '\nAI influencer playground v3.2 pronto: http://192.168.1.60:8010\nLa chiave di accesso è API_KEY nel file .env.\n'
