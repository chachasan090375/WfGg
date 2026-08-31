#!/data/data/com.termux/files/usr/bin/bash
set -euo pipefail
ROOT="${HOME}/wfgg-lastwar-preview"
cd "$ROOT"
python scripts/lastwar-audie-board-usage-v12.py "$ROOT"
echo "VIEWER=http://127.0.0.1:8788/lab/lastwar-audie-board-usage-viewer.html?v=12"
