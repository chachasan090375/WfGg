#!/data/data/com.termux/files/usr/bin/bash
set -Eeuo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BRANCH="portal-auth-lastwar-lab-v1"
cd "$ROOT"
[[ "$(git branch --show-current)" == "$BRANCH" ]] || { echo "ERREUR: branche LAB incorrecte" >&2; exit 1; }
[[ -s "$ROOT/frontend/lab/master-assets-v2/meta/audie-mesh-external-v8.json" ]] || bash "$ROOT/scripts/lastwar-audie-mesh-external-resolver-v8.sh"
command -v python >/dev/null 2>&1 || { echo "ERREUR: python absent" >&2; exit 1; }
PYTHONUNBUFFERED=1 python "$ROOT/scripts/lastwar-audie-mesh-android-v9.py" "$ROOT"
echo "VIEWER=http://127.0.0.1:8788/lab/lastwar-audie-mesh-carrier-viewer.html?v=9"
