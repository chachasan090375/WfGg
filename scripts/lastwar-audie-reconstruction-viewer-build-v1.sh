#!/data/data/com.termux/files/usr/bin/bash
set -Eeuo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BRANCH="portal-auth-lastwar-lab-v1"
LOCAL="$ROOT/frontend/lab/local_assets/lastwar-formation-ptr-exact-v4/bundles"
OUT="$ROOT/frontend/lab/audie-reconstruction-data"
UNITY_VERSION="2019.4.41f1"

fail(){ printf 'ERREUR: %s\n' "$*" >&2; exit 1; }
cd "$ROOT"
[[ "$(git branch --show-current)" == "$BRANCH" ]] || fail "branche LAB incorrecte"
[[ -d "$LOCAL" ]] || fail "cache bundles V4 absent: $LOCAL"
for bid in 26631 26633 26634; do [[ -s "$LOCAL/bundle-$bid.bundle" ]] || fail "bundle $bid absent"; done
command -v python >/dev/null 2>&1 || fail "python absent"
python - <<'PYCHK' >/dev/null 2>&1 || fail "UnityPy / texture2ddecoder / Pillow absents"
import UnityPy, texture2ddecoder
from PIL import Image
PYCHK

mkdir -p "$OUT/textures" "$OUT/meshes"
rm -f "$OUT"/textures/*.png "$OUT"/meshes/*.obj "$OUT/manifest.json" 2>/dev/null || true

echo "AUDIE_RECON_V1_START"
PYTHONUNBUFFERED=1 python - "$LOCAL" "$OUT" "$UNITY_VERSION" <<'PY'
from pathlib import Path
from collections import Counter
import hashlib, json, re, sys
import UnityPy
import texture2ddecoder as t2d
from PIL import Image
from UnityPy.enums import TextureFormat

local=Path(sys.argv[1]); out=Path(sys.argv[2]); unity_version=sys.argv[3]
UnityPy.config.FALLBACK_UNITY_VERSION=unity_version
texdir=out/'textures'; meshdir=out/'meshes'; texdir.mkdir(parents=True,exist_ok=True); meshdir.mkdir(parents=True,exist_ok=True)

def typ(o): return str(getattr(getattr(o,'type',None),'name','') or '')
def pid(o): return int(getattr(o,'path_id',0) or 0)
def pname(o):
    try: return str(o.peek_name() or '')
    except Exception: return ''
def safe(s):
    z=re.sub(r'[^A-Za-z0-9._-]+','_',str(s)).strip('._')
    return z[:120] or 'asset'
def bgra(raw,w,h): return Image.frombytes('RGBA',(w,h),raw,'raw','BGRA')

def decode_texture(d):
    w=int(d.m_Width); h=int(d.m_Height); fmt=TextureFormat(int(d.m_TextureFormat)); name=fmt.name; data=bytes(d.get_image_data())
    if 'Crunched' in name:
        try: data=t2d.unpack_unity_crunch(data)
        except Exception: data=t2d.unpack_crunch(data)
        name=name.replace('Crunched','')
    if name.startswith('ASTC'):
        m=re.search(r'(\d+)x(\d+)',name)
        if not m: raise NotImplementedError(name)
        im=bgra(t2d.decode_astc(data,w,h,int(m.group(1)),int(m.group(2))),w,h)
    elif name in ('ETC_RGB4','ETC_RGB4_3DS'): im=bgra(t2d.decode_etc1(data,w,h),w,h)
    elif name=='ETC2_RGB': im=bgra(t2d.decode_etc2(data,w,h),w,h)
    elif name=='ETC2_RGBA1': im=bgra(t2d.decode_etc2a1(data,w,h),w,h)
    elif name=='ETC2_RGBA8': im=bgra(t2d.decode_etc2a8(data,w,h),w,h)
    elif name=='DXT1': im=bgra(t2d.decode_bc1(data,w,h),w,h)
    elif name=='DXT5': im=bgra(t2d.decode_bc3(data,w,h),w,h)
    elif name=='BC4': im=bgra(t2d.decode_bc4(data,w,h),w,h)
    elif name=='BC5': im=bgra(t2d.decode_bc5(data,w,h),w,h)
    elif name=='BC7': im=bgra(t2d.decode_bc7(data,w,h),w,h)
    elif name=='RGBA32': im=Image.frombytes('RGBA',(w,h),data[:w*h*4],'raw','RGBA')
    elif name=='BGRA32': im=Image.frombytes('RGBA',(w,h),data[:w*h*4],'raw','BGRA')
    elif name=='ARGB32': im=Image.frombytes('RGBA',(w,h),data[:w*h*4],'raw','ARGB')
    elif name=='RGB24': im=Image.frombytes('RGB',(w,h),data[:w*h*3],'raw','RGB').convert('RGBA')
    else: raise NotImplementedError(name)
    return im.transpose(Image.Transpose.FLIP_TOP_BOTTOM), fmt.name

def load_bundle(bid):
    return UnityPy.load(str(local/f'bundle-{bid}.bundle'))

# 1) Audie textures: exact named maps from the two texture bundles.
textures=[]; texture_errors=[]
for bid in (26633,26634):
    print('AUDIE_RECON_V1_SCAN_TEXTURES',bid,flush=True)
    env=load_bundle(bid)
    for o in list(getattr(env,'objects',[]) or []):
        if typ(o)!='Texture2D': continue
        name=pname(o)
        if 'A_Hero_Audie_01' not in name: continue
        try:
            d=o.read(); im,fmt=decode_texture(d)
            fn=f'b{bid}_p{pid(o)}_{safe(name)}.png'; fp=texdir/fn; im.save(fp,'PNG',optimize=True)
            raw=fp.read_bytes()
            role='other'
            up=name.upper()
            if up.endswith('_HIGH_N') or up.endswith('_N'): role='normal'
            elif up.endswith('_HIGH_D'): role='high-diffuse'
            elif up.endswith('_D'): role='diffuse'
            elif up.endswith('_S'): role='surface'
            textures.append({'bundleId':bid,'pathID':str(pid(o)),'name':name,'role':role,'width':int(d.m_Width),'height':int(d.m_Height),'format':fmt,'src':f'/lab/audie-reconstruction-data/textures/{fn}','sha256':hashlib.sha256(raw).hexdigest()})
        except Exception as e:
            texture_errors.append({'bundleId':bid,'pathID':str(pid(o)),'name':name,'error':f'{type(e).__name__}:{e}'})

# 2) Meshes: export every real Mesh from the known mesh bundle.
meshes=[]; mesh_errors=[]
print('AUDIE_RECON_V1_SCAN_MESHES 26631',flush=True)
env=load_bundle(26631)
for o in list(getattr(env,'objects',[]) or []):
    if typ(o)!='Mesh': continue
    name=pname(o)
    try:
        m=o.read(); exp=getattr(m,'export',None)
        if not callable(exp): raise RuntimeError('Mesh.export unavailable')
        text=exp(); fn=f'b26631_p{pid(o)}_{safe(name)}.obj'; fp=meshdir/fn; fp.write_text(text,'utf-8',newline='')
        meshes.append({'bundleId':26631,'pathID':str(pid(o)),'name':name,'src':f'/lab/audie-reconstruction-data/meshes/{fn}','objBytes':fp.stat().st_size})
    except Exception as e:
        mesh_errors.append({'bundleId':26631,'pathID':str(pid(o)),'name':name,'error':f'{type(e).__name__}:{e}'})

# 3) Context bundles: inventory names only, to expose Material/Prefab/Animation evidence without fabricating links.
context=[]
for bid,role in ((26629,'material-common'),(17859,'prefab'),(26626,'animation')):
    p=local/f'bundle-{bid}.bundle'
    if not p.exists():
        context.append({'bundleId':bid,'role':role,'missing':True,'objects':[]}); continue
    print('AUDIE_RECON_V1_SCAN_CONTEXT',bid,role,flush=True)
    try:
        e=load_bundle(bid); objs=[]; counts=Counter()
        for o in list(getattr(e,'objects',[]) or []):
            t=typ(o); counts[t]+=1; n=pname(o)
            if n or t in ('Material','GameObject','AnimationClip','MeshRenderer','SkinnedMeshRenderer','MeshFilter'):
                objs.append({'type':t,'pathID':str(pid(o)),'name':n})
        # keep full small inventories; these bundles are manageable and useful for exact-name inspection
        context.append({'bundleId':bid,'role':role,'missing':False,'counts':dict(counts),'objects':objs})
    except Exception as ex:
        context.append({'bundleId':bid,'role':role,'error':f'{type(ex).__name__}:{ex}','objects':[]})

textures.sort(key=lambda x:({'diffuse':0,'high-diffuse':1,'normal':2,'surface':3}.get(x['role'],9),x['name']))
meshes.sort(key=lambda x:(x['name'].lower(),int(x['pathID'])))
manifest={
 'format':'WFGG_LASTWAR_AUDIE_RECONSTRUCTION_V1',
 'title':'A_Hero_Audie_01 — UV Reconstruction Bench',
 'authority':{
   'inventedGeometry':False,
   'meshBundle':26631,
   'textureBundles':[26633,26634],
   'manualCrossBundleUVTest':True,
   'warning':'The viewer intentionally tests real exported meshes against real Audie textures. A visual match proves UV compatibility, not yet the exact runtime renderer/material linkage.'
 },
 'counts':{'textures':len(textures),'meshes':len(meshes),'textureErrors':len(texture_errors),'meshErrors':len(mesh_errors)},
 'textures':textures,'meshes':meshes,'context':context,
 'diagnostics':{'textureErrors':texture_errors,'meshErrors':mesh_errors}
}
(out/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n','utf-8')
print('AUDIE_RECON_V1_READY',f'textures={len(textures)}',f'meshes={len(meshes)}',f'textureErrors={len(texture_errors)}',f'meshErrors={len(mesh_errors)}',flush=True)
print('MANIFEST='+str(out/'manifest.json'),flush=True)
PY

echo "VIEWER=http://127.0.0.1:8788/lab/lastwar-audie-reconstruction-viewer.html?v=1"
