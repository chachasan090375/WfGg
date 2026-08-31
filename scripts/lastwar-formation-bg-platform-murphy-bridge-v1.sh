#!/data/data/com.termux/files/usr/bin/bash
set -Eeuo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BRANCH="portal-auth-lastwar-lab-v1"
INDEX="$ROOT/frontend/lab/master-assets-v2/index/lastwar-graphics-master-index-v1.json"
ATLAS="$ROOT/frontend/lab/master-assets-v2/index/lastwar-code-discovery-atlas-v1.json"
STAGE="$ROOT/frontend/lab/master-assets-v2/meta/current15-exact-bundle-stage.json"
SCENE="$ROOT/frontend/lab/master-assets-v2/meta/current15-authoritative-export-scene-index-v1.json"
RUNTIME="$ROOT/frontend/lab/master-assets-v2/meta/current15-runtime-pack-v1.json"
DYNAMIC="$ROOT/frontend/lab/master-assets-v2/meta/formation-dynamic-binding-bridge-v1.json"
CLOSURE="$ROOT/frontend/lab/local_assets/lastwar-formation-ptr-exact-v4/bundles"
OUT="$ROOT/frontend/lab/master-assets-v2/meta/formation-bg-platform-murphy-bridge-v1.json"
REPORT="$HOME/storage/downloads/WFGG_LASTWAR_FORMATION_BG_PLATFORM_MURPHY_BRIDGE_V1.txt"
CACHE="$HOME/.cache/wfgg-formation-bg-platform-murphy-bridge-v1"
UNITY_VERSION="2019.4.41f1"
BG_BUNDLE=10347
MURPHY_ID=50006

fail(){ printf 'ERREUR: %s\n' "$*" >&2; exit 1; }
cd "$ROOT"
[[ "$(git branch --show-current)" == "$BRANCH" ]] || fail "branche LAB incorrecte"
for f in "$INDEX" "$ATLAS" "$STAGE" "$SCENE" "$RUNTIME" "$DYNAMIC"; do [[ -s "$f" ]] || fail "fichier requis absent: $f"; done
[[ -s "$CLOSURE/bundle-$BG_BUNDLE.bundle" ]] || fail "bundle $BG_BUNDLE absent du cache Formation"
command -v python >/dev/null 2>&1 || fail "python absent"
python - <<'PYCHK' >/dev/null 2>&1 || fail "UnityPy absent"
import UnityPy
PYCHK
mkdir -p "$CACHE" "$(dirname "$REPORT")"

echo "BG_PLATFORM_MURPHY_V1_START"
PYTHONUNBUFFERED=1 python - "$ROOT" "$INDEX" "$ATLAS" "$STAGE" "$SCENE" "$RUNTIME" "$DYNAMIC" "$CLOSURE" "$OUT" "$REPORT" "$CACHE" "$UNITY_VERSION" "$BG_BUNDLE" "$MURPHY_ID" <<'PY'
from __future__ import annotations
from pathlib import Path
from collections import Counter,defaultdict
import json,re,sys,zipfile
import UnityPy
from UnityPy.enums import TextureFormat

root,indexp,atlasp,stagep,scenep,runtimep,dynamicp,closurep,outp,reportp,cachep=map(Path,sys.argv[1:12])
unity_version=sys.argv[12];bg_bundle=int(sys.argv[13]);murphy_id=int(sys.argv[14])
UnityPy.config.FALLBACK_UNITY_VERSION=unity_version

print('BG_PLATFORM_MURPHY_V1_STAGE load-metadata',flush=True)
idx=json.loads(indexp.read_text('utf-8'))
atlas=json.loads(atlasp.read_text('utf-8'))
stage=json.loads(stagep.read_text('utf-8'))
scene=json.loads(scenep.read_text('utf-8'))
runtime=json.loads(runtimep.read_text('utf-8'))
dynamic=json.loads(dynamicp.read_text('utf-8'))
records=idx.get('bundles')
if not isinstance(records,list) or not records:raise SystemExit('INDEX_SCHEMA_ERROR bundles')
byid={int(r['bundleId']):r for r in records if isinstance(r,dict) and r.get('bundleId') is not None}
if bg_bundle not in byid:raise SystemExit(f'BG_BUNDLE_NOT_IN_INDEX {bg_bundle}')

