#!/data/data/com.termux/files/usr/bin/bash
set -Eeuo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BRANCH="portal-auth-lastwar-lab-v1"
INDEX="$ROOT/frontend/lab/master-assets-v2/index/lastwar-graphics-master-index-v1.json"
STAGE="$ROOT/frontend/lab/master-assets-v2/meta/current15-exact-bundle-stage.json"
CLOSURE="$ROOT/frontend/lab/local_assets/lastwar-formation-ptr-exact-v4/bundles"
OUTDIR="$ROOT/frontend/lab/formation-bridge-bundle-viewer-data"
UNITY_VERSION="2019.4.41f1"
TARGETS=(10347 6933 17859 26626 26628 26629 26631 26633 26634)

fail(){ printf 'ERREUR: %s\n' "$*" >&2; exit 1; }
cd "$ROOT"
[[ "$(git branch --show-current)" == "$BRANCH" ]] || fail "branche LAB incorrecte"
[[ -s "$INDEX" ]] || fail "index graphique absent"
[[ -s "$STAGE" ]] || fail "stage Current15 absent"
[[ -d "$CLOSURE" ]] || fail "cache Formation absent"
command -v python >/dev/null 2>&1 || fail "python absent"
python - <<'PYCHK' >/dev/null 2>&1 || fail "UnityPy / texture2ddecoder / Pillow absents"
import UnityPy, texture2ddecoder
from PIL import Image
PYCHK
mkdir -p "$OUTDIR"

echo "FORMATION_BRIDGE_BUNDLE_VIEWER_V1_START targets=${#TARGETS[@]}"
PYTHONUNBUFFERED=1 python - "$ROOT" "$INDEX" "$STAGE" "$CLOSURE" "$OUTDIR" "$UNITY_VERSION" "${TARGETS[@]}" <<'PY'
from pathlib import Path
from collections import Counter
import json,re,sys
import UnityPy, texture2ddecoder as t2d
from PIL import Image
from UnityPy.enums import TextureFormat

root,indexp,stagep,closure,outdir=map(Path,sys.argv[1:6])
unity_version=sys.argv[6]; targets=[int(x) for x in sys.argv[7:]]
UnityPy.config.FALLBACK_UNITY_VERSION=unity_version
idx=json.loads(indexp.read_text('utf-8'))
stage=json.loads(stagep.read_text('utf-8'))
byid={int(x['bundleId']):x for x in idx.get('bundles',[]) if isinstance(x,dict) and x.get('bundleId') is not None}
roles={
  10347:'background-assets',6933:'formation-consumer',17859:'murphy-prefab',26626:'murphy-animation',
  26628:'murphy-material',26629:'murphy-material-common',26631:'murphy-mesh',26633:'murphy-texture',26634:'murphy-texture-pbr'
}

murphy=next((h for h in stage.get('heroes',[]) if int(h.get('heroId',-1))==50006),None)
if not murphy: raise SystemExit('MURPHY_STAGE_MISSING')
stage_paths={int(b['bundleId']):root/str(b.get('localRel') or '') for b in murphy.get('bundles',[]) if b.get('bundleId') is not None}

def source_for(bid):
    p=closure/f'bundle-{bid}.bundle'
    if p.is_file(): return p,'formation-closure'
    p=stage_paths.get(bid)
    if p and p.is_file(): return p,'current15-murphy-stage'
    return None,'missing'

def typ(o): return str(getattr(getattr(o,'type',None),'name','') or '')
def pid(o): return int(getattr(o,'path_id',0) or 0)
def sf(o): return str(getattr(getattr(o,'assets_file',None),'name','') or '')
def pname(o):
    try:return str(o.peek_name() or '')
    except:return ''
def safe(s):
    z=re.sub(r'[^A-Za-z0-9._-]+','_',str(s)).strip('._')
    return z[:100] or 'asset'
def bgra(raw,w,h):return Image.frombytes('RGBA',(w,h),raw,'raw','BGRA')
def decode(d):
    w=int(d.m_Width);h=int(d.m_Height);fmt=TextureFormat(int(d.m_TextureFormat));name=fmt.name;data=bytes(d.get_image_data())
    if 'Crunched' in name:
        try:data=t2d.unpack_unity_crunch(data)
        except Exception:data=t2d.unpack_crunch(data)
        name=name.replace('Crunched','')
    if name.startswith('ASTC'):
        m=re.search(r'(\d+)x(\d+)',name)
        if not m:raise NotImplementedError(name)
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
    return im.transpose(Image.Transpose.FLIP_TOP_BOTTOM),fmt.name

