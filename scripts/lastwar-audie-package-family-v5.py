#!/data/data/com.termux/files/usr/bin/python
from pathlib import Path
from collections import Counter, defaultdict
import json,re,sys
import UnityPy

ROOT=Path(sys.argv[1]).resolve()
V1=ROOT/'frontend/lab/master-assets-v2/meta/audie-family-scan-v1.json'
V4=ROOT/'frontend/lab/master-assets-v2/meta/audie-crossbundle-v4.json'
OUT=ROOT/'frontend/lab/master-assets-v2/meta/audie-package-family-v5.json'
UnityPy.config.FALLBACK_UNITY_VERSION='2019.4.41f1'

print('AUDIE_PACKAGE_FAMILY_V5_START', flush=True)
v1=json.loads(V1.read_text('utf-8'))
v4=json.loads(V4.read_text('utf-8')) if V4.exists() else {}

def strings(x):
    if isinstance(x,str):
        yield x
    elif isinstance(x,dict):
        for v in x.values(): yield from strings(v)
    elif isinstance(x,list):
        for v in x: yield from strings(v)

def category(text):
    s=str(text).lower().replace('\\','/')
    rules=[
      ('texture',r'(^|[/_])textures?([/_]|$)'),
      ('material',r'(^|[/_])materials?([/_]|$)'),
      ('animation',r'(^|[/_])animations?([/_]|$)'),
      ('prefab',r'(^|[/_])prefabs?([/_]|$)'),
      ('mesh',r'(^|[/_])meshes?([/_]|$)'),
      ('skin',r'(^|[/_])skins?([/_]|$)'),
      ('bullet',r'(^|[/_])bullet([/_]|$)'),
      ('camera',r'(^|[/_])camera([/_]|$)'),
      ('timeline',r'(^|[/_])timeline([/_]|$)'),
    ]
    for k,p in rules:
        if re.search(p,s): return k
    return 'other'

def bid_from_any(x):
    if isinstance(x,dict):
        for k in ('bundleId','bundleID','id'):
            try:
                if k in x and str(x[k]).isdigit(): return int(x[k])
            except: pass
    return None

def typ(o): return str(getattr(getattr(o,'type',None),'name','') or '')
def pname(o):
    try:return str(o.peek_name() or '')
    except:return ''

# 1) The V1 master-index hits already contain every indexed bundle record mentioning Audie.
idx=[]
for r in v1.get('indexHits',[]):
    ss=sorted({s for s in strings(r) if 'audie' in s.lower()})
    if not ss: continue
    txt=' | '.join(ss)
    idx.append({'bundleId':bid_from_any(r),'category':category(txt),'audieStrings':ss,'record':r})

# 2) Build a physical bundle catalogue. We intentionally include named package files and bundle-ID aliases.
roots=[ROOT/'frontend/lab/local_assets', Path.home()/'.cache']
paths=[]; seen=set()
for base in roots:
    if not base.exists(): continue
    for p in base.rglob('*.bundle'):
        try:k=str(p.resolve())
        except:k=str(p)
        if k in seen: continue
        seen.add(k); paths.append(p)
print('AUDIE_PACKAGE_FAMILY_V5_CATALOG',f'bundles={len(paths)}',flush=True)

by_bid=defaultdict(list)
for p in paths:
    m=re.search(r'(?:bundle|candidate)-(\d+)\.bundle$',p.name,re.I)
    if m: by_bid[int(m.group(1))].append(p)

cand=set()
# Directly named Audie package files are strongest nomenclature evidence.
for p in paths:
    n=p.name.lower()
    if 'audie' in n or 'a_hero_audie_01' in n: cand.add(p)
# Resolve every index-hit bundle ID to any local physical alias.
for r in idx:
    if r['bundleId'] is not None:
        cand.update(by_bid.get(r['bundleId'],[]))
# Retain all physically proven Audie bundles from V1.
for b in v1.get('hitBundles',[]):
    p=Path(str(b.get('path') or ''))
    if p.is_file(): cand.add(p)
# Retain V4 candidate paths if present.
for s in strings(v4.get('candidates',[])):
    p=Path(s)
    if p.is_file(): cand.add(p)

cand=sorted(cand,key=lambda p:p.name.lower())
print('AUDIE_PACKAGE_FAMILY_V5_CANDIDATES',len(cand),flush=True)