# Index semantics are explicit in the canonical builder: dependencyBundleIds = forward dependencies;
# dependentBundleIds = reverse dependents. Keep both distinct in the result.
def ids(v):
    out=[]
    for x in v or []:
        try:out.append(int(x))
        except:pass
    return sorted(set(out))

def norm(s):return str(s or '').replace('\\','/').rsplit('/',1)[-1].lower()
def typ(o):return str(getattr(getattr(o,'type',None),'name','') or '')
def pid(o):return int(getattr(o,'path_id',0) or 0)
def sf(o):return str(getattr(getattr(o,'assets_file',None),'name','') or '')
def pname(o):
    try:return str(o.peek_name() or '')
    except:return ''

def pptr(v):
    if not isinstance(v,dict):return None
    fk=next((k for k in ('m_FileID','fileID','fileId','m_FileId') if k in v),None)
    pk=next((k for k in ('m_PathID','pathID','pathId','m_PathId') if k in v),None)
    if fk is None or pk is None:return None
    try:return int(v[fk]),int(v[pk])
    except:return None

def walk_ptrs(v,path='$'):
    if isinstance(v,dict):
        q=pptr(v)
        if q is not None:yield path,q[0],q[1]
        for k,x in v.items():yield from walk_ptrs(x,f'{path}.{k}')
    elif isinstance(v,(list,tuple)):
        for i,x in enumerate(v):yield from walk_ptrs(x,f'{path}[{i}]')

def ext_names(af):
    out=[]
    for ex in list(getattr(af,'externals',None) or []):
        vals=[]
        for a in ('path','name','file_name','fileName'):
            try:
                v=getattr(ex,a,None)
                if v:vals.append(str(v))
            except:pass
        out.append(vals)
    return out

def ref_names(af,file_id):
    if file_id==0:
        n=str(getattr(af,'name','') or '');return [n] if n else []
    ex=ext_names(af);i=file_id-1
    return ex[i] if 0<=i<len(ex) else []

# -------- Formation fixed background / platform identities --------
print('BG_PLATFORM_MURPHY_V1_STAGE identify-bg-platform',flush=True)
bg_env=UnityPy.load(str(closurep/f'bundle-{bg_bundle}.bundle'))
bg_objs=list(getattr(bg_env,'objects',[]) or [])
TARGET_NAMES=('bg265','yueka_linshiziyuan')
targets=[]
for o in bg_objs:
    if typ(o)!='Texture2D' or pname(o) not in TARGET_NAMES:continue
    d=o.read()
    try:fmt=TextureFormat(int(d.m_TextureFormat)).name
    except:fmt=str(getattr(d,'m_TextureFormat',''))
    targets.append({
        'name':pname(o),'bundleId':bg_bundle,'serializedFile':sf(o),'pathIDExact':str(pid(o)),
        'width':int(d.m_Width),'height':int(d.m_Height),'format':fmt,
        'humanClassification':('blurred-background' if pname(o)=='bg265' else 'formation-platform-board'),
        'humanValidated':True,
    })
if sorted(x['name'] for x in targets)!=sorted(TARGET_NAMES):
    raise SystemExit(f'BG_TARGET_GUARD expected={TARGET_NAMES} got={[x["name"] for x in targets]}')
for x in targets:print('BG_PLATFORM_MURPHY_V1_TARGET',x['name'],x['width'],x['height'],x['pathIDExact'],flush=True)

bg_rec=byid[bg_bundle]
bg_forward=ids(bg_rec.get('dependencyBundleIds'))
bg_reverse=ids(bg_rec.get('dependentBundleIds'))

# -------- materialize only current reverse dependents and confirm exact PPtr consumers --------
def resolve_phys(v):
    if not v:return None
    p=Path(str(v)).expanduser();cands=[p,Path.home()/'storage/downloads'/p.name,Path.home()/'storage/shared/Download'/p.name,root/p]
    for q in cands:
        if q.is_file():return q
    return None

