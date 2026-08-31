#!/data/data/com.termux/files/usr/bin/bash
set -euo pipefail
ROOT="${HOME}/wfgg-lastwar-preview"
cd "$ROOT"
git pull --ff-only origin portal-auth-lastwar-lab-v1
bash scripts/lastwar-formation-vehicle-texture-viewer-build-v1.sh
printf 'OPEN=http://127.0.0.1:8788/lab/lastwar-formation-vehicle-texture-viewer.html?v=1\n'
