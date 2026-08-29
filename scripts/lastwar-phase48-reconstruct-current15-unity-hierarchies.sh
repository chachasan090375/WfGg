#!/data/data/com.termux/files/usr/bin/bash
set -Eeuo pipefail

# WfGg Last War LAB — PHASE 48
# RECONSTRUCT EXACT UNITY HIERARCHIES FOR THE 15 CURRENT FORMATION UNITS
# CODE ONLY · OFFLINE ONLY · no root · no run-as · no Last War network.
#
# Input is Phase 47 only: exact queue_model_path bundles plus exact same-model
# dependencies. No similarity matching, no generic vehicle, no generated geometry.

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BRANCH="portal-auth-lastwar-lab-v1"
UNITY_VERSION="2019.4.41f1"
P47="$ROOT/frontend/lab/master-assets-v2/meta/current15-exact-bundle-stage.json"
LOCAL="$ROOT/frontend/lab/local_assets/lastwar-current15-exact-v1"
OUT="$ROOT/frontend/lab/master-assets-v2/meta/current15-unity-hierarchy-v1.json"
REPORT="$HOME/storage/downloads/WFGG_LASTWAR_PHASE48_CURRENT15_UNITY_HIERARCHIES.txt"
PY="${TMPDIR:-$HOME/.cache}/wfgg-phase48-current15-hierarchies.py"

fail(){ printf 'ERREUR: %s\n' "$*" >&2; exit 1; }
cd "$ROOT"
[[ "$(git branch --show-current)" == "$BRANCH" ]] || fail "branche active incorrecte"
[[ -s "$P47" ]] || fail "Phase47 absente: $P47"
[[ -d "$LOCAL" ]] || fail "bundles locaux Phase47 absents: $LOCAL"
command -v python >/dev/null 2>&1 || fail "python absent"

python - <<'PY' >/dev/null 2>&1 || fail "UnityPy absent — relancer une phase précédente ayant installé UnityPy"
import UnityPy
PY

mkdir -p "$(dirname "$OUT")" "$(dirname "$PY")"

cat > "$PY" <<'PYEOF'
from pathlib import Path
from collections import defaultdict
import json, math, os, re, sys, traceback

p47p=Path(sys.argv[1]); localroot=Path(sys.argv[2]); outp=Path(sys.argv[3]); reportp=Path(sys.argv[4]); UNITY_VERSION=sys.argv[5]

try:
    import UnityPy
except Exception as e:
    raise SystemExit(f'UnityPy absent: {e}')

UnityPy.config.FALLBACK_UNITY_VERSION=UNITY_VERSION
src=json.loads(p47p.read_text(encoding='utf-8'))
heroes=src.get('heroes') or []
if len(heroes)!=15:
    raise SystemExit(f'expected 15 Phase47 heroes, got {len(heroes)}')

KEEP_TYPES={
 'GameObject','Transform','RectTransform','Mesh','MeshFilter','MeshRenderer',
 'SkinnedMeshRenderer','Renderer','Animator','Animation','AnimationClip',
 'AnimatorController','RuntimeAnimatorController','Material','Texture2D','Shader'
}

def norm(s): return re.sub(r'[^a-z0-9]+','_',str(s or '').lower()).strip('_')
def unique(seq):
    out=[];seen=set()
    for x in seq:
        k=json.dumps(x,sort_keys=True,ensure_ascii=False) if isinstance(x,(dict,list)) else str(x)
        if k in seen:continue
        seen.add(k);out.append(x)
    return out

def read_obj(reader):
    try:return reader.read()
    except Exception:
        try:return reader.parse_as_object()
        except Exception:return None

def ptr_reader(ptr):
    if ptr is None:return None
    for attr in ('get_obj','get_object'):
        try:
            fn=getattr(ptr,attr,None)
            if fn:
                x=fn()
                if x:return x
        except Exception:pass
    try:
        if hasattr(ptr,'path_id') and getattr(ptr,'path_id',0):
            return ptr
    except Exception:pass
    return None

