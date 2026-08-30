#!/data/data/com.termux/files/usr/bin/bash
set -Eeuo pipefail

# WfGg Last War LAB — exact serialized PPtr audit for UIHeroPVPFormationPanel.
# Goal: prove object-to-object Unity serialization links without guessing.
# No global bundle scan. Installed game is read-only.

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BRANCH="portal-auth-lastwar-lab-v1"
INDEX="$ROOT/frontend/lab/master-assets-v2/index/lastwar-graphics-master-index-v1.json"
TARGET_ASSET='Assets/Main/Prefabs/UI/UIHero/LWHero/UIHeroPVPFormationPanel.prefab'
EXPECTED_BUNDLE=6933
LOCAL="$ROOT/frontend/lab/local_assets/lastwar-formation-ptr-exact-v1"
OUT="$ROOT/frontend/lab/master-assets-v2/meta/formation-ptr-exact-v1.json"
REPORT="$HOME/storage/downloads/WFGG_LASTWAR_FORMATION_PTR_EXACT.txt"
PY="${TMPDIR:-$HOME/.cache}/wfgg-lastwar-formation-ptr-exact.py"

fail(){ printf 'ERREUR: %s\n' "$*" >&2; exit 1; }
cd "$ROOT"
[[ "$(git branch --show-current)" == "$BRANCH" ]] || fail "branche LAB incorrecte"
[[ -s "$INDEX" ]] || fail "graphics master index absent"
command -v python >/dev/null 2>&1 || fail "python absent"
python - <<'PYCHK' >/dev/null 2>&1 || fail "UnityPy absent dans Python Termux"
import UnityPy
PYCHK
mkdir -p "$LOCAL" "$(dirname "$OUT")" "$(dirname "$REPORT")" "$(dirname "$PY")"

cat > "$PY" <<'PYEOF'
from __future__ import annotations
from pathlib import Path
from collections import deque, Counter, defaultdict
import hashlib, json, re, sys, time, zipfile

import UnityPy
try:
    from UnityPy.classes.PPtr import PPtr
except Exception:
    PPtr=None

index_p=Path(sys.argv[1]); target_asset=sys.argv[2]; expected_bundle=int(sys.argv[3]); local=Path(sys.argv[4]); out=Path(sys.argv[5]); report=Path(sys.argv[6])
t0=time.time(); idx=json.loads(index_p.read_text('utf-8'))
by_id={int(x['bundleId']):x for x in idx.get('bundles',[])}
lookup=idx.get('lookup',{}).get('assetPathToBundleId',{})
target_bid=lookup.get(target_asset)
if target_bid is None: raise SystemExit('TARGET_ASSET_NOT_IN_INDEX')
target_bid=int(target_bid)
if target_bid!=expected_bundle: raise SystemExit(f'TARGET_BUNDLE_MISMATCH expected={expected_bundle} actual={target_bid}')

# Compute the dependency closure, but only load all of it when it stays reasonably small.
def closure(root):
    seen=set(); q=deque([root])
    while q:
        bid=q.popleft()
        if bid in seen: continue
        seen.add(bid)
        b=by_id.get(bid)
        if not b: continue
        for d in b.get('dependencyBundleIds',[]):
            if int(d) not in seen: q.append(int(d))
    return sorted(seen)

full_closure=closure(target_bid)
direct=[target_bid]+[int(x) for x in by_id[target_bid].get('dependencyBundleIds',[])]
# Exactness beats breadth. If closure is large, load only target+direct deps and mark unresolved externals explicitly.
LOAD_ALL_LIMIT=96
selected=full_closure if len(full_closure)<=LOAD_ALL_LIMIT else sorted(set(direct))
mode='full_dependency_closure' if selected==full_closure else 'target_plus_direct_dependencies'

bundle_dir=local/'bundles'; bundle_dir.mkdir(parents=True,exist_ok=True)
extract_log=[]; unresolved_bundle_locations=[]

