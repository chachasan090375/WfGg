#!/data/data/com.termux/files/usr/bin/bash
set -Eeuo pipefail

# WfGg Last War LAB — PHASE 53B
# EXPORT EXACT REFERENCED SCENE ASSETS BY UNITY PPtr
# CODE ONLY · OFFLINE ONLY · exact Phase47 bundles only.
#
# Phase53 proved the authoritative roots for all 15 heroes but name-based
# matching of Phase49 OBJ/PNG files was ambiguous for several models.
# This phase removes names from asset identity entirely:
#   GameObject/Transform/component graph -> exact Unity PPtr -> Mesh/Material/Texture
# and exports the exact dereferenced objects used by the authoritative prefab.
# No fuzzy matching, no generated geometry, no generated motion, no network.

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BRANCH="portal-auth-lastwar-lab-v1"
UNITY_VERSION="2019.4.41f1"
P47="$ROOT/frontend/lab/master-assets-v2/meta/current15-exact-bundle-stage.json"
P52="$ROOT/frontend/lab/master-assets-v2/meta/current15-runtime-pack-v1.json"
SRC="$ROOT/frontend/lab/local_assets/lastwar-current15-exact-v1"
OUT="$ROOT/frontend/lab/local_assets/lastwar-current15-runtime-v3-exact-scene"
MANIFEST="$ROOT/frontend/lab/master-assets-v2/meta/current15-runtime-scene-links-v2.json"
REPORT="$HOME/storage/downloads/WFGG_LASTWAR_PHASE53B_CURRENT15_EXACT_SCENE_ASSETS.txt"
PY="${TMPDIR:-$HOME/.cache}/wfgg-phase53b-exact-scene-assets.py"

fail(){ printf 'ERREUR: %s\n' "$*" >&2; exit 1; }
cd "$ROOT"
[[ "$(git branch --show-current)" == "$BRANCH" ]] || fail "branche active incorrecte"
[[ -s "$P47" ]] || fail "Phase47 absente"
[[ -s "$P52" ]] || fail "Phase52 absente"
[[ -d "$SRC" ]] || fail "bundles locaux Phase47 absents"
command -v python >/dev/null 2>&1 || fail "python absent"
python - <<'PY' >/dev/null 2>&1 || fail "UnityPy/MeshHandler/Pillow/texture2ddecoder absents — relancer Phase49B"
import UnityPy, texture2ddecoder
from UnityPy.helpers.MeshHelper import MeshHandler
from PIL import Image
PY

rm -rf "$OUT"
mkdir -p "$OUT" "$(dirname "$MANIFEST")" "$(dirname "$REPORT")" "$(dirname "$PY")"

cat > "$PY" <<'PYEOF'
from __future__ import annotations
from pathlib import Path
from collections import defaultdict
import hashlib, json, math, os, re, sys, traceback

p47p,p52p,src,out,manifestp,reportp,unity_version=sys.argv[1:]
p47p=Path(p47p);p52p=Path(p52p);src=Path(src);out=Path(out);manifestp=Path(manifestp);reportp=Path(reportp)

import UnityPy
from UnityPy.helpers.MeshHelper import MeshHandler
from UnityPy.enums import TextureFormat
import texture2ddecoder as t2d
from PIL import Image
UnityPy.config.FALLBACK_UNITY_VERSION=unity_version

j47=json.loads(p47p.read_text(encoding='utf-8'))
j52=json.loads(p52p.read_text(encoding='utf-8'))
h47={int(x['heroId']):x for x in j47.get('heroes',[])}
h52={int(x['heroId']):x for x in j52.get('heroes',[])}
ids=sorted(set(h47)&set(h52))
if len(ids)!=15: raise SystemExit(f'expected 15 common heroes, got {len(ids)}')

SAFE=re.compile(r'[^A-Za-z0-9._-]+')
def safe(s): return SAFE.sub('_',str(s or '')).strip('._')[:150] or 'asset'
def tname(r):
    try:return r.type.name
    except:return str(getattr(r,'type',''))
def robj(r):
    try:return r.read()
    except Exception:
        try:return r.parse_as_object()
        except:return None
def attr(o,*names,default=None):
    for n in names:
        try:
            v=getattr(o,n)
            if v is not None:return v
        except:pass
    return default
