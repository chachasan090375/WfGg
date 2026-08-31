#!/data/data/com.termux/files/usr/bin/bash
set -Eeuo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BRANCH="portal-auth-lastwar-lab-v1"
META="$ROOT/frontend/lab/master-assets-v2/meta"
SOURCE="$META/formation-human-selected-texture-direct-bundle-consumers-v2.json"
SUMMARY="$META/formation-ptr-exact-v4-summary-v1.json"
LOCAL="$ROOT/frontend/lab/local_assets/lastwar-formation-ptr-exact-v4/bundles"
OUT="$META/formation-selected-material-render-consumers-v1.json"
REPORT="$HOME/storage/downloads/WFGG_LASTWAR_FORMATION_SELECTED_MATERIAL_RENDER_CONSUMERS_V1.txt"
UNITY_VERSION="2019.4.41f1"

fail(){ printf 'ERREUR: %s\n' "$*" >&2; exit 1; }
cd "$ROOT"
[[ "$(git branch --show-current)" == "$BRANCH" ]] || fail "branche LAB incorrecte"
for f in "$SOURCE" "$SUMMARY"; do [[ -s "$f" ]] || fail "fichier absent: $f"; done
[[ -d "$LOCAL" ]] || fail "cache bundles V4 absent: $LOCAL"
command -v python >/dev/null 2>&1 || fail "python absent"
python - <<'PYCHK' >/dev/null 2>&1 || fail "UnityPy absent"
import UnityPy
PYCHK
mkdir -p "$(dirname "$REPORT")"

echo "MATERIAL_RENDER_CONSUMERS_V1_START"
echo "MATERIAL_RENDER_CONSUMERS_V1_PREFLIGHT_OK"

PYTHONUNBUFFERED=1 python - "$SOURCE" "$SUMMARY" "$LOCAL" "$OUT" "$REPORT" "$UNITY_VERSION" <<'PY'
from __future__ import annotations
from pathlib import Path
from collections import defaultdict
import json,re,sys
import UnityPy

sourcep,sump,localp,outp,reportp=map(Path,sys.argv[1:6])
unity_version=sys.argv[6]
UnityPy.config.FALLBACK_UNITY_VERSION=unity_version

print('MATERIAL_RENDER_CONSUMERS_V1_STAGE load-inputs',flush=True)
src=json.loads(sourcep.read_text('utf-8'))
sumj=json.loads(sump.read_text('utf-8'))
expected=set(int(x) for x in ((sumj.get('dependencySelection') or {}).get('selectedBundleIds') or []))
if len(expected)!=195:raise SystemExit(f'SUMMARY_CLOSURE_GUARD expected195 actual={len(expected)}')

bundle_files={}
for p in localp.glob('bundle-*.bundle'):
    m=re.fullmatch(r'bundle-(\d+)\.bundle',p.name)
    if m:bundle_files[int(m.group(1))]=p
missing=sorted(expected-set(bundle_files))
if missing:raise SystemExit(f'BUNDLE_CACHE_GUARD missing={len(missing)} sample={missing[:10]}')

# Derive the exact material frontier from the previous exact texture->consumer scan.
materials={}
for tr in src.get('textureResults',[]):
    for c in tr.get('consumerObjects',[]):
        if int(c.get('sourceBundleId',-1))!=14169:continue
        if str(c.get('sourceObjectType') or '')!='Material':continue
        key=(str(c.get('sourceObjectPathID')),str(c.get('sourceObjectName') or ''))
        materials[key]={
            'storageBundleId':14169,
            'pathID':str(c.get('sourceObjectPathID')),
            'name':str(c.get('sourceObjectName') or ''),
            'sourceTextures':[]
        }
for tr in src.get('textureResults',[]):
    tname=str((tr.get('target') or {}).get('name') or '')
    for c in tr.get('consumerObjects',[]):
        key=(str(c.get('sourceObjectPathID')),str(c.get('sourceObjectName') or ''))
        if key in materials and tname not in materials[key]['sourceTextures']:
            materials[key]['sourceTextures'].append(tname)
for m in materials.values():m['sourceTextures'].sort()

expected_names={'Terrain_Ground','O_terrain_grass02_3TextureNS1','O_terrain_road_01','O_terrain_road_02_nsj','O_terrain_shamo_back'}
actual_names={x['name'] for x in materials.values()}
if len(materials)!=5 or actual_names!=expected_names:
    raise SystemExit(f'MATERIAL_FRONTIER_GUARD count={len(materials)} names={sorted(actual_names)}')
