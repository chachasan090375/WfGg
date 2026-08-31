#!/data/data/com.termux/files/usr/bin/bash
set -Eeuo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BRANCH="portal-auth-lastwar-lab-v1"
cd "$ROOT"
[[ "$(git branch --show-current)" == "$BRANCH" ]] || { echo "ERREUR: branche LAB incorrecte" >&2; exit 1; }
[[ -s "$ROOT/frontend/lab/audie-assembly-2d-v14-data/manifest.json" ]] || bash "$ROOT/scripts/lastwar-audie-assembly-2d-v14.sh"
PYTHONUNBUFFERED=1 python "$ROOT/scripts/lastwar-audie-assembly-strict-v15.py" "$ROOT"
echo "VIEWER=http://127.0.0.1:8788/lab/lastwar-audie-assembly-strict-v15.html?v=15"
