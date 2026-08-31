#!/data/data/com.termux/files/usr/bin/bash
set -euo pipefail
ROOT="${HOME}/wfgg-lastwar-preview"
cd "$ROOT"
bash scripts/lastwar-formation-vehicle-texture-viewer-build-v1.sh
termux-open-url 'http://127.0.0.1:8788/lab/lastwar-formation-vehicle-texture-viewer.html?v=1' 2>/dev/null || true
