#!/data/data/com.termux/files/usr/bin/bash
set -Eeuo pipefail

# WfGg Last War LAB — V3 direct texture decode with proven Unity fallback.
# Patches only a temporary copy of V3 so the reviewed decoder logic stays unchanged.

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BRANCH="portal-auth-lastwar-lab-v1"
SRC="$ROOT/scripts/lastwar-formation-preblurred-texture-direct-decode-v3.sh"
TMP="$ROOT/scripts/.lastwar-formation-preblurred-texture-direct-decode-v3-fixed.tmp.sh"
UNITY_VERSION="2019.4.41f1"

fail(){ printf 'ERREUR: %s\n' "$*" >&2; exit 1; }
cd "$ROOT"
[[ "$(git branch --show-current)" == "$BRANCH" ]] || fail "branche LAB incorrecte"
[[ -s "$SRC" ]] || fail "V3 absent: $SRC"
command -v python >/dev/null 2>&1 || fail "python absent"

python - "$SRC" "$TMP" "$UNITY_VERSION" <<'PY'
from pathlib import Path
import sys
srcp,tmp,uv=Path(sys.argv[1]),Path(sys.argv[2]),sys.argv[3]
s=srcp.read_text('utf-8')
needle='import UnityPy\n'
count=s.count(needle)
if count < 2:
    raise SystemExit(f'V3_IMPORT_GUARD expected>=2 actual={count}')
s=s.replace(needle, needle+f"UnityPy.config.FALLBACK_UNITY_VERSION={uv!r}\n")
tmp.write_text(s,'utf-8')
print('FORMATION_TEXTURE_V3_FIXED_PATCH',f'fallbackUnity={uv}',f'patchedImports={count}')
PY
chmod +x "$TMP"
cleanup(){ rm -f "$TMP" 2>/dev/null || true; }
trap cleanup EXIT
bash "$TMP"