def deref(ptr):
    if ptr is None:return None
    for fnname in ('read','deref_parse_as_object','parse_as_object'):
        try:
            fn=getattr(ptr,fnname,None)
            if fn:return fn()
        except Exception:pass
    try:
        r=ptr_reader(ptr)
        if r is not None and hasattr(r,'read'):return r.read()
    except Exception:pass
    return None

def obj_name(data, fallback=''):
    if data is None:return str(fallback or '')
    return str(getattr(data,'m_Name','') or getattr(data,'name','') or fallback or '')

def ptr_name(ptr):
    try:return obj_name(deref(ptr))
    except Exception:return ''

def path_id_of(x):
    for obj in (x,ptr_reader(x)):
        if obj is None:continue
        for a in ('path_id','m_PathID'):
            try:
                v=getattr(obj,a,None)
                if v is not None:return int(v)
            except Exception:pass
    return None

def vec(v, fields):
    if v is None:return None
    out=[]
    for f in fields:
        try:out.append(float(getattr(v,f)))
        except Exception:return None
    return out

def safe_file(reader):
    for a in ('assets_file','assetsfile'):
        try:
            f=getattr(reader,a,None)
            if f is not None:
                return str(getattr(f,'name','') or getattr(f,'path','') or '')
        except Exception:pass
    return ''

def component_game_object(d):
    return ptr_name(getattr(d,'m_GameObject',None))

def material_names(d):
    vals=[]
    for p in getattr(d,'m_Materials',[]) or []:
        n=ptr_name(p)
        if n:vals.append(n)
    return unique(vals)

def mesh_meta(d):
    vc=None;sub=None;ib=None
    try:vc=int(getattr(getattr(d,'m_VertexData',None),'m_VertexCount',0) or 0)
    except Exception:pass
    try:sub=len(getattr(d,'m_SubMeshes',[]) or [])
    except Exception:pass
    try:ib=len(getattr(d,'m_IndexBuffer',b'') or b'')
    except Exception:pass
    return vc,sub,ib

def image_meta(d):
    w=h=fmt=None
    try:w=int(getattr(d,'m_Width',0) or 0);h=int(getattr(d,'m_Height',0) or 0)
    except Exception:pass
    try:fmt=str(getattr(d,'m_TextureFormat','') or '')
    except Exception:pass
    return w,h,fmt

def expected_root_name(queue_path):
    return Path(str(queue_path or '')).stem

def root_match_score(name,expected):
    n=norm(name);e=norm(expected)
    if not n or not e:return 0
    if n==e:return 10000
    if n.startswith(e) or e.startswith(n):return 7000
    # city/world/pve variants often wrap the exact model root.
    if e in n or n in e:return 5000
    return 0