def carve_bundle(bid:int):
    rec=by_id.get(bid)
    if not rec:
        unresolved_bundle_locations.append({'bundleId':bid,'reason':'bundle_not_in_index'}); return None
    loc=rec.get('preferredExtraction')
    if not isinstance(loc,dict):
        unresolved_bundle_locations.append({'bundleId':bid,'reason':'preferredExtraction_absent'}); return None
    apk=Path(str(loc.get('physicalApk','')))
    entry=loc.get('fragmentEntry'); off=loc.get('offset'); span=loc.get('spanBytes')
    if not apk.is_file() or not entry or not isinstance(off,int) or not isinstance(span,int) or span<=0:
        unresolved_bundle_locations.append({'bundleId':bid,'reason':'incomplete_physical_coordinates','preferredExtraction':loc}); return None
    dst=bundle_dir/f'bundle-{bid}.bundle'
    # Reuse only if byte size agrees with canonical extraction span.
    if dst.is_file() and dst.stat().st_size==span:
        extract_log.append({'bundleId':bid,'path':str(dst),'bytes':span,'reused':True}); return dst
    with zipfile.ZipFile(apk) as z:
        with z.open(entry,'r') as src, dst.open('wb') as fh:
            try:
                src.seek(off)
            except Exception:
                left=off
                while left:
                    chunk=src.read(min(left,1024*1024))
                    if not chunk: raise EOFError(f'fragment EOF before offset bundle={bid}')
                    left-=len(chunk)
            remaining=span
            while remaining:
                chunk=src.read(min(remaining,1024*1024))
                if not chunk: raise EOFError(f'fragment EOF during bundle carve bundle={bid}')
                fh.write(chunk); remaining-=len(chunk)
    extract_log.append({'bundleId':bid,'path':str(dst),'bytes':dst.stat().st_size,'reused':False})
    return dst

bundle_files=[]
for bid in selected:
    p=carve_bundle(bid)
    if p: bundle_files.append((bid,p))
if not any(bid==target_bid for bid,_ in bundle_files): raise SystemExit('TARGET_BUNDLE_EXTRACTION_FAILED')

print('FORMATION_PTR_EXTRACT',f'mode={mode}',f'closure={len(full_closure)}',f'selected={len(selected)}',f'extracted={len(bundle_files)}')

# Load selected bundles in a single Environment so UnityPy can dereference external PPtrs when the external serialized file is available.
env=UnityPy.load(*[str(p) for _,p in bundle_files])
container=getattr(env,'container',{})
root_reader=container.get(target_asset)
if root_reader is None:
    # Case-insensitive exact-path recovery only; no basename guessing.
    matches=[(k,v) for k,v in container.items() if str(k).lower()==target_asset.lower()]
    if len(matches)==1: root_reader=matches[0][1]
if root_reader is None:
    nearby=[str(k) for k in container.keys() if 'uiheropvpformationpanel' in str(k).lower()]
    raise SystemExit('TARGET_PREFAB_CONTAINER_ENTRY_NOT_FOUND exactPathRequired=true nearby='+repr(nearby[:20]))

# Helpers for exact serialized identities.
def af_name(af):
    for k in ('name','path'):
        v=getattr(af,k,None)
        if v: return str(v)
    return '<serialized-file>'

def parent_name(af):
    p=getattr(af,'parent',None)
    for k in ('name','path'):
        v=getattr(p,k,None) if p is not None else None
        if v: return str(v)
    return ''

def infer_bundle_id(reader):
    names=[af_name(reader.assets_file),parent_name(reader.assets_file)]
    for s in names:
        m=re.search(r'bundle-(\d+)\.bundle',s,re.I)
        if m: return int(m.group(1))
    return None

def objkey(reader):
    return f"{parent_name(reader.assets_file)}|{af_name(reader.assets_file)}#{int(reader.path_id)}"

def objtype(reader):
    t=getattr(reader,'type',None)
    return getattr(t,'name',str(t) if t is not None else 'Unknown')

def objname(reader):
    try:
        n=reader.peek_name()
        if n is not None:return str(n)
    except Exception: pass
    return None

def external_info(reader,file_id:int):
    if file_id<=0:return None
    exts=getattr(reader.assets_file,'externals',[]) or []
    i=file_id-1
    if 0<=i<len(exts):
        ex=exts[i]
        return {'fileID':file_id,'path':str(getattr(ex,'path','')),'guid':str(getattr(ex,'guid','')) if getattr(ex,'guid',None) is not None else None,'type':getattr(ex,'type',None)}
    return {'fileID':file_id,'path':None,'invalidExternalIndex':True}

# Read typetrees conservatively. Built-in Unity types should parse exactly. Missing MonoBehaviour script trees are recorded, never fabricated.
def read_tree(reader):
    try:
        return reader.read_typetree(),None
    except Exception as e:
        try:
            # On modern UnityPy this can recover generated MonoBehaviour trees if available.
            return reader.read_typetree(check_read=False),f'check_read_false_after:{type(e).__name__}'
        except Exception as e2:
            return None,f'{type(e).__name__}:{e} | fallback {type(e2).__name__}:{e2}'

