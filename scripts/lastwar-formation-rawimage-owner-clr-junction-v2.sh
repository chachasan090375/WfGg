#!/data/data/com.termux/files/usr/bin/bash
set -Eeuo pipefail

# WfGg Last War LAB — corrected FormationBg / FormationRT owner -> CLR junction V2.
# V1 read g['objects']; exact PPtr V4 stores its serialized graph records under g['nodes'].
# V2 derives the same reviewed engine, changes only that schema key/output version,
# and requires the node count to match the exact V4 summary before analysis.

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BRANCH="portal-auth-lastwar-lab-v1"
SRC="$ROOT/scripts/lastwar-formation-rawimage-owner-clr-junction-v1.sh"
SUMMARY="$ROOT/frontend/lab/master-assets-v2/meta/formation-ptr-exact-v4-summary-v1.json"
TMP="$ROOT/scripts/.lastwar-formation-rawimage-owner-clr-junction-v2.generated.sh"

fail(){ printf 'ERREUR: %s\n' "$*" >&2; exit 1; }
cleanup(){ rm -f "$TMP"; }
trap cleanup EXIT

cd "$ROOT"
[[ "$(git branch --show-current)" == "$BRANCH" ]] || fail "branche LAB incorrecte"
[[ -s "$SRC" ]] || fail "moteur V1 absent: $SRC"
[[ -s "$SUMMARY" ]] || fail "résumé V4 absent: $SUMMARY"

python - "$SRC" "$TMP" <<'PY'
from pathlib import Path
import sys
src=Path(sys.argv[1]).read_text('utf-8')
old="objects=g.get('objects') or []"
new="objects=g.get('nodes') or []"
if src.count(old)!=1:
    raise SystemExit(f'V1_SCHEMA_PATTERN_COUNT_{src.count(old)}')
s=src.replace(old,new)
s=s.replace('RAWIMAGE_OWNER_CLR_JUNCTION_V1','RAWIMAGE_OWNER_CLR_JUNCTION_V2')
s=s.replace('rawimage-owner-clr-junction-v1','rawimage-owner-clr-junction-v2')
s=s.replace('RAWIMAGE OWNER CLR JUNCTION V1','RAWIMAGE OWNER CLR JUNCTION V2')
# Insert exact node-count guard after summary counts are loaded.
needle="counts=sj.get('counts') or {}"
if s.count(needle)!=1:
    raise SystemExit(f'V1_SUMMARY_GUARD_PATTERN_COUNT_{s.count(needle)}')
s=s.replace(needle, needle+"\nexpected_nodes=int(counts.get('objects') or 0)\nif expected_nodes<=0 or len(objects)!=expected_nodes:\n    raise SystemExit(f'PTR_V4_NODE_SCHEMA_MISMATCH expected={expected_nodes} actual={len(objects)}')")
Path(sys.argv[2]).write_text(s,'utf-8')
PY
chmod 700 "$TMP"
exec bash "$TMP"
