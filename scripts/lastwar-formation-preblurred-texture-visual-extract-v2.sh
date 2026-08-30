#!/data/data/com.termux/files/usr/bin/bash
set -Eeuo pipefail

# WfGg Last War LAB — Formation preblur visual export V2
# Runs the already-reviewed V1 extraction logic under an isolated newer UnityPy
# environment, leaving the project's existing Python/UnityPy installation untouched.

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BRANCH="portal-auth-lastwar-lab-v1"
V1="$ROOT/scripts/lastwar-formation-preblurred-texture-visual-extract-v1.sh"
VENV="$HOME/.cache/wfgg-unitypy-texture-export-v2"
PIPLOG="$HOME/storage/downloads/WFGG_LASTWAR_FORMATION_TEXTURE_EXPORT_V2_PIP.log"
TMP_ENGINE="$ROOT/scripts/.lastwar-formation-preblurred-texture-visual-extract-v2-engine.tmp.sh"

fail(){ printf 'ERREUR: %s\n' "$*" >&2; exit 1; }
cd "$ROOT"
[[ "$(git branch --show-current)" == "$BRANCH" ]] || fail "branche LAB incorrecte"
[[ -s "$V1" ]] || fail "moteur V1 absent"
command -v python >/dev/null 2>&1 || fail "python absent"
mkdir -p "$HOME/.cache" "$(dirname "$PIPLOG")"

SYS_VER="$(python - <<'PY'
try:
 import UnityPy
 print(getattr(UnityPy,'__version__','unknown'))
except Exception:
 print('absent')
PY
)"
echo "FORMATION_TEXTURE_V2_SYSTEM_UNITYPY=$SYS_VER"

if [[ ! -x "$VENV/bin/python" ]]; then
  rm -rf "$VENV"
  python -m venv "$VENV" || fail "creation venv impossible"
fi

VENV_VER="$($VENV/bin/python - <<'PY'
try:
 import UnityPy
 print(getattr(UnityPy,'__version__','absent'))
except Exception:
 print('absent')
PY
)"

if [[ "$VENV_VER" != "1.24.1" ]]; then
  echo "FORMATION_TEXTURE_V2_INSTALL UnityPy=1.24.1 isolated=$VENV"
  if ! "$VENV/bin/python" -m pip install --disable-pip-version-check --upgrade 'UnityPy==1.24.1' Pillow >"$PIPLOG" 2>&1; then
    echo "--- pip tail ---" >&2
    tail -n 40 "$PIPLOG" >&2 || true
    fail "installation UnityPy isolée échouée; log=$PIPLOG"
  fi
fi

VENV_VER="$($VENV/bin/python - <<'PY'
import UnityPy
print(getattr(UnityPy,'__version__','unknown'))
PY
)"
[[ "$VENV_VER" == "1.24.1" ]] || fail "UnityPy isolé inattendu: $VENV_VER"

$VENV/bin/python - <<'PYCHK' >/dev/null 2>&1 || fail "UnityPy/Pillow isolés incomplets"
import UnityPy
from PIL import Image,ImageDraw
from UnityPy.export import Texture2DConverter
PYCHK

echo "FORMATION_TEXTURE_V2_PREFLIGHT isolatedUnityPy=$VENV_VER systemUnityPy=$SYS_VER"

# Derive V2 only by changing output identities. Inputs, scope, ranking and export
# logic remain exactly those of V1.
python - "$V1" "$TMP_ENGINE" <<'PY'
from pathlib import Path
import sys
src=Path(sys.argv[1]).read_text('utf-8')
repls={
 'formation-preblurred-texture-visual-extract-v1.json':'formation-preblurred-texture-visual-extract-v2.json',
 'WFGG_LASTWAR_FORMATION_PREBLURRED_TEXTURE_VISUAL_EXTRACT_V1.txt':'WFGG_LASTWAR_FORMATION_PREBLURRED_TEXTURE_VISUAL_EXTRACT_V2.txt',
 'WFGG_LASTWAR_FORMATION_TEXTURE_VISUAL_CANDIDATES_V1':'WFGG_LASTWAR_FORMATION_TEXTURE_VISUAL_CANDIDATES_V2',
 "'WFGG_LASTWAR_FORMATION_PREBLURRED_TEXTURE_VISUAL_EXTRACT_V1'":"'WFGG_LASTWAR_FORMATION_PREBLURRED_TEXTURE_VISUAL_EXTRACT_V2'",
 'FORMATION PREBLURRED TEXTURE VISUAL EXTRACT V1':'FORMATION PREBLURRED TEXTURE VISUAL EXTRACT V2',
}
for a,b in repls.items(): src=src.replace(a,b)
Path(sys.argv[2]).write_text(src,'utf-8')
PY
chmod +x "$TMP_ENGINE"
cleanup(){ rm -f "$TMP_ENGINE" 2>/dev/null || true; }
trap cleanup EXIT

# Force every `python` invoked by the reviewed V1 engine to resolve to the
# isolated interpreter. The repository/global Python installation is untouched.
PATH="$VENV/bin:$PATH" bash "$TMP_ENGINE"

echo "=== FORMATION TEXTURE VISUAL EXPORT V2 TERMINE ==="
echo "UnityPy isolé: $VENV_VER"
echo "Rapport: $HOME/storage/downloads/WFGG_LASTWAR_FORMATION_PREBLURRED_TEXTURE_VISUAL_EXTRACT_V2.txt"
echo "Planche: $HOME/storage/downloads/WFGG_LASTWAR_FORMATION_TEXTURE_VISUAL_CANDIDATES_V2/CONTACT_SHEET.png"
echo "ZIP: $HOME/storage/downloads/WFGG_LASTWAR_FORMATION_TEXTURE_VISUAL_CANDIDATES_V2.zip"
echo "UnityPy système inchangé: $SYS_VER"
