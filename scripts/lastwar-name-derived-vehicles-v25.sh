#!/data/data/com.termux/files/usr/bin/bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
python scripts/lastwar-name-derived-vehicles-v25.py "$ROOT"
printf '\nOuvre ensuite :\nhttp://127.0.0.1:8788/lab/lastwar-name-derived-vehicles-v25.html?v=25\n'
