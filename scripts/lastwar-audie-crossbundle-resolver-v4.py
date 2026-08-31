from pathlib import Path
from collections import defaultdict
import json,re,sys
import UnityPy

ROOT=Path(sys.argv[1])
V3=ROOT/'frontend/lab/master-assets-v2/meta/audie-material-map-v3.json'
OUT=ROOT/'frontend/lab/master-assets-v2/meta/audie-crossbundle-v4.json'
UnityPy.config.FALLBACK_UNITY_VERSION='2019.4.41f1'

if not V3.exists():
    raise SystemExit('V3 absente')
V=json.loads(V3.read_text('utf-8'))

def aliases(s):
    if not s:return set()
    s=str(s).replace('\\','/')
    b=Path(s).name.lower(); out={b}
    if '.' in b: out.add(b.rsplit('.',1)[0])
    return {x for x in out if x}

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
def externals_from_af(af):
    out=[]
    for e in list(getattr(af,'externals',[]) or []):
        s=''
        for a in ('path','name','file_name'):
            x=getattr(e,a,None)
            if x:s=str(x);break
        if not s:s=str(e)
        out.append(s)
    return out
def ptrs(tree):
    out=[]
    def walk(x,path):
        if isinstance(x,dict):
            if 'm_FileID' in x and 'm_PathID' in x:
                try:f=int(x.get('m_FileID') or 0);p=int(x.get('m_PathID') or 0)
                except:f=p=0
                if p:out.append((path,f,p))
            for k,v in x.items():walk(v,f'{path}.{k}' if path else str(k))
        elif isinstance(x,list):
            for i,v in enumerate(x):walk(v,f'{path}[{i}]')
    walk(tree,'');return out
def readtree(o):
    try:return o.read_typetree()
    except:return None
def bid(p):
    m=re.search(r'bundle-(\d+)\.bundle$',p.name)
    return int(m.group(1)) if m else None

def bundle_files():
    seen=set(); out=[]
    for base in (ROOT/'frontend/lab/local_assets', Path.home()/'.cache'):
        if not base.exists(): continue
        for p in base.rglob('*.bundle'):
            try:k=str(p.resolve())
            except:k=str(p)
            if k not in seen:seen.add(k);out.append(p)
    return sorted(out,key=str)

# Exact Audie Texture2D targets from V3, keyed by serialized-file alias + pathID.
tex_targets=[]; tex_by_key=defaultdict(list); tex_aliases=set()
for t in V.get('textures',[]):
    rec={k:t.get(k) for k in ('bundleId','bundlePath','serializedFile','pathID','name','variant','role','width','height','format')}
    tex_targets.append(rec)
    for a in aliases(t.get('serializedFile')):
        tex_aliases.add(a); tex_by_key[(a,int(t.get('pathID') or 0))].append(rec)

paths=bundle_files()
print('AUDIE_CROSSBUNDLE_V4_START',f'bundles={len(paths)}',f'textureTargets={len(tex_targets)}',flush=True)

# PHASE 1 — cheap reverse dependency discovery: only inspect serialized-file external tables.
dep_candidates=[]; dep_hits=[]; errors=[]
for i,p in enumerate(paths,1):
    if i==1 or i%50==0: print('V4_PHASE1_DEPENDENCIES',f'{i}/{len(paths)}',p.name,flush=True)
    try:
        env=UnityPy.load(str(p)); objs=list(getattr(env,'objects',[]) or [])
    except Exception as e:
        errors.append({'phase':1,'path':str(p),'error':f'{type(e).__name__}:{e}'}); continue
    afs={}
    for o in objs:
        af=getattr(o,'assets_file',None)
        if af is not None: afs[id(af)]=af
    matched=[]
    for af in afs.values():
        for idx,ep in enumerate(externals_from_af(af),1):
            aa=aliases(ep)
            hit=sorted(aa & tex_aliases)
            if hit: matched.append({'sourceSerializedFile':str(getattr(af,'name','') or getattr(af,'path','')),'fileID':idx,'externalPath':ep,'matchedAliases':hit})
    # Include original texture bundles for local pointer checks.
    contains_target=any(str(p)==str(t.get('bundlePath')) for t in tex_targets)
    if matched or contains_target:
        dep_candidates.append(p)
        dep_hits.append({'bundleId':bid(p),'path':str(p),'externalMatches':matched,'containsTargetTexture':contains_target})

print('V4_PHASE1_READY',f'candidates={len(dep_candidates)}',flush=True)

