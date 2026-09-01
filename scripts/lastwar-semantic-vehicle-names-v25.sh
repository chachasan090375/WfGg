#!/data/data/com.termux/files/usr/bin/bash
set -euo pipefail
ROOT="${1:-$HOME/wfgg-lastwar-preview}"
cd "$ROOT"
python scripts/lastwar-semantic-vehicle-names-v25.py "$ROOT"
echo
echo "Ouvre : http://127.0.0.1:8788/lab/lastwar-semantic-vehicle-names-v25.html?v=25"