print('MATERIAL_RENDER_CONSUMERS_V1_FRONTIER',f'materials={len(materials)}', ' | '.join(sorted(actual_names)),flush=True)

def norm_file_name(s):
    s=str(s or '').replace('\\','/')
    if not s:return ''
    return s.rsplit('/',1)[-1]

def file_name_of_obj(obj):
    af=getattr(obj,'assets_file',None)
    return str(getattr(af,'name','') or '')

def try_name(obj):
    try:
        n=obj.peek_name()
        if n:return str(n)
    except Exception:pass
    return ''

def external_names(assets_file):
    out=[]
    exts=getattr(assets_file,'externals',None)
    if not exts:return out
    for ex in exts:
        vals=[]
        for a in ('path','name','file_name','fileName'):
            try:
                v=getattr(ex,a,None)
                if v:vals.append(str(v))
            except Exception:pass
        out.append(vals)
    return out

def ptr_hits(tree,path='$'):
    if isinstance(tree,dict):
        fks=('m_FileID','fileID','fileId','m_FileId');pks=('m_PathID','pathID','pathId','m_PathId')
        fk=next((k for k in fks if k in tree),None);pk=next((k for k in pks if k in tree),None)
        if fk is not None and pk is not None:
            try:yield path,int(tree[fk]),int(tree[pk])
            except Exception:pass
        for k,v in tree.items():yield from ptr_hits(v,f'{path}.{k}')
    elif isinstance(tree,(list,tuple)):
        for i,v in enumerate(tree):yield from ptr_hits(v,f'{path}[{i}]')

def resolve_ref_names(source_af,file_id):
    if file_id==0:return [str(getattr(source_af,'name','') or '')]
    if file_id<0:return []
    ex=external_names(source_af);idx=file_id-1
    return ex[idx] if 0<=idx<len(ex) else []

def ident(sf,pid):return (norm_file_name(sf),int(pid))

def meta_public(x):
    if not x:return None
    return {k:x.get(k) for k in ('bundleId','bundleLabels','serializedFile','pathID','type','name')}

# ---------- pass 1: exact object inventory ----------
print('MATERIAL_RENDER_CONSUMERS_V1_STAGE inventory-objects',flush=True)
objects={};bundle_labels=defaultdict(set);duplicates=[];load_failures=[]
for pos,bid in enumerate(sorted(expected),1):
    print('MATERIAL_RENDER_CONSUMERS_V1_INVENTORY',f'{pos}/195',f'bundle={bid}',flush=True)
    p=bundle_files[bid]
    try:env=UnityPy.load(str(p))
    except Exception as e:
        load_failures.append({'bundleId':bid,'stage':'load-pass1','error':f'{type(e).__name__}:{e}'})
        continue
    for obj in list(getattr(env,'objects',[]) or []):
        sf=file_name_of_obj(obj);pid=int(getattr(obj,'path_id',0) or 0)
        typ=str(getattr(getattr(obj,'type',None),'name','') or '');name=try_name(obj)
        if typ=='AssetBundle' and name:bundle_labels[bid].add(name)
        key=ident(sf,pid)
        rec={'bundleId':bid,'serializedFile':sf,'pathID':str(pid),'type':typ,'name':name}
        if key in objects and (objects[key]['bundleId']!=bid or objects[key]['type']!=typ):
            duplicates.append({'identity':[key[0],str(key[1])],'first':objects[key],'second':rec})
        else:objects[key]=rec
for rec in objects.values():rec['bundleLabels']=sorted(bundle_labels.get(rec['bundleId'],set()))
print('MATERIAL_RENDER_CONSUMERS_V1_INVENTORY_OK',f'objects={len(objects)}',f'duplicateIdentities={len(duplicates)}',flush=True)
if duplicates:
    # Serialized CAB/pathID identity should be unique in this exact closure. Stop rather than silently choosing.
    raise SystemExit(f'OBJECT_IDENTITY_GUARD duplicates={len(duplicates)} sample={duplicates[:2]}')

# Resolve the five exact Material target identities in bundle 14169.
material_targets={}
for m in materials.values():
    pid=int(m['pathID']);hits=[(k,v) for k,v in objects.items() if v['bundleId']==14169 and int(v['pathID'])==pid and v['type']=='Material' and v['name']==m['name']]
    if len(hits)!=1:raise SystemExit(f'MATERIAL_TARGET_RESOLUTION name={m["name"]} pid={pid} hits={len(hits)}')
    key,meta=hits[0];material_targets[key]={**m,'serializedFile':meta['serializedFile'],'bundleLabels':meta['bundleLabels']}
    print('MATERIAL_RENDER_CONSUMERS_V1_TARGET',m['name'],f'pid={pid}',f'file={meta["serializedFile"]}',flush=True)

