#!/data/data/com.termux/files/usr/bin/bash
set -Eeuo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BRANCH="portal-auth-lastwar-lab-v1"
OUT="$ROOT/frontend/lab/master-assets-v2/meta/audie-family-scan-v1.json"
UNITY_VERSION="2019.4.41f1"
cd "$ROOT"
[[ "$(git branch --show-current)" == "$BRANCH" ]] || { echo "ERREUR: branche LAB incorrecte" >&2; exit 1; }
command -v python >/dev/null 2>&1 || { echo "ERREUR: python absent" >&2; exit 1; }
python - <<'PYCHK' >/dev/null 2>&1 || { echo "ERREUR: UnityPy absent" >&2; exit 1; }
import UnityPy
PYCHK
mkdir -p "$(dirname "$OUT")"
TMP="$(mktemp)"
trap 'rm -f "$TMP"' EXIT
find "$ROOT/frontend/lab/local_assets" "$HOME/.cache" -type f \( -name 'bundle-*.bundle' -o -name '*.bundle' \) 2>/dev/null | sort -u > "$TMP" || true
COUNT=$(wc -l < "$TMP" | tr -d ' ')
echo "AUDIE_FAMILY_SCAN_V1_START bundleFiles=$COUNT"
PYTHONUNBUFFERED=1 python - "$TMP" "$OUT" "$ROOT" "$UNITY_VERSION" <<'PY'
from pathlib import Path
from collections import Counter
import json,re,sys
import UnityPy
lst,out,root,uv=Path(sys.argv[1]),Path(sys.argv[2]),Path(sys.argv[3]),sys.argv[4]
UnityPy.config.FALLBACK_UNITY_VERSION=uv
paths=[Path(x) for x in lst.read_text('utf-8').splitlines() if x.strip()]

def typ(o): return str(getattr(getattr(o,'type',None),'name','') or '')
def pid(o): return int(getattr(o,'path_id',0) or 0)
def pname(o):
    try:return str(o.peek_name() or '')
    except:return ''
def bid_from_path(p):
    m=re.search(r'bundle-(\d+)\.bundle$',p.name)
    return int(m.group(1)) if m else None

def asset_meta(o):
    r={'type':typ(o),'pathID':str(pid(o)),'name':pname(o)}
    if r['type']=='Texture2D':
        try:
            d=o.read(); r['width']=int(d.m_Width); r['height']=int(d.m_Height); r['format']=str(getattr(d,'m_TextureFormat',''))
        except Exception as e:r['readError']=f'{type(e).__name__}:{e}'
    return r

hits=[]; bundle_inventories=[]; errors=[]
for i,p in enumerate(paths,1):
    if i%50==0: print('AUDIE_FAMILY_SCAN_V1_PROGRESS',f'{i}/{len(paths)}',flush=True)
    try:
        env=UnityPy.load(str(p)); objs=list(getattr(env,'objects',[]) or [])
    except Exception as e:
        errors.append({'path':str(p),'error':f'{type(e).__name__}:{e}'}); continue
    named=[]
    for o in objs:
        n=pname(o)
        if n and ('audie' in n.lower() or 'a_hero_audie' in n.lower()): named.append(asset_meta(o))
    if not named: continue
    bid=bid_from_path(p)
    counts=Counter(typ(o) for o in objs)
    companions=[]
    keep={'Texture2D','Material','Mesh','GameObject','MeshRenderer','SkinnedMeshRenderer','MeshFilter','AnimationClip','Animator','AnimatorController','Avatar','Shader','AssetBundle'}
    for o in objs:
        t=typ(o); n=pname(o)
        if t in keep and (n or t in {'MeshRenderer','SkinnedMeshRenderer','MeshFilter'}):
            companions.append({'type':t,'pathID':str(pid(o)),'name':n})
    rec={'bundleId':bid,'path':str(p),'hits':named,'counts':dict(counts),'companions':companions[:2500]}
    hits.extend([dict(x,bundleId=bid,bundlePath=str(p)) for x in named]); bundle_inventories.append(rec)

# Existing extracted/generated files whose filenames contain Audie.
file_hits=[]
for base in [root/'frontend/lab']:
    if base.exists():
        for p in base.rglob('*'):
            if p.is_file() and 'audie' in p.name.lower():
                file_hits.append(str(p.relative_to(root)))

# Search the master graphics index for metadata mentioning Audie, including bundles not currently cached.
index_hits=[]
idx=root/'frontend/lab/master-assets-v2/index/lastwar-graphics-master-index-v1.json'
if idx.exists():
    try:
        j=json.loads(idx.read_text('utf-8'))
        for r in j.get('bundles',[]):
            s=json.dumps(r,ensure_ascii=False)
            if 'audie' in s.lower(): index_hits.append(r)
    except Exception as e: errors.append({'path':str(idx),'error':f'{type(e).__name__}:{e}'})

# Classify suffixes to expose missing map families.
suffix=Counter()
for h in hits:
    n=h.get('name','')
    m=re.search(r'A_Hero_Audie_01(?:_High)?_([A-Za-z0-9]+)$',n,re.I)
    if m:suffix[m.group(1).upper()]+=1
known=set(suffix)
expected=['D','N','S','M','AO','E','MASK','ALPHA','R','ROUGHNESS','METALLIC','EMISSION']
missing=[x for x in expected if x not in known]
res={
 'format':'WFGG_LASTWAR_AUDIE_FAMILY_SCAN_V1',
 'query':['Audie','A_Hero_Audie_01'],
 'bundleFilesScanned':len(paths),
 'namedHits':hits,
 'hitBundles':bundle_inventories,
 'indexHits':index_hits,
 'fileHits':sorted(set(file_hits)),
 'suffixCounts':dict(sorted(suffix.items())),
 'notObservedCommonSuffixes':missing,
 'errors':errors[:200],
 'rules':['No missing suffix is assumed to exist; notObservedCommonSuffixes is only a checklist.','Hit bundles include companion Unity objects so unnamed Mesh/Material/Renderer pieces in the same bundle can be reviewed.','Index hits may reveal Audie-related bundles that are known by metadata but absent from the current local cache.']
}
out.write_text(json.dumps(res,ensure_ascii=False,indent=2)+'\n','utf-8')
print('AUDIE_FAMILY_SCAN_V1_READY',f'namedHits={len(hits)}',f'hitBundles={len(bundle_inventories)}',f'indexHits={len(index_hits)}',f'fileHits={len(file_hits)}',f'suffixes={dict(suffix)}',flush=True)
print('JSON='+str(out),flush=True)
PY
URL="http://127.0.0.1:8788/lab/lastwar-audie-family-viewer.html?v=1"
echo "VIEWER=$URL"
