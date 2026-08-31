#!/data/data/com.termux/files/usr/bin/bash
set -Eeuo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BRANCH="portal-auth-lastwar-lab-v1"
SUMMARY="$ROOT/frontend/lab/master-assets-v2/meta/formation-ptr-exact-v4-summary-v1.json"
LOCAL="$ROOT/frontend/lab/local_assets/lastwar-formation-ptr-exact-v4/bundles"
BUNDLE_ID="${1:-14169}"
OUTDIR="$ROOT/frontend/lab/bundle-reconstruction-data/$BUNDLE_ID"
REPORT="$HOME/storage/downloads/WFGG_LASTWAR_BUNDLE_RECONSTRUCTION_VIEWER_${BUNDLE_ID}_V1.txt"
UNITY_VERSION="2019.4.41f1"
MAX_TEXTURES="${MAX_TEXTURES:-320}"
MAX_MESHES="${MAX_MESHES:-160}"

fail(){ printf 'ERREUR: %s\n' "$*" >&2; exit 1; }
cd "$ROOT"
[[ "$(git branch --show-current)" == "$BRANCH" ]] || fail "branche LAB incorrecte"
[[ -s "$SUMMARY" ]] || fail "summary V4 absent"
[[ -d "$LOCAL" ]] || fail "cache bundles V4 absent"
[[ -s "$LOCAL/bundle-$BUNDLE_ID.bundle" ]] || fail "bundle $BUNDLE_ID absent du cache V4"
command -v python >/dev/null 2>&1 || fail "python absent"
python - <<'PYCHK' >/dev/null 2>&1 || fail "UnityPy / texture2ddecoder / Pillow absents"
import UnityPy, texture2ddecoder
from PIL import Image
PYCHK
mkdir -p "$OUTDIR/textures" "$OUTDIR/meshes" "$(dirname "$REPORT")"
rm -f "$OUTDIR"/textures/*.png "$OUTDIR"/meshes/*.obj "$OUTDIR/manifest.json" 2>/dev/null || true

echo "BUNDLE_RECON_V1_START bundle=$BUNDLE_ID"
PYTHONUNBUFFERED=1 python - "$SUMMARY" "$LOCAL" "$OUTDIR" "$REPORT" "$BUNDLE_ID" "$UNITY_VERSION" "$MAX_TEXTURES" "$MAX_MESHES" <<'PY'
from __future__ import annotations
from pathlib import Path
from collections import Counter,defaultdict
import hashlib,json,math,re,sys
import UnityPy
import texture2ddecoder as t2d
from PIL import Image
from UnityPy.enums import TextureFormat

summaryp,localp,outdir,reportp=map(Path,sys.argv[1:5])
bundle_id=int(sys.argv[5]);unity_version=sys.argv[6];max_textures=int(sys.argv[7]);max_meshes=int(sys.argv[8])
UnityPy.config.FALLBACK_UNITY_VERSION=unity_version
textures_dir=outdir/'textures';meshes_dir=outdir/'meshes'
textures_dir.mkdir(parents=True,exist_ok=True);meshes_dir.mkdir(parents=True,exist_ok=True)

print('BUNDLE_RECON_V1_STAGE closure-map',flush=True)
sumj=json.loads(summaryp.read_text('utf-8'))
closure=sorted({int(x) for x in ((sumj.get('dependencySelection') or {}).get('selectedBundleIds') or [])})
if len(closure)!=195:raise SystemExit(f'CLOSURE_GUARD expected=195 actual={len(closure)}')
bundle_paths={bid:localp/f'bundle-{bid}.bundle' for bid in closure if (localp/f'bundle-{bid}.bundle').is_file()}
if bundle_id not in bundle_paths:raise SystemExit(f'ROOT_BUNDLE_NOT_IN_CLOSURE bundle={bundle_id}')

# Map serialized-file identity -> current cached bundle. This is resolution infrastructure only.
sf_to_bundle=defaultdict(set);bundle_files=defaultdict(set);map_errors=[]
for pos,bid in enumerate(closure,1):
    p=bundle_paths.get(bid)
    if not p:continue
    try:
        env=UnityPy.load(str(p))
        for obj in list(getattr(env,'objects',[]) or []):
            af=getattr(obj,'assets_file',None);nm=str(getattr(af,'name','') or '')
            if nm:sf_to_bundle[nm].add(bid);sf_to_bundle[nm.rsplit('/',1)[-1]].add(bid);bundle_files[bid].add(nm)
        fs=getattr(env,'files',None)
        if isinstance(fs,dict):
            for k,v in fs.items():
                for nm in (str(k or ''),str(getattr(v,'name','') or '')):
                    if nm:sf_to_bundle[nm].add(bid);sf_to_bundle[nm.rsplit('/',1)[-1]].add(bid);bundle_files[bid].add(nm)
    except Exception as e:map_errors.append({'bundleId':bid,'error':f'{type(e).__name__}:{e}'})
    if pos%25==0:print('BUNDLE_RECON_V1_MAP',f'{pos}/195',f'serializedFiles={len(sf_to_bundle)}',flush=True)

root_path=bundle_paths[bundle_id]
root_env=UnityPy.load(str(root_path))
root_objects=list(getattr(root_env,'objects',[]) or [])
print('BUNDLE_RECON_V1_ROOT',f'bundle={bundle_id}',f'objects={len(root_objects)}',flush=True)

def typ(o):return str(getattr(getattr(o,'type',None),'name','') or '')
def sf(o):return str(getattr(getattr(o,'assets_file',None),'name','') or '')
def pid(o):return int(getattr(o,'path_id',0) or 0)
def pname(o):
    try:return str(o.peek_name() or '')
    except:return ''
def safe(s):
    z=re.sub(r'[^A-Za-z0-9._-]+','_',str(s)).strip('._')
    return (z[:96] or 'asset')
def norm_file(s):return str(s or '').replace('\\','/').rsplit('/',1)[-1]

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

def ref_file_candidates(source_af,file_id):
    if file_id==0:
        n=str(getattr(source_af,'name','') or '');return [n,norm_file(n)] if n else []
    ex=ext_names(source_af);idx=file_id-1
    if idx<0 or idx>=len(ex):return []
    vals=[]
    for x in ex[idx]:
        vals.extend((x,norm_file(x)))
    return [x for x in dict.fromkeys(vals) if x]

env_cache={bundle_id:root_env}
def load_bundle(bid):
    if bid in env_cache:return env_cache[bid]
    p=bundle_paths.get(bid)
    if not p:return None
    try:env_cache[bid]=UnityPy.load(str(p));return env_cache[bid]
    except:return None

def resolve_ref(source_af,file_id,path_id,expected_type=None):
    if not path_id:return None
    cands=ref_file_candidates(source_af,file_id)
    bids=[]
    for c in cands:bids.extend(sorted(sf_to_bundle.get(c,set())))
    bids=list(dict.fromkeys(bids))
    if file_id==0:
        srcn=str(getattr(source_af,'name','') or '')
        bids=list(dict.fromkeys([bundle_id]+bids))
    hits=[]
    for bid in bids:
        env=load_bundle(bid)
        if env is None:continue
        for o in list(getattr(env,'objects',[]) or []):
            if pid(o)!=path_id:continue
            if expected_type and typ(o)!=expected_type:continue
            if cands and norm_file(sf(o)) not in {norm_file(x) for x in cands}:continue
            hits.append((bid,o))
    if len(hits)==1:return hits[0]
    if len(hits)>1:
        exact=[x for x in hits if sf(x[1]) in cands]
        if len(exact)==1:return exact[0]
    return None

# ---------- direct Android-safe Texture2D decode ----------
def bgra(raw,w,h):return Image.frombytes('RGBA',(w,h),raw,'raw','BGRA')
def decode_texture(d):
    w=int(d.m_Width);h=int(d.m_Height);fmt=TextureFormat(int(d.m_TextureFormat));name=fmt.name;data=bytes(d.get_image_data())
    if 'Crunched' in name:
        try:data=t2d.unpack_unity_crunch(data)
        except Exception:data=t2d.unpack_crunch(data)
        name=name.replace('Crunched','')
    if name.startswith('ASTC'):
        m=re.search(r'(\d+)x(\d+)',name)
        if not m:raise NotImplementedError(name)
        im=bgra(t2d.decode_astc(data,w,h,int(m.group(1)),int(m.group(2))),w,h)
    elif name in ('ETC_RGB4','ETC_RGB4_3DS'):im=bgra(t2d.decode_etc1(data,w,h),w,h)
    elif name=='ETC2_RGB':im=bgra(t2d.decode_etc2(data,w,h),w,h)
    elif name=='ETC2_RGBA1':im=bgra(t2d.decode_etc2a1(data,w,h),w,h)
    elif name=='ETC2_RGBA8':im=bgra(t2d.decode_etc2a8(data,w,h),w,h)
    elif name=='DXT1':im=bgra(t2d.decode_bc1(data,w,h),w,h)
    elif name=='DXT5':im=bgra(t2d.decode_bc3(data,w,h),w,h)
    elif name=='BC4':im=bgra(t2d.decode_bc4(data,w,h),w,h)
    elif name=='BC5':im=bgra(t2d.decode_bc5(data,w,h),w,h)
    elif name=='BC7':im=bgra(t2d.decode_bc7(data,w,h),w,h)
    elif name=='RGBA32':im=Image.frombytes('RGBA',(w,h),data[:w*h*4],'raw','RGBA')
    elif name=='BGRA32':im=Image.frombytes('RGBA',(w,h),data[:w*h*4],'raw','BGRA')
    elif name=='ARGB32':im=Image.frombytes('RGBA',(w,h),data[:w*h*4],'raw','ARGB')
    elif name=='RGB24':im=Image.frombytes('RGB',(w,h),data[:w*h*3],'raw','RGB').convert('RGBA')
    else:raise NotImplementedError(name)
    return im.transpose(Image.Transpose.FLIP_TOP_BOTTOM),fmt.name

# ---------- inventory ----------
type_counts=Counter(typ(o) for o in root_objects)
assetbundle_name=''
for o in root_objects:
    if typ(o)=='AssetBundle':assetbundle_name=pname(o);break

# Cache typetrees for root objects only.
trees={};tree_errors=[]
for i,o in enumerate(root_objects,1):
    try:trees[(sf(o),pid(o))]=o.read_typetree()
    except Exception as e:
        if len(tree_errors)<100:tree_errors.append({'type':typ(o),'name':pname(o),'pathID':str(pid(o)),'error':f'{type(e).__name__}:{e}'})

SELECTED_MATERIALS={'Terrain_Ground','O_terrain_grass02_3TextureNS1','O_terrain_road_01','O_terrain_road_02_nsj','O_terrain_shamo_back'}

# ---------- materials ----------
def pair_items(v):
    if isinstance(v,dict):
        for k,x in v.items():yield str(k),x
    elif isinstance(v,list):
        for x in v:
            if isinstance(x,(list,tuple)) and len(x)==2:yield str(x[0]),x[1]
            elif isinstance(x,dict):
                if 'first' in x and 'second' in x:yield str(x['first']),x['second']
                elif 'key' in x and 'value' in x:yield str(x['key']),x['value']

def extract_material_slots(tree):
    sp=(tree or {}).get('m_SavedProperties') if isinstance(tree,dict) else None
    if not isinstance(sp,dict):return []
    texenv=sp.get('m_TexEnvs') or sp.get('m_TextureEnvs') or []
    out=[]
    for slot,val in pair_items(texenv):
        if not isinstance(val,dict):continue
        tv=val.get('m_Texture') or val.get('texture')
        q=pptr(tv)
        if q is None:continue
        rec={'slot':slot,'fileID':q[0],'pathID':str(q[1])}
        sc=val.get('m_Scale');off=val.get('m_Offset')
        if isinstance(sc,dict):rec['scale']={k:sc.get(k) for k in ('x','y') if k in sc}
        if isinstance(off,dict):rec['offset']={k:off.get(k) for k in ('x','y') if k in off}
        out.append(rec)
    return out

material_objs=[o for o in root_objects if typ(o)=='Material']
materials=[]
texture_requests=[]
for o in material_objs:
    tree=trees.get((sf(o),pid(o)),{})
    name=pname(o)
    slots=extract_material_slots(tree)
    af=getattr(o,'assets_file',None)
    for sl in slots:
        res=resolve_ref(af,sl['fileID'],int(sl['pathID']),'Texture2D')
        if res:
            bid,to=res;sl['resolved']={'bundleId':bid,'serializedFile':sf(to),'pathID':str(pid(to)),'name':pname(to)}
            texture_requests.append((name in SELECTED_MATERIALS,bid,to))
        else:sl['resolved']=None
    shader=None
    if isinstance(tree,dict):
        q=pptr(tree.get('m_Shader'))
        if q:
            rr=resolve_ref(af,q[0],q[1])
            if rr:shader={'bundleId':rr[0],'pathID':str(pid(rr[1])),'type':typ(rr[1]),'name':pname(rr[1])}
            else:shader={'fileID':q[0],'pathID':str(q[1]),'resolved':False}
    materials.append({'id':f'b{bundle_id}:p{pid(o)}','bundleId':bundle_id,'serializedFile':sf(o),'pathID':str(pid(o)),'name':name,'selectedHuman':name in SELECTED_MATERIALS,'shader':shader,'textureSlots':slots})
materials.sort(key=lambda x:(not x['selectedHuman'],x['name'].lower(),x['pathID']))

# ---------- export textures: selected material refs first, then other material refs, then local ----------
seen_tex=set();texture_objs=[]
for pri,bid,o in sorted(texture_requests,key=lambda x:(not x[0],x[1],pid(x[2]))):
    k=(bid,sf(o),pid(o))
    if k not in seen_tex:seen_tex.add(k);texture_objs.append((bid,o,'material-reference'))
for o in root_objects:
    if typ(o)=='Texture2D':
        k=(bundle_id,sf(o),pid(o))
        if k not in seen_tex:seen_tex.add(k);texture_objs.append((bundle_id,o,'bundle-local'))
textures=[];texture_by_identity={};texture_fail=[]
for seq,(bid,o,reason) in enumerate(texture_objs[:max_textures],1):
    try:
        d=o.read();im,fmt=decode_texture(d);name=pname(o) or str(getattr(d,'m_Name','') or '')
        fn=f'{seq:03d}_b{bid}_p{pid(o)}_{safe(name)}.png';fp=textures_dir/fn;im.save(fp,'PNG',optimize=True)
        raw=fp.read_bytes();rec={'id':f'b{bid}:{norm_file(sf(o))}:p{pid(o)}','bundleId':bid,'serializedFile':sf(o),'pathID':str(pid(o)),'name':name,'width':int(d.m_Width),'height':int(d.m_Height),'format':fmt,'reason':reason,'src':f'/lab/bundle-reconstruction-data/{bundle_id}/textures/{fn}','pngBytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()}
        textures.append(rec);texture_by_identity[(bid,norm_file(sf(o)),str(pid(o)))]=rec
        if seq%20==0:print('BUNDLE_RECON_V1_TEXTURES',f'{seq}/{min(len(texture_objs),max_textures)}',flush=True)
    except Exception as e:texture_fail.append({'bundleId':bid,'pathID':str(pid(o)),'name':pname(o),'error':f'{type(e).__name__}:{e}'})
# attach local PNG ids to material slots
for m in materials:
    for sl in m['textureSlots']:
        r=sl.get('resolved')
        if not r:continue
        rec=texture_by_identity.get((int(r['bundleId']),norm_file(r['serializedFile']),str(r['pathID'])))
        if rec:sl['textureId']=rec['id'];sl['src']=rec['src']

# ---------- meshes ----------
mesh_candidates=[];seen_mesh=set()
for o in root_objects:
    if typ(o)=='Mesh':
        k=(bundle_id,sf(o),pid(o));seen_mesh.add(k);mesh_candidates.append((bundle_id,o,'bundle-local'))
# add Mesh refs found anywhere in root typetrees, but only when they resolve as Mesh
for o in root_objects:
    af=getattr(o,'assets_file',None);tree=trees.get((sf(o),pid(o)))
    if tree is None:continue
    for field,file_id,path_id in walk_ptrs(tree):
        if not path_id:continue
        rr=resolve_ref(af,file_id,path_id,'Mesh')
        if not rr:continue
        bid,mo=rr;k=(bid,sf(mo),pid(mo))
        if k not in seen_mesh:seen_mesh.add(k);mesh_candidates.append((bid,mo,f'referenced-by:{typ(o)}:{pname(o)}'))
meshes=[];mesh_fail=[];mesh_by_identity={}
for seq,(bid,o,reason) in enumerate(mesh_candidates[:max_meshes],1):
    try:
        m=o.read();exp=getattr(m,'export',None)
        if not callable(exp):raise RuntimeError('Mesh.export unavailable')
        text=exp();name=pname(o) or str(getattr(m,'m_Name','') or '')
        fn=f'{seq:03d}_b{bid}_p{pid(o)}_{safe(name)}.obj';fp=meshes_dir/fn;fp.write_text(text,'utf-8',newline='')
        rec={'id':f'b{bid}:{norm_file(sf(o))}:p{pid(o)}','bundleId':bid,'serializedFile':sf(o),'pathID':str(pid(o)),'name':name,'reason':reason,'src':f'/lab/bundle-reconstruction-data/{bundle_id}/meshes/{fn}','objBytes':fp.stat().st_size}
        meshes.append(rec);mesh_by_identity[(bid,norm_file(sf(o)),str(pid(o)))]=rec
    except Exception as e:mesh_fail.append({'bundleId':bid,'pathID':str(pid(o)),'name':pname(o),'error':f'{type(e).__name__}:{e}'})

# ---------- root object/component/hierarchy reconstruction ----------
def vec(d,keys=('x','y','z')):
    return [float(d.get(k,0) or 0) for k in keys] if isinstance(d,dict) else None

def local_ref(source_o,v,expected=None):
    q=pptr(v)
    if not q:return None
    rr=resolve_ref(getattr(source_o,'assets_file',None),q[0],q[1],expected)
    if not rr:return {'fileID':q[0],'pathID':str(q[1]),'resolved':False}
    bid,to=rr
    return {'bundleId':bid,'serializedFile':sf(to),'pathID':str(pid(to)),'type':typ(to),'name':pname(to),'resolved':True}

objects=[]
for o in root_objects:
    tree=trees.get((sf(o),pid(o)),{})
    ptr_count=sum(1 for _ in walk_ptrs(tree)) if tree is not None else 0
    objects.append({'bundleId':bundle_id,'serializedFile':sf(o),'pathID':str(pid(o)),'type':typ(o),'name':pname(o),'ptrCount':ptr_count})
objects.sort(key=lambda x:(x['type'],x['name'].lower(),x['pathID']))

gameobjects={};transforms={};meshfilters={};renderers={}
for o in root_objects:
    t=typ(o);tree=trees.get((sf(o),pid(o)),{})
    if not isinstance(tree,dict):continue
    if t=='GameObject':
        comps=[]
        for c in tree.get('m_Component') or []:
            v=c.get('component') if isinstance(c,dict) else None
            if v is None and isinstance(c,dict):v=c.get('m_Component')
            r=local_ref(o,v)
            if r:comps.append(r)
        gameobjects[str(pid(o))]={'pathID':str(pid(o)),'name':pname(o) or str(tree.get('m_Name') or ''),'components':comps}
    elif t in ('Transform','RectTransform'):
        go=local_ref(o,tree.get('m_GameObject'),'GameObject');father=local_ref(o,tree.get('m_Father'))
        transforms[str(pid(o))]={'pathID':str(pid(o)),'gameObject':go,'father':father,'localPosition':vec(tree.get('m_LocalPosition')),'localRotation':vec(tree.get('m_LocalRotation'),('x','y','z','w')),'localScale':vec(tree.get('m_LocalScale'))}
    elif t=='MeshFilter':
        meshfilters[str(pid(o))]={'pathID':str(pid(o)),'gameObject':local_ref(o,tree.get('m_GameObject'),'GameObject'),'mesh':local_ref(o,tree.get('m_Mesh'),'Mesh')}
    elif t in ('MeshRenderer','SkinnedMeshRenderer'):
        mats=[]
        for v in tree.get('m_Materials') or []:
            r=local_ref(o,v,'Material')
            if r:mats.append(r)
        rec={'pathID':str(pid(o)),'type':t,'gameObject':local_ref(o,tree.get('m_GameObject'),'GameObject'),'materials':mats}
        if t=='SkinnedMeshRenderer':rec['mesh']=local_ref(o,tree.get('m_Mesh'),'Mesh')
        renderers[str(pid(o))]=rec

# map GO -> components and reconstructable render entries
transform_by_go={}
for tr in transforms.values():
    g=tr.get('gameObject') or {}
    if g.get('resolved'):transform_by_go[str(g['pathID'])]=tr
meshfilter_by_go={}
for mf in meshfilters.values():
    g=mf.get('gameObject') or {}
    if g.get('resolved'):meshfilter_by_go[str(g['pathID'])]=mf
scene=[]
for rr in renderers.values():
    g=rr.get('gameObject') or {}
    if not g.get('resolved'):continue
    gpid=str(g['pathID']);go=gameobjects.get(gpid,{'pathID':gpid,'name':g.get('name') or ''})
    mref=rr.get('mesh') if rr['type']=='SkinnedMeshRenderer' else (meshfilter_by_go.get(gpid) or {}).get('mesh')
    meshrec=None
    if mref and mref.get('resolved'):
        meshrec=mesh_by_identity.get((int(mref['bundleId']),norm_file(mref['serializedFile']),str(mref['pathID'])))
    mats=[]
    for mr in rr.get('materials') or []:
        hit=next((m for m in materials if str(m['pathID'])==str(mr.get('pathID')) and int(m['bundleId'])==int(mr.get('bundleId',-1))),None)
        mats.append({'ref':mr,'materialId':hit['id'] if hit else None,'name':hit['name'] if hit else mr.get('name')})
    tr=transform_by_go.get(gpid)
    scene.append({'gameObject':go,'renderer':rr,'transform':tr,'mesh':meshrec,'materials':mats,'reconstructable':meshrec is not None})

# parent GO resolution from Transform father -> father's GameObject
tr_by_pid={str(x['pathID']):x for x in transforms.values()}
for srec in scene:
    tr=srec.get('transform')
    parent_go=None
    if tr:
        f=tr.get('father') or {}
        if f.get('resolved'):
            ftr=tr_by_pid.get(str(f['pathID']))
            if ftr and (ftr.get('gameObject') or {}).get('resolved'):parent_go=str(ftr['gameObject']['pathID'])
    srec['parentGameObjectPathID']=parent_go

manifest={
 'format':'WFGG_LASTWAR_BUNDLE_RECONSTRUCTION_VIEWER_V1',
 'bundle':{'bundleId':bundle_id,'assetBundleName':assetbundle_name,'path':str(root_path),'serializedFiles':sorted(bundle_files.get(bundle_id,set()))},
 'authority':{'actualBundleObjectsOnly':True,'inventedGameGeometry':False,'runtimeUseProof':False,'transformPreview':'raw serialized Unity local transforms; viewer coordinate interpretation is inspection-only'},
 'counts':{'objects':len(root_objects),'types':dict(sorted(type_counts.items())),'materials':len(materials),'texturesExported':len(textures),'textureCandidates':len(texture_objs),'meshesExported':len(meshes),'meshCandidates':len(mesh_candidates),'gameObjects':len(gameobjects),'transforms':len(transforms),'renderers':len(renderers),'reconstructableRenderers':sum(1 for x in scene if x['reconstructable'])},
 'materials':materials,'textures':textures,'meshes':meshes,'objects':objects,'scene':scene,
 'diagnostics':{'serializedFileMapErrors':map_errors,'typetreeErrors':tree_errors,'textureFailures':texture_fail,'meshFailures':mesh_fail,'textureExportLimit':max_textures,'meshExportLimit':max_meshes},
 'viewer':{'url':f'/lab/lastwar-bundle-reconstruction-viewer.html?bundle={bundle_id}'}
}
(outdir/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n','utf-8')
lines=['WfGg Last War — BUNDLE RECONSTRUCTION VIEWER V1','',f'bundle={bundle_id} assetBundleName={assetbundle_name}',f"objects={len(root_objects)} materials={len(materials)} texturesExported={len(textures)} meshesExported={len(meshes)} renderers={len(renderers)} reconstructableRenderers={sum(1 for x in scene if x['reconstructable'])}",f'textureFailures={len(texture_fail)} meshFailures={len(mesh_fail)} typetreeErrors={len(tree_errors)} mapErrors={len(map_errors)}','',f'viewer=http://127.0.0.1:8788/lab/lastwar-bundle-reconstruction-viewer.html?bundle={bundle_id}','', 'RULE: decoded PNGs and OBJ meshes come from actual bundle assets; no generated game geometry.','RULE: reconstruction uses only serialized GameObject/Transform/Mesh/Renderer links that resolve exactly.','RULE: missing links stay unresolved; runtime usage is not inferred.']
reportp.write_text('\n'.join(lines)+'\n','utf-8')
print('BUNDLE_RECON_V1_OK',f'bundle={bundle_id}',f'materials={len(materials)}',f'textures={len(textures)}',f'meshes={len(meshes)}',f'renderers={len(renderers)}',f'reconstructable={sum(1 for x in scene if x["reconstructable"])}',flush=True)
print('BUNDLE_RECON_V1_MANIFEST',outdir/'manifest.json',flush=True)
print('BUNDLE_RECON_V1_REPORT',reportp,flush=True)
PY

echo "=== BUNDLE RECONSTRUCTION VIEWER BUILD V1 TERMINE ==="
echo "Viewer: http://127.0.0.1:8788/lab/lastwar-bundle-reconstruction-viewer.html?bundle=$BUNDLE_ID"
echo "Rapport: $REPORT"
echo "Données générées locales: $OUTDIR"
