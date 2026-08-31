#!/data/data/com.termux/files/usr/bin/bash
set -Eeuo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BRANCH="portal-auth-lastwar-lab-v1"
cd "$ROOT"
[[ "$(git branch --show-current)" == "$BRANCH" ]] || { echo "ERREUR: branche LAB incorrecte" >&2; exit 1; }
[[ -s "$ROOT/frontend/lab/master-assets-v2/meta/audie-material-map-v3.json" ]] || bash "$ROOT/scripts/lastwar-audie-material-map-v3.sh"
command -v python >/dev/null 2>&1 || { echo "ERREUR: python absent" >&2; exit 1; }
python - <<'PYCHK' >/dev/null 2>&1 || { echo "ERREUR: UnityPy absent" >&2; exit 1; }
import UnityPy
PYCHK
PYTHONUNBUFFERED=1 python "$ROOT/scripts/lastwar-audie-crossbundle-resolver-v4.py" "$ROOT"
echo "VIEWER=http://127.0.0.1:8788/lab/lastwar-audie-crossbundle-viewer.html?v=4"