outrows=[]
for idx,h in enumerate(heroes,1):
    hid=int(h['heroId']);name=h.get('name') or str(hid);hdir=localroot/str(hid)
    expected=expected_root_name(h.get('queueModelPath'))
    bundle_paths=[]
    for b in h.get('bundles') or []:
        logical=os.path.basename(str(b.get('logicalName') or ''))
        if not logical:continue
        p=hdir/logical
        if p.is_file():bundle_paths.append(p)
    bundle_paths=unique(bundle_paths)
    print(f'PHASE48_HERO {idx}/15 id={hid} name={name} bundles={len(bundle_paths)}',flush=True)

    row={
      'heroId':hid,'name':name,'queueModelPath':h.get('queueModelPath'),'expectedRoot':expected,
      'bundleCount':len(bundle_paths),'parseOk':False,'errors':[],
      'objectCounts':{},'gameObjects':[],'transforms':[],'meshFilters':[],
      'renderers':[],'skinnedRenderers':[],'meshes':[],'materials':[],
      'textures':[],'animators':[],'animationClips':[],'rootCandidates':[],
      'selectedRoot':None,'hierarchy':[],'sceneReady':False,'animationReady':False,
    }
    if not bundle_paths:
        row['errors'].append('no local exact bundles')
        outrows.append(row);continue

    try:
        UnityPy.config.FALLBACK_UNITY_VERSION=UNITY_VERSION
        # Load all exact files for this model in one environment so PPtrs can resolve
        # between prefab/mesh/material/texture/animation bundles.
        env=UnityPy.load(*[str(p) for p in bundle_paths])
        readers=list(env.objects)
        row['parseOk']=True
        counts=defaultdict(int)

        go_by_pid={}; transform_by_go={}; transform_pid_by_go={}; transform_parent={}; transform_children=defaultdict(list)
        transform_rows=[]

        # First pass: GameObjects and transforms build identity graph.
        for reader in readers:
            typ=getattr(reader.type,'name',str(reader.type));counts[typ]+=1
            if typ not in ('GameObject','Transform','RectTransform'):continue
            d=read_obj(reader)
            if d is None:continue
            if typ=='GameObject':
                pid=path_id_of(reader);nm=obj_name(d)
                if pid is not None:go_by_pid[pid]=nm
                row['gameObjects'].append({'pathId':pid,'name':nm,'file':safe_file(reader)})
            else:
                pid=path_id_of(reader);go_ptr=getattr(d,'m_GameObject',None);go_pid=path_id_of(go_ptr);go_name=ptr_name(go_ptr)
                father=getattr(d,'m_Father',None);father_pid=path_id_of(father)
                kids=[path_id_of(x) for x in (getattr(d,'m_Children',[]) or [])]
                kids=[x for x in kids if x is not None]
                tr={
                  'pathId':pid,'gameObjectPathId':go_pid,'gameObject':go_name,'parentTransformPathId':father_pid,
                  'childTransformPathIds':kids,
                  'localPosition':vec(getattr(d,'m_LocalPosition',None),('x','y','z')),
                  'localRotation':vec(getattr(d,'m_LocalRotation',None),('x','y','z','w')),
                  'localScale':vec(getattr(d,'m_LocalScale',None),('x','y','z')),
                  'file':safe_file(reader)
                }
                transform_rows.append(tr)
                if go_pid is not None:
                    transform_by_go[go_pid]=tr;transform_pid_by_go[go_pid]=pid
                if pid is not None:
                    transform_parent[pid]=father_pid
                    for k in kids:transform_children[pid].append(k)

        row['transforms']=transform_rows

        # Resolve GameObject names again after all objects were loaded.
        for tr in row['transforms']:
            if not tr['gameObject'] and tr['gameObjectPathId'] in go_by_pid:
                tr['gameObject']=go_by_pid[tr['gameObjectPathId']]

        # Component pass.
        for reader in readers:
            typ=getattr(reader.type,'name',str(reader.type))
            if typ not in KEEP_TYPES:continue
            if typ in ('GameObject','Transform','RectTransform'):continue
            d=read_obj(reader)
            if d is None:continue
            pid=path_id_of(reader);nm=obj_name(d,typ);file=safe_file(reader)
            if typ=='Mesh':
                vc,sub,ib=mesh_meta(d);row['meshes'].append({'pathId':pid,'name':nm,'vertexCount':vc,'subMeshCount':sub,'indexBufferBytes':ib,'file':file})
            elif typ=='MeshFilter':
                mesh=getattr(d,'m_Mesh',None);row['meshFilters'].append({'pathId':pid,'gameObject':component_game_object(d),'mesh':ptr_name(mesh),'meshPathId':path_id_of(mesh),'file':file})
            elif typ in ('MeshRenderer','Renderer'):
                row['renderers'].append({'pathId':pid,'gameObject':component_game_object(d),'materials':material_names(d),'enabled':bool(getattr(d,'m_Enabled',1)),'file':file})
            elif typ=='SkinnedMeshRenderer':
                mesh=getattr(d,'m_Mesh',None)
                row['skinnedRenderers'].append({'pathId':pid,'gameObject':component_game_object(d),'mesh':ptr_name(mesh),'meshPathId':path_id_of(mesh),'materials':material_names(d),'enabled':bool(getattr(d,'m_Enabled',1)),'file':file})
            elif typ=='Material':
                sh=getattr(d,'m_Shader',None);row['materials'].append({'pathId':pid,'name':nm,'shader':ptr_name(sh),'shaderPathId':path_id_of(sh),'file':file})
            elif typ=='Texture2D':
                w,hh,fmt=image_meta(d);row['textures'].append({'pathId':pid,'name':nm,'width':w,'height':hh,'format':fmt,'file':file})
            elif typ=='Animator':
                ctrl=getattr(d,'m_Controller',None);row['animators'].append({'pathId':pid,'gameObject':component_game_object(d),'controller':ptr_name(ctrl),'controllerPathId':path_id_of(ctrl),'file':file})
            elif typ=='AnimationClip':
                length=None;loop=None
                try:length=float(getattr(d,'m_MuscleClipSize',0) or getattr(d,'m_StopTime',0) or 0)
                except Exception:pass
                try:
                    settings=getattr(d,'m_AnimationClipSettings',None);loop=bool(getattr(settings,'m_LoopTime',False)) if settings is not None else None
                except Exception:pass
                row['animationClips'].append({'pathId':pid,'name':nm,'lengthHint':length,'loop':loop,'file':file})

        row['objectCounts']=dict(sorted(counts.items()))

        # Root candidates are top-level Transforms, scored against authoritative prefab stem.
        roots=[]
        transform_by_pid={t['pathId']:t for t in row['transforms'] if t['pathId'] is not None}
        for tr in row['transforms']:
            if tr['pathId'] is None:continue
            if tr['parentTransformPathId'] not in (None,0):continue
            sc=root_match_score(tr['gameObject'],expected)
            roots.append({'transformPathId':tr['pathId'],'gameObject':tr['gameObject'],'score':sc})
        roots.sort(key=lambda x:(x['score'],x['gameObject']==expected),reverse=True)
        row['rootCandidates']=roots[:30]
        if roots:
            row['selectedRoot']=roots[0]

        # Build compact hierarchy from selected root. Keep only transform topology and
        # authentic local transforms; renderer binding stays in separate arrays above.
        selected_pid=(row['selectedRoot'] or {}).get('transformPathId')
        if selected_pid is not None:
            seen=set()
            def walk(pid,depth=0):
                if pid in seen or depth>80:return
                seen.add(pid);tr=transform_by_pid.get(pid)
                if not tr:return
                row['hierarchy'].append({
                  'depth':depth,'transformPathId':pid,'gameObject':tr['gameObject'],
                  'localPosition':tr['localPosition'],'localRotation':tr['localRotation'],'localScale':tr['localScale']
                })
                for k in tr.get('childTransformPathIds') or []:walk(k,depth+1)
            walk(selected_pid)

        # Render readiness is based only on authentic Unity objects.
        renderer_count=len(row['renderers'])+len(row['skinnedRenderers'])
        mesh_links=sum(1 for x in row['meshFilters'] if x.get('mesh') or x.get('meshPathId')) + sum(1 for x in row['skinnedRenderers'] if x.get('mesh') or x.get('meshPathId'))
        selected_score=(row['selectedRoot'] or {}).get('score',0)
        row['sceneReady']=bool(row['parseOk'] and selected_pid is not None and renderer_count>0 and mesh_links>0 and len(row['meshes'])>0)
        # Exact name match is reported separately; it is useful for QA but not required
        # because some authoritative queue prefabs intentionally use city/world wrappers.
        row['authoritativeRootMatch']=bool(selected_score>=5000)
        row['animationReady']=bool(row['animationClips'])
        row['stats']={
          'gameObjects':len(row['gameObjects']),'transforms':len(row['transforms']),
          'hierarchyNodes':len(row['hierarchy']),'meshFilters':len(row['meshFilters']),
          'renderers':len(row['renderers']),'skinnedRenderers':len(row['skinnedRenderers']),
          'meshes':len(row['meshes']),'materials':len(row['materials']),
          'textures':len(row['textures']),'animators':len(row['animators']),
          'animationClips':len(row['animationClips'])
        }

    except Exception as e:
        row['errors'].append(repr(e))
        row['errors'].append(traceback.format_exc(limit=6))

    # Keep report deterministic / compact.
    for k in ('gameObjects','transforms','meshFilters','renderers','skinnedRenderers','meshes','materials','textures','animators','animationClips'):
        row[k]=unique(row[k])
    outrows.append(row)
    st=row.get('stats') or {}
    print(f"PHASE48_RESULT {hid} scene={row['sceneReady']} rootMatch={row.get('authoritativeRootMatch',False)} renderers={st.get('renderers',0)+st.get('skinnedRenderers',0)} meshes={st.get('meshes',0)} clips={st.get('animationClips',0)}",flush=True)

