#!/data/data/com.termux/files/usr/bin/bash
set -Eeuo pipefail

# WfGg Last War LAB — PHASE 50
# EXPORT EXACT CURRENT-15 RIG / SKINNING / IDLE CLIP STRUCTURE
# CODE ONLY · OFFLINE ONLY · exact Phase47 bundles only.
#
# Goals:
#  - keep the exact Unity transform hierarchy and bone references
#  - export Mesh bind poses + vertex bone indices/weights through MeshHandler
#  - export the complete serialized TypeTree for idle/show_idle AnimationClips
#  - do NOT guess animation curves and do NOT generate any geometry
#
# The heavy rig/clip dumps remain local and are NOT committed to Git.

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BRANCH="portal-auth-lastwar-lab-v1"
UNITY_VERSION="2019.4.41f1"
P47="$ROOT/frontend/lab/master-assets-v2/meta/current15-exact-bundle-stage.json"
SRC="$ROOT/frontend/lab/local_assets/lastwar-current15-exact-v1"
OUT="$ROOT/frontend/lab/local_assets/lastwar-current15-rig-idle-v1"
MANIFEST="$ROOT/frontend/lab/master-assets-v2/meta/current15-rig-idle-structure-v1.json"
REPORT="$HOME/storage/downloads/WFGG_LASTWAR_PHASE50_CURRENT15_RIG_IDLE_STRUCTURE.txt"
PY="${TMPDIR:-$HOME/.cache}/wfgg-phase50-rig-idle.py"

fail(){ printf 'ERREUR: %s\n' "$*" >&2; exit 1; }
cd "$ROOT"
[[ "$(git branch --show-current)" == "$BRANCH" ]] || fail "branche active incorrecte"
[[ -s "$P47" ]] || fail "Phase47 absente: $P47"
[[ -d "$SRC" ]] || fail "Assets locaux Phase47 absents: $SRC"
command -v python >/dev/null 2>&1 || fail "python absent"

python - <<'PY' >/dev/null 2>&1 || fail "UnityPy absent"
import UnityPy
from UnityPy.helpers.MeshHelper import MeshHandler
PY

rm -rf "$OUT"
mkdir -p "$OUT" "$(dirname "$MANIFEST")" "$(dirname "$PY")"

cat > "$PY" <<'PYEOF'
from pathlib import Path
from collections import defaultdict
import base64, gzip, hashlib, json, math, os, re, sys, traceback

p47p=Path(sys.argv[1]); src=Path(sys.argv[2]); outroot=Path(sys.argv[3]); manifestp=Path(sys.argv[4]); reportp=Path(sys.argv[5]); unity_version=sys.argv[6]

data=json.loads(p47p.read_text(encoding='utf-8'))
heroes=data.get('heroes') or []
if len(heroes)!=15:
    raise SystemExit(f'expected 15 heroes, got {len(heroes)}')

try:
    import UnityPy
    from UnityPy.helpers.MeshHelper import MeshHandler
except Exception as e:
    raise SystemExit(f'UnityPy core import failed: {e!r}')
UnityPy.config.FALLBACK_UNITY_VERSION=unity_version

SAFE=re.compile(r'[^A-Za-z0-9._-]+')
def safe(s,fallback='asset'):
    x=SAFE.sub('_',str(s or '')).strip('._')
    return x[:180] or fallback

def type_name(r):
    try:return r.type.name
    except Exception:return str(getattr(r,'type',''))

def read_obj(r):
    try:return r.read()
    except Exception:
        try:return r.parse_as_object()
        except Exception:return None

def path_id(x):
    if x is None:return None
    for y in (x,getattr(x,'reader',None)):
        if y is None:continue
        for a in ('path_id','m_PathID'):
            try:
                v=getattr(y,a,None)
                if v is not None:return int(v)
            except Exception:pass
    try:
        v=getattr(x,'path_id',None)
        return int(v) if v is not None else None
    except Exception:return None

def ptr_obj(ptr):
    if ptr is None:return None
    for fn in ('read','deref_parse_as_object','parse_as_object'):
        try:
            f=getattr(ptr,fn,None)
            if callable(f):return f()
        except Exception:pass
    return None

def obj_name(d,fallback=''):
    return str(getattr(d,'m_Name','') or getattr(d,'name','') or fallback or '') if d is not None else str(fallback or '')

def ptr_name(ptr):
    try:return obj_name(ptr_obj(ptr))
    except Exception:return ''