def pptr_count(v):
    n=0
    def rec(x):
        nonlocal n
        if isinstance(x,dict):
            fk=next((k for k in ('m_FileID','fileID','fileId','m_FileId') if k in x),None)
            pk=next((k for k in ('m_PathID','pathID','pathId','m_PathId') if k in x),None)
            if fk is not None and pk is not None:n+=1
            for y in x.values():rec(y)
        elif isinstance(x,(list,tuple)):
            for y in x:rec(y)
    rec(v);return n

bundles=[]; failures=[]
for pos,bid in enumerate(targets,1):
    src,source_kind=source_for(bid)
    if not src: raise SystemExit(f'BUNDLE_SOURCE_MISSING {bid}')
    print('FORMATION_BRIDGE_BUNDLE_VIEWER_V1_BUNDLE',f'{pos}/{len(targets)}',f'bundle={bid}',f'source={source_kind}',flush=True)
    env=UnityPy.load(str(src)); objs=list(getattr(env,'objects',[]) or []); counts=Counter(typ(o) for o in objs)
    rec=byid.get(bid,{})
    bdir=outdir/str(bid); texdir=bdir/'textures'; texdir.mkdir(parents=True,exist_ok=True)
    for old in texdir.glob('*.png'):
        try:old.unlink()
        except:pass
    textures=[]; objects=[]
    for o in objs:
        otype=typ(o); nm=pname(o); pc=None
        try:pc=pptr_count(o.read_typetree())
        except:pc=None
        objects.append({'type':otype,'name':nm,'pathID':str(pid(o)),'serializedFile':sf(o),'ptrCount':pc})
        if otype!='Texture2D':continue
        try:
            d=o.read();im,fmt=decode(d);w=int(d.m_Width);h=int(d.m_Height)
            fn=f'p{pid(o)}_{safe(nm)}.png';im.save(texdir/fn,'PNG',optimize=False)
            textures.append({'name':nm,'pathID':str(pid(o)),'width':w,'height':h,'format':fmt,'src':f'/lab/formation-bridge-bundle-viewer-data/{bid}/textures/{fn}'})
        except Exception as e:
            failures.append({'bundleId':bid,'type':'Texture2D','name':nm,'pathID':str(pid(o)),'error':f'{type(e).__name__}:{e}'})
    textures.sort(key=lambda x:(-(x['width']*x['height']),x['name'].lower()))
    objects.sort(key=lambda x:(x['type'].lower(),x['name'].lower(),x['pathID']))
    bundle={
      'bundleId':bid,'role':roles.get(bid,'target'),'sourceKind':source_kind,'sourceFile':src.name,
      'logicalName':rec.get('logicalName',''),'aliasName':rec.get('aliasName',''),'assetPaths':rec.get('assetPaths',[]),
      'dependencyBundleIds':rec.get('dependencyBundleIds',[]),'dependentBundleIds':rec.get('dependentBundleIds',[]),
      'objectCount':len(objs),'typeCounts':dict(counts),'textureCount':len(textures),'textures':textures,'objects':objects,
      'meshObjects':[x for x in objects if x['type']=='Mesh'],'materialObjects':[x for x in objects if x['type']=='Material'],
      'animationObjects':[x for x in objects if x['type'] in ('AnimationClip','AnimatorController','AnimatorOverrideController')]
    }
    bundles.append(bundle)
    (bdir/'manifest.json').write_text(json.dumps(bundle,ensure_ascii=False,indent=2)+'\n','utf-8')

manifest={
 'format':'WFGG_LASTWAR_FORMATION_BRIDGE_BUNDLE_VIEWER_V1',
 'bundles':bundles,
 'counts':{'bundles':len(bundles),'textures':sum(x['textureCount'] for x in bundles),'decodeFailures':len(failures)},
 'decodeFailures':failures,
 'guardrails':{'actualGameAssetsOnly':True,'generatedVisuals':False,'labOnly':True,'mainUntouched':True}
}
(outdir/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n','utf-8')
print('FORMATION_BRIDGE_BUNDLE_VIEWER_V1_READY',f"bundles={len(bundles)}",f"textures={manifest['counts']['textures']}",f"failures={len(failures)}",flush=True)
PY

echo "Viewer: http://127.0.0.1:8788/lab/lastwar-formation-bridge-bundle-viewer.html?v=1"