RENDER_TYPES={'MeshRenderer','SkinnedMeshRenderer','Renderer','Terrain','ParticleSystemRenderer','TrailRenderer','LineRenderer','SpriteRenderer'}
LINK_TYPES={'MeshFilter','Transform','RectTransform','Terrain','MeshRenderer','SkinnedMeshRenderer','Renderer','MonoBehaviour','LODGroup'}
BOOKKEEP_TYPES={'AssetBundle','ResourceManager'}

# ---------- pass 2: scan PPtrs and keep exact material hits + ownership/render links ----------
print('MATERIAL_RENDER_CONSUMERS_V1_STAGE scan-pointers',flush=True)
material_hits=[];components_by_go=defaultdict(list);object_links=defaultdict(list);ptr_total=0;tree_failures=[]
for pos,bid in enumerate(sorted(expected),1):
    print('MATERIAL_RENDER_CONSUMERS_V1_SCAN',f'{pos}/195',f'bundle={bid}',flush=True)
    p=bundle_files[bid]
    try:env=UnityPy.load(str(p))
    except Exception as e:
        load_failures.append({'bundleId':bid,'stage':'load-pass2','error':f'{type(e).__name__}:{e}'})
        continue
    for obj in list(getattr(env,'objects',[]) or []):
        source_sf=file_name_of_obj(obj);source_pid=int(getattr(obj,'path_id',0) or 0);source_key=ident(source_sf,source_pid)
        source_meta=objects.get(source_key) or {'bundleId':bid,'bundleLabels':sorted(bundle_labels.get(bid,set())),'serializedFile':source_sf,'pathID':str(source_pid),'type':str(getattr(getattr(obj,'type',None),'name','') or ''),'name':try_name(obj)}
        source_af=getattr(obj,'assets_file',None)
        try:tree=obj.read_typetree()
        except Exception as e:
            if len(tree_failures)<500:tree_failures.append({'bundleId':bid,'pathID':str(source_pid),'type':source_meta['type'],'name':source_meta['name'],'error':f'{type(e).__name__}:{e}'})
            continue
        for field_path,file_id,path_id in ptr_hits(tree):
            ptr_total+=1
            if path_id==0:continue
            target_key=None;target_meta=None
            for rn in resolve_ref_names(source_af,file_id):
                k=ident(rn,path_id)
                if k in objects:
                    target_key=k;target_meta=objects[k];break
            if target_key is None:continue
            # Exact material hit.
            if target_key in material_targets:
                mat=material_targets[target_key]
                material_hits.append({'materialName':mat['name'],'materialPathID':mat['pathID'],'source':meta_public(source_meta),'fieldPath':field_path,'fileID':file_id})
                print('MATERIAL_RENDER_CONSUMERS_V1_HIT',f'material={mat["name"]}',f'bundle={bid}',f'type={source_meta["type"]}',f'name={source_meta["name"]}',f'field={field_path}',flush=True)
            # Ownership: most Components point to m_GameObject.
            if target_meta['type']=='GameObject' and (field_path.endswith('.m_GameObject') or '.m_GameObject.' in field_path):
                components_by_go[target_key].append(source_key)
            # Keep compact links for render/ownership enrichment.
            if source_meta['type'] in RENDER_TYPES|LINK_TYPES or target_meta['type'] in {'GameObject','Mesh','TerrainData','Transform','RectTransform','Material'}:
                object_links[source_key].append({'fieldPath':field_path,'fileID':file_id,'targetKey':target_key})

print('MATERIAL_RENDER_CONSUMERS_V1_SCAN_OK',f'ptrs={ptr_total}',f'materialHits={len(material_hits)}',f'treeFailures={len(tree_failures)}',flush=True)

# ---------- enrich render hits with owner GameObject, sibling components, mesh/terrain links ----------
def link_targets(source_key,types=None,field_contains=None):
    out=[]
    for e in object_links.get(source_key,[]):
        tm=objects.get(e['targetKey'])
        if not tm:continue
        if types and tm['type'] not in types:continue
        if field_contains and field_contains not in e['fieldPath']:continue
        out.append({'fieldPath':e['fieldPath'],'target':meta_public(tm)})
    return out

