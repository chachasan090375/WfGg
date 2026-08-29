#!/data/data/com.termux/files/usr/bin/bash
set -Eeuo pipefail

# WfGg Last War LAB — PHASE 49
# EXPORT EXACT CURRENT-15 UNITY GEOMETRY/TEXTURES FOR WEB RENDERER
# CODE ONLY · OFFLINE ONLY · exact Phase47 bundles only.
#
# This phase does NOT invent geometry, does NOT substitute models, and does not
# touch the Escouades UI yet. It exports renderable geometry and textures from
# the exact bundles staged in Phase47. Animation clips are inventoried for the
# following animation-export phase.

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BRANCH="portal-auth-lastwar-lab-v1"
UNITY_VERSION="2019.4.41f1"
P47="$ROOT/frontend/lab/master-assets-v2/meta/current15-exact-bundle-stage.json"
SRC="$ROOT/frontend/lab/local_assets/lastwar-current15-exact-v1"
OUT="$ROOT/frontend/lab/local_assets/lastwar-current15-web-v1"
MANIFEST="$ROOT/frontend/lab/master-assets-v2/meta/current15-web-export-v1.json"
REPORT="$HOME/storage/downloads/WFGG_LASTWAR_PHASE49_CURRENT15_WEB_EXPORT.txt"
PY="${TMPDIR:-$HOME/.cache}/wfgg-phase49-web-export.py"

fail(){ printf 'ERREUR: %s\n' "$*" >&2; exit 1; }
cd "$ROOT"
[[ "$(git branch --show-current)" == "$BRANCH" ]] || fail "branche active incorrecte"
[[ -s "$P47" ]] || fail "Phase47 absente: $P47"
[[ -d "$SRC" ]] || fail "Assets locaux Phase47 absents: $SRC"
command -v python >/dev/null 2>&1 || fail "python absent"

rm -rf "$OUT"
mkdir -p "$OUT" "$(dirname "$MANIFEST")" "$(dirname "$PY")"

cat > "$PY" <<'PYEOF'
from pathlib import Path
from collections import defaultdict
import hashlib, json, math, os, re, sys, traceback

p47p=Path(sys.argv[1]); src=Path(sys.argv[2]); outroot=Path(sys.argv[3]); manifestp=Path(sys.argv[4]); reportp=Path(sys.argv[5]); unity_version=sys.argv[6]

data=json.loads(p47p.read_text(encoding='utf-8'))
heroes=data.get('heroes') or []
if len(heroes)!=15: raise SystemExit(f'expected 15 heroes, got {len(heroes)}')

try:
    import UnityPy
except Exception as e:
    raise SystemExit(f'UnityPy absent: {e}')
UnityPy.config.FALLBACK_UNITY_VERSION=unity_version

SAFE=re.compile(r'[^A-Za-z0-9._-]+')
def safe(s, fallback='asset'):
    x=SAFE.sub('_',str(s or '')).strip('._')
    return x[:180] or fallback

def sha256_file(p,chunk=1024*1024):
    h=hashlib.sha256()
    with p.open('rb') as f:
        while True:
            b=f.read(chunk)
            if not b:break
            h.update(b)
    return h.hexdigest()

def read_obj(reader):
    try:return reader.read()
    except Exception:
        try:return reader.parse_as_object()
        except Exception:return None

def obj_name(d, fallback=''):
    return str(getattr(d,'m_Name','') or getattr(d,'name','') or fallback or '')

def ptr_obj(ptr):
    if ptr is None:return None
    try:return ptr.read()
    except Exception:
        try:return ptr.deref_parse_as_object()
        except Exception:return None

def ptr_name(ptr):
    d=ptr_obj(ptr)
    return obj_name(d) if d is not None else ''

def vec(v, names):
    if v is None:return None
    out=[]
    for n in names:
        try:out.append(float(getattr(v,n)))
        except Exception:return None
    return out

def type_name(reader):
    try:return reader.type.name
    except Exception:return str(getattr(reader,'type',''))

