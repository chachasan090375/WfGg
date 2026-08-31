#!/data/data/com.termux/files/usr/bin/bash
set -euo pipefail
ROOT="$HOME/wfgg-lastwar-preview"
cd "$ROOT"
IDX="$ROOT/frontend/lab/master-assets-v2/meta/unity-asset-name-index-v1.json"
if [ ! -s "$IDX" ]; then
  echo "A_HERO_V16_INDEX_MISSING -> build global reusable Unity name index"
  python scripts/lastwar-unity-asset-index-v1.py "$ROOT"
else
  echo "A_HERO_V16_INDEX_REUSE $IDX"
fi
python scripts/lastwar-a-hero-generic-v16.py
printf '\nVIEWER=http://127.0.0.1:8788/lab/lastwar-a-hero-generic-v16.html?v=16\n'
