#!/data/data/com.termux/files/usr/bin/bash
set -euo pipefail
cd "$(dirname "$0")/.."
python scripts/lastwar-semantic-vehicle-name-v25.py
printf '\nV25 prête : http://127.0.0.1:8788/lab/lastwar-semantic-vehicle-name-v25.html?v=25\n'