def mesh_export_text(mesh):
    # UnityPy Mesh export API differs slightly between releases. Try the public
    # object export first, then installed exporter helpers without assuming one.
    err=[]
    fn=getattr(mesh,'export',None)
    if callable(fn):
        try:
            x=fn()
            if isinstance(x,bytes):x=x.decode('utf-8','ignore')
            if isinstance(x,str) and ('v ' in x or 'f ' in x):return x,None
        except Exception as e:err.append('mesh.export:'+repr(e))
    try:
        from UnityPy.export import MeshExporter
        for name in ('export_mesh','export_obj'):
            f=getattr(MeshExporter,name,None)
            if callable(f):
                try:
                    x=f(mesh)
                    if isinstance(x,bytes):x=x.decode('utf-8','ignore')
                    if isinstance(x,str) and ('v ' in x or 'f ' in x):return x,None
                except Exception as e:err.append('MeshExporter.'+name+':'+repr(e))
    except Exception as e:err.append('MeshExporter import:'+repr(e))
    return None,' | '.join(err) or 'no mesh export API'

def material_dict(mat):
    row={'name':obj_name(mat,'Material')}
    # Common Unity material fields; keep only serializable primitives.
    try:row['shader']=ptr_name(getattr(mat,'m_Shader',None))
    except Exception:pass
    try:
        saved=getattr(mat,'m_SavedProperties',None)
        if saved is not None:
            for field in ('m_TexEnvs','m_Floats','m_Colors','m_Ints'):
                val=getattr(saved,field,None)
                if val is not None:
                    try:row[field]=str(val)[:20000]
                    except Exception:pass
    except Exception:pass
    return row

def transform_row(t):
    go=ptr_obj(getattr(t,'m_GameObject',None)); go_name=obj_name(go,'') if go else ''
    parent=''
    try:parent=ptr_name(getattr(t,'m_Father',None))
    except Exception:pass
    return {
      'gameObject':go_name,
      'parentTransform':parent,
      'localPosition':vec(getattr(t,'m_LocalPosition',None),('x','y','z')),
      'localRotation':vec(getattr(t,'m_LocalRotation',None),('x','y','z','w')),
      'localScale':vec(getattr(t,'m_LocalScale',None),('x','y','z')),
    }

