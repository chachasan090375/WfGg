#!/data/data/com.termux/files/usr/bin/bash
set -Eeuo pipefail

# WfGg Last War LAB — LuaUIFormLogic current-install locator V7.
# V7 does not infer "next" from the previous bundle. It consumes the exact
# nextPrefabFamilyDelta emitted by V6, cross-checks it against V3, then reuses
# the reviewed V5 audit engine with only the selector/output wiring patched.
# Expected evidence-selected target: bundle 6974, delta 11.
# APK remains read-only; no global scan; no candidate promotion.

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BRANCH="portal-auth-lastwar-lab-v1"
SRC="$ROOT/scripts/lastwar-formation-luauiformlogic-current-install-locator-v5.sh"
V3="$ROOT/frontend/lab/master-assets-v2/meta/formation-luauiformlogic-current-install-locator-v3.json"
V6="$ROOT/frontend/lab/master-assets-v2/meta/formation-luauiformlogic-current-install-locator-v6.json"
TMP="$ROOT/scripts/.lastwar-formation-luauiformlogic-current-install-locator-v7.generated.sh"
EXPECTED_V5_BLOB="979ff33c41418d6e9c1843094113924022d77fd1"

fail(){ printf 'ERREUR: %s\n' "$*" >&2; exit 1; }
cleanup(){ rm -f "$TMP"; }
trap cleanup EXIT

cd "$ROOT"
[[ "$(git branch --show-current)" == "$BRANCH" ]] || fail "branche LAB incorrecte"
[[ -s "$SRC" ]] || fail "moteur V5 absent: $SRC"
[[ -s "$V3" ]] || fail "JSON V3 absent: $V3"
[[ -s "$V6" ]] || fail "JSON V6 absent: $V6"
[[ "$(git hash-object "$SRC")" == "$EXPECTED_V5_BLOB" ]] || fail "V5 source différent du moteur audité; refus de dérivation silencieuse"

# Metadata-only preflight: exact next target must be 6974/delta11 and must exist identically in V3.
python - "$V3" "$V6" <<'PY'
import json,sys
v3=json.load(open(sys.argv[1],encoding='utf-8'))
v6=json.load(open(sys.argv[2],encoding='utf-8'))
if v3.get('format')!='WFGG_LASTWAR_FORMATION_LUAUIFORMLOGIC_CURRENT_INSTALL_LOCATOR_V3':
    raise SystemExit('V3_FORMAT_MISMATCH')
if v6.get('format')!='WFGG_LASTWAR_FORMATION_LUAUIFORMLOGIC_CURRENT_INSTALL_LOCATOR_V6':
    raise SystemExit('V6_FORMAT_MISMATCH')
n=v6.get('nextPrefabFamilyDelta') or {}
bid=int(n.get('bundleId') or 0); delta=int(n.get('deltaCount') or 0)
aps=[str(x) for x in (n.get('assetPaths') or [])]
if bid!=6974 or delta!=11:
    raise SystemExit(f'UNEXPECTED_V6_NEXT expected=6974/delta11 actual={bid}/delta{delta}')
groups=((v3.get('formationFamily') or {}).get('groups') or [])
rows=[g for g in groups if int(g.get('bundleId') or 0)==bid]
if len(rows)!=1: raise SystemExit(f'V3_GROUP_IDENTITY_COUNT_{len(rows)}')
g=rows[0]
if int(g.get('deltaCount') or 0)!=delta:
    raise SystemExit(f'V3_V6_DELTA_MISMATCH v3={g.get("deltaCount")} v6={delta}')
v3aps=[str(x) for x in (g.get('assetPaths') or [])]
if sorted(v3aps)!=sorted(aps):
    raise SystemExit('V3_V6_ASSETPATH_MISMATCH')
pref=[p for p in aps if p.lower().endswith('.prefab')]
if not pref: raise SystemExit('V6_NEXT_HAS_NO_PREFAB')
print(f'LUAUIFORM_V7_PREFLIGHT selected={bid} delta={delta} deltaIds={",".join(map(str,g.get("deltaBundleIds") or []))}')
for p in pref: print('LUAUIFORM_V7_PREFLIGHT_ASSET',p)
PY

# Derive the already-reviewed V5 engine. Patch only:
#  - source metadata path/format V4 -> V6
#  - selector -> exact V6.nextPrefabFamilyDelta + V3 identity cross-check
#  - version/output namespace V5 -> V7
python - "$SRC" "$TMP" <<'PY'
from pathlib import Path
import sys
s=Path(sys.argv[1]).read_text('utf-8')
old_path='V4="$ROOT/frontend/lab/master-assets-v2/meta/formation-luauiformlogic-current-install-locator-v4.json"'
new_path='V4="$ROOT/frontend/lab/master-assets-v2/meta/formation-luauiformlogic-current-install-locator-v6.json"'
if s.count(old_path)!=1: raise SystemExit(f'V5_V4_PATH_PATTERN_COUNT_{s.count(old_path)}')
s=s.replace(old_path,new_path)
old_fmt="if v4.get('format')!='WFGG_LASTWAR_FORMATION_LUAUIFORMLOGIC_CURRENT_INSTALL_LOCATOR_V4': raise SystemExit('V4_FORMAT_MISMATCH')"
new_fmt="if v4.get('format')!='WFGG_LASTWAR_FORMATION_LUAUIFORMLOGIC_CURRENT_INSTALL_LOCATOR_V6': raise SystemExit('V6_FORMAT_MISMATCH')"
if s.count(old_fmt)!=1: raise SystemExit(f'V5_FORMAT_PATTERN_COUNT_{s.count(old_fmt)}')
s=s.replace(old_fmt,new_fmt)
start="# Select next prefab-family group only. Ignore image/texture-only groups.\n"
end="selected_closure=closure(selected_bid); actual_delta=sorted(selected_closure-baseline); overlap=selected_closure & baseline\n"
a=s.find(start); b=s.find(end)
if a<0 or b<0 or b<=a: raise SystemExit('V5_SELECTION_BLOCK_NOT_FOUND')
replacement="""# Select exactly the evidence-carried next prefab-family group from V6.\ngroups=((v3.get('formationFamily') or {}).get('groups') or [])\nnext_meta=v4.get('nextPrefabFamilyDelta') or {}\nselected_bid=int(next_meta.get('bundleId') or 0)\nexpected_delta=int(next_meta.get('deltaCount') or 0)\nnext_paths=[str(x) for x in (next_meta.get('assetPaths') or [])]\nif selected_bid!=6974 or expected_delta!=11: raise SystemExit(f'V7_TARGET_GUARD expected=6974/delta11 actual={selected_bid}/delta{expected_delta}')\nrows=[g for g in groups if int(g.get('bundleId') or 0)==selected_bid]\nif len(rows)!=1: raise SystemExit(f'V7_V3_GROUP_COUNT_{len(rows)}')\nselected_v3=rows[0]\nprefab_paths=[p for p in next_paths if p.lower().endswith('.prefab')]\nif not prefab_paths: raise SystemExit('V7_TARGET_HAS_NO_PREFAB')\nif sorted(str(x) for x in (selected_v3.get('assetPaths') or []))!=sorted(next_paths): raise SystemExit('V7_V3_V6_ASSETPATH_MISMATCH')\n"""
s=s[:a]+replacement+end+s[b+len(end):]
# V7 needs delta 11; V5 cap is already 12, so no widening required.
s=s.replace('V5','V7').replace('v5','v7')
Path(sys.argv[2]).write_text(s,'utf-8')
PY
chmod 700 "$TMP"
bash "$TMP"