def materialize_index_bundle(bid):
    cp=closurep/f'bundle-{bid}.bundle'
    if cp.is_file():return cp,'cached-formation-closure'
    rec=byid.get(bid) or {};pe=rec.get('preferredExtraction') or {};phys=resolve_phys(pe.get('physicalApk'))
    if not phys:return None,'current-source-unavailable'
    try:
        off=int(pe.get('offset') or 0);span=pe.get('spanBytes')
        if span is None and pe.get('end') is not None:span=int(pe['end'])-off
        span=int(span) if span is not None else None
        if not span or span<=0 or span>134217728:return None,'current-span-invalid'
        out=cachep/f'bundle-{bid}.bundle';entry=pe.get('fragmentEntry')
        if entry:
            with zipfile.ZipFile(phys,'r') as zf:
                with zf.open(str(entry),'r') as f:
                    try:f.seek(off)
                    except Exception:
                        if off:f.read(off)
                    data=f.read(span)
        else:
            with phys.open('rb') as f:f.seek(off);data=f.read(span)
        if len(data)!=span:return None,f'short-read-{len(data)}-of-{span}'
        out.write_bytes(data);UnityPy.load(str(out));return out,'current-index-preferredExtraction'
    except Exception as e:return None,f'extraction-error:{type(e).__name__}:{e}'

print('BG_PLATFORM_MURPHY_V1_STAGE scan-bg-reverse-dependents',f'count={len(bg_reverse)}',flush=True)
bg_hits=[];bg_resolution=[];bg_read_fail=[];ptrs_scanned=0
target_by_pid={int(x['pathIDExact']):x for x in targets}
for pos,bid in enumerate(bg_reverse,1):
    p,how=materialize_index_bundle(bid);bg_resolution.append({'bundleId':bid,'resolution':how})
    print('BG_PLATFORM_MURPHY_V1_BG_DEPENDENT',f'{pos}/{len(bg_reverse)}',f'bundle={bid}',f'resolution={how}',flush=True)
    if not p:continue
    try:env=UnityPy.load(str(p))
    except Exception as e:
        bg_read_fail.append({'bundleId':bid,'stage':'load','error':f'{type(e).__name__}:{e}'});continue
    for o in list(getattr(env,'objects',[]) or []):
        af=getattr(o,'assets_file',None);otype=typ(o);oname=pname(o)
        try:tree=o.read_typetree()
        except Exception as e:
            if len(bg_read_fail)<200:bg_read_fail.append({'bundleId':bid,'stage':'typetree','type':otype,'name':oname,'pathID':str(pid(o)),'error':f'{type(e).__name__}:{e}'})
            continue
        for field,fid,pth in walk_ptrs(tree):
            ptrs_scanned+=1
            target=target_by_pid.get(pth)
            if not target:continue
            names=ref_names(af,fid)
            if not any(norm(n)==norm(target['serializedFile']) for n in names):continue
            meta_only=(otype=='AssetBundle' and ('.m_PreloadTable' in field or '.m_Container' in field))
            hit={'target':target['name'],'sourceBundleId':bid,'sourceSerializedFile':str(getattr(af,'name','') or ''),'sourceType':otype,'sourceName':oname,'sourcePathID':str(pid(o)),'fieldPath':field,'fileID':fid,'metadataOnly':meta_only}
            bg_hits.append(hit)
            print('BG_PLATFORM_MURPHY_V1_BG_HIT',f'target={target["name"]}',f'bundle={bid}',f'type={otype}',f'name={oname or "-"}',f'metadataOnly={meta_only}',flush=True)

# -------- Murphy exact staged family --------
print('BG_PLATFORM_MURPHY_V1_STAGE murphy-exact-family',flush=True)
murphy=next((h for h in stage.get('heroes',[]) if int(h.get('heroId',-1))==murphy_id),None)
if not murphy:raise SystemExit('MURPHY_STAGE_MISSING')
murphy_bundles=[]
for b in murphy.get('bundles',[]):
    bid=int(b['bundleId']);lp=root/str(b.get('localRel') or '')
    if not lp.is_file():raise SystemExit(f'MURPHY_LOCAL_BUNDLE_MISSING bundle={bid} path={lp}')
    murphy_bundles.append({**b,'bundleId':bid,'localPath':lp})
