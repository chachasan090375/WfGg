#!/data/data/com.termux/files/usr/bin/python
from pathlib import Path
from collections import Counter, defaultdict
import hashlib, json, re, sys
import UnityPy
import texture2ddecoder as t2d
from PIL import Image
from UnityPy.enums import TextureFormat

ROOT=Path(sys.argv[1]).resolve()
V5=ROOT/'frontend/lab/master-assets-v2/meta/audie-package-family-v5.json'
OUT=ROOT/'frontend/lab/audie-mesh-carrier-v6-data'
UnityPy.config.FALLBACK_UNITY_VERSION='2019.4.41f1'

if not V5.is_file():
    raise SystemExit('ERREUR: V5 absent: '+str(V5))

v5=json.loads(V5.read_text('utf-8'))
carriers=v5.get('meshCarriers') or []
if not carriers:
    raise SystemExit('ERREUR: aucun mesh carrier V5')

meshdir=OUT/'meshes'; texdir=OUT/'textures'
meshdir.mkdir(parents=True,exist_ok=True); texdir.mkdir(parents=True,exist_ok=True)
for p in list(meshdir.glob('*.obj'))+list(texdir.glob('*.png')):
    try:p.unlink()
    except:pass

def typ(o): return str(getattr(getattr(o,'type',None),'name','') or '')
def pid(o): return int(getattr(o,'path_id',0) or 0)
def pname(o):
    try:return str(o.peek_name() or '')
    except:return ''
def safe(s):
    z=re.sub(r'[^A-Za-z0-9._-]+','_',str(s)).strip('._')
    return z[:100] or 'asset'
def ser_name(o):
    for a in ('assets_file','serialized_file'):
        x=getattr(o,a,None)
        if x is not None:
            for b in ('name','file_name'):
                y=getattr(x,b,None)
                if y:return str(y)
    return ''
def key(o): return (ser_name(o),pid(o))
def pptr_info(v):
    if v is None:return None
    try:
        file_id=int(getattr(v,'m_FileID',getattr(v,'file_id',0)) or 0)
        path_id=int(getattr(v,'m_PathID',getattr(v,'path_id',0)) or 0)
        return {'fileID':file_id,'pathID':str(path_id)}
    except:return None

def bgra(raw,w,h): return Image.frombytes('RGBA',(w,h),raw,'raw','BGRA')
def decode_texture(d):
    w=int(d.m_Width); h=int(d.m_Height); fmt=TextureFormat(int(d.m_TextureFormat)); name=fmt.name; data=bytes(d.get_image_data())
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

def tex_variant(name):
    n=name.lower()
    if 'bullet' in n:return 'bullet'
    if 'high' in n:return 'high'
    return 'base'
def tex_role(name):
    n=name.upper()
    if n.endswith('_D'):return 'D'
    if n.endswith('_N'):return 'N'
    if n.endswith('_S'):return 'S'
    return 'other'

# Include every locally scanned V5 bundle as a texture source; mesh carriers remain the geometry source.
all_bundle_paths=[]; seen=set()
for rec in v5.get('bundles',[]):
    p=Path(str(rec.get('path') or ''))
    if p.is_file():
        k=str(p.resolve())
        if k not in seen:seen.add(k);all_bundle_paths.append(p)

textures=[]; tex_seen=set(); texture_errors=[]
print('AUDIE_MESH_CARRIER_V6_TEXTURE_SCAN',len(all_bundle_paths),flush=True)
for i,p in enumerate(all_bundle_paths,1):
    try:env=UnityPy.load(str(p))
    except Exception:continue
    for o in list(getattr(env,'objects',[]) or []):
        if typ(o)!='Texture2D':continue
        n=pname(o)
        if 'a_hero_audie_01' not in n.lower():continue
        try:
            d=o.read(); im,fmt=decode_texture(d)
            raw=im.tobytes(); h=hashlib.sha256(raw).hexdigest()
            dedupe=(h,n)
            if dedupe in tex_seen:continue
            tex_seen.add(dedupe)
            fn=f't_{len(textures):03d}_{safe(n)}.png'; im.save(texdir/fn,'PNG',optimize=True)
            textures.append({'name':n,'variant':tex_variant(n),'role':tex_role(n),'width':int(d.m_Width),'height':int(d.m_Height),'format':fmt,'bundle':p.name,'pathID':str(pid(o)),'src':'/lab/audie-mesh-carrier-v6-data/textures/'+fn,'sha256':h})
        except Exception as e:
            texture_errors.append({'bundle':p.name,'name':n,'pathID':str(pid(o)),'error':f'{type(e).__name__}:{e}'})

