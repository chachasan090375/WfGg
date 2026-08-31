#!/data/data/com.termux/files/usr/bin/bash
set -Eeuo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BRANCH="portal-auth-lastwar-lab-v1"
SRC="$ROOT/scripts/lastwar-lua-runtime-materialize-v1.sh"
TMP="$ROOT/scripts/.lastwar-lua-runtime-materialize-v2.$$.sh"
trap 'rm -f "$TMP"' EXIT
fail(){ printf 'ERREUR: %s\n' "$*" >&2; exit 1; }
cd "$ROOT"
[[ "$(git branch --show-current)" == "$BRANCH" ]] || fail "branche LAB incorrecte"
[[ -s "$SRC" ]] || fail "materializer v1 absent"
python - "$SRC" "$TMP" <<'PY'
from pathlib import Path
import re,sys
src,tmp=map(Path,sys.argv[1:])
s=src.read_text('utf-8')
old=re.compile(r'APK=""\nwhile IFS= read -r line; do\n.*?\[\[ -n "\$APK" && -r "\$APK" \]\] \|\| fail "split_install_time_pack\.apk introuvable"\n',re.S)
new=r'''APK=""
APK_ENTRY="assets/lwScripts/LWScripts.data"
printf 'APK_RESOLVE_BY_ENTRY %s\n' "$APK_ENTRY"
while IFS= read -r line; do
  p="${line#package:}"
  [[ -n "$p" && -r "$p" ]] || continue
  if unzip -Z1 "$p" "$APK_ENTRY" 2>/dev/null | grep -Fxq "$APK_ENTRY"; then
    APK="$p"
    printf 'APK_RESOLVED %s\n' "$APK"
    break
  fi
done < <(pm path com.fun.lastwar.gp 2>/dev/null || true)
[[ -n "$APK" && -r "$APK" ]] || fail "APK contenant $APK_ENTRY introuvable"
'''
s,n=old.subn(new,s,count=1)
if n!=1: raise SystemExit('APK_RESOLVER_PATCH_FAILED')
tmp.write_text(s,'utf-8')
PY
chmod 700 "$TMP"
exec bash "$TMP"