if len(murphy_bundles)!=7:raise SystemExit(f'MURPHY_BUNDLE_GUARD expected=7 actual={len(murphy_bundles)}')
queue_entry=next((b for b in murphy_bundles if b.get('kind')=='queue'),None)
if not queue_entry:raise SystemExit('MURPHY_QUEUE_BUNDLE_MISSING')
print('BG_PLATFORM_MURPHY_V1_MURPHY',f'queueBundle={queue_entry["bundleId"]}',f'family={"|".join(str(x["bundleId"]) for x in murphy_bundles)}',flush=True)

family_env={};family_objects={};family_sf_to_bid=defaultdict(set);family_key=defaultdict(list)
for b in murphy_bundles:
    bid=b['bundleId'];env=UnityPy.load(str(b['localPath']));family_env[bid]=env;objs=list(getattr(env,'objects',[]) or []);family_objects[bid]=objs
    for o in objs:
        nm=sf(o)
        if nm:
            family_sf_to_bid[norm(nm)].add(bid)
            family_key[(norm(nm),pid(o))].append((bid,o))
    fs=getattr(env,'files',None)
    if isinstance(fs,dict):
        for k,v in fs.items():
            for nm in (str(k or ''),str(getattr(v,'name','') or '')):
                if nm:family_sf_to_bid[norm(nm)].add(bid)

def resolve_family(source_af,fid,pth):
    if not pth:return None
    names=ref_names(source_af,fid)
    if fid==0:
        n=str(getattr(source_af,'name','') or '')
        names=[n] if n else []
    hits=[]
    for n in names:hits.extend(family_key.get((norm(n),pth),[]))
    uniq=[];seen=set()
    for bid,o in hits:
        k=(bid,pid(o),sf(o))
        if k not in seen:seen.add(k);uniq.append((bid,o))
    return uniq[0] if len(uniq)==1 else None

family_inventory=[]
for b in murphy_bundles:
    c=Counter(typ(o) for o in family_objects[b['bundleId']])
    family_inventory.append({'bundleId':b['bundleId'],'kind':b.get('kind'),'role':b.get('role'),'logicalName':b.get('logicalName'),'objectCount':sum(c.values()),'typeCounts':dict(c)})

queue_bid=queue_entry['bundleId'];queue_objs=family_objects[queue_bid]
root_go=[o for o in queue_objs if typ(o)=='GameObject' and pname(o)=='A_Hero_Audie_01']
renderer_types={'SkinnedMeshRenderer','MeshRenderer','MeshFilter'}
interesting_targets={'Mesh','Material','Texture2D','AnimationClip','AnimatorController','Avatar','Shader','GameObject','Transform'}
render_edges=[];render_read_fail=[]
for o in queue_objs:
    if typ(o) not in renderer_types and typ(o) not in {'Animator','Animation'}:continue
    af=getattr(o,'assets_file',None)
    try:tree=o.read_typetree()
    except Exception as e:
        render_read_fail.append({'sourceType':typ(o),'sourceName':pname(o),'pathID':str(pid(o)),'error':f'{type(e).__name__}:{e}'});continue
    for field,fid,pth in walk_ptrs(tree):
        rr=resolve_family(af,fid,pth)
        if not rr:continue
        tb,to=rr
        if typ(to) not in interesting_targets:continue
        render_edges.append({'sourceBundleId':queue_bid,'sourceType':typ(o),'sourceName':pname(o),'sourcePathID':str(pid(o)),'fieldPath':field,'targetBundleId':tb,'targetType':typ(to),'targetName':pname(to),'targetPathID':str(pid(to))})

# Material -> Texture2D exact family edges, useful for the actual surface rendering chain.
material_texture_edges=[]
for b in murphy_bundles:
    bid=b['bundleId']
    for o in family_objects[bid]:
        if typ(o)!='Material':continue
        af=getattr(o,'assets_file',None)
        try:tree=o.read_typetree()
        except:continue
        for field,fid,pth in walk_ptrs(tree):
            rr=resolve_family(af,fid,pth)
            if not rr:continue
            tb,to=rr
            if typ(to)!='Texture2D':continue
            material_texture_edges.append({'materialBundleId':bid,'materialName':pname(o),'materialPathID':str(pid(o)),'fieldPath':field,'textureBundleId':tb,'textureName':pname(to),'texturePathID':str(pid(to))})