def owner_go(source_key):
    for e in object_links.get(source_key,[]):
        tm=objects.get(e['targetKey'])
        if tm and tm['type']=='GameObject' and 'm_GameObject' in e['fieldPath']:
            return e['targetKey'],tm
    return None,None

render_rows=[];packaging_rows=[];other_rows=[]
for h in material_hits:
    sm=h['source'];source_key=ident(sm['serializedFile'],int(sm['pathID']))
    st=sm['type']
    if st in BOOKKEEP_TYPES:
        packaging_rows.append(h);continue
    if st not in RENDER_TYPES:
        other_rows.append(h);continue
    gokey,gometa=owner_go(source_key)
    siblings=[]
    if gokey is not None:
        for ck in components_by_go.get(gokey,[]):
            cm=objects.get(ck)
            if not cm:continue
            item={'component':meta_public(cm),'meshLinks':link_targets(ck,{'Mesh'}),'terrainDataLinks':link_targets(ck,{'TerrainData'}),'materialLinks':link_targets(ck,{'Material'})}
            siblings.append(item)
    render_rows.append({**h,'ownerGameObject':meta_public(gometa),'sourceMeshLinks':link_targets(source_key,{'Mesh'}),'sourceTerrainDataLinks':link_targets(source_key,{'TerrainData'}),'siblingComponents':siblings})

# Some Material refs can be from non-render objects. Preserve, do not promote.
by_material=defaultdict(lambda:{'render':[],'packaging':[],'other':[]})
for x in render_rows:by_material[x['materialName']]['render'].append(x)
for x in packaging_rows:by_material[x['materialName']]['packaging'].append(x)
for x in other_rows:by_material[x['materialName']]['other'].append(x)

bundle_agg=defaultdict(lambda:{'materials':set(),'renderObjects':set(),'gameObjects':set(),'types':set(),'hits':0})
for x in render_rows:
    b=int(x['source']['bundleId']);u=bundle_agg[b];u['materials'].add(x['materialName']);u['renderObjects'].add((x['source']['type'],x['source']['name'],x['source']['pathID']));u['types'].add(x['source']['type']);u['hits']+=1
    if x.get('ownerGameObject'):u['gameObjects'].add((x['ownerGameObject']['name'],x['ownerGameObject']['pathID']))
agg=[]
for bid,u in bundle_agg.items():
    agg.append({'bundleId':bid,'bundleLabels':sorted(bundle_labels.get(bid,set())),'materialCount':len(u['materials']),'materials':sorted(u['materials']),'renderHitCount':u['hits'],'renderTypes':sorted(u['types']),'renderObjects':[{'type':a,'name':b,'pathID':c} for a,b,c in sorted(u['renderObjects'])],'gameObjects':[{'name':a,'pathID':b} for a,b in sorted(u['gameObjects'])]})
agg.sort(key=lambda x:(-x['materialCount'],-x['renderHitCount'],x['bundleId']))

out={
 'format':'WFGG_LASTWAR_FORMATION_SELECTED_MATERIAL_RENDER_CONSUMERS_V1',
 'method':'derive five exact Material objects from human-selected texture direct consumers, then scan exact current 195-bundle closure and separate render consumers from AssetBundle packaging refs',
 'materialTargets':[{'identity':[k[0],str(k[1])],**v} for k,v in material_targets.items()],
 'counts':{'closureBundles':195,'objectsInventoried':len(objects),'ptrsScanned':ptr_total,'materials':5,'materialDirectHits':len(material_hits),'renderHits':len(render_rows),'packagingHits':len(packaging_rows),'otherHits':len(other_rows),'renderConsumerBundles':len(agg),'treeFailures':len(tree_failures),'loadFailures':len(load_failures)},
 'byMaterial':dict(by_material),'renderBundleAggregate':agg,'diagnostics':{'treeFailures':tree_failures,'loadFailures':load_failures},
 'guardrails':{'labBranchOnly':True,'mainUntouched':True,'historicalOffsetsReused':False,'serializedReferenceEvidenceNotRuntimeProof':True,'generatedVisuals':False}
}
outp.write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n','utf-8')

lines=['WfGg Last War — SELECTED MATERIAL RENDER CONSUMERS V1','',
 f"closureBundles=195 objectsInventoried={len(objects)} ptrsScanned={ptr_total} materials=5 directHits={len(material_hits)} renderHits={len(render_rows)} packagingHits={len(packaging_rows)} otherHits={len(other_rows)} renderConsumerBundles={len(agg)} treeFailures={len(tree_failures)} loadFailures={len(load_failures)}",'',
 'MATERIAL TARGETS']
