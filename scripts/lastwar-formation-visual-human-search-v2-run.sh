#!/data/data/com.termux/files/usr/bin/bash
set -Eeuo pipefail

# WfGg Last War LAB — continuous human visual search V2 runner
# Builds the six-point V2 review lot, validates its manifest, then serves the LAB.

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BRANCH="portal-auth-lastwar-lab-v1"
SRC="$ROOT/scripts/lastwar-formation-visual-human-search-v2.sh"
TMP="$ROOT/scripts/.lastwar-formation-visual-human-search-v2.runtime.sh"
MANIFEST="$ROOT/frontend/lab/formation-texture-review-v2/manifest.json"
PORT=8788

fail(){ printf 'ERREUR: %s\n' "$*" >&2; exit 1; }
cd "$ROOT"
[[ "$(git branch --show-current)" == "$BRANCH" ]] || fail "branche LAB incorrecte"
[[ -s "$SRC" ]] || fail "V2 absent: $SRC"

# Runtime hardening without touching the extraction logic:
# - resolve relative current-index physical sources from the repo cwd;
# - refuse a malformed/empty graphics index instead of silently producing zero external candidates.
python - "$SRC" "$TMP" <<'PY'
from pathlib import Path
import sys
src=Path(sys.argv[1]).read_text('utf-8')
old="cands=[p,Path.home()/'storage/downloads'/p.name,Path.home()/'storage/shared/Download'/p.name,ROOT/p]"
new="cands=[p,Path.home()/'storage/downloads'/p.name,Path.home()/'storage/shared/Download'/p.name,Path.cwd()/p]"
if old not in src:
    raise SystemExit('ERREUR: correctif chemin V2 attendu introuvable')
src=src.replace(old,new,1)
needle="s=json.loads(sump.read_text('utf-8'));idx=json.loads(indexp.read_text('utf-8'))"
insert=needle+"\nindex_bundles=idx.get('bundles')\nif not isinstance(index_bundles,list) or not index_bundles:\n    raise SystemExit('GRAPHICS_INDEX_SCHEMA_INVALID expected non-empty bundles[]')"
if needle not in src:
    raise SystemExit('ERREUR: garde schéma V2 impossible à injecter')
src=src.replace(needle,insert,1)
loop="for rec in idx.get('bundles',[]):"
if loop not in src:
    raise SystemExit('ERREUR: boucle index V2 attendue introuvable')
src=src.replace(loop,"for rec in index_bundles:",1)
Path(sys.argv[2]).write_text(src,'utf-8')
PY
chmod +x "$TMP"
cleanup(){ rm -f "$TMP" 2>/dev/null || true; }
trap cleanup EXIT

bash "$TMP"
[[ -s "$MANIFEST" ]] || fail "manifeste V2 absent après construction"

ITEMS="$(python - "$MANIFEST" <<'PY'
from pathlib import Path
import json,sys
p=Path(sys.argv[1]);m=json.loads(p.read_text('utf-8'))
if m.get('format')!='WFGG_LASTWAR_FORMATION_VISUAL_HUMAN_SEARCH_MANIFEST_V2':
    raise SystemExit('MANIFEST_FORMAT_INVALID')
items=m.get('items')
if not isinstance(items,list):
    raise SystemExit('MANIFEST_ITEMS_INVALID')
c=m.get('counts') or {}
print(len(items))
print(f"closure={c.get('closureShown',0)} external={c.get('externalShown',0)}",file=sys.stderr)
PY
)"

echo "FORMATION_VISUAL_V2_READY items=$ITEMS"
echo "LAB: http://127.0.0.1:${PORT}/lab/lastwar-formation-texture-viewer.html?v=2.1"
echo "Le serveur reste actif dans cette session Termux. Ctrl+C pour l'arrêter."

exec python -m http.server "$PORT" --directory frontend --bind 127.0.0.1