murphy_scene=next((h for h in scene.get('heroes',[]) if int(h.get('heroId',-1))==murphy_id),None) or {}
murphy_runtime=next((h for h in runtime.get('heroes',[]) if int(h.get('heroId',-1))==murphy_id),None) or {}

# -------- index-level bridge candidates, explicitly candidate-only --------
murphy_ids=sorted(b['bundleId'] for b in murphy_bundles)
queue_reverse=set(ids(byid.get(queue_bid,{}).get('dependentBundleIds')))
any_murphy_reverse=defaultdict(set)
for mbid in murphy_ids:
    for dep in ids(byid.get(mbid,{}).get('dependentBundleIds')):any_murphy_reverse[dep].add(mbid)
common_queue=sorted(set(bg_reverse)&queue_reverse)
common_any=[]
for bid in sorted(set(bg_reverse)&set(any_murphy_reverse)):
    common_any.append({'bundleId':bid,'murphyBundleIdsReferenced':sorted(any_murphy_reverse[bid]),'murphyReferenceCount':len(any_murphy_reverse[bid]),'logicalName':(byid.get(bid) or {}).get('logicalName'),'assetPaths':(byid.get(bid) or {}).get('assetPaths',[])})
common_any.sort(key=lambda x:(-x['murphyReferenceCount'],x['bundleId']))

# -------- code / Lua indexed evidence only --------
print('BG_PLATFORM_MURPHY_V1_STAGE code-lua-index',flush=True)
types=atlas.get('types',[]) or [];methods=atlas.get('methods',[]) or [];frontier=atlas.get('frontier',[]) or []
tm={int(t['rid']):t for t in types if t.get('rid') is not None}
def symbol(m):
    t=tm.get(int(m.get('typeRid',-1)))
    owner=(((t.get('namespace')+'.') if t and t.get('namespace') else '')+(t.get('name','') if t else ''))
    return (owner+'.' if owner else '')+str(m.get('name',''))
terms=['A_Hero_Audie_01','queueModelPath','FightHero','HeroShowSetting','ShowCamera','CamZoomFormation','Formation','HeroQueue']
code_terms=[]
for term in terms:
    q=term.lower();mh=[];th=[];fh=[]
    for m in methods:
        s=symbol(m)
        if q in s.lower():mh.append({'rid':m.get('rid'),'symbol':s,'status':m.get('status'),'tags':m.get('tags',[])})
        if len(mh)>=30:break
    for t in types:
        s=((t.get('namespace')+'.') if t.get('namespace') else '')+str(t.get('name',''))
        if q in s.lower():th.append({'rid':t.get('rid'),'symbol':s,'status':t.get('status')})
        if len(th)>=20:break
    for f in frontier:
        blob=(str(f.get('symbol',''))+' '+json.dumps(f.get('strings',[]),ensure_ascii=False)).lower()
        if q in blob:fh.append({'rid':f.get('rid'),'symbol':f.get('symbol'),'strings':f.get('strings',[]),'tags':f.get('tags',[])})
        if len(fh)>=20:break
    code_terms.append({'term':term,'methodSymbolHits':mh,'typeSymbolHits':th,'frontierStringOrSymbolHits':fh})

lua_meta_files=[
 root/'frontend/lab/master-assets-v2/meta/formation-dynamic-binding-bridge-v1.json',
 root/'frontend/lab/master-assets-v2/meta/formation-lua-source-container-crosswalk-v1.json',
 root/'frontend/lab/master-assets-v2/meta/formation-lua-ui-bridge-detail-v1.json',
 root/'frontend/lab/master-assets-v2/meta/formation-xlua-index-crosswalk-v1.json',
 root/'frontend/lab/master-assets-v2/meta/formation-xlua-loader-storage-boundary-v1.json',
 root/'frontend/lab/master-assets-v2/meta/heroshow-clr-il-audit-v1.json',
 root/'frontend/lab/master-assets-v2/meta/heroshow-scene-loader-audit-v1.json',
]
literal_evidence=[]
for fp in lua_meta_files:
    if not fp.is_file():continue
    text=fp.read_text('utf-8',errors='replace').lower();hits={}
    for term in terms:
        n=text.count(term.lower())
        if n:hits[term]=n
    if hits:literal_evidence.append({'file':str(fp.relative_to(root)),'literalCounts':hits})