def oname(o,fb=''):
    if o is None:return str(fb or '')
    return str(getattr(o,'m_Name','') or getattr(o,'name','') or fb or '')
def obj_reader(o): return attr(o,'object_reader','reader')
def reader_file(r):
    af=attr(r,'assets_file','assetsfile')
    return str(attr(af,'name','path',default='') or '')
def reader_pid(r):
    try:return int(attr(r,'path_id','m_PathID'))
    except:return None
def reader_key(r):
    if r is None:return None
    return (reader_file(r),reader_pid(r))
def ptr_reader(p):
    if p is None:return None
    for fn in ('get_obj','get_object'):
        try:
            f=getattr(p,fn,None)
            if callable(f):
                r=f()
                if r is not None:return r
        except:pass
    try:
        o=p.read();r=obj_reader(o)
        if r is not None:return r
    except:pass
    return None
def pobj(p):
    if p is None:return None
    for fn in ('read','deref_parse_as_object','parse_as_object'):
        try:
            f=getattr(p,fn,None)
            if callable(f):return f()
        except:pass
    r=ptr_reader(p)
    return robj(r) if r is not None else None
def pkey(p):
    r=ptr_reader(p)
    if r is not None:return reader_key(r)
    # Last-resort identity still includes fileID/pathID from the PPtr itself.
    try:return (f'fileID:{int(attr(p,"file_id","m_FileID",default=0))}',int(attr(p,'path_id','m_PathID')))
    except:return None
def pname(p):return oname(pobj(p))
def keystr(k):
    if not k:return None
    return f'{k[0]}::{k[1]}'
def vec(v,names):
    if v is None:return None
    try:return [float(getattr(v,n)) for n in names]
    except:return None
def expected_root(queue_path):return Path(str(queue_path or '')).stem
def root_score(n,e):
    n=str(n or '');e=str(e or '')
    if n==e:return 10000
    nl=n.lower();el=e.lower()
    if nl==el:return 9500
    if nl.startswith(el) or el.startswith(nl):return 7000
    if el in nl or nl in el:return 5000
    return 0