def vec(v,names):
    if v is None:return None
    try:return [float(getattr(v,n)) for n in names]
    except Exception:return None

def matrix16(m):
    if m is None:return None
    # UnityPy Matrix4x4f uses e00..e33 in current generated classes.
    for prefix in ('e','m_'):
        vals=[];ok=True
        for r in range(4):
            for c in range(4):
                attr=f'{prefix}{r}{c}'
                try:vals.append(float(getattr(m,attr)))
                except Exception:ok=False;break
            if not ok:break
        if ok:return vals
    # Fallback for list-like matrix representations.
    try:
        flat=[]
        for x in m:
            if isinstance(x,(list,tuple)):flat.extend(float(y) for y in x)
            else:flat.append(float(x))
        if len(flat)==16:return flat
    except Exception:pass
    return None

def jsonable(x,depth=0):
    if depth>60:return {'__truncated_depth__':True}
    if x is None or isinstance(x,(bool,int,float,str)):return x
    if isinstance(x,(bytes,bytearray,memoryview)):
        b=bytes(x)
        return {'__bytes_b64__':base64.b64encode(b).decode('ascii'),'length':len(b)}
    if isinstance(x,dict):return {str(k):jsonable(v,depth+1) for k,v in x.items()}
    if isinstance(x,(list,tuple)):return [jsonable(v,depth+1) for v in x]
    # TypeTree dictionaries should cover clips; keep a safe generic fallback.
    try:
        d=vars(x)
        return {'__class__':x.__class__.__name__,**{str(k):jsonable(v,depth+1) for k,v in d.items() if not str(k).startswith('_')}}
    except Exception:return str(x)

def write_gz_json(path,obj):
    path.parent.mkdir(parents=True,exist_ok=True)
    raw=json.dumps(obj,ensure_ascii=False,separators=(',',':')).encode('utf-8')
    with gzip.open(path,'wb',compresslevel=6) as f:f.write(raw)
    return len(raw),path.stat().st_size,hashlib.sha256(path.read_bytes()).hexdigest()

def tree_signatures(x,prefix='',depth=0,out=None):
    if out is None:out=[]
    if depth>10:return out
    if isinstance(x,dict):
        for k,v in x.items():
            p=(prefix+'.'+str(k)).strip('.')
            if isinstance(v,dict):
                out.append({'path':p,'type':'dict','count':len(v)})
                tree_signatures(v,p,depth+1,out)
            elif isinstance(v,(list,tuple)):
                out.append({'path':p,'type':'array','count':len(v)})
                # recurse only through first object-like member to reveal schema
                if v and isinstance(v[0],(dict,list,tuple)):tree_signatures(v[0],p+'[0]',depth+1,out)
            elif isinstance(v,(bytes,bytearray,memoryview)):
                out.append({'path':p,'type':'bytes','count':len(v)})
            else:
                val=v if isinstance(v,(bool,int,float,str)) else None
                out.append({'path':p,'type':type(v).__name__,'value':val})
    elif isinstance(x,(list,tuple)):
        out.append({'path':prefix,'type':'array','count':len(x)})
    return out

def interesting_signatures(sigs):
    tokens=('muscle','streamed','dense','constant','binding','curve','sample','clip','rotation','position','scale','float','pthash','path')
    out=[]
    for s in sigs:
        p=s.get('path','').lower()
        if any(t in p for t in tokens):out.append(s)
    return out[:180]

def clip_kind(name):
    n=str(name or '').lower().replace(' ','')
    if 'show_idle' in n or 'showidle' in n:return 'presentationIdle'
    if n.endswith('_idle') or n.endswith('idle') or '_idle_' in n:return 'idle'
    return None

def mesh_skin(mesh):
    mh=MeshHandler(mesh);mh.process()
    bi=mh.m_BoneIndices or []
    bw=mh.m_BoneWeights or []
    bind=getattr(mesh,'m_BindPose',None) or []
    bind16=[m for m in (matrix16(x) for x in bind) if m is not None]
    return {
      'vertexCount':int(mh.m_VertexCount or len(mh.m_Vertices or [])),
      'boneIndexCount':len(bi),'boneWeightCount':len(bw),'bindPoseCount':len(bind16),
      'boneIndices':[[int(v) for v in x] for x in bi],
      'boneWeights':[[float(v) for v in x] for x in bw],
      'bindPoses':bind16,
    }