boundary=[{'rid':m.get('rid'),'symbol':m.get('symbol'),'externalCalls':m.get('externalCalls',[])} for m in dynamic.get('atlasExactBoundaryMethods',[])]

real_bg_consumers=[h for h in bg_hits if not h['metadataOnly']]
metadata_bg_hits=[h for h in bg_hits if h['metadataOnly']]
result={
 'format':'WFGG_LASTWAR_FORMATION_BG_PLATFORM_MURPHY_BRIDGE_V1',
 'backgroundPlatform':{
   'bundleId':bg_bundle,'logicalName':bg_rec.get('logicalName'),'assetPaths':bg_rec.get('assetPaths',[]),
   'targets':targets,'forwardDependencyBundleIds':bg_forward,'reverseDependentBundleIds':bg_reverse,
   'exactPPtrHits':bg_hits,'realConsumerHits':real_bg_consumers,'metadataOnlyHits':metadata_bg_hits,
   'scan':{'reverseDependents':len(bg_reverse),'resolvedBundles':sum(1 for x in bg_resolution if x['resolution'] in ('cached-formation-closure','current-index-preferredExtraction')),'ptrsScanned':ptrs_scanned,'readFailures':len(bg_read_fail),'resolution':bg_resolution,'readFailuresDetail':bg_read_fail},
 },
 'murphy':{
   'heroId':murphy_id,'name':murphy.get('name'),'queueModelPath':murphy.get('queueModelPath'),'formationKind':murphy.get('formationKind'),
   'queueBundleId':queue_bid,'bundleIds':murphy_ids,'exactBundles':[{k:v for k,v in b.items() if k!='localPath'} for b in murphy_bundles],
   'familyInventory':family_inventory,'queueRootExactCount':len(root_go),'queueRenderEdges':render_edges,'materialTextureEdges':material_texture_edges,
   'authoritativeScene':murphy_scene,'runtimePack':murphy_runtime,'renderReadFailures':render_read_fail,
 },
 'bridgeCandidates':{
   'definition':'current-index reverse-dependent overlap only; candidate relation, not runtime proof',
   'bgReverseDependentCount':len(bg_reverse),'queueReverseDependentCount':len(queue_reverse),
   'commonWithMurphyQueue':common_queue,'commonWithAnyMurphyBundle':common_any,
 },
 'codeLuaEvidence':{
   'atlasTerms':code_terms,'literalEvidenceInExistingAudits':literal_evidence,'knownXLuaBoundaryMethods':boundary,
   'specificVehicleSelectionInstantiationProven':False,
   'statement':'Exact vehicle assets/render components are known; the specific selected-hero -> vehicle prefab instantiation function is not yet proven in Lua/CLR.',
 },
 'guardrails':{
   'humanVisualClassificationIsRuntimeProof':False,'currentGraphicsIndexOnlyForDependencyBridge':True,'historicalOffsetsReused':False,
   'murphyUsesAlreadyVerifiedStagedBundles':True,'generatedVisuals':False,'candidatePromotion':False,'labBranchOnly':True,
   'authoritativeSceneSource':'current15-authoritative-export-scene-index-v1.json',
   'ignoredKnownRegressionForAuthority':'current15-runtime-scene-links-v4.json',
 }
}
outp.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n','utf-8')

