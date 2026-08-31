#!/data/data/com.termux/files/usr/bin/bash
set -u
ROOT="$HOME/wfgg-lastwar-preview"
cd "$ROOT" || exit 1

echo "AUDIE_COMPANION_2D_V23_RUNNER_START"

if [ ! -f frontend/lab/audie-stream-v22-data/manifest.json ]; then
  echo "ERROR: V22 manifest absent"
  echo "NEXT=bash scripts/lastwar-audie-stream-resolver-v22.sh"
  exit 1
fi

if ! python -c 'import texture2ddecoder' >/dev/null 2>&1; then
  echo "TEXTURE2DDECODER_MISSING"
  python -m pip install --no-cache-dir texture2ddecoder || true
fi

python scripts/lastwar-audie-companion-2d-v23.py "$ROOT"
