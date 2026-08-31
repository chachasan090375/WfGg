#!/data/data/com.termux/files/usr/bin/bash
set -Eeuo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BRANCH="portal-auth-lastwar-lab-v1"
SRC="$ROOT/scripts/lastwar-lua-runtime-materialize-v1.sh"
TMP="$ROOT/scripts/.lastwar-lua-runtime-materialize-v2.$$.sh"
CACHE="$ROOT/frontend/lab/master-assets-v2/meta/lua-runtime-apk-resolved-v1.txt"
trap 'rm -f "$TMP"' EXIT
fail(){ printf 'ERREUR: %s\n' "$*" >&2; exit 1; }
cd "$ROOT"
[[ "$(git branch --show-current)" == "$BRANCH" ]] || fail "branche LAB incorrecte"
[[ -s "$SRC" ]] || fail "materializer v1 absent"
python - "$SRC" "$TMP" "$CACHE" <<'PY'
from pathlib import Path
import re,sys
src,tmp,cache=map(Path,sys.argv[1:])
s=src.read_text('utf-8')
old=re.compile(r'APK=""\nwhile IFS= read -r line; do\n.*?\[\[ -n "\$APK" && -r "\$APK" \]\] \|\| fail "split_install_time_pack\.apk introuvable"\n',re.S)
new=r'''APK=""
APK_ENTRY="assets/lwScripts/LWScripts.data"
APK_CACHE="'''+str(cache)+r'''"
printf 'APK_RESOLVE_BY_ENTRY %s\n' "$APK_ENTRY"
if [[ -s "$APK_CACHE" ]]; then
  APK="$(head -n 1 "$APK_CACHE" | tr -d '\r')"
  if [[ -n "$APK" ]] && unzip -Z1 "$APK" 2>/dev/null | tr -d '\r' | grep -Fxq "$APK_ENTRY"; then
    printf 'APK_RESOLVED_CACHE %s\n' "$APK"
  else
    APK=""
  fi
fi
if [[ -z "$APK" ]]; then
  for attempt in 1 2 3 4; do
    while IFS= read -r line; do
      [[ "$line" == package:* ]] || continue
      p="${line#package:}"
      p="${p%$'\r'}"
      [[ -n "$p" ]] || continue
      printf 'APK_CANDIDATE %s\n' "$p"
      if unzip -Z1 "$p" 2>/dev/null | tr -d '\r' | grep -Fxq "$APK_ENTRY"; then
        APK="$p"
        printf 'APK_RESOLVED_DIRECT %s\n' "$APK"
        break 2
      fi
    done < <(pm path com.fun.lastwar.gp 2>&1 || true)
    sleep 0.3
  done
fi
[[ -n "$APK" ]] || fail "APK contenant $APK_ENTRY introuvable"
'''
s,n=old.subn(new,s,count=1)
if n!=1: raise SystemExit('APK_RESOLVER_PATCH_FAILED')
tmp.write_text(s,'utf-8')
PY
chmod 700 "$TMP"
exec bash "$TMP"