# PHASE 2 — scan only candidate Materials for direct serialized PPtr references to Audie textures.
material_links=[]; material_targets=defaultdict(list); preload_hits=[]
for i,p in enumerate(dep_candidates,1):
    print('V4_PHASE2_MATERIALS',f'{i}/{len(dep_candidates)}',p.name,flush=True)
    try:
        env=UnityPy.load(str(p)); objs=list(getattr(env,'objects',[]) or [])
    except Exception as e:
        errors.append({'phase':2,'path':str(p),'error':f'{type(e).__name__}:{e}'}); continue
    af_ext={}
    for o in objs:
        sf=afkey(o)
        if sf not in af_ext:af_ext[sf]=externals_from_af(getattr(o,'assets_file',None))
    for o in objs:
        t=typ(o)
        if t not in ('Material','AssetBundle'):continue
        tree=readtree(o)
        if tree is None:continue
        sf=afkey(o); ex=af_ext.get(sf,[])
        for field,fid,tp in ptrs(tree):
            if t=='Material' and not ('TexEnv' in field or 'm_Texture' in field or 'm_TexEnvs' in field):continue
            candidate=[]; ep=''
            if fid==0:
                for a in aliases(sf): candidate += tex_by_key.get((a,tp),[])
            else:
                ep=ex[fid-1] if fid>0 and fid-1<len(ex) else ''
                for a in aliases(ep): candidate += tex_by_key.get((a,tp),[])
            if not candidate:continue
            if t=='AssetBundle':
                preload_hits.append({'bundleId':bid(p),'bundlePath':str(p),'serializedFile':sf,'assetBundlePathID':str(pid(o)),'field':field,'fileID':fid,'targetPathID':str(tp),'externalPath':ep,'textures':candidate})
                continue
            rec={'bundleId':bid(p),'bundlePath':str(p),'materialSerializedFile':sf,'materialPathID':str(pid(o)),'materialName':pname(o),'field':field,'fileID':fid,'targetPathID':str(tp),'externalPath':ep,'textures':candidate}
            material_links.append(rec)
            for a in aliases(sf): material_targets[(a,pid(o))].append(rec)

print('V4_PHASE2_READY',f'materialLinks={len(material_links)}',f'preloadHits={len(preload_hits)}',flush=True)

# PHASE 3 — reverse dependency discovery for the newly found Materials.
renderer_candidates=[]; renderer_dep_hits=[]
mat_aliases={a for a,_ in material_targets.keys()}
if material_links:
    material_bundle_paths={x['bundlePath'] for x in material_links}
    for i,p in enumerate(paths,1):
        if i==1 or i%50==0:print('V4_PHASE3_RENDERER_DEPS',f'{i}/{len(paths)}',p.name,flush=True)
        try:
            env=UnityPy.load(str(p)); objs=list(getattr(env,'objects',[]) or [])
        except Exception as e:
            errors.append({'phase':3,'path':str(p),'error':f'{type(e).__name__}:{e}'});continue
        afs={}
        for o in objs:
            af=getattr(o,'assets_file',None)
            if af is not None:afs[id(af)]=af
        matched=[]
        for af in afs.values():
            for idx,ep in enumerate(externals_from_af(af),1):
                hit=sorted(aliases(ep)&mat_aliases)
                if hit:matched.append({'sourceSerializedFile':str(getattr(af,'name','') or getattr(af,'path','')),'fileID':idx,'externalPath':ep,'matchedAliases':hit})
        contains=str(p) in material_bundle_paths
        if matched or contains:
            renderer_candidates.append(p);renderer_dep_hits.append({'bundleId':bid(p),'path':str(p),'externalMatches':matched,'containsMaterial':contains})