out=[]
for h in heroes:
    hid=int(h['heroId']); name=h.get('name') or str(hid); hsrc=src/str(hid); hout=outroot/str(hid)
    (hout/'meshes').mkdir(parents=True,exist_ok=True)
    (hout/'textures').mkdir(parents=True,exist_ok=True)
    bundle_files=sorted(hsrc.glob('*.bundle'))
    row={
      'heroId':hid,'name':name,'queueModelPath':h.get('queueModelPath'),
      'bundleCount':len(bundle_files),'parseOk':False,'rootName':None,
      'meshes':[],'textures':[],'materials':[],'renderers':[],'skinnedRenderers':[],
      'transforms':[],'clips':[],'animators':[],'errors':[]
    }
    if not bundle_files:
        row['errors'].append('no exact bundle files');out.append(row);continue
    try:
        UnityPy.config.FALLBACK_UNITY_VERSION=unity_version
        env=UnityPy.load(*[str(p) for p in bundle_files])
        row['parseOk']=True
        # Deduplicate by object path id when available.
        seen=set(); objects=[]
        for reader in env.objects:
            key=(type_name(reader),getattr(reader,'path_id',None),getattr(reader,'assets_file',None) and str(getattr(reader.assets_file,'name','')))
            if key in seen:continue
            seen.add(key);objects.append(reader)

        # Root expectation comes straight from queue_model_path.
        q=Path(str(h.get('queueModelPath') or '')).stem
        names=[]
        for r in objects:
            if type_name(r)!='GameObject':continue
            d=read_obj(r)
            if d is not None:names.append(obj_name(d))
        if q in names:row['rootName']=q
        elif names:
            qflat=re.sub(r'[^a-z0-9]','',q.lower())
            cand=sorted(names,key=lambda x:(re.sub(r'[^a-z0-9]','',x.lower())==qflat, qflat in re.sub(r'[^a-z0-9]','',x.lower()),len(x)),reverse=True)
            row['rootName']=cand[0]

        mesh_i=0; tex_i=0
        for r in objects:
            typ=type_name(r)
            if typ not in {'Mesh','Texture2D','Material','Transform','MeshFilter','MeshRenderer','SkinnedMeshRenderer','Renderer','AnimationClip','Animator'}:continue
            d=read_obj(r)
            if d is None:continue
            nm=obj_name(d,typ)
            if typ=='Mesh':
                mesh_i+=1
                txt,err=mesh_export_text(d)
                item={'name':nm,'exported':False,'error':err}
                if txt:
                    fn=f'{mesh_i:03d}_{safe(nm,"mesh")}.obj'; p=hout/'meshes'/fn
                    p.write_text(txt,encoding='utf-8')
                    item.update({'exported':True,'file':'meshes/'+fn,'bytes':p.stat().st_size,'sha256':sha256_file(p),'error':None})
                row['meshes'].append(item)
            elif typ=='Texture2D':
                tex_i+=1;item={'name':nm,'exported':False}
                try:
                    img=d.image
                    fn=f'{tex_i:03d}_{safe(nm,"texture")}.png';p=hout/'textures'/fn
                    img.save(p,'PNG')
                    item.update({'exported':True,'file':'textures/'+fn,'width':getattr(img,'width',None),'height':getattr(img,'height',None),'bytes':p.stat().st_size,'sha256':sha256_file(p)})
                except Exception as e:item['error']=repr(e)
                row['textures'].append(item)
            elif typ=='Material':row['materials'].append(material_dict(d))
            elif typ=='Transform':row['transforms'].append(transform_row(d))
            elif typ in ('MeshRenderer','Renderer'):
                go=ptr_name(getattr(d,'m_GameObject',None)); mats=[]
                for p in getattr(d,'m_Materials',[]) or []:mats.append(ptr_name(p))
                row['renderers'].append({'gameObject':go,'materials':[x for x in mats if x]})
            elif typ=='SkinnedMeshRenderer':
                go=ptr_name(getattr(d,'m_GameObject',None)); mesh=ptr_name(getattr(d,'m_Mesh',None)); mats=[];bones=[]
                for p in getattr(d,'m_Materials',[]) or []:mats.append(ptr_name(p))
                for p in getattr(d,'m_Bones',[]) or []:bones.append(ptr_name(p))
                row['skinnedRenderers'].append({'gameObject':go,'mesh':mesh,'materials':[x for x in mats if x],'bones':[x for x in bones if x],'rootBone':ptr_name(getattr(d,'m_RootBone',None))})
            elif typ=='AnimationClip':
                row['clips'].append({'name':nm,'legacy':bool(getattr(d,'m_Legacy',False)),'wrapMode':getattr(d,'m_WrapMode',None),'sampleRate':getattr(d,'m_SampleRate',None)})
            elif typ=='Animator':row['animators'].append({'gameObject':ptr_name(getattr(d,'m_GameObject',None)),'controller':ptr_name(getattr(d,'m_Controller',None))})

        # Hero-local metadata consumed later by the renderer build phase.
        local={k:v for k,v in row.items() if k!='errors'}
        (hout/'scene.json').write_text(json.dumps(local,ensure_ascii=False,indent=2),encoding='utf-8')
    except Exception as e:
        row['errors'].append(repr(e));row['errors'].append(traceback.format_exc()[-8000:])
    out.append(row)
    print('PHASE49_HERO',hid,name,
          f"parse={row['parseOk']}",
          f"meshObj={sum(x.get('exported',False) for x in row['meshes'])}/{len(row['meshes'])}",
          f"texPng={sum(x.get('exported',False) for x in row['textures'])}/{len(row['textures'])}",
          f"clips={len(row['clips'])}",flush=True)

summary={
 'format':'WFGG_LASTWAR_CURRENT15_WEB_EXPORT_V1','networkUsed':False,'unityFallback':unity_version,
 'heroCount':15,
 'parseOkCount':sum(x['parseOk'] for x in out),
 'heroesWithObj':sum(any(m.get('exported') for m in x['meshes']) for x in out),
 'heroesWithPng':sum(any(t.get('exported') for t in x['textures']) for x in out),
 'heroesWithClips':sum(bool(x['clips']) for x in out),
 'meshObjectCount':sum(len(x['meshes']) for x in out),
 'meshObjExportCount':sum(sum(m.get('exported',False) for m in x['meshes']) for x in out),
 'textureObjectCount':sum(len(x['textures']) for x in out),
 'texturePngExportCount':sum(sum(t.get('exported',False) for t in x['textures']) for x in out),
 'heroes':out,
 'guardrails':{
   'exactPhase47BundlesOnly':True,'queueModelPathAuthoritative':True,
   'noSimilarityFallback':True,'noGeneratedGeometry':True,'noLastWarNetwork':True,
   'exportedRenderAssetsCommitted':False
 }
}
manifestp.write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')

