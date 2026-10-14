#!/usr/bin/env bash
# Move Docker's data-root inside /data/data_ssd/pigni (run with sudo).
set -euo pipefail

SRC="/data/data_ssd/docker"
DST="/data/data_ssd/pigni/docker"
DAEMON_JSON="/etc/docker/daemon.json"

if [ "$(id -u)" -ne 0 ]; then
  echo "Run with sudo: sudo bash $0" >&2
  exit 1
fi

if [ ! -d "$SRC" ]; then
  echo "source not found: $SRC" >&2
  exit 1
fi

echo "==> Stopping Docker..."
systemctl stop docker.service docker.socket 2>/dev/null || service docker stop

echo "==> Copying $SRC -> $DST ..."
mkdir -p "$DST"
if command -v rsync >/dev/null; then
  rsync -aHAX --info=progress2 "$SRC"/ "$DST"/
else
  cp -a "$SRC"/. "$DST"/
fi

echo "==> Updating $DAEMON_JSON ..."
cp -a "$DAEMON_JSON" "${DAEMON_JSON}.bak.$(date +%Y%m%d%H%M%S)" 2>/dev/null || true
python3 - "$DAEMON_JSON" "$DST" <<'PY'
import json
import sys

path, dst = sys.argv[1], sys.argv[2]
try:
    data = json.load(open(path))
except FileNotFoundError:
    data = {}
data["data-root"] = dst
with open(path, "w") as handle:
    json.dump(data, handle, indent=4)
PY

echo "==> Starting Docker..."
systemctl start docker.service
sleep 3
docker info | grep -i 'Docker Root Dir'

echo "==> Containers:"
docker ps --format '{{.Names}} {{.Status}}'

cat <<EOF

Done. If containers are running and the storage path is correct:
  sudo rm -rf $SRC

To roll back: restore the ${DAEMON_JSON}.bak.* backup and restart Docker.
EOF
