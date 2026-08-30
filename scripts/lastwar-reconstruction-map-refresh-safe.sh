#!/data/data/com.termux/files/usr/bin/bash
set -Eeuo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BRANCH="portal-auth-lastwar-lab-v1"
ORIG="$ROOT/scripts/lastwar-reconstruction-map-refresh.sh"
# IMPORTANT: the patched runtime must stay under repo/scripts so the original
# script's BASH_SOURCE-based ROOT calculation still resolves to the repository.
TMP="$ROOT/scripts/.lastwar-reconstruction-map-refresh-safe-runtime.sh"
RAW_REL="frontend/lab/master-assets-v2/index/lastwar-visual-reconstruction-map-v1.json"
MANIFEST="$ROOT/frontend/lab/master-assets-v2/index/lastwar-visual-reconstruction-map-v1.manifest.json"
PARTDIR="$ROOT/frontend/lab/master-assets-v2/index/lastwar-visual-reconstruction-map-v1.parts"

trap 'rm -f "$TMP"' EXIT
cd "$ROOT"
[[ "$(git branch --show-current)" == "$BRANCH" ]] || { echo 'ERREUR: branche LAB incorrecte' >&2; exit 1; }

# Refuse to proceed if the oversized raw graph is already part of local HEAD history.
# A later deletion would not remove that blob from the rejected commit history.
if git cat-file -e "HEAD:$RAW_REL" 2>/dev/null; then
  sz="$(git cat-file -s "HEAD:$RAW_REL" 2>/dev/null || echo 0)"
  if [[ "$sz" -ge 100000000 ]]; then
    echo "ERREUR_LOCAL_OVERSIZED_GRAPH_IN_HEAD bytes=$sz" >&2
    echo "Le commit local contient deja le blob >100 MB. Revenir d'abord au HEAD distant puis relancer." >&2
    exit 4
  fi
fi

python - "$ORIG" "$TMP" <<'PY'
from pathlib import Path
import sys
src=Path(sys.argv[1]);dst=Path(sys.argv[2]);s=src.read_text('utf-8')
old='''git add "$OUT" "$DOT"
if ! git diff --cached --quiet; then
  git commit -m "lab: refresh visual reconstruction map"
fi
git push origin "$BRANCH"
printf '%s\\n' '=== VISUAL RECONSTRUCTION MAP TERMINE ===' "JSON: $OUT" "DOT: $DOT" "Rapport: $REPORT"'''
new='''python "$ROOT/scripts/lastwar-reconstruction-map-pack.py" "$OUT"
MANIFEST="$IDX/lastwar-visual-reconstruction-map-v1.manifest.json"
PARTDIR="$IDX/lastwar-visual-reconstruction-map-v1.parts"
git add "$DOT" "$MANIFEST"
git add -A "$PARTDIR"
if ! git diff --cached --quiet; then
  git commit -m "lab: refresh visual reconstruction map pack"
fi
git push origin "$BRANCH"
printf '%s\\n' '=== VISUAL RECONSTRUCTION MAP TERMINE ===' "MANIFEST: $MANIFEST" "PARTS: $PARTDIR" "DOT: $DOT" "Rapport: $REPORT"'''
if old not in s:
    raise SystemExit('SAFE_PATCH_TARGET_NOT_FOUND')
dst.parent.mkdir(parents=True,exist_ok=True)
dst.write_text(s.replace(old,new),'utf-8')
PY
chmod +x "$TMP"
bash "$TMP"
