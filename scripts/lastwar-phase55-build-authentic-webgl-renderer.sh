#!/data/data/com.termux/files/usr/bin/bash
set -Eeuo pipefail

# WfGg Last War LAB — PHASE 55
# BUILD FIRST AUTHENTIC WEBGL RENDERER RUNTIME
# Uses Phase54 exact scene links + Phase51C idle keyframes + Phase49B OBJ/PNG.
# Re-exports skin arrays by exact Unity objectKey in the same pass.
# No generated geometry, no generated motion, no name fallback, no Last War network.

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BRANCH="portal-auth-lastwar-lab-v1"
UNITY_VERSION="2019.4.41f1"
P47="$ROOT/frontend/lab/master-assets-v2/meta/current15-exact-bundle-stage.json"
P54="$ROOT/frontend/lab/master-assets-v2/meta/current15-authoritative-export-scene-index-v1.json"
SRC="$ROOT/frontend/lab/local_assets/lastwar-current15-exact-v1"
SCENES="$ROOT/frontend/lab/local_assets/lastwar-current15-runtime-v5-authoritative"
OUT="$ROOT/frontend/lab/local_assets/lastwar-current15-renderer-v1"
MANIFEST="$ROOT/frontend/lab/master-assets-v2/meta/current15-webgl-renderer-v1.json"
REPORT="$HOME/storage/downloads/WFGG_LASTWAR_PHASE55_AUTHENTIC_WEBGL_RENDERER.txt"
PY="${TMPDIR:-$HOME/.cache}/wfgg-phase55-renderer.py"

fail(){ printf 'ERREUR: %s\n' "$*" >&2; exit 1; }
cd "$ROOT"
[[ "$(git branch --show-current)" == "$BRANCH" ]] || fail "branche active incorrecte"
[[ -s "$P47" && -s "$P54" ]] || fail "Phase47/54 absente"
[[ -d "$SRC" && -d "$SCENES" ]] || fail "assets locaux Phase47/54 absents"
command -v python >/dev/null 2>&1 || fail "python absent"
python - <<'PY' >/dev/null 2>&1 || fail "UnityPy/MeshHandler absent"
import UnityPy
from UnityPy.helpers.MeshHelper import MeshHandler
PY

rm -rf "$OUT"
mkdir -p "$OUT" "$(dirname "$MANIFEST")" "$(dirname "$REPORT")" "$(dirname "$PY")"

cat > "$PY" <<'PYEOF'
from pathlib import Path
import gzip, hashlib, json, os, sys, traceback
from collections import defaultdict
import UnityPy
from UnityPy.helpers.MeshHelper import MeshHandler

p47p,p54p,src,scenes,out,manifestp,reportp,unity_version=map(Path,sys.argv[1:8])+[sys.argv[8]] if False else (Path(sys.argv[1]),Path(sys.argv[2]),Path(sys.argv[3]),Path(sys.argv[4]),Path(sys.argv[5]),Path(sys.argv[6]),Path(sys.argv[7]),sys.argv[8])
UnityPy.config.FALLBACK_UNITY_VERSION=unity_version
j47=json.loads(p47p.read_text(encoding='utf-8')); j54=json.loads(p54p.read_text(encoding='utf-8'))
h47={int(x['heroId']):x for x in j47.get('heroes',[])}
h54={int(x['heroId']):x for x in j54.get('heroes',[])}
ids=sorted(set(h47)&set(h54))
if len(ids)!=15: raise SystemExit(f'expected 15 heroes, got {len(ids)}')

def typ(r):
    try:return r.type.name
    except:return str(getattr(r,'type',''))
def read(r):
    try:return r.read()
    except Exception:
        try:return r.parse_as_object()
        except:return None
def pid(r):
    try:return int(getattr(r,'path_id'))
    except:return None
def afname(r):
    try:
        af=getattr(r,'assets_file'); s=str(getattr(af,'name','') or getattr(af,'path','') or '')
        return s.replace('\\','/').rstrip('/').rsplit('/',1)[-1].lower()
    except:return ''
def key(r):
    p=pid(r);a=afname(r)
    return None if p is None or not a else f'{a}::{p}'
def matrix16(m):
    if m is None:return None
    vals=[]
    for rr in range(4):
        for cc in range(4):
            try: vals.append(float(getattr(m,f'e{rr}{cc}')))
            except Exception:return None
    return vals
def writegz(p,obj):
    raw=json.dumps(obj,ensure_ascii=False,separators=(',',':'),allow_nan=False).encode()
    with gzip.open(p,'wb',compresslevel=6) as f:f.write(raw)
    h=hashlib.sha256(p.read_bytes()).hexdigest()
    return len(raw),p.stat().st_size,h

def skin(mesh):
    mh=MeshHandler(mesh); mh.process()
    bi=mh.m_BoneIndices or []; bw=mh.m_BoneWeights or []
    binds=[]
    for x in (getattr(mesh,'m_BindPose',None) or []):
        v=matrix16(x)
        if v is not None:binds.append(v)
    return {
      'vertexCount':int(mh.m_VertexCount or len(mh.m_Vertices or [])),
      'boneIndices':[[int(v) for v in x] for x in bi],
      'boneWeights':[[float(v) for v in x] for x in bw],
      'bindPoses':binds
    }

