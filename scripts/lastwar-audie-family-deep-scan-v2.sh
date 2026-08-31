#!/data/data/com.termux/files/usr/bin/bash
set -Eeuo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BRANCH="portal-auth-lastwar-lab-v1"
V1="$ROOT/frontend/lab/master-assets-v2/meta/audie-family-scan-v1.json"
OUT="$ROOT/frontend/lab/master-assets-v2/meta/audie-family-deep-scan-v2.json"
INDEX="$ROOT/frontend/lab/master-assets-v2/index/lastwar-graphics-master-index-v1.json"
UNITY_VERSION="2019.4.41f1"
cd "$ROOT"
[[ "$(git branch --show-current)" == "$BRANCH" ]] || { echo "ERREUR: branche LAB incorrecte" >&2; exit 1; }
[[ -s "$V1" ]] || bash "$ROOT/scripts/lastwar-audie-family-scan-v1.sh"
[[ -s "$V1" ]] || { echo "ERREUR: scan Audie V1 absent" >&2; exit 1; }
command -v python >/dev/null 2>&1 || { echo "ERREUR: python absent" >&2; exit 1; }
python - <<'PYCHK' >/dev/null 2>&1 || { echo "ERREUR: UnityPy absent" >&2; exit 1; }
import UnityPy
PYCHK

echo "AUDIE_DEEP_SCAN_V2_START"
PYTHONUNBUFFERED=1 python - "$V1" "$OUT" "$INDEX" "$UNITY_VERSION" <<'PY'
from pathlib import Path
from collections import Counter,defaultdict,deque
import json,re,sys
import UnityPy

v1p=Path(sys.argv[1]); outp=Path(sys.argv[2]); idxp=Path(sys.argv[3]); uv=sys.argv[4]
UnityPy.config.FALLBACK_UNITY_VERSION=uv
v1=json.loads(v1p.read_text('utf-8'))
idx=json.loads(idxp.read_text('utf-8')) if idxp.exists() else {'bundles':[]}

# Logical-name lookup used only as a labelled heuristic for external serialized-file paths.
name_to_bids=defaultdict(set)
for r in idx.get('bundles',[]):
    if not isinstance(r,dict): continue
    try: bid=int(r.get('bundleId'))
    except Exception: continue
    vals=[]
    for k in ('logicalName','aliasName','name'):
        if r.get(k): vals.append(str(r[k]))
    vals += [str(x) for x in (r.get('assetPaths') or [])]
    for s in vals:
        b=Path(s).name.lower()
        if b: name_to_bids[b].add(bid)
        if '.' in b: name_to_bids[b.rsplit('.',1)[0]].add(bid)

def typ(o): return str(getattr(getattr(o,'type',None),'name','') or '')
def pid(o): return int(getattr(o,'path_id',0) or 0)
def pname(o):
    try:return str(o.peek_name() or '')
    except:return ''
def afkey(o):
    af=getattr(o,'assets_file',None)
    for a in ('name','path'):
        x=getattr(af,a,None)
        if x:return str(x)
    return f'assetsfile@{id(af)}'
def get_externals(o):
    af=getattr(o,'assets_file',None)
    ex=[]
    for e in list(getattr(af,'externals',[]) or []):
        s=''
        for a in ('path','name','file_name'):
            x=getattr(e,a,None)
            if x: s=str(x); break
        if not s: s=str(e)
        ex.append(s)
    return ex

def ptrs(tree):
    out=[]
    def walk(x,path):
        if isinstance(x,dict):
            keys=set(x)
            if 'm_FileID' in keys and 'm_PathID' in keys:
                try: f=int(x.get('m_FileID') or 0); p=int(x.get('m_PathID') or 0)
                except Exception: f=p=0
                if p: out.append((path,f,p))
            for k,v in x.items(): walk(v,f'{path}.{k}' if path else str(k))
        elif isinstance(x,list):
            for i,v in enumerate(x): walk(v,f'{path}[{i}]')
    walk(tree,'')
    return out

def read_tree(o):
    try:return o.read_typetree(),None
    except Exception as e:return None,f'{type(e).__name__}:{e}'

def external_candidates(path):
    if not path:return []
    b=Path(path.replace('\\','/')).name.lower()
    keys=[b]
    if '.' in b: keys.append(b.rsplit('.',1)[0])
    z=set()
    for k in keys:z.update(name_to_bids.get(k,set()))
    return sorted(z)

def path_aliases(s):
    if not s:return set()
    s=str(s).replace('\\','/')
    b=Path(s).name.lower(); out={b}
    if '.' in b: out.add(b.rsplit('.',1)[0])
    return {x for x in out if x}

hit_paths=[]
for b in v1.get('hitBundles',[]):
    p=b.get('path')
    if p and Path(p).is_file(): hit_paths.append(Path(p))
seen_real=set(); paths=[]
for p in hit_paths:
    try:key=str(p.resolve())
    except:key=str(p)
    if key not in seen_real: seen_real.add(key); paths.append(p)