for key,m in sorted(material_targets.items(),key=lambda kv:kv[1]['name']):
    lines.append(f"  material={m['name']} bundle=14169 pathID={m['pathID']} serializedFile={m['serializedFile']} textures={' | '.join(m['sourceTextures'])}")
lines+=['','RENDER CONSUMER BUNDLES']
if not agg:lines.append('  NONE')
for b in agg:
    lines.append('='*104)
    lines.append(f"bundle={b['bundleId']} labels={' | '.join(b['bundleLabels']) or '-'} materials={b['materialCount']}/5 renderHits={b['renderHitCount']}")
    lines.append('  materials='+' | '.join(b['materials']))
    for o in b['renderObjects']:lines.append(f"  render type={o['type']} name={o['name'] or '-'} pathID={o['pathID']}")
    for g in b['gameObjects']:lines.append(f"  gameObject name={g['name'] or '-'} pathID={g['pathID']}")
lines+=['','BY MATERIAL']
for name in sorted(by_material):
    r=by_material[name];lines.append('='*104);lines.append(f"material={name} render={len(r['render'])} packaging={len(r['packaging'])} other={len(r['other'])}")
    for x in r['render']:
        s=x['source'];go=x.get('ownerGameObject') or {}
        lines.append(f"  RENDER bundle={s['bundleId']} labels={' | '.join(s.get('bundleLabels') or []) or '-'} type={s['type']} name={s['name'] or '-'} pathID={s['pathID']} field={x['fieldPath']} ownerGO={go.get('name') or '-'} ownerGOPathID={go.get('pathID') or '-'}")
        for z in x.get('sourceMeshLinks',[]):lines.append(f"    mesh field={z['fieldPath']} name={z['target']['name'] or '-'} pathID={z['target']['pathID']} bundle={z['target']['bundleId']}")
        for z in x.get('sourceTerrainDataLinks',[]):lines.append(f"    terrainData field={z['fieldPath']} name={z['target']['name'] or '-'} pathID={z['target']['pathID']} bundle={z['target']['bundleId']}")
        for sib in x.get('siblingComponents',[]):
            c=sib['component'];lines.append(f"    sibling type={c['type']} name={c['name'] or '-'} pathID={c['pathID']}")
            for z in sib.get('meshLinks',[]):lines.append(f"      mesh name={z['target']['name'] or '-'} pathID={z['target']['pathID']} bundle={z['target']['bundleId']}")
            for z in sib.get('terrainDataLinks',[]):lines.append(f"      terrainData name={z['target']['name'] or '-'} pathID={z['target']['pathID']} bundle={z['target']['bundleId']}")
    for x in r['other']:
        s=x['source'];lines.append(f"  OTHER bundle={s['bundleId']} type={s['type']} name={s['name'] or '-'} pathID={s['pathID']} field={x['fieldPath']}")
    for x in r['packaging'][:12]:
        s=x['source'];lines.append(f"  PACKAGING bundle={s['bundleId']} type={s['type']} name={s['name'] or '-'} field={x['fieldPath']}")
lines+=['','DIAGNOSTICS',f'treeFailures={len(tree_failures)} loadFailures={len(load_failures)}',
 'RULE: RENDER means a direct serialized PPtr from a renderer/terrain class to one of the five exact Material targets.',
 'RULE: PACKAGING AssetBundle preload/container references are reported separately and are not treated as render use.',
 'RULE: owner GameObject and sibling component links are exact serialized references when resolved.',
 'RULE: serialized references are stronger than co-location but still do not prove runtime activation.',
 'RULE: current cached 195-bundle closure only; no historical offsets reused.',
 'RULE: no visual generated.']
reportp.write_text('\n'.join(lines)+'\n','utf-8')
print('MATERIAL_RENDER_CONSUMERS_V1_OK',f'renderHits={len(render_rows)}',f'renderBundles={len(agg)}',f'treeFailures={len(tree_failures)}',flush=True)
print('MATERIAL_RENDER_CONSUMERS_V1_REPORT',reportp,flush=True)
print('MATERIAL_RENDER_CONSUMERS_V1_JSON',outp,flush=True)
PY

git add "$OUT"
if ! git diff --cached --quiet; then
  git commit -m "lab: trace selected Formation material render consumers V1"
  git push origin "$BRANCH"
fi

echo "=== MATERIAL RENDER CONSUMERS V1 TERMINE ==="
echo "Rapport: $REPORT"
echo "main/preview inchangés. Aucun visuel généré."