scene_ready=sum(bool(x.get('sceneReady')) for x in outrows)
root_match=sum(bool(x.get('authoritativeRootMatch')) for x in outrows)
anim_ready=sum(bool(x.get('animationReady')) for x in outrows)
parse_ok=sum(bool(x.get('parseOk')) for x in outrows)

out={
 'format':'WFGG_LASTWAR_CURRENT15_UNITY_HIERARCHY_V1','networkUsed':False,
 'unityVersionFallback':UNITY_VERSION,'basis':'Phase47 exact bundles only',
 'heroCount':15,'parseOkCount':parse_ok,'sceneReadyCount':scene_ready,
 'authoritativeRootMatchCount':root_match,'animationReadyCount':anim_ready,
 'heroes':outrows,
 'guardrails':{
   'queueModelPathAuthoritative':True,'exactPhase47BundlesOnly':True,
   'similarityFallback':False,'generatedGeometry':False,'lastWarNetwork':False,
   'rawBundlesCommitted':False
 }
}
outp.write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf-8')

lines=[
 'WfGg Last War LAB — PHASE 48 CURRENT15 UNITY HIERARCHIES',
 'OFFLINE ONLY · exact Phase47 bundles only · no generated geometry',
 f'heroes=15 parseOk={parse_ok}/15 sceneReady={scene_ready}/15 rootMatch={root_match}/15 animationReady={anim_ready}/15',
 f'unityFallback={UNITY_VERSION}',''
]
for h in outrows:
    s=h.get('stats') or {}
    lines.append(f"HERO {h['heroId']} {h['name']} parse={h['parseOk']} scene={h['sceneReady']} rootMatch={h.get('authoritativeRootMatch',False)} animation={h['animationReady']}")
    lines.append(f"  model={h['queueModelPath']}")
    sr=h.get('selectedRoot') or {}
    lines.append(f"  selectedRoot={sr.get('gameObject','-')} score={sr.get('score',0)} hierarchyNodes={s.get('hierarchyNodes',0)}")
    lines.append(f"  objects gameObjects={s.get('gameObjects',0)} transforms={s.get('transforms',0)} renderers={s.get('renderers',0)} skinned={s.get('skinnedRenderers',0)} meshes={s.get('meshes',0)} materials={s.get('materials',0)} textures={s.get('textures',0)} animators={s.get('animators',0)} clips={s.get('animationClips',0)}")
    if h.get('animationClips'):
        names=', '.join(x.get('name','') for x in h['animationClips'][:12])
        lines.append('  clips='+names)
    for e in h.get('errors') or []:lines.append('  ERROR '+str(e).replace('\n',' ')[:500])
    lines.append('')