lines=[
 'WfGg Last War LAB — PHASE 49 CURRENT15 WEB EXPORT',
 'OFFLINE ONLY · exact Phase47 bundles · no generated geometry',
 f"heroes=15 parseOk={summary['parseOkCount']}/15 heroesWithObj={summary['heroesWithObj']}/15 heroesWithPng={summary['heroesWithPng']}/15 heroesWithClips={summary['heroesWithClips']}/15",
 f"meshObjects={summary['meshObjectCount']} objExported={summary['meshObjExportCount']} textureObjects={summary['textureObjectCount']} pngExported={summary['texturePngExportCount']}",
 ''
]
for h in out:
    lines.append(f"HERO {h['heroId']} {h['name']} parse={h['parseOk']} root={h['rootName']} obj={sum(x.get('exported',False) for x in h['meshes'])}/{len(h['meshes'])} png={sum(x.get('exported',False) for x in h['textures'])}/{len(h['textures'])} transforms={len(h['transforms'])} renderers={len(h['renderers'])} skinned={len(h['skinnedRenderers'])} clips={len(h['clips'])}")
    if h['clips']:lines.append('  clips='+', '.join(x['name'] for x in h['clips']))
    for m in h['meshes']:
        if not m.get('exported'):lines.append(f"  MESH_EXPORT_FAIL {m.get('name')} :: {m.get('error')}")
    for t in h['textures']:
        if not t.get('exported'):lines.append(f"  TEXTURE_EXPORT_FAIL {t.get('name')} :: {t.get('error')}")
    for e in h['errors']:lines.append('  ERROR '+str(e).replace('\n',' ')[:1800])
    lines.append('')
lines += [
 'GUARDRAILS','  exact_phase47_bundles_only=true','  queue_model_path_authoritative=true',
 '  no_similarity_fallback=true','  no_generated_geometry=true','  no_lastwar_network=true',
 '  exported_render_assets_not_committed=true'
]
reportp.write_text('\n'.join(lines)+'\n',encoding='utf-8')

print('PHASE49_OK',
      f"parse={summary['parseOkCount']}/15",
      f"obj={summary['heroesWithObj']}/15",
      f"png={summary['heroesWithPng']}/15",
      f"clips={summary['heroesWithClips']}/15",
      f"meshes={summary['meshObjExportCount']}/{summary['meshObjectCount']}",
      f"textures={summary['texturePngExportCount']}/{summary['textureObjectCount']}")
PYEOF

python "$PY" "$P47" "$SRC" "$OUT" "$MANIFEST" "$REPORT" "$UNITY_VERSION"
rm -f "$PY"

# Render exports remain local; only script + compact manifest go to Git.
mkdir -p "$OUT"
cat > "$OUT/.gitignore" <<'EOF'
*
!.gitignore
EOF

git add -f scripts/lastwar-phase49-export-current15-web-geometry.sh frontend/lab/master-assets-v2/meta/current15-web-export-v1.json "$OUT/.gitignore"
if ! git diff --cached --quiet -- scripts/lastwar-phase49-export-current15-web-geometry.sh frontend/lab/master-assets-v2/meta/current15-web-export-v1.json "$OUT/.gitignore"; then
  git commit -m "lab: export exact current 15 web geometry manifest"
fi
git push origin "$BRANCH"

echo "=== PHASE 49 TERMINEE ==="
echo "Exports locaux: frontend/lab/local_assets/lastwar-current15-web-v1"
echo "Manifest: frontend/lab/master-assets-v2/meta/current15-web-export-v1.json"
echo "Rapport: $REPORT"
echo "Ne lance pas encore la page Escouades."
echo "main non modifiée."
