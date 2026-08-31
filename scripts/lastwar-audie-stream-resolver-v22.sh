#!/data/data/com.termux/files/usr/bin/bash
set -u
ROOT="$HOME/wfgg-lastwar-preview"
cd "$ROOT" || exit 1

echo "AUDIE_STREAM_V22_RUNNER_START"
python scripts/lastwar-audie-stream-resolver-v22.py "$ROOT"