all_assets=[]; all_edges=[]; all_material_slots=[]; bundles=[]; errors=[]; exact_textures=[]
AUDIE_TYPES=Counter(); exact_suffix=Counter()
interesting_types={'Material','GameObject','MeshRenderer','SkinnedMeshRenderer','MeshFilter','Transform','RectTransform','Animator','Animation','MonoBehaviour','Mesh','Texture2D','Shader','Avatar','AnimationClip'}

for pos,p in enumerate(paths,1):
    print('AUDIE_DEEP_SCAN_V2_BUNDLE',f'{pos}/{len(paths)}',p.name,flush=True)
    try: env=UnityPy.load(str(p)); objs=list(getattr(env,'objects',[]) or [])
    except Exception as e:
        errors.append({'path':str(p),'error':f'{type(e).__name__}:{e}'}); continue
    m=re.search(r'bundle-(\d+)\.bundle$',p.name); bid=int(m.group(1)) if m else None

    # pathID is scoped to the serialized file. Never resolve on pathID alone across the whole bundle.
    byfile=defaultdict(dict); meta=defaultdict(dict); alias_to_file={}
    for o in objs:
        sf=afkey(o); q=pid(o); byfile[sf][q]=o; meta[sf][q]={'type':typ(o),'name':pname(o)}
        for a in path_aliases(sf): alias_to_file.setdefault(a,sf)

    seeds=set(); audie_named=[]
    for o in objs:
        n=pname(o); t=typ(o); sf=afkey(o); q=pid(o)
        if n and 'audie' in n.lower():
            key=(sf,q); seeds.add(key); audie_named.append(key); AUDIE_TYPES[t]+=1
            rec={'bundleId':bid,'bundlePath':str(p),'serializedFile':sf,'pathID':str(q),'type':t,'name':n}
            all_assets.append(rec)
            if t=='Texture2D' and re.search(r'A_Hero_Audie_01',n,re.I):
                try:
                    d=o.read(); rec2=dict(rec,width=int(d.m_Width),height=int(d.m_Height),format=str(getattr(d,'m_TextureFormat','')))
                except Exception as ex: rec2=dict(rec,readError=f'{type(ex).__name__}:{ex}')
                exact_textures.append(rec2)
                mm=re.search(r'A_Hero_Audie_01(?:_High)?_([A-Za-z0-9]+)$',n,re.I)
                if mm: exact_suffix[mm.group(1).upper()]+=1

    # Parse graph lazily from Audie seeds and local/internal-bundle PPtrs, depth <= 4.
    parsed={}; q=deque((s,0) for s in seeds); queued=set(seeds); local_edges=[]
    while q:
        (sf,sp),depth=q.popleft(); so=byfile.get(sf,{}).get(sp)
        if so is None or typ(so) not in interesting_types: continue
        key=(sf,sp)
        if key not in parsed: parsed[key]=read_tree(so)
        tree,err=parsed[key]
        if tree is None: continue
        exts=get_externals(so)
        for field,fid,tp in ptrs(tree):
            extpath=exts[fid-1] if fid>0 and fid-1<len(exts) else ''
            target_sf=sf if fid==0 else None
            if fid>0 and extpath:
                for a in path_aliases(extpath):
                    if a in alias_to_file:
                        target_sf=alias_to_file[a]; break
            target=meta.get(target_sf,{}).get(tp) if target_sf else None
            edge={'bundleId':bid,'sourceSerializedFile':sf,'sourcePathID':str(sp),'sourceType':typ(so),'sourceName':pname(so),'field':field,'fileID':fid,'targetPathID':str(tp),'externalPath':extpath,'externalBundleCandidates':external_candidates(extpath)}
            if target:
                edge.update({'targetSerializedFile':target_sf,'targetType':target['type'],'targetName':target['name'],'localResolved':True,'resolution':'same-serialized-file' if fid==0 else 'same-bundle-external-file'})
            else: edge.update({'localResolved':False,'resolution':'external-or-unavailable'})
            local_edges.append(edge); all_edges.append(edge)
            tkey=(target_sf,tp) if target_sf else None
            if target and depth<4 and tkey not in queued:
                queued.add(tkey); q.append((tkey,depth+1))

    reached={(e.get('targetSerializedFile'),int(e['targetPathID'])) for e in local_edges if e.get('localResolved') and e.get('targetSerializedFile')}
    mats={x for x in seeds|reached if x[0] in byfile and x[1] in byfile[x[0]] and typ(byfile[x[0]][x[1]])=='Material'}
    for sf,mp in sorted(mats,key=lambda x:(x[0],x[1])):
        mo=byfile[sf][mp]; tree,err=parsed.get((sf,mp),(None,None))
        if tree is None: tree,err=read_tree(mo)
        if tree is None: continue
        exts=get_externals(mo); slots=[]
        for field,fid,tp in ptrs(tree):
            if 'TexEnv' not in field and 'm_Texture' not in field and 'm_TexEnvs' not in field: continue
            extpath=exts[fid-1] if fid>0 and fid-1<len(exts) else ''
            target_sf=sf if fid==0 else None
            if fid>0 and extpath:
                for a in path_aliases(extpath):
                    if a in alias_to_file: target_sf=alias_to_file[a]; break
            tar=meta.get(target_sf,{}).get(tp) if target_sf else None
            slot={'field':field,'fileID':fid,'pathID':str(tp),'externalPath':extpath,'externalBundleCandidates':external_candidates(extpath)}
            if tar: slot.update({'targetSerializedFile':target_sf,'targetType':tar['type'],'targetName':tar['name'],'localResolved':True})
            else: slot['localResolved']=False
            slots.append(slot)
        all_material_slots.append({'bundleId':bid,'serializedFile':sf,'materialPathID':str(mp),'materialName':pname(mo),'slots':slots})

    bundles.append({'bundleId':bid,'path':str(p),'objectCount':len(objs),'serializedFiles':len(byfile),'audieNamedCount':len(audie_named),'seedCount':len(seeds),'parsedReachable':len(parsed),'edgeCount':len(local_edges),'materialCount':len(mats)})

