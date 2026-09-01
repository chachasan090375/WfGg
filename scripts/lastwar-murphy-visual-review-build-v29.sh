#!/data/data/com.termux/files/usr/bin/bash
set -Eeuo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BRANCH="portal-auth-lastwar-lab-v1"
cd "$ROOT"
if [ "$(git branch --show-current)" != "$BRANCH" ]; then
  echo "ERREUR: branche active=$(git branch --show-current), attendu=$BRANCH" >&2
  exit 2
fi
python - <<'PYCHK' >/dev/null 2>&1 || { echo "ERREUR: UnityPy / Pillow / texture2ddecoder manquant" >&2; exit 3; }
import UnityPy, texture2ddecoder
from PIL import Image
PYCHK
printf '\n=== MURPHY / AUDIE VISUAL BUILD V29 ===\n'
printf '\n--- Reconstruction des bundles depuis les BundleFragments APK ---\n'
python scripts/lastwar-murphy-visual-fragment-rescue-v29.py "$ROOT"
printf '\n--- Extraction des rendus pour le viewer ---\n'
python scripts/lastwar-murphy-visual-review-build-v29.py "$ROOT"
printf '\nRecharge le même viewer :\nhttp://127.0.0.1:8788/lab/lastwar-murphy-visual-review-v29.html?v=29b\n'
