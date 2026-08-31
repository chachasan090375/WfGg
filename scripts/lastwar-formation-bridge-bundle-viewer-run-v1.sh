#!/data/data/com.termux/files/usr/bin/bash
set -Eeuo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
bash scripts/lastwar-formation-bridge-bundle-viewer-build-v1.sh
URL="http://127.0.0.1:8788/lab/lastwar-formation-bridge-bundle-viewer.html?v=1"
if command -v curl >/dev/null 2>&1 && curl -fsS --max-time 2 "http://127.0.0.1:8788/lab/" >/dev/null 2>&1; then
  echo "FORMATION_BRIDGE_BUNDLE_VIEWER_SERVER_ALREADY_RUNNING"
  echo "Viewer: $URL"
  exit 0
fi
echo "FORMATION_BRIDGE_BUNDLE_VIEWER_SERVER_START port=8788"
echo "Viewer: $URL"
exec python -m http.server 8788 --directory frontend --bind 127.0.0.1