rows=[]
for idx,h in enumerate(heroes,1):
    hid=int(h['heroId']);name=h.get('name') or str(hid);hsrc=src/str(hid);hout=outroot/str(hid)
    hout.mkdir(parents=True,exist_ok=True)
    files=sorted(hsrc.glob('*.bundle'))
    row={
      'heroId':hid,'name':name,'queueModelPath':h.get('queueModelPath'),'bundleCount':len(files),
      'parseOk':False,'transformCount':0,'skinnedRendererCount':0,'referencedSkinMeshCount':0,
      'skinMeshReadyCount':0,'boneReferenceCount':0,'rigReady':False,
      'animationClipCount':0,'presentationIdleCandidates':[],'idleCandidates':[],
      'selectedClipNames':[],'selectedClipTreeCount':0,'animationStructureReady':False,
      'clipStructures':[],'errors':[]
    }
    print(f'PHASE50_HERO {idx}/15 id={hid} name={name}',flush=True)
    if not files:
        row['errors'].append('no exact Phase47 bundles');rows.append(row);continue
    try:
        UnityPy.config.FALLBACK_UNITY_VERSION=unity_version
        env=UnityPy.load(*[str(p) for p in files])
        row['parseOk']=True
        readers=list(env.objects)

        # Build transform table by path id and GameObject name.
        transforms=[]
        for r in readers:
            if type_name(r) not in ('Transform','RectTransform'):continue
            d=read_obj(r)
            if d is None:continue
            transforms.append({
              'pathId':path_id(r),'gameObject':ptr_name(getattr(d,'m_GameObject',None)),
              'parentPathId':path_id(getattr(d,'m_Father',None)),
              'childrenPathIds':[x for x in (path_id(p) for p in (getattr(d,'m_Children',[]) or [])) if x is not None],
              'localPosition':vec(getattr(d,'m_LocalPosition',None),('x','y','z')),
              'localRotation':vec(getattr(d,'m_LocalRotation',None),('x','y','z','w')),
              'localScale':vec(getattr(d,'m_LocalScale',None),('x','y','z')),
            })
        row['transformCount']=len(transforms)

        # Skinned renderer -> exact bone ordering and referenced Mesh.
        skinned=[];referenced_mesh_ids=set();bone_refs=set()
        for r in readers:
            if type_name(r)!='SkinnedMeshRenderer':continue
            d=read_obj(r)
            if d is None:continue
            meshptr=getattr(d,'m_Mesh',None);mpid=path_id(meshptr)
            if mpid is not None:referenced_mesh_ids.add(mpid)
            bones=[]
            for p in (getattr(d,'m_Bones',[]) or []):
                pid=path_id(p);nm=ptr_name(p)
                if pid is not None:bone_refs.add(pid)
                bones.append({'pathId':pid,'name':nm})
            rootp=getattr(d,'m_RootBone',None);rootpid=path_id(rootp)
            if rootpid is not None:bone_refs.add(rootpid)
            skinned.append({
              'pathId':path_id(r),'gameObject':ptr_name(getattr(d,'m_GameObject',None)),
              'meshPathId':mpid,'mesh':ptr_name(meshptr),'rootBone':{'pathId':rootpid,'name':ptr_name(rootp)},
              'bones':bones,'materials':[ptr_name(p) for p in (getattr(d,'m_Materials',[]) or [])],
            })
        row['skinnedRendererCount']=len(skinned);row['referencedSkinMeshCount']=len(referenced_mesh_ids);row['boneReferenceCount']=len(bone_refs)

        # Export skinning arrays only for meshes actually referenced by a SkinnedMeshRenderer.
        skin_meshes=[]
        for r in readers:
            if type_name(r)!='Mesh' or path_id(r) not in referenced_mesh_ids:continue
            d=read_obj(r)
            if d is None:continue
            item={'pathId':path_id(r),'name':obj_name(d,'Mesh'),'ready':False}
            try:
                skin=mesh_skin(d)
                fn=f"mesh_{path_id(r)}_{safe(item['name'],'mesh')}_skin.json.gz"
                rawb,gzb,sha=write_gz_json(hout/fn,skin)
                item.update({
                  'ready':bool(skin['vertexCount'] and skin['boneIndexCount'] and skin['boneWeightCount']),
                  'vertexCount':skin['vertexCount'],'boneIndexCount':skin['boneIndexCount'],
                  'boneWeightCount':skin['boneWeightCount'],'bindPoseCount':skin['bindPoseCount'],
                  'file':fn,'jsonBytes':rawb,'gzipBytes':gzb,'sha256':sha,
                })
            except Exception as e:item['error']=repr(e)
            skin_meshes.append(item)
        row['skinMeshReadyCount']=sum(x.get('ready',False) for x in skin_meshes)
        row['rigReady']=bool(skinned and referenced_mesh_ids and row['skinMeshReadyCount']>0 and bone_refs)

        # Save exact transform + renderer rig topology locally.
        rig_obj={'heroId':hid,'name':name,'queueModelPath':h.get('queueModelPath'),'transforms':transforms,'skinnedRenderers':skinned,'skinMeshes':skin_meshes}
        rawb,gzb,sha=write_gz_json(hout/'rig.json.gz',rig_obj)
        row['rigFile']={'file':'rig.json.gz','jsonBytes':rawb,'gzipBytes':gzb,'sha256':sha}

        # AnimationClip readers must be retained so their TypeTrees can be dumped exactly.
        clips=[]
        for r in readers:
            if type_name(r)!='AnimationClip':continue
            d=read_obj(r)
            if d is None:continue
            nm=obj_name(d,'AnimationClip');kind=clip_kind(nm)
            clips.append({'reader':r,'object':d,'name':nm,'kind':kind,'pathId':path_id(r)})
        row['animationClipCount']=len(clips)
        row['presentationIdleCandidates']=[c['name'] for c in clips if c['kind']=='presentationIdle']
        row['idleCandidates']=[c['name'] for c in clips if c['kind']=='idle']

        # Export both presentation-idle and ordinary idle when available. This keeps
        # the distinction explicit; Phase50 does not claim which one the Formation UI uses.
        selected=[]
        for kind in ('presentationIdle','idle'):
            cand=[c for c in clips if c['kind']==kind]
            if cand:selected.append(cand[0])
        if not selected:
            # Never substitute another semantic animation; simply report none.
            selected=[]
        # Dedupe by path id/name.
        ded=[];seen=set()
        for c in selected:
            k=(c['pathId'],c['name'])
            if k in seen:continue
            seen.add(k);ded.append(c)
        selected=ded
        row['selectedClipNames']=[c['name'] for c in selected]

        for c in selected:
            cr=c['reader'];nm=c['name'];ci={'name':nm,'kind':c['kind'],'pathId':c['pathId'],'typetreeOk':False}
            try:
                tree=cr.read_typetree(wrap=False,check_read=False)
                sigs=tree_signatures(tree)
                jtree=jsonable(tree)
                fn=f"clip_{safe(nm,'idle')}_{c['pathId']}.json.gz"
                rawb,gzb,sha=write_gz_json(hout/fn,jtree)
                ci.update({
                  'typetreeOk':True,'objectBytes':int(getattr(cr,'byte_size',0) or 0),
                  'file':fn,'jsonBytes':rawb,'gzipBytes':gzb,'sha256':sha,
                  'topLevelKeys':list(tree.keys()) if isinstance(tree,dict) else [],
                  'signatureCount':len(sigs),'interestingSignatures':interesting_signatures(sigs),
                })
            except Exception as e:
                ci['error']=repr(e)
            row['clipStructures'].append(ci)
        row['selectedClipTreeCount']=sum(x.get('typetreeOk',False) for x in row['clipStructures'])
        row['animationStructureReady']=bool(selected and row['selectedClipTreeCount']==len(selected))

    except Exception as e:
        row['errors'].append(repr(e));row['errors'].append(traceback.format_exc()[-7000:])
    rows.append(row)

