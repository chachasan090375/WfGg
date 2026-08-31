#!/data/data/com.termux/files/usr/bin/bash
set -Eeuo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BRANCH="portal-auth-lastwar-lab-v1"
DEP_SCRIPT="$ROOT/scripts/lastwar-formation-selected-material-dependent-bundles-v2.sh"
DEP_JSON="$ROOT/frontend/lab/master-assets-v2/meta/formation-selected-material-dependent-bundles-v2.json"
INDEX="$ROOT/frontend/lab/master-assets-v2/index/lastwar-graphics-master-index-v1.json"
LOCAL="$ROOT/frontend/lab/local_assets/lastwar-formation-ptr-exact-v4/bundles"
EXTRA="$HOME/.cache/wfgg-formation-selected-material-dependents-v2"
BUILDER="$ROOT/scripts/lastwar-bundle-reconstruction-viewer-build-v1.sh"
FAMILY="$ROOT/frontend/lab/bundle-reconstruction-data/family-14169.json"
TMP_BUILDER="$HOME/.cache/wfgg-bundle-recon-family-builder-v1.sh"

fail(){ printf 'ERREUR: %s\n' "$*" >&2; exit 1; }
cd "$ROOT"
[[ "$(git branch --show-current)" == "$BRANCH" ]] || fail "branche LAB incorrecte"
[[ -s "$DEP_SCRIPT" ]] || fail "script dependants absent"
[[ -s "$BUILDER" ]] || fail "builder bundle absent"
[[ -s "$INDEX" ]] || fail "index graphique absent"
mkdir -p "$EXTRA" "$LOCAL" "$(dirname "$FAMILY")" "$(dirname "$TMP_BUILDER")"

echo "BUNDLE_FAMILY_V1_START root=14169"
echo "BUNDLE_FAMILY_V1_STAGE discover-current-dependents"
bash "$DEP_SCRIPT"
[[ -s "$DEP_JSON" ]] || fail "rapport dependants JSON absent"

echo "BUNDLE_FAMILY_V1_STAGE prepare-generic-builder"
python - "$BUILDER" "$TMP_BUILDER" <<'PY'
from pathlib import Path
import sys
src=Path(sys.argv[1]).read_text('utf-8')
old="bundle_paths={bid:localp/f'bundle-{bid}.bundle' for bid in closure if (localp/f'bundle-{bid}.bundle').is_file()}\nif bundle_id not in bundle_paths:raise SystemExit(f'ROOT_BUNDLE_NOT_IN_CLOSURE bundle={bundle_id}')"
new="bundle_paths={bid:localp/f'bundle-{bid}.bundle' for bid in closure if (localp/f'bundle-{bid}.bundle').is_file()}\nfor ep in localp.glob('bundle-*.bundle'):\n    m=re.fullmatch(r'bundle-(\\d+)\\.bundle',ep.name)\n    if m: bundle_paths[int(m.group(1))]=ep\nif bundle_id not in bundle_paths:raise SystemExit(f'ROOT_BUNDLE_NOT_AVAILABLE bundle={bundle_id}')"
if old not in src:
    raise SystemExit('BUILDER_PATCH_GUARD root bundle block not found')
src=src.replace(old,new,1)
old2='for pos,bid in enumerate(closure,1):'
new2='for pos,bid in enumerate(sorted(bundle_paths),1):'
if old2 not in src:
    raise SystemExit('BUILDER_PATCH_GUARD mapping loop not found')
src=src.replace(old2,new2,1)
Path(sys.argv[2]).write_text(src,'utf-8')
PY
chmod +x "$TMP_BUILDER"

mapfile -t CANDIDATES < <(python - "$DEP_JSON" <<'PY'
import json,sys
j=json.load(open(sys.argv[1],encoding='utf-8'))
for x in j.get('bundleAggregate',[]):
    try: print(int(x['bundleId']))
    except Exception: pass
PY
)

echo "BUNDLE_FAMILY_V1_CANDIDATES count=${#CANDIDATES[@]} ids=${CANDIDATES[*]:--}"