by_type=defaultdict(list)
for a in all_assets: by_type[a['type']].append(a)
for t in by_type: by_type[t].sort(key=lambda x:(x.get('name','').lower(),x.get('bundleId') or -1,x.get('serializedFile',''),int(x.get('pathID') or 0)))

strong=[]
seen_strong=set()
def add_strong(e):
    k=(e.get('bundleId'),e.get('sourceSerializedFile') or e.get('serializedFile'),e.get('sourcePathID') or e.get('materialPathID'),e.get('field'),e.get('fileID'),e.get('targetPathID') or e.get('pathID'))
    if k not in seen_strong: seen_strong.add(k); strong.append(e)
for e in all_edges:
    if 'audie' in (e.get('sourceName') or '').lower() or 'audie' in (e.get('targetName') or '').lower(): add_strong(e)
for m in all_material_slots:
    if 'audie' in (m.get('materialName') or '').lower():
        for s in m['slots']:
            add_strong({'bundleId':m['bundleId'],'sourceSerializedFile':m['serializedFile'],'sourcePathID':m['materialPathID'],'sourceType':'Material','sourceName':m['materialName'],'field':s['field'],'fileID':s['fileID'],'targetPathID':s['pathID'],'externalPath':s['externalPath'],'externalBundleCandidates':s['externalBundleCandidates'],'targetSerializedFile':s.get('targetSerializedFile'),'targetType':s.get('targetType'),'targetName':s.get('targetName'),'localResolved':s.get('localResolved',False),'relation':'MATERIAL_TEXTURE_SLOT'})

res={
 'format':'WFGG_LASTWAR_AUDIE_FAMILY_DEEP_SCAN_V2',
 'sourceV1':str(v1p),
 'bundlesDeepScanned':len(bundles),
 'audieNamedAssets':len(all_assets),
 'audieTypes':dict(sorted(AUDIE_TYPES.items())),
 'exactAudieTextureCount':len(exact_textures),
 'exactTextureSuffixCounts':dict(sorted(exact_suffix.items())),
 'exactTextures':exact_textures,
 'assetsByType':dict(by_type),
 'materialSlots':all_material_slots,
 'strongEdges':strong,
 'allReachableEdges':all_edges,
 'bundles':bundles,
 'errors':errors[:200],
 'rules':[
   'Only bundles already proven by V1 to contain an Audie-named Unity object are deep-parsed.',
   'Suffix statistics shown as texture suffixes use Texture2D objects matching A_Hero_Audie_01 only; CAMERA/BULLET/etc are not automatically treated as image layers.',
   'pathID resolution is scoped to the exact serialized file; fileID=0 never resolves against a different serialized file.',
   'External fileID pointers are resolved inside the same bundle only when their external path exactly matches another loaded serialized file; otherwise they remain explicit and receive only labelled index-based bundle candidates.',
   'No mesh/material/texture relationship is invented: graph edges come from Unity typetree PPtr fields.'
 ]
}
outp.parent.mkdir(parents=True,exist_ok=True); outp.write_text(json.dumps(res,ensure_ascii=False,indent=2)+'\n','utf-8')
print('AUDIE_DEEP_SCAN_V2_READY',f'bundles={len(bundles)}',f'assets={len(all_assets)}',f'exactTextures={len(exact_textures)}',f'materialRecords={len(all_material_slots)}',f'strongEdges={len(strong)}',f'edges={len(all_edges)}',flush=True)
print('TEXTURE_SUFFIXES='+json.dumps(dict(exact_suffix),ensure_ascii=False),flush=True)
print('JSON='+str(outp),flush=True)
PY

echo "VIEWER=http://127.0.0.1:8788/lab/lastwar-audie-family-deep-viewer.html?v=2"