summary={
 'format':'WFGG_LASTWAR_CURRENT15_RIG_IDLE_STRUCTURE_V1','networkUsed':False,'unityFallback':unity_version,
 'heroCount':15,'parseOkCount':sum(x['parseOk'] for x in rows),'rigReadyCount':sum(x['rigReady'] for x in rows),
 'heroesWithPresentationIdle':sum(bool(x['presentationIdleCandidates']) for x in rows),
 'heroesWithIdle':sum(bool(x['idleCandidates']) for x in rows),
 'animationStructureReadyCount':sum(x['animationStructureReady'] for x in rows),
 'selectedClipTreeHeroCount':sum(x['selectedClipTreeCount']>0 for x in rows),
 'skinMeshCount':sum(x['referencedSkinMeshCount'] for x in rows),
 'skinMeshReadyCount':sum(x['skinMeshReadyCount'] for x in rows),
 'heroes':rows,
 'guardrails':{
   'exactPhase47BundlesOnly':True,'queueModelPathAuthoritative':True,
   'noSimilarityFallback':True,'noGeneratedGeometry':True,'noLastWarNetwork':True,
   'presentationIdleVsIdleNotAssumed':True,'localRigAndClipDumpsCommitted':False
 }
}
manifestp.write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')

lines=[
 'WfGg Last War LAB — PHASE 50 CURRENT15 RIG + IDLE STRUCTURE',
 'OFFLINE ONLY · exact Phase47 bundles · no generated geometry · no animation substitution',
 f"heroes=15 parseOk={summary['parseOkCount']}/15 rigReady={summary['rigReadyCount']}/15 animationStructureReady={summary['animationStructureReadyCount']}/15",
 f"presentationIdle={summary['heroesWithPresentationIdle']}/15 ordinaryIdle={summary['heroesWithIdle']}/15 selectedClipTrees={summary['selectedClipTreeHeroCount']}/15",
 f"skinMeshes={summary['skinMeshReadyCount']}/{summary['skinMeshCount']}",
 ''
]
for h in rows:
    lines.append(
      f"HERO {h['heroId']} {h['name']} parse={h['parseOk']} rig={h['rigReady']} "
      f"transforms={h['transformCount']} skinned={h['skinnedRendererCount']} skinMeshes={h['skinMeshReadyCount']}/{h['referencedSkinMeshCount']} bones={h['boneReferenceCount']} "
      f"clips={h['animationClipCount']} clipTrees={h['selectedClipTreeCount']} animStruct={h['animationStructureReady']}"
    )
    lines.append('  presentationIdle='+(', '.join(h['presentationIdleCandidates']) if h['presentationIdleCandidates'] else '-'))
    lines.append('  ordinaryIdle='+(', '.join(h['idleCandidates']) if h['idleCandidates'] else '-'))
    for c in h['clipStructures']:
        lines.append(f"  CLIP {c['kind']} {c['name']} typetree={c['typetreeOk']} objectBytes={c.get('objectBytes')} gzipBytes={c.get('gzipBytes')} keys={','.join(c.get('topLevelKeys') or [])}")
        for s in (c.get('interestingSignatures') or [])[:40]:
            extra=(' count='+str(s.get('count'))) if 'count' in s else ((' value='+repr(s.get('value'))) if 'value' in s else '')
            lines.append(f"    {s.get('path')} [{s.get('type')}]"+extra)
        if c.get('error'):lines.append('    ERROR '+c['error'])
    for e in h['errors']:lines.append('  ERROR '+str(e).replace('\n',' ')[:1600])
    lines.append('')
