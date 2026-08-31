#!/data/data/com.termux/files/usr/bin/bash
set -euo pipefail
ROOT="${HOME}/wfgg-lastwar-preview"
cd "$ROOT"
bash scripts/lastwar-formation-vehicle-texture-viewer-build-v1.sh
PORT="${PORT:-8788}"
printf 'FORMATION_VEHICLE_TEXTURE_VIEWER_V1_SERVER_START port=%s\n' "$PORT"
printf 'OPEN=http://127.0.0.1:%s/lab/lastwar-formation-vehicle-texture-viewer.html?v=1\n' "$PORT"
cd frontend
python -m http.server "$PORT" --bind 127.0.0.1
