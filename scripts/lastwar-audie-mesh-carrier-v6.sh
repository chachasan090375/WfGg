#!/data/data/com.termux/files/usr/bin/bash
set -Eeuo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BRANCH="portal-auth-lastwar-lab-v1"
cd "$ROOT"
[[ "$(git branch --show-current)" == "$BRANCH" ]] || { echo "ERREUR: branche LAB incorrecte" >&2; exit 1; }
[[ -s "$ROOT/frontend/lab/master-assets-v2/meta/audie-package-family-v5.json" ]] || bash "$ROOT/scripts/lastwar-audie-package-family-v5.sh"
command -v python >/dev/null 2>&1 || { echo "ERREUR: python absent" >&2; exit 1; }
python - <<'PYCHK' >/dev/null 2>&1 || { echo "ERREUR: UnityPy / texture2ddecoder / Pillow absents" >&2; exit 1; }
import UnityPy, texture2ddecoder
from PIL import Image
PYCHK
PYTHONUNBUFFERED=1 python "$ROOT/scripts/lastwar-audie-mesh-carrier-v6.py" "$ROOT"
python - "$ROOT" <<'PYFIX'
from pathlib import Path
import json,sys
root=Path(sys.argv[1]); p=root/'frontend/lab/audie-mesh-carrier-v6-data/manifest.json'
m=json.loads(p.read_text('utf-8'))
by_bundle={c.get('basename'):c for c in m.get('carriers',[])}
for mesh in m.get('meshes',[]):
    c=by_bundle.get(mesh.get('bundle')) or {}
    sf=mesh.get('serializedFile') or ''
    pid=str(mesh.get('pathID') or '')
    mesh['rendererReferenced']=any(
        int((r.get('mesh') or {}).get('fileID',-1))==0 and
        str((r.get('mesh') or {}).get('pathID') or '')==pid and
        (r.get('serializedFile') or '')==sf
        for r in c.get('renderRefs',[])
    )
for c in m.get('carriers',[]):
    c['rendererReferencedMeshes']=sum(1 for x in m.get('meshes',[]) if x.get('bundle')==c.get('basename') and x.get('rendererReferenced'))
m.setdefault('counts',{})['rendererReferencedMeshes']=sum(1 for x in m.get('meshes',[]) if x.get('rendererReferenced'))
m.setdefault('rules',[]).append('V6 runner hardening: rendererReferenced requires local fileID=0, identical serialized file, and identical pathID.')
p.write_text(json.dumps(m,ensure_ascii=False,indent=2)+'\n','utf-8')
print('AUDIE_MESH_CARRIER_V6_PTR_HARDENED rendererReferenced='+str(m['counts']['rendererReferencedMeshes']))
PYFIX
echo "VIEWER=http://127.0.0.1:8788/lab/lastwar-audie-mesh-carrier-viewer.html?v=6"