# PHASE 4 — renderer/material reverse links and local GO/Mesh resolution.
chains=[]
for i,p in enumerate(renderer_candidates,1):
    print('V4_PHASE4_RENDERERS',f'{i}/{len(renderer_candidates)}',p.name,flush=True)
    try:
        env=UnityPy.load(str(p));objs=list(getattr(env,'objects',[]) or [])
    except Exception as e:
        errors.append({'phase':4,'path':str(p),'error':f'{type(e).__name__}:{e}'});continue
    byfile=defaultdict(dict); af_ext={}
    for o in objs:
        sf=afkey(o);byfile[sf][pid(o)]=o
        if sf not in af_ext:af_ext[sf]=externals_from_af(getattr(o,'assets_file',None))
    def local_target(source,fid,tp):
        sf=afkey(source)
        if fid==0:return byfile.get(sf,{}).get(tp)
        return None
    # MeshFilters indexed by GameObject pathID in same serialized file.
    mf_by_go={}
    for o in objs:
        if typ(o)!='MeshFilter':continue
        tr=readtree(o)
        if tr is None:continue
        go=None;mesh=None
        for field,fid,tp in ptrs(tr):
            tar=local_target(o,fid,tp);tt=typ(tar) if tar is not None else ''
            if tt=='GameObject' and go is None:go=(afkey(o),tp,pname(tar))
            if tt=='Mesh' and mesh is None:mesh={'serializedFile':afkey(o),'pathID':str(tp),'name':pname(tar)}
        if go and mesh:mf_by_go[(go[0],go[1])]=mesh
    for o in objs:
        if typ(o) not in ('MeshRenderer','SkinnedMeshRenderer'):continue
        tr=readtree(o)
        if tr is None:continue
        sf=afkey(o);ex=af_ext.get(sf,[]);hits=[];go=None;mesh=None
        for field,fid,tp in ptrs(tr):
            tar=local_target(o,fid,tp);tt=typ(tar) if tar is not None else ''
            if tt=='GameObject' and go is None:go={'serializedFile':sf,'pathID':str(tp),'name':pname(tar)}
            if tt=='Mesh' and mesh is None:mesh={'serializedFile':sf,'pathID':str(tp),'name':pname(tar)}
            mats=[]; ep=''
            if fid==0:
                for a in aliases(sf):mats+=material_targets.get((a,tp),[])
            else:
                ep=ex[fid-1] if fid>0 and fid-1<len(ex) else ''
                for a in aliases(ep):mats+=material_targets.get((a,tp),[])
            if mats:hits.append({'field':field,'fileID':fid,'materialPathID':str(tp),'externalPath':ep,'materials':mats})
        if not hits:continue
        if mesh is None and go is not None:
            mesh=mf_by_go.get((go['serializedFile'],int(go['pathID'])))
        chains.append({'bundleId':bid(p),'bundlePath':str(p),'rendererType':typ(o),'rendererName':pname(o),'rendererSerializedFile':sf,'rendererPathID':str(pid(o)),'gameObject':go,'mesh':mesh,'materialHits':hits,'reconstructible':bool(mesh)})

if chains: verdict='CROSS_BUNDLE_RENDERER_MESH_CHAIN_FOUND' if any(x['reconstructible'] for x in chains) else 'CROSS_BUNDLE_RENDERER_FOUND_MESH_UNRESOLVED'
elif material_links: verdict='CROSS_BUNDLE_MATERIAL_FOUND_RENDERER_UNRESOLVED'
elif preload_hits: verdict='AUDIE_TEXTURE_PACKAGED_NO_SERIALIZED_MATERIAL_CONSUMER'
else: verdict='NO_SERIALIZED_CONSUMER_FOUND_RUNTIME_BINDING_LIKELY'

res={'format':'WFGG_LASTWAR_AUDIE_CROSSBUNDLE_V4','verdict':verdict,'bundleFilesScanned':len(paths),'textureTargets':tex_targets,'dependencyCandidates':dep_hits,'materialLinks':material_links,'preloadHits':preload_hits,'rendererDependencyCandidates':renderer_dep_hits,'chains':chains,'stats':{'textureTargets':len(tex_targets),'dependencyCandidates':len(dep_candidates),'materialLinks':len(material_links),'preloadHits':len(preload_hits),'rendererCandidates':len(renderer_candidates),'chains':len(chains),'reconstructibleChains':sum(1 for x in chains if x['reconstructible'])},'errors':errors[:300],'rules':['Phase 1 scans only external serialized-file tables across the full local bundle corpus.','A Material link is accepted only when its PPtr target matches both the serialized-file alias and pathID of an exact Audie Texture2D.','Renderer links are resolved in a second reverse pass from the proven Material serialized-file/pathID targets.','No link is inferred from filenames or bundle proximity alone.','If no serialized Material consumer exists, runtime/script shader binding remains the leading explanation.']}
OUT.parent.mkdir(parents=True,exist_ok=True);OUT.write_text(json.dumps(res,ensure_ascii=False,indent=2)+'\n','utf-8')
print('AUDIE_CROSSBUNDLE_V4_READY',f'verdict={verdict}',f'materials={len(material_links)}',f'chains={len(chains)}',f'reconstructible={sum(1 for x in chains if x["reconstructible"])}',flush=True)
print('JSON='+str(OUT),flush=True)
