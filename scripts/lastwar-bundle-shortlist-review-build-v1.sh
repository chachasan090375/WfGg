#!/data/data/com.termux/files/usr/bin/bash
set -Eeuo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BRANCH="portal-auth-lastwar-lab-v1"
LOCAL="$ROOT/frontend/lab/local_assets/lastwar-formation-ptr-exact-v4/bundles"
OUTDIR="$ROOT/frontend/lab/bundle-shortlist-review-data"
UNITY_VERSION="2019.4.41f1"
TARGETS=(10347 23473 26598)
fail(){ printf 'ERREUR: %s\n' "$*" >&2; exit 1; }
cd "$ROOT"
[[ "$(git branch --show-current)" == "$BRANCH" ]] || fail "branche LAB incorrecte"
[[ -d "$LOCAL" ]] || fail "cache bundles absent"
python - <<'PYCHK' >/dev/null 2>&1 || fail "UnityPy / texture2ddecoder / Pillow absents"
import UnityPy, texture2ddecoder
from PIL import Image
PYCHK
mkdir -p "$OUTDIR/textures"
rm -f "$OUTDIR"/textures/*.png "$OUTDIR/manifest.json" 2>/dev/null || true
PYTHONUNBUFFERED=1 python - "$LOCAL" "$OUTDIR" "$UNITY_VERSION" "${TARGETS[@]}" <<'PY'
from pathlib import Path
from collections import Counter
import json,re,sys
import UnityPy, texture2ddecoder as t2d
from PIL import Image
from UnityPy.enums import TextureFormat
local=Path(sys.argv[1]);out=Path(sys.argv[2]);UnityPy.config.FALLBACK_UNITY_VERSION=sys.argv[3]
targets=[int(x) for x in sys.argv[4:]]
texdir=out/'textures';texdir.mkdir(parents=True,exist_ok=True)
def typ(o): return str(getattr(getattr(o,'type',None),'name','') or '')
def pid(o): return int(getattr(o,'path_id',0) or 0)
def pname(o):
    try:return str(o.peek_name() or '')
    except:return ''
def safe(s):
    z=re.sub(r'[^A-Za-z0-9._-]+','_',str(s)).strip('._')
    return z[:90] or 'asset'
def bgra(raw,w,h):return Image.frombytes('RGBA',(w,h),raw,'raw','BGRA')
def decode(d):
    w=int(d.m_Width);h=int(d.m_Height);fmt=TextureFormat(int(d.m_TextureFormat));name=fmt.name;data=bytes(d.get_image_data())
    if 'Crunched' in name:
        try:data=t2d.unpack_unity_crunch(data)
        except Exception:data=t2d.unpack_crunch(data)
        name=name.replace('Crunched','')
    if name.startswith('ASTC'):
        m=re.search(r'(\d+)x(\d+)',name)
        if not m: raise NotImplementedError(name)
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
    else: raise NotImplementedError(name)
    return im.transpose(Image.Transpose.FLIP_TOP_BOTTOM),fmt.name
bundles=[];failures=[]
for bid in targets:
    p=local/f'bundle-{bid}.bundle'
    if not p.is_file(): raise SystemExit(f'MISSING_BUNDLE {bid}')
    print('SHORTLIST_BUNDLE',bid,flush=True)
    env=UnityPy.load(str(p));objs=list(getattr(env,'objects',[]) or []);counts=Counter(typ(o) for o in objs)
    bname=''
    for o in objs:
        if typ(o)=='AssetBundle':
            bname=pname(o)
            if bname:break
    textures=[]
    for o in objs:
        if typ(o)!='Texture2D': continue
        nm=pname(o)
        try:
            d=o.read();w=int(d.m_Width);h=int(d.m_Height);im,fmt=decode(d)
            fn=f'b{bid}_p{pid(o)}_{safe(nm)}.png';im.save(texdir/fn,'PNG',optimize=False)
            textures.append({'name':nm,'pathID':str(pid(o)),'width':w,'height':h,'format':fmt,'file':'textures/'+fn})
        except Exception as e:
            failures.append({'bundleId':bid,'pathID':str(pid(o)),'name':nm,'error':f'{type(e).__name__}:{e}'})
    textures.sort(key=lambda x:(-(x['width']*x['height']),x['name']))
    bundles.append({'bundleId':bid,'name':bname,'typeCounts':dict(counts),'objectCount':len(objs),'textures':textures})
manifest={'format':'WFGG_LASTWAR_BUNDLE_SHORTLIST_REVIEW_V1','bundles':bundles,'counts':{'bundles':len(bundles),'decodedTextures':sum(len(b['textures']) for b in bundles),'decodeFailures':len(failures)},'decodeFailures':failures,'guardrails':{'actualDecodedGameTexturesOnly':True,'generatedVisuals':False,'labBranchOnly':True}}
(out/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n','utf-8')
print('SHORTLIST_READY',f"bundles={len(bundles)}",f"textures={manifest['counts']['decodedTextures']}",f"failures={len(failures)}",flush=True)
PY
echo "Viewer: http://127.0.0.1:8788/lab/lastwar-bundle-shortlist-review.html?v=1"
