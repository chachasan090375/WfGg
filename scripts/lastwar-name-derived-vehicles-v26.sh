#!/data/data/com.termux/files/usr/bin/bash
set -euo pipefail
cd "$(dirname "$0")/.."
python scripts/lastwar-name-derived-vehicles-v26.py "$PWD"
echo
echo "Open: http://127.0.0.1:8788/lab/lastwar-name-derived-vehicles-v26.html?v=26"
