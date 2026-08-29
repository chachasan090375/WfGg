#!/data/data/com.termux/files/usr/bin/bash
set -Eeuo pipefail

# WfGg Last War LAB — Formation Layer 0 render pack.
# Reuses the already extracted exact world bundles and produces:
#   - Android-safe Texture2D PNG exports
#   - exact object identities (assets_file + pathId)
#   - Transform / MeshFilter / Renderer / Material / Texture graph
#   - exact candidate root descendant counts
# No Last War network, no generated landscape, no name-similarity binding.

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BRANCH="portal-auth-lastwar-lab-v1"
SRC="$ROOT/frontend/lab/local_assets/lastwar-formation-layer0-world-v1"
CONTRACT="$ROOT/frontend/lab/master-assets-v2/meta/formation-layer0-contract-v1.json"
OUT="$ROOT/frontend/lab/local_assets/lastwar-formation-layer0-renderpack-v1"
MANIFEST="$ROOT/frontend/lab/master-assets-v2/meta/formation-layer0-renderpack-v1.json"
REPORT="$HOME/storage/downloads/WFGG_LASTWAR_FORMATION_LAYER0_RENDERPACK.txt"
PY="${TMPDIR:-$HOME/.cache}/wfgg-layer0-renderpack.py"
UNITY_VERSION="2019.4.41f1"

fail(){ printf 'ERREUR: %s\n' "$*" >&2; exit 1; }
cd "$ROOT"
[[ "$(git branch --show-current)" == "$BRANCH" ]] || fail "branche LAB incorrecte"
[[ -d "$SRC/bundles" ]] || fail "pack Layer0 local absent; relance d'abord lastwar-formation-layer0-world-pack.sh"
[[ -s "$CONTRACT" ]] || fail "contrat Layer0 absent"
command -v python >/dev/null 2>&1 || fail "python absent"

# Same Android-safe decoder path already validated on the current15 vehicle pack.
if ! python - <<'PY' >/dev/null 2>&1
import texture2ddecoder
assert callable(getattr(texture2ddecoder,'decode_astc',None))
PY
then
  echo "LAYER0_DECODER_REBUILD texture2ddecoder"
  pkg install -y clang make >/dev/null 2>&1 || true
  python -m pip install --no-cache-dir --force-reinstall --no-binary=:all: --no-build-isolation texture2ddecoder >/dev/null 2>&1 || true
fi

rm -rf "$OUT"
mkdir -p "$OUT/textures" "$OUT/scene" "$(dirname "$MANIFEST")" "$(dirname "$REPORT")" "$(dirname "$PY")"

cat > "$PY" <<'PYEOF'
from pathlib import Path
from collections import Counter, defaultdict
import hashlib, json, re, sys, traceback

src=Path(sys.argv[1]); out=Path(sys.argv[2]); contractp=Path(sys.argv[3]); manifestp=Path(sys.argv[4]); reportp=Path(sys.argv[5]); unity_version=sys.argv[6]
contract=json.loads(contractp.read_text(encoding='utf-8'))

try:
    import UnityPy
    from UnityPy.enums import TextureFormat
    UnityPy.config.FALLBACK_UNITY_VERSION=unity_version
except Exception as e:
    raise SystemExit('UnityPy core import failed: '+repr(e))
try:
    import texture2ddecoder as t2d
    DECODER_ERROR=None
except Exception as e:
    t2d=None; DECODER_ERROR=repr(e)
try:
    from PIL import Image
except Exception as e:
    raise SystemExit('Pillow import failed: '+repr(e))

SAFE=re.compile(r'[^A-Za-z0-9._-]+')
def safe(s,fb='asset'):
    x=SAFE.sub('_',str(s or '')).strip('._')
    return x[:160] or fb