lines+=['GUARDRAILS','  exact_phase47_bundles_only=true','  queue_model_path_authoritative=true','  no_similarity_fallback=true','  no_generated_geometry=true','  no_lastwar_network=true','  raw_bundles_not_committed=true']
reportp.write_text('\n'.join(lines)+'\n',encoding='utf-8')

print('PHASE48_OK',f'parse={parse_ok}/15',f'scene={scene_ready}/15',f'rootMatch={root_match}/15',f'animation={anim_ready}/15')
PYEOF

python "$PY" "$P47" "$LOCAL" "$OUT" "$REPORT" "$UNITY_VERSION"
rm -f "$PY"

git add scripts/lastwar-phase48-reconstruct-current15-unity-hierarchies.sh frontend/lab/master-assets-v2/meta/current15-unity-hierarchy-v1.json
if ! git diff --cached --quiet -- scripts/lastwar-phase48-reconstruct-current15-unity-hierarchies.sh frontend/lab/master-assets-v2/meta/current15-unity-hierarchy-v1.json; then
  git commit -m "lab: reconstruct exact current 15 Unity hierarchies"
fi
git push origin "$BRANCH"

echo "=== PHASE 48 TERMINEE ==="
echo "Manifest: frontend/lab/master-assets-v2/meta/current15-unity-hierarchy-v1.json"
echo "Rapport: $REPORT"
echo "Ne lance pas encore la page Escouades."
echo "main non modifiée."