def is_pptr_dict(v):
    return isinstance(v,dict) and 'm_FileID' in v and 'm_PathID' in v and isinstance(v.get('m_FileID'),int) and isinstance(v.get('m_PathID'),int)

def walk_pptrs(v,path='$'):
    if is_pptr_dict(v):
        yield path,int(v['m_FileID']),int(v['m_PathID']); return
    if PPtr is not None and isinstance(v,PPtr):
        yield path,int(v.m_FileID),int(v.m_PathID); return
    if isinstance(v,dict):
        for k,x in v.items(): yield from walk_pptrs(x,path+'.'+str(k))
    elif isinstance(v,(list,tuple)):
        for i,x in enumerate(v): yield from walk_pptrs(x,f'{path}[{i}]')

# Keep exact scalar render state for key Unity object types, while explicitly recording any omitted large payload.
STATE_TYPES={'GameObject','Transform','RectTransform','MeshRenderer','SkinnedMeshRenderer','MeshFilter','Renderer','CanvasRenderer','Canvas','Camera','Light','Material','Texture2D','Sprite','Animator','Animation','ParticleSystem','ParticleSystemRenderer'}
SKIP_KEYS={'m_VertexData','m_IndexBuffer','m_StreamData','image data','m_ImageData','m_AudioData','m_MeshCompression','m_Shapes'}

def scalar_projection(v,path='$',omitted=None,depth=0):
    if omitted is None: omitted=[]
    if depth>24:
        omitted.append(path+':depth_limit'); return None
    if v is None or isinstance(v,(bool,int,float,str)):return v
    if is_pptr_dict(v):return {'m_FileID':v['m_FileID'],'m_PathID':v['m_PathID']}
    if isinstance(v,(bytes,bytearray,memoryview)):
        omitted.append(path+f':binary_bytes={len(v)}'); return {'_omittedBinaryBytes':len(v)}
    if isinstance(v,dict):
        out={}
        for k,x in v.items():
            kp=path+'.'+str(k)
            if str(k) in SKIP_KEYS:
                try:n=len(x)
                except:n=None
                omitted.append(kp+(f':len={n}' if n is not None else ''))
                continue
            out[str(k)]=scalar_projection(x,kp,omitted,depth+1)
        return out
    if isinstance(v,(list,tuple)):
        if len(v)>512:
            omitted.append(path+f':array_len={len(v)}'); return {'_omittedArrayLength':len(v)}
        return [scalar_projection(x,f'{path}[{i}]',omitted,depth+1) for i,x in enumerate(v)]
    # Wrapped UnityPy scalar/vector object: serialize public fields only when small.
    d=getattr(v,'__dict__',None)
    if isinstance(d,dict):return scalar_projection({k:x for k,x in d.items() if not k.startswith('_')},path,omitted,depth+1)
    return str(v)

def relation_for(src_type,field_path,dst_type=None):
    p=field_path.lower()
    if src_type=='GameObject' and '.m_component' in p:return 'component_ref',True
    if src_type in ('Transform','RectTransform') and ('.m_father' in p or '.m_children' in p):return 'hierarchy_ref',True
    if 'm_material' in p:return 'material_ref',True
    if 'm_mesh' in p:return 'mesh_ref',True
    if 'm_sprite' in p:return 'sprite_ref',True
    if 'm_texture' in p or 'texenv' in p:return 'texture_ref',True
    if 'm_shader' in p:return 'shader_ref',True
    if 'm_script' in p:return 'script_ref',False
    if 'm_gameobject' in p:return 'gameobject_ref',True
    return 'serialized_ref',False

# Resolve a pointer strictly through UnityPy's serialized external table. If it cannot resolve, preserve the exact external path + pathID as unresolved.
def deref(reader,file_id,path_id):
    if path_id==0:return None,None
    if file_id==0:
        dst=getattr(reader.assets_file,'objects',{}).get(path_id)
        return dst,None if dst is not None else 'local_pathid_not_found'
    if PPtr is None:return None,'UnityPy.PPtr_class_unavailable'
    try:
        pp=PPtr(m_FileID=file_id,m_PathID=path_id,assetsfile=reader.assets_file)
        return pp.deref(),None
    except Exception as e:
        return None,f'{type(e).__name__}:{e}'