def sha256_file(p):
    h=hashlib.sha256()
    with p.open('rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''): h.update(b)
    return h.hexdigest()

def typ(r):
    try:return r.type.name
    except:return str(getattr(r,'type',''))
def read(r):
    try:return r.read()
    except Exception:
        try:return r.parse_as_object()
        except:return None
def attr(o,*names,default=None):
    for n in names:
        try:
            v=getattr(o,n)
            if v is not None:return v
        except Exception:pass
    return default
def raw_pid(x):
    if x is None:return None
    for n in ('path_id','m_PathID'):
        try:
            v=getattr(x,n,None)
            if v is not None:return int(v)
        except Exception:pass
    return None
def raw_fid(p):
    if p is None:return 0
    for n in ('m_FileID','file_id','fileID'):
        try:
            v=getattr(p,n,None)
            if v is not None:return int(v)
        except Exception:pass
    return 0
def af_of_reader(r):
    for n in ('assets_file','assetsfile'):
        try:
            x=getattr(r,n,None)
            if x is not None:return x
        except Exception:pass
    return None
def af_name(af):
    if af is None:return ''
    return str(getattr(af,'name','') or getattr(af,'path','') or '')
def norm_file(s):
    s=str(s or '').replace('\\','/').rstrip('/')
    if '/' in s:s=s.rsplit('/',1)[-1]
    return s.lower()
def rkey(r):
    p=raw_pid(r);n=norm_file(af_name(af_of_reader(r)))
    return None if p is None or not n else (n,p)
def keyrow(k):
    return None if k is None else {'assetsFile':k[0],'pathId':k[1],'objectKey':f'{k[0]}::{k[1]}'}
def keystr(k):return None if k is None else f'{k[0]}::{k[1]}'
def ext_path(e):
    for n in ('path','path_name','m_PathName','name'):
        try:
            v=getattr(e,n,None)
            if v:return str(v)
        except Exception:pass
    return ''
def source_af_of_ptr(p):
    for n in ('assets_file','assetsfile','_assets_file'):
        try:
            x=getattr(p,n,None)
            if x is not None:return x
        except Exception:pass
    return None
def pkey(p):
    if p is None:return None
    path=raw_pid(p)
    if path in (None,0):return None
    srcaf=source_af_of_ptr(p)
    if srcaf is None:return None
    fid=raw_fid(p)
    if fid==0:return (norm_file(af_name(srcaf)),path)
    exts=list(getattr(srcaf,'externals',[]) or [])
    if fid<1 or fid>len(exts):return None
    target=norm_file(ext_path(exts[fid-1]))
    return None if not target else (target,path)
def name(o,fb=''):
    if o is None:return str(fb or '')
    return str(getattr(o,'m_Name','') or getattr(o,'name','') or fb or '')
def vec(v,ns):
    if v is None:return None
    try:return [float(getattr(v,n)) for n in ns]
    except:return None

def pair_items(x):
    if x is None:return []
    if isinstance(x,dict):return list(x.items())
    out=[]
    for it in x or []:
        if isinstance(it,(list,tuple)) and len(it)>=2:
            out.append((it[0],it[1]));continue
        if isinstance(it,dict):
            k=it.get('first',it.get('key',it.get('Key')));v=it.get('second',it.get('value',it.get('Value')))
        else:
            k=attr(it,'first','key','Key');v=attr(it,'second','value','Value')
        if k is not None:out.append((k,v))
    return out

def texture_format_name(tex):
    try:return TextureFormat(int(tex.m_TextureFormat)).name
    except Exception:return str(getattr(tex,'m_TextureFormat','UNKNOWN'))

def decfn(*names):
    if t2d is None:return None
    for n in names:
        f=getattr(t2d,n,None)
        if callable(f):return f
    return None

def direct_texture_image(tex):
    raw=bytes(tex.get_image_data())
    w=int(getattr(tex,'m_Width',0) or 0);h=int(getattr(tex,'m_Height',0) or 0)
    if w<=0 or h<=0:raise ValueError(f'invalid texture size {w}x{h}')
    fmt=texture_format_name(tex)
    if fmt=='RGBA32':img=Image.frombytes('RGBA',(w,h),raw[:w*h*4],'raw','RGBA')
    elif fmt=='ARGB32':img=Image.frombytes('RGBA',(w,h),raw[:w*h*4],'raw','ARGB')
    elif fmt=='BGRA32':img=Image.frombytes('RGBA',(w,h),raw[:w*h*4],'raw','BGRA')
    elif fmt=='RGB24':img=Image.frombytes('RGB',(w,h),raw[:w*h*3],'raw','RGB').convert('RGBA')
    elif fmt=='BGR24':img=Image.frombytes('RGB',(w,h),raw[:w*h*3],'raw','BGR').convert('RGBA')
    elif fmt in ('Alpha8','R8'):
        band=Image.frombytes('L',(w,h),raw[:w*h])
        if fmt=='Alpha8':
            img=Image.new('RGBA',(w,h),(255,255,255,0));img.putalpha(band)
        else:img=Image.merge('RGBA',(band,band,band,Image.new('L',(w,h),255)))
    else:
        if t2d is None:raise RuntimeError('texture2ddecoder unavailable: '+str(DECODER_ERROR))
        f=None;args=(raw,w,h)
        if fmt.startswith('ASTC'):
            m=re.search(r'_(\d+)x(\d+)$',fmt)
            if not m:raise NotImplementedError('ASTC block size unresolved: '+fmt)
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
        elif fmt in ('PVRTC_RGB2','PVRTC_RGBA2'):
            f=decfn('decode_pvrtc');args=(raw,w,h,True)
        elif fmt in ('PVRTC_RGB4','PVRTC_RGBA4'):
            f=decfn('decode_pvrtc');args=(raw,w,h,False)
        else:raise NotImplementedError('direct decoder not implemented: '+fmt)
        if f is None:raise RuntimeError('decoder function absent for '+fmt)
        decoded=f(*args)
        img=Image.frombytes('RGBA',(w,h),decoded,'raw','BGRA')
    img=img.transpose(Image.Transpose.FLIP_TOP_BOTTOM)
    return img,fmt,len(raw)

def color(v):
    if v is None:return None
    try:return [float(v.r),float(v.g),float(v.b),float(v.a)]
    except Exception:return None

def tex_slots(mat):
    sp=attr(mat,'m_SavedProperties','savedProperties')
    te=attr(sp,'m_TexEnvs','TexEnvs',default=[])
    out=[]
    for k,v in pair_items(te):
        tp=attr(v,'m_Texture','texture') if v is not None else None
        if tp is None and isinstance(v,dict):tp=v.get('m_Texture',v.get('texture'))
        scale=attr(v,'m_Scale','scale') if v is not None else None
        offset=attr(v,'m_Offset','offset') if v is not None else None
        out.append({'slot':str(k),'textureKey':keyrow(pkey(tp)),'scale':vec(scale,('x','y')),'offset':vec(offset,('x','y'))})
    return out

def material_props(mat):
    sp=attr(mat,'m_SavedProperties','savedProperties')
    floats={str(k):float(v) for k,v in pair_items(attr(sp,'m_Floats','Floats',default=[])) if isinstance(v,(int,float))}
    colors={}
    for k,v in pair_items(attr(sp,'m_Colors','Colors',default=[])):
        c=color(v)
        if c is not None:colors[str(k)]=c
    return floats,colors

bundle_files=sorted(src.joinpath('bundles').iterdir())
if not bundle_files:raise SystemExit('no staged Layer0 bundles')
env=UnityPy.load(*[str(p) for p in bundle_files])
seen=set();objs=[]
for r in env.objects:
    k=(typ(r),raw_pid(r),norm_file(af_name(af_of_reader(r))))
    if k in seen:continue
    seen.add(k);objs.append(r)
readers={rkey(r):r for r in objs if rkey(r) is not None}
loaded_files=sorted({k[0] for k in readers})
counts=Counter(typ(r) for r in objs)

# Android-safe exact texture export by object identity.
tex_exports={};tex_rows=[];format_counts=Counter();texture_errors=[]
for r in [x for x in objs if typ(x)=='Texture2D']:
    d=read(r);rk=rkey(r)
    if d is None or rk is None:continue
    nm=name(d,'Texture2D');fmt=texture_format_name(d);format_counts[fmt]+=1
    item={'key':keyrow(rk),'name':nm,'format':fmt,'width':getattr(d,'m_Width',None),'height':getattr(d,'m_Height',None),'exported':False}
    try:
        im,fmt2,rawbytes=direct_texture_image(d)
        fn=f"{len(tex_rows)+1:04d}_{safe(nm,'texture')}.png";p=out/'textures'/fn;im.save(p,'PNG')
        item.update({'exported':True,'file':'textures/'+fn,'format':fmt2,'rawBytes':rawbytes,'bytes':p.stat().st_size,'sha256':sha256_file(p)})
        tex_exports[rk]=item
    except Exception as e:
        item['error']=repr(e);texture_errors.append(item)
    tex_rows.append(item)

# Exact Unity scene graph.
go={};tr={};go_to_tr={};meshfilters=[];renderers=[];materials={};meshes={};textures={};external_targets=set();unkeyed=[]
def reg(k):
    if k is not None and k[0] not in loaded_files:external_targets.add(k[0])

for r in objs:
    t=typ(r);d=read(r);rk=rkey(r)
    if d is None or rk is None:continue
    if t=='GameObject':go[rk]=name(d)
    elif t in ('Transform','RectTransform'):
        gk=pkey(attr(d,'m_GameObject'));pk=pkey(attr(d,'m_Father'));reg(gk);reg(pk)
        kids=[]
        for pp in (attr(d,'m_Children',default=[]) or []):
            q=pkey(pp);reg(q)
            if q:kids.append(q)
        tr[rk]={'key':keyrow(rk),'gameObject':gk,'name':'','parent':pk,'children':kids,'localPosition':vec(attr(d,'m_LocalPosition'),('x','y','z')),'localRotation':vec(attr(d,'m_LocalRotation'),('x','y','z','w')),'localScale':vec(attr(d,'m_LocalScale'),('x','y','z'))}
        if gk:go_to_tr[gk]=rk
    elif t=='Mesh':meshes[rk]={'key':keyrow(rk),'name':name(d,'Mesh')}
    elif t=='Texture2D':textures[rk]={'key':keyrow(rk),'name':name(d,'Texture2D'),'export':tex_exports.get(rk)}
    elif t=='Material':
        slots=tex_slots(d)
        for s in slots:
            kd=s.get('textureKey');reg((kd['assetsFile'],kd['pathId']) if kd else None)
        fl,co=material_props(d)
        materials[rk]={'key':keyrow(rk),'name':name(d,'Material'),'shaderKey':keyrow(pkey(attr(d,'m_Shader'))),'renderQueue':int(getattr(d,'m_CustomRenderQueue',-1) or -1),'textures':slots,'floats':fl,'colors':co}

for k,t in tr.items():
    t['name']=go.get(t['gameObject'],'')

# Components after transform map exists.
for r in objs:
    t=typ(r)
    if t not in ('MeshFilter','MeshRenderer','Renderer','SkinnedMeshRenderer'):continue
    d=read(r);rk=rkey(r)
    if d is None or rk is None:continue
    gk=pkey(attr(d,'m_GameObject'));reg(gk);tk=go_to_tr.get(gk)
    if tk is None:continue
    base={'componentKey':keyrow(rk),'gameObjectKey':keyrow(gk),'transformKey':keyrow(tk),'materialKeys':[]}
    if t=='MeshFilter':
        mk=pkey(attr(d,'m_Mesh'));reg(mk);meshfilters.append({**base,'meshKey':keyrow(mk)})
    else:
        mats=[]
        for pp in (attr(d,'m_Materials',default=[]) or []):
            mk=pkey(pp);reg(mk)
            if mk:mats.append(keyrow(mk))
        base['materialKeys']=mats
        if t=='SkinnedMeshRenderer':
            mk=pkey(attr(d,'m_Mesh'));reg(mk);base['meshKey']=keyrow(mk)
        renderers.append(base)

# Pair MeshFilter and MeshRenderer on the same GameObject.
mf_by_go={x['gameObjectKey']['objectKey']:x for x in meshfilters if x.get('gameObjectKey')}
render_rows=[]
used_materials=set();used_textures=set();unresolved_mesh=[];unresolved_material=[];unresolved_texture=[]
for rr in renderers:
    gok=rr['gameObjectKey']['objectKey'] if rr.get('gameObjectKey') else None
    mf=mf_by_go.get(gok);mesh_key=rr.get('meshKey') or (mf.get('meshKey') if mf else None)
    mkt=(mesh_key['assetsFile'],mesh_key['pathId']) if mesh_key else None
    if mkt and mkt not in meshes:unresolved_mesh.append(mesh_key)
    mats=[]
    for kd in rr.get('materialKeys',[]):
        mk=(kd['assetsFile'],kd['pathId']);used_materials.add(mk);m=materials.get(mk)
        if m is None:
            unresolved_material.append(kd);continue
        mats.append(m)
        for ts in m['textures']:
            td=ts.get('textureKey')
            if not td:continue
            tk=(td['assetsFile'],td['pathId']);used_textures.add(tk)
            if tk not in tex_exports:unresolved_texture.append(td)
    render_rows.append({**rr,'meshKey':mesh_key,'meshName':meshes.get(mkt,{}).get('name'),'materials':mats})

# Compute exact named root candidates and their descendant closure.
def descendants(rootk):
    outk=[];stack=[rootk];seen2=set()
    while stack:
        k=stack.pop()
        if k in seen2 or k not in tr:continue
        seen2.add(k);outk.append(k);stack.extend(tr[k]['children'])
    return outk

wanted_names=[Path(str(x['name'])).stem for x in contract['authoritativeRoots']]
root_rows=[]
for wanted in wanted_names:
    exact=[k for k,v in tr.items() if v['name']==wanted]
    for k in exact:
        ds=descendants(k);dset=set(ds)
        comp=sum(1 for r in render_rows if r.get('transformKey') and (r['transformKey']['assetsFile'],r['transformKey']['pathId']) in dset)
        root_rows.append({'name':wanted,'transformKey':keyrow(k),'descendantTransforms':len(ds),'renderComponents':comp})

# Full transform rows and deterministic paths where possible.
pathmemo={}
def pathof(k):
    if k in pathmemo:return pathmemo[k]
    t=tr.get(k)
    if not t:return ''
    p=pathof(t['parent']) if t['parent'] in tr else ''
    x=(p+'/'+t['name']) if p else t['name'];pathmemo[k]=x;return x
transform_rows=[]
for k,t in tr.items():
    transform_rows.append({'key':t['key'],'name':t['name'],'path':pathof(k),'parentKey':keyrow(t['parent']),'childrenKeys':[keyrow(x) for x in t['children']],'localPosition':t['localPosition'],'localRotation':t['localRotation'],'localScale':t['localScale']})

scene={'format':'WFGG_LASTWAR_FORMATION_LAYER0_SCENE_GRAPH_V1','transforms':transform_rows,'renderers':render_rows,'roots':root_rows}
(out/'scene'/'scene-graph.json').write_text(json.dumps(scene,ensure_ascii=False,separators=(',',':')),encoding='utf-8')

summary={
 'format':'WFGG_LASTWAR_FORMATION_LAYER0_RENDERPACK_V1','networkUsed':False,'generatedArtwork':False,'unityFallback':unity_version,
 'sourceBundleCount':len(bundle_files),'objectTypeCounts':dict(counts),'textureFormats':dict(format_counts),
 'textureCount':len(tex_rows),'textureExported':sum(x['exported'] for x in tex_rows),'textureErrors':len(texture_errors),
 'transformCount':len(transform_rows),'meshCount':len(meshes),'meshFilterCount':len(meshfilters),'rendererCount':len(render_rows),'materialCount':len(materials),
 'usedMaterialCount':len(used_materials),'usedTextureCount':len(used_textures),
 'unresolvedMeshCount':len({x['objectKey'] for x in unresolved_mesh if x}),'unresolvedMaterialCount':len({x['objectKey'] for x in unresolved_material if x}),'unresolvedTextureCount':len({x['objectKey'] for x in unresolved_texture if x}),
 'externalTargetFiles':sorted(external_targets),'roots':root_rows,'sceneFile':'scene/scene-graph.json','textures':tex_rows,
 'bake':contract['bake'],
 'guardrails':{'androidSafeDirectTextureDecode':True,'exactObjectKeys':True,'noNameFallback':True,'noGeneratedLandscape':True,'noRuntimeBlur':True,'noLastWarNetwork':True}
}
manifestp.write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')

lines=[
 'WfGg Last War — FORMATION LAYER0 RENDERPACK',
 'existing exact Layer0 bundles · Android-safe direct Texture2D decode · exact object keys',
 f"bundles={summary['sourceBundleCount']} textures={summary['textureExported']}/{summary['textureCount']} textureErrors={summary['textureErrors']}",
 f"transforms={summary['transformCount']} meshes={summary['meshCount']} meshFilters={summary['meshFilterCount']} renderers={summary['rendererCount']} materials={summary['materialCount']}",
 f"usedMaterials={summary['usedMaterialCount']} usedTextures={summary['usedTextureCount']} unresolvedMesh={summary['unresolvedMeshCount']} unresolvedMaterial={summary['unresolvedMaterialCount']} unresolvedTexture={summary['unresolvedTextureCount']}",
 'textureFormats='+json.dumps(dict(format_counts),ensure_ascii=False,sort_keys=True),
 '', 'ROOT CANDIDATES'
]
for r in root_rows:lines.append(f"  {r['name']} descendants={r['descendantTransforms']} renderComponents={r['renderComponents']} key={r['transformKey']['objectKey']}")
lines += ['', 'EXTERNAL TARGET FILES']
lines.extend('  '+x for x in sorted(external_targets))
if texture_errors:
    lines += ['', 'TEXTURE FAILURES']
    for x in texture_errors:lines.append(f"  {x['name']} format={x['format']} size={x.get('width')}x{x.get('height')} :: {x.get('error')}")
lines += ['', 'BAKE CONTRACT',f"  master={contract['bake']['masterWidth']}x{contract['bake']['masterHeight']}",f"  gaussian_sigma_px={contract['bake']['gaussianSigmaPx']}",'  runtime_blur=false','','GUARDRAILS','  exact_object_keys=true','  no_name_fallback=true','  android_safe_direct_texture_decode=true','  no_fake_css_landscape=true','  no_generated_substitute_artwork=true','  no_lastwar_network=true']
reportp.write_text('\n'.join(lines)+'\n',encoding='utf-8')
print('LAYER0_RENDERPACK_OK',f"textures={summary['textureExported']}/{summary['textureCount']}",f"roots={len(root_rows)}",f"unresolved={summary['unresolvedMeshCount']}/{summary['unresolvedMaterialCount']}/{summary['unresolvedTextureCount']}")
print('LAYER0_RENDERPACK_REPORT',reportp)
PYEOF

python "$PY" "$SRC" "$OUT" "$CONTRACT" "$MANIFEST" "$REPORT" "$UNITY_VERSION"
rm -f "$PY"

git add scripts/lastwar-formation-layer0-renderpack.sh "$MANIFEST"
if ! git diff --cached --quiet; then
  git commit -m "lab: record exact Formation Layer0 render pack"
  git push origin "$BRANCH"
fi

echo "=== LAYER0 RENDERPACK TERMINE ==="
echo "Rapport : $REPORT"
echo "Scene : frontend/lab/local_assets/lastwar-formation-layer0-renderpack-v1/scene/scene-graph.json"
echo "Textures : frontend/lab/local_assets/lastwar-formation-layer0-renderpack-v1/textures"
echo "Aucun blur runtime. main non modifiee."
