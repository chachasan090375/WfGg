#!/data/data/com.termux/files/usr/bin/bash
set -Eeuo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
[[ -s "$ROOT/frontend/lab/audie-assembly-2d-v14-data/manifest.json" ]] || bash "$ROOT/scripts/lastwar-audie-assembly-2d-v14.sh"
PYTHONUNBUFFERED=1 python "$ROOT/scripts/lastwar-audie-2d-raw-v20.py" "$ROOT"
echo "VIEWER=http://127.0.0.1:8788/lab/lastwar-audie-2d-raw-v20.html?v=20"