lines=['WfGg Last War — FORMATION BG/PLATFORM + MURPHY BRIDGE V1','']
lines.append(f'BG bundle={bg_bundle} logical={bg_rec.get("logicalName","")} forwardDeps={len(bg_forward)} reverseDependents={len(bg_reverse)}')
for t in targets:lines.append(f"  TARGET {t['name']} {t['width']}x{t['height']} format={t['format']} serializedFile={t['serializedFile']} pathID={t['pathIDExact']} humanClass={t['humanClassification']}")
lines.append(f"BG exactPPtrHits={len(bg_hits)} realConsumers={len(real_bg_consumers)} metadataOnly={len(metadata_bg_hits)} ptrsScanned={ptrs_scanned} readFailures={len(bg_read_fail)}")
for h in real_bg_consumers:lines.append(f"  BG_CONSUMER target={h['target']} bundle={h['sourceBundleId']} type={h['sourceType']} name={h['sourceName'] or '-'} field={h['fieldPath']} pathID={h['sourcePathID']}")
lines+=['','MURPHY EXACT RENDER FAMILY']
lines.append(f"hero={murphy_id} name={murphy.get('name')} queueModelPath={murphy.get('queueModelPath')}")
lines.append(f"queueBundle={queue_bid} familyBundles={'|'.join(map(str,murphy_ids))} queueRootExactCount={len(root_go)}")
for b in murphy_bundles:lines.append(f"  BUNDLE id={b['bundleId']} kind={b.get('kind')} role={b.get('role')} logical={b.get('logicalName')}")
lines.append(f"authoritative transforms={murphy_scene.get('transformCount')} meshLinks={murphy_scene.get('meshLinkCount')} unresolvedMesh={murphy_scene.get('unresolvedMeshLinks')} materials={murphy_scene.get('materialCount')} unresolvedMaterials={murphy_scene.get('unresolvedMaterialLinks')}")
lines.append(f"queueRenderEdges={len(render_edges)} materialTextureEdges={len(material_texture_edges)}")
for e in render_edges:lines.append(f"  RENDER {e['sourceType']}:{e['sourceName'] or '-'} field={e['fieldPath']} -> bundle={e['targetBundleId']} {e['targetType']}:{e['targetName'] or '-'} targetPathID={e['targetPathID']}")
for e in material_texture_edges:lines.append(f"  SURFACE Material:{e['materialName'] or '-'} bundle={e['materialBundleId']} field={e['fieldPath']} -> Texture2D:{e['textureName'] or '-'} bundle={e['textureBundleId']}")
lines+=['','INDEX BRIDGE CANDIDATES (NOT PROOF)']
lines.append(f"commonWithMurphyQueue={len(common_queue)} ids={'|'.join(map(str,common_queue)) or '-'}")
for x in common_any[:80]:lines.append(f"  CANDIDATE bundle={x['bundleId']} murphyRefs={x['murphyReferenceCount']} murphyBundleIds={'|'.join(map(str,x['murphyBundleIdsReferenced']))} logical={x.get('logicalName') or '-'}")
lines+=['','CODE / LUA INDEX EVIDENCE']
for x in code_terms:lines.append(f"term={x['term']} methods={len(x['methodSymbolHits'])} types={len(x['typeSymbolHits'])} frontier={len(x['frontierStringOrSymbolHits'])}")
for f in literal_evidence:lines.append(f"  LITERAL file={f['file']} counts="+' '.join(f'{k}:{v}' for k,v in f['literalCounts'].items()))
lines.append('KNOWN_XLUA_BOUNDARY='+' | '.join(f"M{b['rid']} {b['symbol']}" for b in boundary))
lines+=['','CONCLUSION STATUS','exact_vehicle_assets_known=true','exact_vehicle_render_hierarchy_known=true','specific_selected_hero_to_vehicle_instantiation_proven=false','bg_platform_human_visual_classification_runtime_proof=false','RULE: reverse-dependent overlap is candidate-only until exact serialized/runtime evidence confirms it.','RULE: no historical offsets reused.','RULE: no visual generated.']
reportp.write_text('\n'.join(lines)+'\n','utf-8')
print('BG_PLATFORM_MURPHY_V1_OK',f'bgRealConsumers={len(real_bg_consumers)}',f'renderEdges={len(render_edges)}',f'commonAny={len(common_any)}',flush=True)
print('BG_PLATFORM_MURPHY_V1_REPORT',reportp,flush=True)
PY

git add "$OUT"
if ! git diff --cached --quiet; then
  git commit -m "lab: record Formation background platform Murphy bridge V1"
  git push origin "$BRANCH"
fi

echo "=== BG / PLATFORM + MURPHY BRIDGE V1 TERMINE ==="
echo "Rapport: $REPORT"
echo "main/preview inchangés. Aucun visuel généré."