keep_types={'AssetBundle','GameObject','Transform','Mesh','MeshFilter','MeshRenderer','SkinnedMeshRenderer','Material','Texture2D','AnimationClip','Animator','AnimatorController','Avatar','MonoBehaviour','Shader'}
scanned=[]; errors=[]; mesh_carriers=[]
for i,p in enumerate(cand,1):
    print('AUDIE_PACKAGE_FAMILY_V5_SCAN',f'{i}/{len(cand)}',p.name,flush=True)
    try:
        env=UnityPy.load(str(p)); objs=list(getattr(env,'objects',[]) or [])
    except Exception as e:
        errors.append({'path':str(p),'error':f'{type(e).__name__}:{e}'}); continue
    counts=Counter(typ(o) for o in objs)
    names=defaultdict(list)
    audie=[]
    for o in objs:
        t=typ(o); n=pname(o)
        if n and 'audie' in n.lower(): audie.append({'type':t,'name':n,'pathID':str(getattr(o,'path_id',0) or 0)})
        if t in keep_types and n and len(names[t])<80: names[t].append(n)
    m=re.search(r'(?:bundle|candidate)-(\d+)\.bundle$',p.name,re.I)
    bid=int(m.group(1)) if m else None
    cat=category(p.name+' '+' '.join(x['name'] for x in audie[:20]))
    rec={
      'path':str(p),'basename':p.name,'bundleId':bid,'category':cat,'objectCount':len(objs),
      'counts':dict(counts),'audieNamed':audie[:250],
      'samples':{k:v for k,v in names.items()},
      'meshCount':counts.get('Mesh',0),'meshRendererCount':counts.get('MeshRenderer',0),
      'skinnedMeshRendererCount':counts.get('SkinnedMeshRenderer',0),'meshFilterCount':counts.get('MeshFilter',0),
      'materialCount':counts.get('Material',0),'textureCount':counts.get('Texture2D',0),
      'gameObjectCount':counts.get('GameObject',0),'animationClipCount':counts.get('AnimationClip',0)
    }
    scanned.append(rec)
    if rec['meshCount'] or rec['meshRendererCount'] or rec['skinnedMeshRendererCount'] or rec['meshFilterCount']:
        mesh_carriers.append(rec)

cat_index=Counter(x['category'] for x in idx)
cat_local=Counter(x['category'] for x in scanned)
# Extract the strongest package-family strings for human inspection.
package_names=[]
for r in idx:
    for s in r['audieStrings']:
        z=s.lower()
        if 'a_hero_audie_01' in z or 'hero_audie' in z:
            package_names.append(s)
for r in scanned:
    if 'audie' in r['basename'].lower(): package_names.append(r['basename'])
package_names=sorted(set(package_names),key=str.lower)

if mesh_carriers:
    verdict='MESH_CARRIER_FOUND'
elif any(k in cat_index for k in ('mesh','prefab')):
    verdict='MODEL_FAMILY_INDEXED_BUT_NOT_LOCAL'
elif idx:
    verdict='AUDIE_PACKAGE_FAMILY_MAPPED_NO_MESH_CARRIER_YET'
else:
    verdict='NO_AUDIE_PACKAGE_INDEX_EVIDENCE'

res={
 'format':'WFGG_LASTWAR_AUDIE_PACKAGE_FAMILY_V5',
 'verdict':verdict,
 'indexHitCount':len(idx),
 'physicalCandidateCount':len(cand),
 'scannedCandidateCount':len(scanned),
 'meshCarrierCount':len(mesh_carriers),
 'indexCategories':dict(cat_index),
 'localCategories':dict(cat_local),
 'packageNames':package_names,
 'indexHits':idx,
 'bundles':scanned,
 'meshCarriers':mesh_carriers,
 'v4Summary':{
   'verdict':v4.get('verdict'),
   'materialLinks':v4.get('materialLinks',v4.get('materialLinkCount',0)),
   'preloadHits':v4.get('preloadHits',v4.get('preloadHitCount',0)),
   'chains':v4.get('chains',v4.get('chainCount',0))
 },
 'errors':errors[:200],
 'rules':[
   'V5 uses the package nomenclature revealed by V4 instead of assuming Texture→Material PPtrs exist.',
   'Every master-index record mentioning Audie is grouped by package role; the word models in the common root is not treated as proof of a mesh package.',
   'A mesh carrier is reported only when a locally loaded Unity bundle actually contains Mesh/MeshFilter/MeshRenderer/SkinnedMeshRenderer objects.',
   'No filename category is treated as a reconstruction link by itself.'
 ]
}
OUT.parent.mkdir(parents=True,exist_ok=True)
OUT.write_text(json.dumps(res,ensure_ascii=False,indent=2)+'\n','utf-8')
print('AUDIE_PACKAGE_FAMILY_V5_READY',f'verdict={verdict}',f'indexHits={len(idx)}',f'candidates={len(cand)}',f'meshCarriers={len(mesh_carriers)}',flush=True)
print('INDEX_CATEGORIES='+json.dumps(dict(cat_index),ensure_ascii=False),flush=True)
print('LOCAL_CATEGORIES='+json.dumps(dict(cat_local),ensure_ascii=False),flush=True)
for x in mesh_carriers[:20]:
    print('MESH_CARRIER',x['basename'],f"mesh={x['meshCount']}",f"mr={x['meshRendererCount']}",f"smr={x['skinnedMeshRendererCount']}",f"mf={x['meshFilterCount']}",flush=True)
print('JSON='+str(OUT),flush=True)