out_carriers=[]; meshes=[]; mesh_errors=[]
for ci,rec in enumerate(carriers,1):
    p=Path(str(rec.get('path') or ''))
    print('AUDIE_MESH_CARRIER_V6_CARRIER',f'{ci}/{len(carriers)}',p.name,flush=True)
    if not p.is_file():continue
    try:
        env=UnityPy.load(str(p)); objs=list(getattr(env,'objects',[]) or [])
    except Exception as e:
        mesh_errors.append({'bundle':p.name,'error':f'{type(e).__name__}:{e}'});continue
    byk={key(o):o for o in objs}
    render_refs=[]
    for o in objs:
        t=typ(o)
        if t not in ('MeshFilter','MeshRenderer','SkinnedMeshRenderer'):continue
        try:d=o.read()
        except Exception:continue
        rr={'type':t,'pathID':str(pid(o)),'name':pname(o),'serializedFile':ser_name(o),'mesh':None,'materials':[],'gameObject':None}
        for attr in ('m_Mesh','mesh'):
            q=pptr_info(getattr(d,attr,None))
            if q and int(q['pathID']):rr['mesh']=q;break
        mats=getattr(d,'m_Materials',None)
        if mats:
            rr['materials']=[x for x in (pptr_info(v) for v in mats) if x]
        rr['gameObject']=pptr_info(getattr(d,'m_GameObject',None))
        render_refs.append(rr)
    carrier_meshes=[]
    for o in objs:
        if typ(o)!='Mesh':continue
        n=pname(o)
        try:
            m=o.read(); exp=getattr(m,'export',None)
            if not callable(exp):raise RuntimeError('Mesh.export unavailable')
            text=exp(); fn=f'c{ci:02d}_p{pid(o)}_{safe(n)}.obj'; fp=meshdir/fn; fp.write_text(text,'utf-8',newline='')
            referenced=any((r.get('mesh') or {}).get('pathID')==str(pid(o)) for r in render_refs)
            mr={'carrierIndex':ci-1,'bundle':p.name,'bundlePath':str(p),'category':rec.get('category'),'pathID':str(pid(o)),'serializedFile':ser_name(o),'name':n or ('Mesh_'+str(pid(o))),'src':'/lab/audie-mesh-carrier-v6-data/meshes/'+fn,'objBytes':fp.stat().st_size,'rendererReferenced':referenced}
            meshes.append(mr);carrier_meshes.append(mr)
        except Exception as e:
            mesh_errors.append({'bundle':p.name,'pathID':str(pid(o)),'name':n,'error':f'{type(e).__name__}:{e}'})
    score=(40 if rec.get('category')=='prefab' else 0)+(20 if rec.get('skinnedMeshRendererCount',0) else 0)+(15 if rec.get('meshRendererCount',0) else 0)+(10 if rec.get('meshFilterCount',0) else 0)+min(20,len(carrier_meshes))
    out_carriers.append({'index':ci-1,'basename':p.name,'path':str(p),'category':rec.get('category'),'score':score,'counts':rec.get('counts',{}),'audieNamed':rec.get('audieNamed',[]),'renderRefs':render_refs,'meshCount':len(carrier_meshes),'rendererReferencedMeshes':sum(1 for x in carrier_meshes if x['rendererReferenced'])})

out_carriers.sort(key=lambda x:(-x['score'],x['basename'].lower()))
# preserve carrier index links after sorting using basename/path, no geometry is altered
rank={c['basename']:i+1 for i,c in enumerate(out_carriers)}
for m in meshes:m['carrierRank']=rank.get(m['bundle'],999)
meshes.sort(key=lambda x:(x['carrierRank'],not x['rendererReferenced'],x['name'].lower(),int(x['pathID'])))
textures.sort(key=lambda x:({'base':0,'high':1,'bullet':2}.get(x['variant'],9),{'D':0,'N':1,'S':2}.get(x['role'],9),-x['width']*x['height'],x['name'].lower()))

verdict='MESHES_EXPORTED' if meshes else 'CARRIERS_FOUND_BUT_MESH_EXPORT_EMPTY'
manifest={
 'format':'WFGG_LASTWAR_AUDIE_MESH_CARRIER_V6',
 'verdict':verdict,
 'counts':{'carriers':len(out_carriers),'meshes':len(meshes),'rendererReferencedMeshes':sum(1 for x in meshes if x['rendererReferenced']),'textures':len(textures),'meshErrors':len(mesh_errors),'textureErrors':len(texture_errors)},
 'carriers':out_carriers,'meshes':meshes,'textures':textures,
 'diagnostics':{'meshErrors':mesh_errors[:200],'textureErrors':texture_errors[:200]},
 'rules':[
   'Every displayed mesh is exported from one of the 11 physical V5 mesh carriers.',
   'rendererReferenced means a renderer-like object in the same loaded bundle points to the mesh pathID; it is not inferred from a filename.',
   'Audie textures are real Texture2D assets; applying a D map in the viewer is an explicit UV compatibility test until an exact material consumer is resolved.',
   'No geometry is generated or approximated.'
 ]
}
OUT.mkdir(parents=True,exist_ok=True)
(OUT/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n','utf-8')
print('AUDIE_MESH_CARRIER_V6_READY',f'verdict={verdict}',f'carriers={len(out_carriers)}',f'meshes={len(meshes)}',f'rendererReferenced={manifest["counts"]["rendererReferencedMeshes"]}',f'textures={len(textures)}',flush=True)
for c in out_carriers:
    print('V6_CARRIER',f'rank={rank.get(c["basename"])}',f'score={c["score"]}',f'mesh={c["meshCount"]}',f'refmesh={c["rendererReferencedMeshes"]}',c['basename'],flush=True)
print('JSON='+str(OUT/'manifest.json'),flush=True)