def sha256_file(p):
    h=hashlib.sha256()
    with p.open('rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
    return h.hexdigest()

def manual_obj(mesh):
    mh=MeshHandler(mesh);mh.process()
    verts=mh.m_Vertices or []
    if not verts:raise ValueError('MeshHandler produced no vertices')
    uvs=mh.m_UV0 or []; normals=mh.m_Normals or []
    lines=[f'g {safe(oname(mesh,"mesh"))}\n']
    for p in verts:lines.append('v {:.9g} {:.9g} {:.9g}\n'.format(-float(p[0]),float(p[1]),float(p[2])).replace('nan','0'))
    for uv in uvs:lines.append('vt {:.9g} {:.9g}\n'.format(float(uv[0]),float(uv[1])).replace('nan','0'))
    for n in normals:lines.append('vn {:.9g} {:.9g} {:.9g}\n'.format(-float(n[0]),float(n[1]),float(n[2])).replace('nan','0'))
    have_uv=len(uvs)>=len(verts);have_n=len(normals)>=len(verts);faces=0
    for gi,tris in enumerate(mh.get_triangles()):
        lines.append(f'g {safe(oname(mesh,"mesh"))}_{gi}\n')
        for a,b,c in tris:
            ids=(int(c)+1,int(b)+1,int(a)+1)
            if have_uv and have_n:lines.append('f {0}/{0}/{0} {1}/{1}/{1} {2}/{2}/{2}\n'.format(*ids))
            elif have_uv:lines.append('f {0}/{0} {1}/{1} {2}/{2}\n'.format(*ids))
            elif have_n:lines.append('f {0}//{0} {1}//{1} {2}//{2}\n'.format(*ids))
            else:lines.append('f {} {} {}\n'.format(*ids))
            faces+=1
    if not faces:raise ValueError('MeshHandler produced no triangles')
    return ''.join(lines),len(verts),faces,len(uvs),len(normals)

def decfn(*names):
    for n in names:
        f=getattr(t2d,n,None)
        if callable(f):return f
    return None
def texture_format_name(tex):
    try:return TextureFormat(int(tex.m_TextureFormat)).name
    except:return str(getattr(tex,'m_TextureFormat','UNKNOWN'))
def direct_texture_image(tex):
    raw=bytes(tex.get_image_data());w=int(getattr(tex,'m_Width',0) or 0);h=int(getattr(tex,'m_Height',0) or 0)
    if w<=0 or h<=0:raise ValueError(f'invalid texture size {w}x{h}')
    fmt=texture_format_name(tex)
    if fmt=='RGBA32':img=Image.frombytes('RGBA',(w,h),raw[:w*h*4],'raw','RGBA')
    elif fmt=='ARGB32':img=Image.frombytes('RGBA',(w,h),raw[:w*h*4],'raw','ARGB')
    elif fmt=='BGRA32':img=Image.frombytes('RGBA',(w,h),raw[:w*h*4],'raw','BGRA')
    elif fmt=='RGB24':img=Image.frombytes('RGB',(w,h),raw[:w*h*3],'raw','RGB').convert('RGBA')
    elif fmt=='BGR24':img=Image.frombytes('RGB',(w,h),raw[:w*h*3],'raw','BGR').convert('RGBA')
    elif fmt in ('Alpha8','R8'):
        band=Image.frombytes('L',(w,h),raw[:w*h])
        if fmt=='Alpha8':img=Image.new('RGBA',(w,h),(255,255,255,0));img.putalpha(band)
        else:img=Image.merge('RGBA',(band,band,band,Image.new('L',(w,h),255)))
    else:
        f=None;args=(raw,w,h)
        if fmt.startswith('ASTC'):
            m=re.search(r'_(\d+)x(\d+)$',fmt)
            if not m:raise NotImplementedError(fmt)
            bw,bh=map(int,m.groups());f=decfn('decode_astc');args=(raw,w,h,bw,bh)
        elif fmt in ('ETC_RGB4','ETC_RGB4_3DS'):f=decfn('decode_etc1')
        elif fmt=='ETC2_RGB':f=decfn('decode_etc2','decode_etc2_rgb')
        elif fmt=='ETC2_RGBA1':f=decfn('decode_etc2a1','decode_etc2_rgba1')
        elif fmt=='ETC2_RGBA8':f=decfn('decode_etc2a8','decode_etc2_rgba8')
        elif fmt in ('EAC_R','EAC_R_SIGNED'):f=decfn('decode_eacr_signed' if fmt.endswith('SIGNED') else 'decode_eacr')
        elif fmt in ('EAC_RG','EAC_RG_SIGNED'):f=decfn('decode_eacrg_signed' if fmt.endswith('SIGNED') else 'decode_eacrg')
        elif fmt=='DXT1':f=decfn('decode_bc1')
        elif fmt=='DXT5':f=decfn('decode_bc3')
        elif fmt=='BC4':f=decfn('decode_bc4')
        elif fmt=='BC5':f=decfn('decode_bc5')
        elif fmt in ('BC6H','BC6H_SF16','BC6H_UF16'):f=decfn('decode_bc6')
        elif fmt=='BC7':f=decfn('decode_bc7')
        elif fmt=='ATC_RGB4':f=decfn('decode_atc_rgb4')
        elif fmt=='ATC_RGBA8':f=decfn('decode_atc_rgba8')
        elif fmt in ('PVRTC_RGB2','PVRTC_RGBA2'):f=decfn('decode_pvrtc');args=(raw,w,h,True)
        elif fmt in ('PVRTC_RGB4','PVRTC_RGBA4'):f=decfn('decode_pvrtc');args=(raw,w,h,False)
        else:raise NotImplementedError(fmt)
        if f is None:raise RuntimeError('decoder absent '+fmt)
        decoded=f(*args);img=Image.frombytes('RGBA',(w,h),decoded,'raw','BGRA')
    return img.transpose(Image.Transpose.FLIP_TOP_BOTTOM),fmt,len(raw)

def pair_items(x):
    if x is None:return []
    if isinstance(x,dict):return list(x.items())
    out=[]
    for it in x or []:
        if isinstance(it,(tuple,list)) and len(it)>=2:out.append((it[0],it[1]));continue
        if isinstance(it,dict):k=it.get('first',it.get('key',it.get('Key')));v=it.get('second',it.get('value',it.get('Value')))
        else:k=attr(it,'first','key','Key');v=attr(it,'second','value','Value')
        if k is not None:out.append((k,v))
    return out

def value_json(v):
    if v is None:return None
    if isinstance(v,(bool,int,float,str)):return v
    if isinstance(v,(tuple,list)):return [value_json(x) for x in v]
    vals=[]
    for n in ('r','g','b','a'):
        try:vals.append(float(getattr(v,n)))
        except:vals=[];break
    if vals:return vals
    vals=[]
    for n in ('x','y','z','w'):
        try:vals.append(float(getattr(v,n)))
        except:break
    if vals:return vals
    try:return float(v)
    except:return str(v)

def material_properties(mat):
    sp=attr(mat,'m_SavedProperties','savedProperties');out={'textures':[],'floats':{},'colors':{}}
    for k,v in pair_items(attr(sp,'m_TexEnvs','TexEnvs',default=[])):
        tp=attr(v,'m_Texture','texture') if v is not None else None
        if tp is None and isinstance(v,dict):tp=v.get('m_Texture',v.get('texture'))
        sc=attr(v,'m_Scale','scale');off=attr(v,'m_Offset','offset')
        out['textures'].append({'slot':str(k),'texturePtr':tp,'scale':vec(sc,('x','y')),'offset':vec(off,('x','y'))})
    for k,v in pair_items(attr(sp,'m_Floats','Floats',default=[])):out['floats'][str(k)]=value_json(v)
    for k,v in pair_items(attr(sp,'m_Colors','Colors',default=[])):out['colors'][str(k)]=value_json(v)
    return out

rows=[]
for idx,hid in enumerate(ids,1):
    h=h47[hid];r52=h52[hid];nm=h.get('name') or str(hid);expected=expected_root(h.get('queueModelPath'));hd=out/str(hid)
    (hd/'meshes').mkdir(parents=True,exist_ok=True);(hd/'textures').mkdir(parents=True,exist_ok=True)
    print(f'PHASE53B_HERO {idx}/15 id={hid} name={nm}',flush=True)
    row={'heroId':hid,'name':nm,'parseOk':False,'rootExact':False,'sceneLinked':False,'textureLinked':False,'meshRefs':0,'meshExports':0,'textureRefs':0,'textureExports':0,'errors':[]}
    try:
        files=[];hdir=src/str(hid)
        for b in h.get('bundles') or []:
            logical=os.path.basename(str(b.get('logicalName') or ''));p=hdir/logical
            if logical and p.is_file():files.append(p)
        files=sorted(set(files))
        if not files:raise ValueError('no exact Phase47 bundles')
        env=UnityPy.load(*[str(x) for x in files]);readers=list(env.objects);row['parseOk']=True

        # Build composite-key Transform graph. Path IDs are only unique inside an
        # assets file, therefore every graph identity is (assets_file,path_id).
        trs={};tr_by_go={}
        for r in readers:
            if tname(r) not in ('Transform','RectTransform'):continue
            o=robj(r)
            if o is None:continue
            k=reader_key(r);gp=attr(o,'m_GameObject');gk=pkey(gp);fp=attr(o,'m_Father');fk=pkey(fp)
            kids=[pkey(x) for x in (attr(o,'m_Children',default=[]) or [])];kids=[x for x in kids if x]
            trs[k]={'key':k,'name':pname(gp),'gameObjectKey':gk,'parentKey':fk,'children':kids,
                    'localPosition':vec(attr(o,'m_LocalPosition'),('x','y','z')),'localRotation':vec(attr(o,'m_LocalRotation'),('x','y','z','w')),'localScale':vec(attr(o,'m_LocalScale'),('x','y','z'))}
            if gk:tr_by_go[gk]=k
        roots=[t for t in trs.values() if t.get('parentKey') not in trs]
        roots.sort(key=lambda x:root_score(x.get('name'),expected),reverse=True)
        if not roots or root_score(roots[0].get('name'),expected)<5000:raise ValueError('authoritative root absent')
        root=roots[0];rootk=root['key'];row['rootExact']=True
        def under(k):
            seen=set();cur=k
            while cur in trs and cur not in seen:
                if cur==rootk:return True
                seen.add(cur);cur=trs[cur].get('parentKey')
            return False
        memo={}
        def pathof(k):
            if k in memo:return memo[k]
            t=trs.get(k)
            if not t:return ''
            pk=t.get('parentKey');pp=pathof(pk) if pk in trs else ''
            p=(pp+'/'+t['name']) if pp else t['name'];memo[k]=p;return p
        scene_tr=[]
        for k,t in trs.items():
            if under(k):scene_tr.append({'key':keystr(k),'name':t['name'],'path':pathof(k),'parentKey':keystr(t.get('parentKey')),'childrenKeys':[keystr(x) for x in t['children']],
                                          'localPosition':t['localPosition'],'localRotation':t['localRotation'],'localScale':t['localScale']})
        scene_tr.sort(key=lambda x:x['path'])

        # Collect components only under authoritative root. Keep exact PPtrs alive
        # until all referenced Mesh/Material/Texture objects have been exported.
        mesh_components=[];renderer_components=[];material_ptrs={}
        for r in readers:
            typ=tname(r)
            if typ not in ('MeshFilter','MeshRenderer','Renderer','SkinnedMeshRenderer'):continue
            o=robj(r)
            if o is None:continue
            gp=attr(o,'m_GameObject');gk=pkey(gp);tk=tr_by_go.get(gk)
            if not under(tk):continue
            base={'componentKey':keystr(reader_key(r)),'gameObject':pname(gp),'transformKey':keystr(tk),'transformPath':pathof(tk)}
            mats=[]
            for mp in (attr(o,'m_Materials',default=[]) or []):
                mk=pkey(mp);mats.append({'key':keystr(mk),'name':pname(mp)})
                if mk:material_ptrs.setdefault(mk,mp)
            if typ=='MeshFilter':
                mp=attr(o,'m_Mesh');mesh_components.append({**base,'kind':'MeshFilter','meshPtr':mp,'meshKey':keystr(pkey(mp)),'mesh':pname(mp),'materials':[]})
            elif typ=='SkinnedMeshRenderer':
                mp=attr(o,'m_Mesh');bones=[]
                for bp in (attr(o,'m_Bones',default=[]) or []):
                    bk=pkey(bp);bones.append({'key':keystr(bk),'path':pathof(bk) if bk in trs else None,'name':pname(bp)})
                rb=attr(o,'m_RootBone');rbk=pkey(rb)
                mesh_components.append({**base,'kind':'SkinnedMeshRenderer','meshPtr':mp,'meshKey':keystr(pkey(mp)),'mesh':pname(mp),'materials':mats,'bones':bones,
                                        'rootBone':{'key':keystr(rbk),'path':pathof(rbk) if rbk in trs else None,'name':pname(rb)}})
            else:renderer_components.append({**base,'kind':typ,'materials':mats})

        # MeshRenderer materials belong to MeshFilter on the same GameObject.
        mats_by_transform={x['transformKey']:x['materials'] for x in renderer_components}
        for x in mesh_components:
            if x['kind']=='MeshFilter':x['materials']=mats_by_transform.get(x['transformKey'],[])

        mesh_exports={};mesh_errors=[]
        for comp in mesh_components:
            mp=comp.pop('meshPtr');mk=pkey(mp);ks=keystr(mk)
            if not mk:
                mesh_errors.append({'component':comp['componentKey'],'error':'null mesh PPtr'});continue
            if ks not in mesh_exports:
                mo=pobj(mp)
                if mo is None:
                    mesh_exports[ks]={'key':ks,'name':comp['mesh'],'exported':False,'error':'mesh deref failed'}
                else:
                    try:
                        txt,vn,fn,uvn,nn=manual_obj(mo);fnm=f"mesh_{abs(int(mk[1]))}_{safe(oname(mo,'mesh'))}.obj";p=hd/'meshes'/fnm;p.write_text(txt,encoding='utf-8')
                        mesh_exports[ks]={'key':ks,'name':oname(mo),'exported':True,'file':'meshes/'+fnm,'vertices':vn,'faces':fn,'uvs':uvn,'normals':nn,'bytes':p.stat().st_size,'sha256':sha256_file(p)}
                    except Exception as e:mesh_exports[ks]={'key':ks,'name':oname(mo),'exported':False,'error':repr(e)}
            comp['meshAsset']=mesh_exports[ks]
        row['meshRefs']=len(mesh_exports);row['meshExports']=sum(bool(x.get('exported')) for x in mesh_exports.values())
        unresolved_mesh=[x for x in mesh_exports.values() if not x.get('exported')]

        texture_ptrs={};material_rows=[]
        for mk,mp in material_ptrs.items():
            mo=pobj(mp)
            if mo is None:
                material_rows.append({'key':keystr(mk),'name':pname(mp),'error':'material deref failed','textures':[]});continue
            pr=material_properties(mo);mr={'key':keystr(mk),'name':oname(mo),'shader':pname(attr(mo,'m_Shader')),'floats':pr['floats'],'colors':pr['colors'],'textures':[]}
            for tx in pr['textures']:
                tp=tx.pop('texturePtr');tk=pkey(tp)
                tr={**tx,'key':keystr(tk),'name':pname(tp)};mr['textures'].append(tr)
                if tk: texture_ptrs.setdefault(tk,tp)
            material_rows.append(mr)

        tex_exports={}
        for tk,tp in texture_ptrs.items():
            ks=keystr(tk);to=pobj(tp)
            if to is None:tex_exports[ks]={'key':ks,'name':pname(tp),'exported':False,'error':'texture deref failed'};continue
            try:
                img,fmt,rawb=direct_texture_image(to);fnm=f"tex_{abs(int(tk[1]))}_{safe(oname(to,'texture'))}.png";p=hd/'textures'/fnm;img.save(p,'PNG')
                tex_exports[ks]={'key':ks,'name':oname(to),'exported':True,'file':'textures/'+fnm,'format':fmt,'width':img.width,'height':img.height,'rawBytes':rawb,'bytes':p.stat().st_size,'sha256':sha256_file(p)}
            except Exception as e:tex_exports[ks]={'key':ks,'name':oname(to),'exported':False,'error':repr(e)}
        for m in material_rows:
            for t in m.get('textures',[]):t['asset']=tex_exports.get(t.get('key'))
        row['textureRefs']=len(tex_exports);row['textureExports']=sum(bool(x.get('exported')) for x in tex_exports.values())
        unresolved_tex=[x for x in tex_exports.values() if not x.get('exported')]

        scene={'format':'WFGG_LASTWAR_HERO_RUNTIME_SCENE_V2_EXACT_PTR','heroId':hid,'name':nm,'queueModelPath':h.get('queueModelPath'),'rendererMode':r52.get('rendererMode'),
               'root':{'key':keystr(rootk),'name':root['name'],'path':pathof(rootk)},'transforms':scene_tr,'meshComponents':mesh_components,'rendererComponents':renderer_components,
               'meshes':list(mesh_exports.values()),'materials':material_rows,'textures':list(tex_exports.values()),
               'runtime52Base':f'../lastwar-current15-runtime-v1/{hid}/','idleAnimation':'animation/idle.json.gz','rig':'rig.json.gz',
               'guardrails':{'exactUnityPPtrIdentity':True,'noNameMatchingForAssets':True,'noFuzzyMatching':True,'noGeneratedGeometry':True,'noGeneratedMotion':True,'noAnimationSubstitution':True}}
        (hd/'scene.json').write_text(json.dumps(scene,ensure_ascii=False,indent=2),encoding='utf-8')
        row['transformCount']=len(scene_tr);row['componentCount']=len(mesh_components)+len(renderer_components);row['unresolvedMesh']=len(unresolved_mesh);row['unresolvedTexture']=len(unresolved_tex)
        row['sceneLinked']=bool(row['rootExact'] and row['meshRefs']>0 and row['meshExports']==row['meshRefs'])
        row['textureLinked']=bool(row['textureExports']==row['textureRefs'])
        if unresolved_mesh:row['errors'].append('unresolved mesh exports: '+','.join(str(x.get('name')) for x in unresolved_mesh[:12]))
        if unresolved_tex:row['errors'].append('unresolved texture exports: '+','.join(str(x.get('name')) for x in unresolved_tex[:12]))
    except Exception as e:
        row['errors'].append(repr(e));row['traceback']=traceback.format_exc()[-4000:]
    rows.append(row)
    print('PHASE53B_HERO_DONE',hid,f"linked={row['sceneLinked']}",f"textures={row['textureLinked']}",f"mesh={row['meshExports']}/{row['meshRefs']}",f"tex={row['textureExports']}/{row['textureRefs']}",flush=True)

summary={'format':'WFGG_LASTWAR_CURRENT15_RUNTIME_SCENE_LINKS_V2_EXACT_PTR','networkUsed':False,'heroCount':15,'parseOkCount':sum(x['parseOk'] for x in rows),
         'rootExactCount':sum(x['rootExact'] for x in rows),'sceneLinkedCount':sum(x['sceneLinked'] for x in rows),'textureLinkedCount':sum(x['textureLinked'] for x in rows),
         'transformCount':sum(x.get('transformCount',0) for x in rows),'meshRefCount':sum(x['meshRefs'] for x in rows),'meshExportCount':sum(x['meshExports'] for x in rows),
         'textureRefCount':sum(x['textureRefs'] for x in rows),'textureExportCount':sum(x['textureExports'] for x in rows),'unresolvedMeshCount':sum(x.get('unresolvedMesh',0) for x in rows),'unresolvedTextureCount':sum(x.get('unresolvedTexture',0) for x in rows),
         'heroes':[{k:v for k,v in x.items() if k!='traceback'} for x in rows],
         'guardrails':{'exactUnityPPtrIdentity':True,'noNameMatchingForAssets':True,'noFuzzyMatching':True,'noGeneratedGeometry':True,'noGeneratedMotion':True,'noAnimationSubstitution':True,'noLastWarNetwork':True}}
manifestp.write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
lines=['WfGg Last War LAB — PHASE 53B EXACT PPtr SCENE ASSETS',f"heroes=15 parseOk={summary['parseOkCount']}/15 rootExact={summary['rootExactCount']}/15 sceneLinked={summary['sceneLinkedCount']}/15 textureLinked={summary['textureLinkedCount']}/15",
       f"transforms={summary['transformCount']} mesh={summary['meshExportCount']}/{summary['meshRefCount']} textures={summary['textureExportCount']}/{summary['textureRefCount']} unresolvedMesh={summary['unresolvedMeshCount']} unresolvedTexture={summary['unresolvedTextureCount']}",'']
for x in rows:lines.append(f"HERO {x['heroId']} {x['name']} linked={x['sceneLinked']} textureLinked={x['textureLinked']} rootExact={x['rootExact']} transforms={x.get('transformCount',0)} mesh={x['meshExports']}/{x['meshRefs']} tex={x['textureExports']}/{x['textureRefs']} unresolvedMesh={x.get('unresolvedMesh',0)} unresolvedTexture={x.get('unresolvedTexture',0)} errors={x['errors']}")
lines += ['','GUARDRAILS','  exact_unity_pptr_identity=true','  no_name_matching_for_assets=true','  no_fuzzy_matching=true','  no_generated_geometry=true','  no_generated_motion=true','  no_animation_substitution=true','  no_lastwar_network=true']
reportp.write_text('\n'.join(lines)+'\n',encoding='utf-8')
print('PHASE53B_OK',f"sceneLinked={summary['sceneLinkedCount']}/15",f"textureLinked={summary['textureLinkedCount']}/15",f"mesh={summary['meshExportCount']}/{summary['meshRefCount']}",f"textures={summary['textureExportCount']}/{summary['textureRefCount']}",f"unresolvedMesh={summary['unresolvedMeshCount']}",f"unresolvedTexture={summary['unresolvedTextureCount']}",flush=True)
print('PHASE53B_REPORT',reportp,flush=True)
PYEOF

python "$PY" "$P47" "$P52" "$SRC" "$OUT" "$MANIFEST" "$REPORT" "$UNITY_VERSION"

git add "$MANIFEST"
if ! git diff --cached --quiet; then
  git commit -m "lab: record exact PPtr-linked current15 scene assets"
  git push origin "$BRANCH"
fi
printf 'PHASE53B_DONE report=%s\n' "$REPORT"