for BID in "${CANDIDATES[@]}"; do
  SRC=""
  if [[ -s "$LOCAL/bundle-$BID.bundle" ]]; then SRC="$LOCAL/bundle-$BID.bundle"; fi
  if [[ -z "$SRC" && -s "$EXTRA/bundle-$BID.bundle" ]]; then
    cp -f "$EXTRA/bundle-$BID.bundle" "$LOCAL/bundle-$BID.bundle"
    SRC="$LOCAL/bundle-$BID.bundle"
  fi
  if [[ -z "$SRC" ]]; then
    echo "BUNDLE_FAMILY_V1_SKIP bundle=$BID reason=resolved-file-not-available"
    continue
  fi
  echo "BUNDLE_FAMILY_V1_BUILD bundle=$BID"
  bash "$TMP_BUILDER" "$BID" || echo "BUNDLE_FAMILY_V1_BUILD_FAILED bundle=$BID"
done

echo "BUNDLE_FAMILY_V1_STAGE write-family-manifest"
python - "$DEP_JSON" "$INDEX" "$ROOT/frontend/lab/bundle-reconstruction-data" "$FAMILY" <<'PY'
from pathlib import Path
import json,sys

dep=json.loads(Path(sys.argv[1]).read_text('utf-8'))
idx=json.loads(Path(sys.argv[2]).read_text('utf-8'))
data=Path(sys.argv[3]);out=Path(sys.argv[4])
byid={}
for r in idx.get('bundles',[]):
    if isinstance(r,dict) and r.get('bundleId') is not None:
        try:byid[int(r['bundleId'])]=r
        except Exception:pass
items=[]
for x in dep.get('bundleAggregate',[]):
    try:bid=int(x['bundleId'])
    except Exception:continue
    rec=byid.get(bid,{})
    objects=x.get('objects') or []
    types=sorted({str(o.get('sourceObjectType') or '') for o in objects if isinstance(o,dict) and o.get('sourceObjectType')})
    ready=(data/str(bid)/'manifest.json').is_file()
    manifest_summary=None
    if ready:
        try:
            mj=json.loads((data/str(bid)/'manifest.json').read_text('utf-8'))
            manifest_summary=mj.get('counts') or mj.get('summary')
        except Exception:pass
    items.append({
        'bundleId':bid,
        'hitCount':int(x.get('hits') or 0),
        'materials':x.get('materials') or [],
        'consumerTypes':types,
        'logicalName':rec.get('logicalName'),
        'aliasName':rec.get('aliasName'),
        'assetPaths':rec.get('assetPaths') or [],
        'ready':ready,
        'manifestSummary':manifest_summary,
    })
items.sort(key=lambda z:(not z['ready'],-len(z['materials']),-z['hitCount'],z['bundleId']))
res={
    'format':'WFGG_LASTWAR_BUNDLE_FAMILY_RECONSTRUCTION_VIEWER_V1',
    'rootBundleId':14169,
    'rootRole':'material-resource-bundle',
    'hitCount':sum(x['hitCount'] for x in items),
    'candidates':items,
    'rules':[
        'Candidates come only from current-index dependentBundleIds of bundle 14169 with exact serialized references to one or more of the five selected materials.',
        'Reconstruction manifests use only serialized Unity objects actually present/resolved; unresolved pieces remain unresolved.',
        'No historical physical offsets are reused.'
    ]
}
out.write_text(json.dumps(res,ensure_ascii=False,indent=2)+'\n','utf-8')
print('BUNDLE_FAMILY_V1_READY',f'candidates={len(items)}',f'ready={sum(1 for x in items if x["ready"])}',flush=True)
PY

URL="http://127.0.0.1:8788/lab/lastwar-bundle-family-viewer.html?v=1"
if command -v curl >/dev/null 2>&1 && curl -fsS --max-time 2 "http://127.0.0.1:8788/lab/" >/dev/null 2>&1; then
  echo "BUNDLE_FAMILY_V1_SERVER_ALREADY_RUNNING"
  echo "Viewer: $URL"
  exit 0
fi

echo "BUNDLE_FAMILY_V1_SERVER_START port=8788"
echo "Viewer: $URL"
exec python -m http.server 8788 --directory frontend --bind 127.0.0.1