nodes={}; edges=[]; edge_seen=set(); parse_errors=[]; unresolved_refs=[]; queue=deque([root_reader]); seen=set(); MAX_OBJECTS=120000

while queue:
    reader=queue.popleft(); key=objkey(reader)
    if key in seen:continue
    if len(seen)>=MAX_OBJECTS:raise SystemExit('PPTR_GRAPH_OBJECT_LIMIT_EXCEEDED')
    seen.add(key)
    typ=objtype(reader); tree,err=read_tree(reader); name=objname(reader)
    node={'id':key,'pathID':int(reader.path_id),'type':typ,'name':name,'serializedFile':af_name(reader.assets_file),'parentFile':parent_name(reader.assets_file),'bundleId':infer_bundle_id(reader)}
    if err:node['typetreeWarning']=err
    if typ in STATE_TYPES and tree is not None:
        omitted=[]; node['renderState']=scalar_projection(tree,omitted=omitted)
        if omitted:node['renderStateOmitted']=omitted
    nodes[key]=node
    if tree is None:
        parse_errors.append({'object':key,'type':typ,'error':err}); continue
    for fpath,file_id,path_id in walk_pptrs(tree):
        if path_id==0:continue
        dst,derr=deref(reader,file_id,path_id)
        ext=external_info(reader,file_id)
        if dst is not None:
            dkey=objkey(dst); dtype=objtype(dst); rel,eligible=relation_for(typ,fpath,dtype)
            ek=(key,dkey,fpath,file_id,path_id)
            if ek not in edge_seen:
                edge_seen.add(ek); edges.append({'from':key,'to':dkey,'relation':rel,'fieldPath':fpath,'fileID':file_id,'pathID':path_id,'proof':'serialized_pptr','confidence':'serialized_exact','renderEligible':eligible,'external':ext})
            if dkey not in seen:queue.append(dst)
        else:
            if file_id==0:
                target=f"unresolved:{af_name(reader.assets_file)}#{path_id}"
            else:
                ep=(ext or {}).get('path') or f'fileID:{file_id}'
                target=f"unresolved:{ep}#{path_id}"
            rel,eligible=relation_for(typ,fpath,None)
            ek=(key,target,fpath,file_id,path_id)
            if ek not in edge_seen:
                edge_seen.add(ek);edges.append({'from':key,'to':target,'relation':rel,'fieldPath':fpath,'fileID':file_id,'pathID':path_id,'proof':'serialized_pptr_value','confidence':'serialized_exact_target_unresolved','renderEligible':eligible,'external':ext,'resolutionError':derr})
            unresolved_refs.append({'from':key,'sourceType':typ,'fieldPath':fpath,'fileID':file_id,'pathID':path_id,'external':ext,'resolutionError':derr})

# Classify useful exact chains without inventing any relation.
rel_counts=Counter(e['relation'] for e in edges); conf_counts=Counter(e['confidence'] for e in edges); type_counts=Counter(n['type'] for n in nodes.values())
render_exact=[e for e in edges if e.get('renderEligible') and e.get('confidence')=='serialized_exact']
render_unresolved=[e for e in edges if e.get('renderEligible') and e.get('confidence')!='serialized_exact']

result={
 'format':'WFGG_LASTWAR_FORMATION_PPTR_EXACT_V1',
 'target':{'assetPath':target_asset,'bundleId':target_bid,'rootObject':objkey(root_reader),'rootType':objtype(root_reader),'rootName':objname(root_reader)},
 'sourceIndex':{'path':str(index_p),'format':idx.get('format'),'gameresSha256':idx.get('source',{}).get('gameresSha256')},
 'dependencySelection':{'mode':mode,'fullClosureCount':len(full_closure),'selectedCount':len(selected),'fullClosureBundleIds':full_closure,'selectedBundleIds':selected,'loadAllLimit':LOAD_ALL_LIMIT},
 'extraction':{'bundles':extract_log,'unresolvedBundleLocations':unresolved_bundle_locations},
 'counts':{'objects':len(nodes),'edges':len(edges),'renderExactEdges':len(render_exact),'renderUnresolvedEdges':len(render_unresolved),'unresolvedRefs':len(unresolved_refs),'parseErrors':len(parse_errors),'objectTypes':dict(type_counts),'relations':dict(rel_counts),'confidence':dict(conf_counts)},
 'fidelityPolicy':{
   'noGuessing':True,
   'serializedExactMeaning':'m_FileID/m_PathID read directly from Unity serialized data and target successfully dereferenced in loaded dependency set.',
   'serializedExactTargetUnresolvedMeaning':'pointer value is exact, but target object is not claimed until its external serialized file is loaded/resolved.',
   'bundleDependencyIsNotVisualProof':True,
   'certificationBlockedIfRenderUnresolved':bool(render_unresolved),
   'certificationBlockedIfRenderStateOmitted':any(n.get('renderStateOmitted') for n in nodes.values()),
 },
 'nodes':list(nodes.values()),
 'edges':edges,
 'unresolvedRefs':unresolved_refs,
 'parseErrors':parse_errors,
 'guardrails':{'globalBundleScan':False,'candidateNameMatching':False,'installedGameReadOnly':True,'mainUntouched':True},
 'elapsedSeconds':round(time.time()-t0,3),
}
out.write_text(json.dumps(result,ensure_ascii=False,separators=(',',':'))+'\n','utf-8')