lines += [
 'GUARDRAILS','  exact_phase47_bundles_only=true','  queue_model_path_authoritative=true',
 '  no_similarity_fallback=true','  no_generated_geometry=true','  no_lastwar_network=true',
 '  presentation_idle_vs_idle_not_assumed=true','  local_rig_and_clip_dumps_not_committed=true'
]
reportp.write_text('\n'.join(lines)+'\n',encoding='utf-8')

print('PHASE50_OK',
      f"parse={summary['parseOkCount']}/15",
      f"rig={summary['rigReadyCount']}/15",
      f"animStruct={summary['animationStructureReadyCount']}/15",
      f"presentationIdle={summary['heroesWithPresentationIdle']}/15",
      f"ordinaryIdle={summary['heroesWithIdle']}/15",
      f"skinMeshes={summary['skinMeshReadyCount']}/{summary['skinMeshCount']}")
PYEOF

python "$PY" "$P47" "$SRC" "$OUT" "$MANIFEST" "$REPORT" "$UNITY_VERSION"
rm -f "$PY"

# Only the compact manifest + script belong in Git. Exact rig/clip dumps remain local.
git add scripts/lastwar-phase50-export-current15-rig-idle-structure.sh frontend/lab/master-assets-v2/meta/current15-rig-idle-structure-v1.json
if ! git diff --cached --quiet -- scripts/lastwar-phase50-export-current15-rig-idle-structure.sh frontend/lab/master-assets-v2/meta/current15-rig-idle-structure-v1.json; then
  git commit -m "lab: map exact current15 rig and idle clip structures"
fi
git push origin "$BRANCH"

echo "=== PHASE 50 TERMINEE ==="
echo "Rig/clips locaux: frontend/lab/local_assets/lastwar-current15-rig-idle-v1"
echo "Manifest: frontend/lab/master-assets-v2/meta/current15-rig-idle-structure-v1.json"
echo "Rapport: $REPORT"
echo "Ne lance pas encore la page Escouades."
echo "main non modifiée."