rows=[]
for n,hid in enumerate(ids,1):
    h=h47[hid]; meta=h54[hid]; name=h.get('name') or str(hid)
    print(f'PHASE55_HERO {n}/15 id={hid} name={name}',flush=True)
    row={'heroId':hid,'name':name,'sceneReady':bool(meta.get('sceneLinked')),'skinComponentCount':0,'skinReadyCount':0,'errors':[]}
    try:
        sp=scenes/str(hid)/'scene.json'
        if not sp.is_file(): raise ValueError('Phase54 scene.json absent')
        scene=json.loads(sp.read_text(encoding='utf-8'))
        sk=scene.get('skinnedRenderers',[]) or []
        row['skinComponentCount']=len(sk)
        wanted={x.get('meshKey',{}).get('objectKey') for x in sk if x.get('meshKey')}
        wanted.discard(None)
        hdir=src/str(hid)
        files=sorted({hdir/os.path.basename(str(b.get('logicalName') or '')) for b in h.get('bundles',[]) if os.path.basename(str(b.get('logicalName') or '')) and (hdir/os.path.basename(str(b.get('logicalName') or ''))).is_file()})
        env=UnityPy.load(*[str(p) for p in files])
        meshreaders={key(r):r for r in env.objects if typ(r)=='Mesh' and key(r)}
        skins={}
        for comp in sk:
            ck=(comp.get('componentKey') or {}).get('objectKey'); mk=(comp.get('meshKey') or {}).get('objectKey')
            ent={'componentKey':ck,'meshKey':mk,'bones':comp.get('bones',[]),'rootBone':comp.get('rootBone'),'ready':False}
            r=meshreaders.get(mk)
            if r is not None:
                m=read(r)
                if m is not None:
                    try:
                        s=skin(m); ent['skin']=s
                        ent['ready']=bool(s['vertexCount'] and len(s['boneIndices'])==s['vertexCount'] and len(s['boneWeights'])==s['vertexCount'] and s['bindPoses'])
                    except Exception as e: ent['error']=repr(e)
            if ent['ready']:row['skinReadyCount']+=1
            skins[ck or ('mesh:'+str(mk))]=ent
        hd=out/str(hid);hd.mkdir(parents=True,exist_ok=True)
        rawb,gzb,sh=writegz(hd/'skin.json.gz',{'format':'WFGG_LASTWAR_HERO_EXACT_SKIN_V1','heroId':hid,'components':skins})
        idx={'format':'WFGG_LASTWAR_HERO_WEBGL_RUNTIME_V1','heroId':hid,'name':name,'sceneUrl':f'../lastwar-current15-runtime-v5-authoritative/{hid}/scene.json','assetBase':f'../lastwar-current15-runtime-v1/{hid}/','idleUrl':f'../lastwar-current15-runtime-v1/{hid}/animation/idle.json.gz','skinUrl':f'../lastwar-current15-renderer-v1/{hid}/skin.json.gz','rendererMode':meta.get('rendererMode')}
        (hd/'renderer.json').write_text(json.dumps(idx,ensure_ascii=False,indent=2),encoding='utf-8')
        row['rendererReady']=bool(row['sceneReady'] and (not sk or row['skinReadyCount']>0))
        row['skinFile']={'jsonBytes':rawb,'gzipBytes':gzb,'sha256':sh}
    except Exception as e:
        row['rendererReady']=False;row['errors'].append(repr(e));row['traceback']=traceback.format_exc()[-2500:]
    rows.append(row)
    print('PHASE55_HERO_DONE',hid,f"renderer={row['rendererReady']}",f"skin={row['skinReadyCount']}/{row['skinComponentCount']}",flush=True)

summary={'format':'WFGG_LASTWAR_CURRENT15_WEBGL_RENDERER_V1','heroCount':15,'sceneReadyCount':sum(x['sceneReady'] for x in rows),'rendererReadyCount':sum(x.get('rendererReady',False) for x in rows),'skinComponentCount':sum(x['skinComponentCount'] for x in rows),'skinReadyCount':sum(x['skinReadyCount'] for x in rows),'heroes':[{k:v for k,v in x.items() if k!='traceback'} for x in rows],'guardrails':{'exactObjectKeys':True,'noGeneratedGeometry':True,'noGeneratedMotion':True,'noNameFallback':True,'noLastWarNetwork':True}}
manifestp.write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
lines=['WfGg Last War LAB — PHASE 55 AUTHENTIC WEBGL RENDERER',f"heroes=15 sceneReady={summary['sceneReadyCount']}/15 rendererReady={summary['rendererReadyCount']}/15",f"skinComponents={summary['skinComponentCount']} skinReady={summary['skinReadyCount']}",'']
for x in rows:lines.append(f"HERO {x['heroId']} {x['name']} renderer={x.get('rendererReady')} skin={x['skinReadyCount']}/{x['skinComponentCount']} errors={x['errors']}")
lines += ['','GUARDRAILS','  exact_object_keys=true','  no_generated_geometry=true','  no_generated_motion=true','  no_name_fallback=true','  no_lastwar_network=true']
reportp.write_text('\n'.join(lines)+'\n',encoding='utf-8')
print('PHASE55_OK',f"rendererReady={summary['rendererReadyCount']}/15",f"skinReady={summary['skinReadyCount']}/{summary['skinComponentCount']}")
print('PHASE55_REPORT',reportp)
PYEOF

python "$PY" "$P47" "$P54" "$SRC" "$SCENES" "$OUT" "$MANIFEST" "$REPORT" "$UNITY_VERSION"
rm -f "$PY"

git add "$MANIFEST"
if ! git diff --cached --quiet; then
  git commit -m "lab: record exact WebGL skin runtime"
  git push origin "$BRANCH"
fi

echo "=== PHASE 55 TERMINEE ==="
echo "Viewer: http://127.0.0.1:8877/lab/lastwar-auth-renderer.html"
echo "Rapport: $REPORT"
echo "main non modifiée."