lines=[
 'WfGg Last War — FORMATION EXACT PPtr AUDIT','',
 f'targetAsset={target_asset}',f'targetBundle={target_bid}',f'root={result["target"]["rootObject"]}',
 f'dependencyMode={mode} fullClosure={len(full_closure)} selected={len(selected)} extracted={len(bundle_files)}',
 f'objects={len(nodes)} edges={len(edges)} renderExact={len(render_exact)} renderUnresolved={len(render_unresolved)} unresolvedRefs={len(unresolved_refs)} parseErrors={len(parse_errors)} elapsed={result["elapsedSeconds"]}',
 'relations='+json.dumps(dict(rel_counts),ensure_ascii=False),
 'confidence='+json.dumps(dict(conf_counts),ensure_ascii=False),'',
 'RULE: only serialized PPtr values are facts. No basename/path-family/bundle-neighborhood candidate is promoted.',
 'RULE: unresolved external target remains unresolved; no substitute is selected.', ''
]
for e in render_exact[:120]:
    lines.append(f"EXACT {e['from']} --{e['relation']} {e['fieldPath']} fileID={e['fileID']} pathID={e['pathID']}--> {e['to']}")
for e in render_unresolved[:120]:
    lines.append(f"UNRESOLVED_RENDER {e['from']} --{e['relation']} {e['fieldPath']} fileID={e['fileID']} pathID={e['pathID']}--> {e['to']} error={e.get('resolutionError')}")
report.write_text('\n'.join(lines)+'\n','utf-8')

print('FORMATION_PTR_EXACT_OK',f'objects={len(nodes)}',f'edges={len(edges)}',f'renderExact={len(render_exact)}',f'renderUnresolved={len(render_unresolved)}',f'unresolved={len(unresolved_refs)}',f'elapsed={result["elapsedSeconds"]}')
print('FORMATION_PTR_TARGET',target_asset,'bundle='+str(target_bid),'root='+objkey(root_reader))
print('FORMATION_PTR_DEPENDENCIES',f'mode={mode}',f'full={len(full_closure)}',f'selected={len(selected)}')
for e in render_exact[:24]:print('FORMATION_PTR_EXACT',e['relation'],e['fieldPath'],'->',e['to'])
for e in render_unresolved[:24]:print('FORMATION_PTR_UNRESOLVED_RENDER',e['relation'],e['fieldPath'],'->',e['to'])
print('FORMATION_PTR_JSON',out)
print('FORMATION_PTR_REPORT',report)
PYEOF

python "$PY" "$INDEX" "$TARGET_ASSET" "$EXPECTED_BUNDLE" "$LOCAL" "$OUT" "$REPORT"

# Output is metadata/evidence only. Local carved bundles stay untracked in local_assets.
size="$(wc -c < "$OUT" | tr -d ' ')"
if [[ "$size" -ge 90000000 ]]; then
  fail "audit JSON trop gros pour GitHub (${size} bytes); ne pas committer, empaquetage requis"
fi

git add "$OUT"
if ! git diff --cached --quiet; then
  git commit -m "lab: map exact Formation prefab PPtr graph"
fi
git push origin "$BRANCH"
printf '%s\n' '=== FORMATION EXACT PPtr AUDIT TERMINE ===' "JSON: $OUT" "Rapport: $REPORT" 'Aucun lien candidat promu en preuve de rendu.'
