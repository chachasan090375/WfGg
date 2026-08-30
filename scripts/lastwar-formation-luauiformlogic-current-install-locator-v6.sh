#!/data/data/com.termux/files/usr/bin/bash
set -Eeuo pipefail

# WfGg Last War LAB — LuaUIFormLogic current-install locator V6.
# V5 replayed bundle 6934 because it read the wrong V4 JSON field:
#   wrong: v4.selectedBundleId / v4.selectedBundle
#   exact: v4.selection.bundleId
# V6 deliberately reuses the already-reviewed V5 engine, patches only that selector,
# renames its outputs to V6, and adds a replay guard. No scope widening.

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BRANCH="portal-auth-lastwar-lab-v1"
SRC="$ROOT/scripts/lastwar-formation-luauiformlogic-current-install-locator-v5.sh"
V3="$ROOT/frontend/lab/master-assets-v2/meta/formation-luauiformlogic-current-install-locator-v3.json"
V4="$ROOT/frontend/lab/master-assets-v2/meta/formation-luauiformlogic-current-install-locator-v4.json"
TMP="$ROOT/scripts/.lastwar-formation-luauiformlogic-current-install-locator-v6.generated.sh"
EXPECTED_V5_BLOB="979ff33c41418d6e9c1843094113924022d77fd1"

fail(){ printf 'ERREUR: %s\n' "$*" >&2; exit 1; }
cleanup(){ rm -f "$TMP"; }
trap cleanup EXIT

cd "$ROOT"
[[ "$(git branch --show-current)" == "$BRANCH" ]] || fail "branche LAB incorrecte"
[[ -s "$SRC" ]] || fail "moteur V5 absent: $SRC"
[[ -s "$V3" ]] || fail "JSON V3 absent: $V3"
[[ -s "$V4" ]] || fail "JSON V4 absent: $V4"
[[ "$(git hash-object "$SRC")" == "$EXPECTED_V5_BLOB" ]] || fail "V5 source différent du moteur audité; refus de dérivation silencieuse"

# Preflight from existing metadata only. This proves which group V6 must select before APK access.
python - "$V3" "$V4" <<'PY'
import json,sys
v3=json.load(open(sys.argv[1],encoding='utf-8'))
v4=json.load(open(sys.argv[2],encoding='utf-8'))
if v3.get('format')!='WFGG_LASTWAR_FORMATION_LUAUIFORMLOGIC_CURRENT_INSTALL_LOCATOR_V3':
    raise SystemExit('V3_FORMAT_MISMATCH')
if v4.get('format')!='WFGG_LASTWAR_FORMATION_LUAUIFORMLOGIC_CURRENT_INSTALL_LOCATOR_V4':
    raise SystemExit('V4_FORMAT_MISMATCH')
prev=int(((v4.get('selection') or {}).get('bundleId')) or 0)
target=int(((v3.get('target') or {}).get('bundleId')) or 0)
if prev<=0: raise SystemExit('V4_SELECTION_BUNDLE_MISSING')
c=[]
for g in ((v3.get('formationFamily') or {}).get('groups') or []):
    bid=int(g.get('bundleId') or 0)
    delta=int(g.get('deltaCount') or 0)
    aps=[str(x) for x in (g.get('assetPaths') or [])]
    pref=[p for p in aps if p.lower().endswith('.prefab')]
    if bid in (0,prev,target) or delta<=0 or not pref: continue
    c.append((delta,bid,pref,g.get('deltaBundleIds') or []))
if not c: raise SystemExit('NO_NEXT_PREFAB_FAMILY_DELTA')
c.sort(key=lambda x:(x[0],x[1]))
delta,bid,pref,ids=c[0]
# Current V3/V4 evidence requires 6929 next. Refuse any silent drift.
if prev!=6934:
    raise SystemExit(f'UNEXPECTED_PREVIOUS_BUNDLE expected=6934 actual={prev}')
if bid!=6929 or delta!=9:
    raise SystemExit(f'UNEXPECTED_NEXT_BUNDLE expected=6929/delta9 actual={bid}/delta{delta}')
print(f'LUAUIFORM_V6_PREFLIGHT previous={prev} selected={bid} delta={delta} deltaIds={",".join(map(str,ids))}')
for p in pref: print('LUAUIFORM_V6_PREFLIGHT_ASSET',p)
PY

# Generate V6 from the exact reviewed V5 engine.
python - "$SRC" "$TMP" <<'PY'
from pathlib import Path
import sys
src=Path(sys.argv[1]).read_text('utf-8')
old="prev_bid=int(v4.get('selectedBundleId') or v4.get('selectedBundle') or 0)"
new="prev_bid=int(((v4.get('selection') or {}).get('bundleId')) or v4.get('selectedBundleId') or v4.get('selectedBundle') or 0)"
if src.count(old)!=1:
    raise SystemExit(f'V5_PREV_SELECTOR_PATTERN_COUNT_{src.count(old)}')
s=src.replace(old,new)
needle="candidates.sort(key=lambda x:(x[0],x[1])); expected_delta,selected_bid,selected_v3,prefab_paths=candidates[0]"
if s.count(needle)!=1:
    raise SystemExit(f'V5_SELECTION_PATTERN_COUNT_{s.count(needle)}')
s=s.replace(needle,needle+"\nif selected_bid==prev_bid: raise SystemExit(f'V6_REPLAY_GUARD selected={selected_bid} previous={prev_bid}')\nif selected_bid!=6929 or expected_delta!=9: raise SystemExit(f'V6_TARGET_GUARD expected=6929/delta9 actual={selected_bid}/delta{expected_delta}')")
# Version/output isolation. This does not alter scope or evidence logic.
s=s.replace('V5','V6').replace('v5','v6')
Path(sys.argv[2]).write_text(s,'utf-8')
PY
chmod 700 "$TMP"

bash "$TMP"
