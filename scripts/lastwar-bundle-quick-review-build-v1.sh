#!/data/data/com.termux/files/usr/bin/bash
set -Eeuo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BRANCH="portal-auth-lastwar-lab-v1"
SUMMARY="$ROOT/frontend/lab/master-assets-v2/meta/formation-ptr-exact-v4-summary-v1.json"
LOCAL="$ROOT/frontend/lab/local_assets/lastwar-formation-ptr-exact-v4/bundles"
OUTDIR="$ROOT/frontend/lab/bundle-quick-review-data"
REPORT="$HOME/storage/downloads/WFGG_LASTWAR_BUNDLE_QUICK_REVIEW_V1.txt"
UNITY_VERSION="2019.4.41f1"
MAX_PREVIEWS="${MAX_PREVIEWS:-4}"

fail(){ printf 'ERREUR: %s\n' "$*" >&2; exit 1; }
cd "$ROOT"
[[ "$(git branch --show-current)" == "$BRANCH" ]] || fail "branche LAB incorrecte"
[[ -s "$SUMMARY" ]] || fail "summary V4 absent"
[[ -d "$LOCAL" ]] || fail "cache bundles V4 absent"
command -v python >/dev/null 2>&1 || fail "python absent"
python - <<'PYCHK' >/dev/null 2>&1 || fail "UnityPy / texture2ddecoder / Pillow absents"
import UnityPy, texture2ddecoder
from PIL import Image
PYCHK
mkdir -p "$OUTDIR/previews" "$(dirname "$REPORT")"
rm -f "$OUTDIR"/previews/*.png "$OUTDIR/manifest.json" 2>/dev/null || true

echo "BUNDLE_QUICK_REVIEW_V1_START"
PYTHONUNBUFFERED=1 python - "$SUMMARY" "$LOCAL" "$OUTDIR" "$REPORT" "$UNITY_VERSION" "$MAX_PREVIEWS" <<'PY'
from pathlib import Path
from collections import Counter
import json,re,sys
import UnityPy
import texture2ddecoder as t2d
from PIL import Image
from UnityPy.enums import TextureFormat

summaryp,localp,outdir,reportp=map(Path,sys.argv[1:5])
unity_version=sys.argv[5];max_previews=int(sys.argv[6])
UnityPy.config.FALLBACK_UNITY_VERSION=unity_version
previews=outdir/'previews';previews.mkdir(parents=True,exist_ok=True)

summ=json.loads(summaryp.read_text('utf-8'))
closure=sorted({int(x) for x in ((summ.get('dependencySelection') or {}).get('selectedBundleIds') or [])})
if len(closure)!=195:raise SystemExit(f'CLOSURE_GUARD expected195 actual={len(closure)}')
paths={bid:localp/f'bundle-{bid}.bundle' for bid in closure}
missing=[bid for bid,p in paths.items() if not p.is_file()]
if missing:raise SystemExit(f'BUNDLE_CACHE_GUARD missing={len(missing)} sample={missing[:10]}')

TECH_RE=re.compile(r'(normal|_n(?:$|_)|mask|rough|metal|metallic|ao(?:$|_)|height|noise|lut|flow|sdf|font|icon|emoji|sprite|atlas)',re.I)
SCENE_RE=re.compile(r'(terrain|ground|grass|road|world|city|map|desert|sand|snow|rock|mountain|water|river|sky|cloud)',re.I)

def typ(o):return str(getattr(getattr(o,'type',None),'name','') or '')
def pid(o):return int(getattr(o,'path_id',0) or 0)
def pname(o):
    try:return str(o.peek_name() or '')
    except:return ''
def safe(s):
    z=re.sub(r'[^A-Za-z0-9._-]+','_',str(s)).strip('._')
    return (z[:90] or 'asset')
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

records=[];decode_failures=[];load_failures=[]
for pos,bid in enumerate(closure,1):
    print('BUNDLE_QUICK_REVIEW_V1_BUNDLE',f'{pos}/195',f'bundle={bid}',flush=True)
    p=paths[bid]
    try:env=UnityPy.load(str(p))
    except Exception as e:
        load_failures.append({'bundleId':bid,'error':f'{type(e).__name__}:{e}'})
        records.append({'bundleId':bid,'name':'','typeCounts':{},'objectCount':0,'sceneScore':-1,'previewTextures':[],'loadError':str(e)})
        continue
    objs=list(getattr(env,'objects',[]) or [])
    counts=Counter(typ(o) for o in objs)
    bname=''
    for o in objs:
        if typ(o)=='AssetBundle':
            bname=pname(o)
            if bname:break
    texmeta=[]
    for o in objs:
        if typ(o)!='Texture2D':continue
        nm=pname(o)
        try:
            d=o.read();w=int(d.m_Width);h=int(d.m_Height);fmt=TextureFormat(int(d.m_TextureFormat)).name
        except Exception as e:
            decode_failures.append({'bundleId':bid,'pathID':str(pid(o)),'name':nm,'stage':'metadata','error':f'{type(e).__name__}:{e}'})
            continue
        area=max(1,w*h)
        score=area
        if SCENE_RE.search(nm):score*=1.35
        if TECH_RE.search(nm):score*=0.34
        if w<64 or h<64:score*=0.15
        texmeta.append({'obj':o,'name':nm,'pathID':pid(o),'width':w,'height':h,'format':fmt,'area':area,'score':score})
    texmeta.sort(key=lambda x:(-x['score'],-x['area'],x['name']))
    chosen=[];seen_names=set()
    for t in texmeta:
        key=(t['name'].lower(),t['width'],t['height'])
        if key in seen_names:continue
        seen_names.add(key);chosen.append(t)
        if len(chosen)>=max_previews:break
    previews_out=[]
    for n,t in enumerate(chosen,1):
        try:
            d=t['obj'].read();im,fmt=decode_texture(d)
            fn=f"b{bid}_{n:02d}_p{t['pathID']}_{safe(t['name'])}.png"
            fp=previews/fn;im.save(fp,'PNG',optimize=False)
            previews_out.append({'name':t['name'],'pathID':str(t['pathID']),'width':t['width'],'height':t['height'],'format':fmt,'file':'previews/'+fn})
        except Exception as e:
            decode_failures.append({'bundleId':bid,'pathID':str(t['pathID']),'name':t['name'],'stage':'decode','error':f'{type(e).__name__}:{e}'})
    scene_score=(counts.get('MeshRenderer',0)+counts.get('SkinnedMeshRenderer',0)+counts.get('Terrain',0))*100000 + counts.get('Mesh',0)*1000 + counts.get('GameObject',0)*10 + counts.get('Material',0)*5 + counts.get('Texture2D',0)
    records.append({'bundleId':bid,'name':bname,'objectCount':len(objs),'typeCounts':dict(counts),'sceneScore':scene_score,'previewTextures':previews_out,'loadError':None})

records.sort(key=lambda r:(-int(r.get('sceneScore') or 0),r['bundleId']))
for rank,r in enumerate(records,1):r['geometryRank']=rank
manifest={'format':'WFGG_LASTWAR_BUNDLE_QUICK_REVIEW_V1','scope':'exact current Formation closure','bundleCount':len(records),'maxPreviewTexturesPerBundle':max_previews,'bundles':records,'counts':{'loadFailures':len(load_failures),'decodeFailures':len(decode_failures)},'loadFailures':load_failures,'decodeFailures':decode_failures[:300],'guardrails':{'generatedVisuals':False,'actualDecodedGameTexturesOnly':True,'historicalOffsetsReused':False,'labBranchOnly':True}}
(outdir/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n','utf-8')
lines=['WfGg Last War — BUNDLE QUICK REVIEW V1','',f"bundles={len(records)} maxPreviews={max_previews} loadFailures={len(load_failures)} decodeFailures={len(decode_failures)}",'','Top bundles by serialized geometry potential:']
for r in records[:40]:
    c=r['typeCounts'];lines.append(f"bundle={r['bundleId']} name={r['name'] or '-'} score={r['sceneScore']} GO={c.get('GameObject',0)} Mesh={c.get('Mesh',0)} MeshRenderer={c.get('MeshRenderer',0)} Skinned={c.get('SkinnedMeshRenderer',0)} Terrain={c.get('Terrain',0)} Material={c.get('Material',0)} Texture2D={c.get('Texture2D',0)} previews={len(r['previewTextures'])}")
reportp.write_text('\n'.join(lines)+'\n','utf-8')
print('BUNDLE_QUICK_REVIEW_V1_READY',f'bundles={len(records)}',f'decodeFailures={len(decode_failures)}',flush=True)
print('BUNDLE_QUICK_REVIEW_V1_REPORT',reportp,flush=True)
PY

echo "=== BUNDLE QUICK REVIEW V1 TERMINE ==="
echo "Viewer data: $OUTDIR"
echo "Rapport: $REPORT"
echo "Aucun visuel généré : uniquement textures réelles décodées depuis les bundles."
