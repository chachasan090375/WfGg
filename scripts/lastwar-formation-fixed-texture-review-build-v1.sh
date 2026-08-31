#!/data/data/com.termux/files/usr/bin/bash
set -Eeuo pipefail

# WfGg Last War LAB — fixed-image review lot V1
# Exact current Formation closure/cache only. Selects plausible fixed/background
# Texture2D objects by geometry first, decodes them to PNG, publishes a LAB
# manifest, and never promotes a visual candidate to proof.

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BRANCH="portal-auth-lastwar-lab-v1"
META="$ROOT/frontend/lab/master-assets-v2/meta"
SUMMARY="$META/formation-ptr-exact-v4-summary-v1.json"
REVIEW="$ROOT/frontend/lab/formation-texture-review"
ASSETS="$REVIEW/assets"
MANIFEST="$REVIEW/manifest.json"
OUT="$META/formation-fixed-texture-review-v1.json"
REPORT="$HOME/storage/downloads/WFGG_LASTWAR_FORMATION_FIXED_TEXTURE_REVIEW_V1.txt"
UNITY_VERSION="2019.4.41f1"
MAX_EXPORT=48

fail(){ printf 'ERREUR: %s\n' "$*" >&2; exit 1; }
cd "$ROOT"
[[ "$(git branch --show-current)" == "$BRANCH" ]] || fail "branche LAB incorrecte"
[[ -s "$SUMMARY" ]] || fail "summary V4 absent: $SUMMARY"
command -v python >/dev/null 2>&1 || fail "python absent"
python - <<'PYCHK' >/dev/null 2>&1 || fail "UnityPy/texture2ddecoder/Pillow absents"
import UnityPy, texture2ddecoder
from PIL import Image
PYCHK
mkdir -p "$ASSETS" "$(dirname "$REPORT")"
rm -f "$ASSETS"/*.png "$MANIFEST" 2>/dev/null || true

python - "$SUMMARY" "$REVIEW" "$OUT" "$REPORT" "$UNITY_VERSION" "$MAX_EXPORT" <<'PY'
from __future__ import annotations
from pathlib import Path
from collections import defaultdict
import hashlib,json,math,re,sys,traceback
import UnityPy
import texture2ddecoder as t2d
from PIL import Image
from UnityPy.enums import TextureFormat

sump,reviewp,outp,reportp=map(Path,sys.argv[1:5]); unity_version=sys.argv[5]; max_export=int(sys.argv[6])
UnityPy.config.FALLBACK_UNITY_VERSION=unity_version
s=json.loads(sump.read_text('utf-8'))
closure={int(x) for x in ((s.get('dependencySelection') or {}).get('selectedBundleIds') or [])}
if len(closure)!=195: raise SystemExit(f'CLOSURE_MISMATCH expected=195 actual={len(closure)}')
assets=reviewp/'assets';assets.mkdir(parents=True,exist_ok=True)

# Proven current-build cache only.
bundle_paths={}
roots=[sump.parents[2]/'local_assets'/'lastwar-formation-ptr-exact-v2'/'bundles',
       sump.parents[2]/'local_assets'/'lastwar-formation-ptr-exact-v4'/'bundles']
for root in roots:
    if not root.is_dir(): continue
    for p in root.glob('bundle-*.bundle'):
        m=re.fullmatch(r'bundle-(\d+)\.bundle',p.name)
        if m and int(m.group(1)) in closure: bundle_paths.setdefault(int(m.group(1)),p)
if len(bundle_paths)!=195: raise SystemExit(f'CACHE_CLOSURE_MISMATCH expected=195 actual={len(bundle_paths)}')

TECH=re.compile(r'(^|[_\-])(n|normal)([_\-]|$)|noise|mask|splat|control|ctrl|lightmap|rough|metal|height|flow|distort|ramp|particle|lut|shadowmap',re.I)
VISUAL=re.compile(r'background|\bbg\b|world|city|scene|map|ground|terrain|formation|show|environment|env_',re.I)

def geometry_ok(w,h):
    if w < 480 or h < 480: return False
    if w*h < 512*768: return False
    ratio=w/h
    return 0.45 <= ratio <= 2.40

def rank_score(name,w,h):
    area=w*h; ratio=w/h; reasons=[]
    score=min(180, int(math.log2(max(1,area/(512*512)) + 1)*58))
    reasons.append('large-geometry')
    if 0.65 <= ratio <= 1.85: score+=26; reasons.append('screen-region-ratio')
    elif 0.50 <= ratio <= 2.10: score+=12; reasons.append('broad-screen-ratio')
    if VISUAL.search(name or ''): score+=18; reasons.append('visual-name-hint')
    if TECH.search(name or ''): score-=85; reasons.append('technical-map-penalty')
    return score,reasons

# Metadata pass across exact 195-bundle closure. No global scan.
candidates=[]; texture_seen=0; bundle_errors=[]
for bid,p in sorted(bundle_paths.items()):
    try: env=UnityPy.load(str(p))
    except Exception as e:
        bundle_errors.append({'bundleId':bid,'error':f'{type(e).__name__}:{e}'});continue
    for obj in list(getattr(env,'objects',[]) or []):
        if getattr(getattr(obj,'type',None),'name','')!='Texture2D': continue
        texture_seen+=1
        try:
            d=obj.read();w=int(getattr(d,'m_Width',0) or 0);h=int(getattr(d,'m_Height',0) or 0)
            try:name=str(obj.peek_name() or getattr(d,'m_Name','') or '')
            except:name=str(getattr(d,'m_Name','') or '')
            if not geometry_ok(w,h): continue
            fmt=TextureFormat(int(d.m_TextureFormat)).name
            score,reasons=rank_score(name,w,h)
            candidates.append({'bundleId':bid,'bundlePath':str(p),'pathID':int(obj.path_id),'name':name,'width':w,'height':h,'textureFormat':fmt,'score':score,'reasons':reasons})
        except Exception as e:
            continue
candidates.sort(key=lambda r:(-r['score'],-r['width']*r['height'],r['bundleId'],r['pathID']))

# Direct decoder: bypass UnityPy Texture2DConverter/astc_encoder Android boundary.
def bgra(raw,w,h): return Image.frombytes('RGBA',(w,h),raw,'raw','BGRA')
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
    else: raise NotImplementedError('DIRECT_DECODER_FORMAT '+name)
    return im.transpose(Image.Transpose.FLIP_TOP_BOTTOM),fmt,len(data)

def safe(s):
    z=re.sub(r'[^A-Za-z0-9._-]+','_',str(s)).strip('._')
    return z[:72] or 'texture'

exported=[];failures=[]
# Open only candidate bundles; decode in ranking order until the review lot is full.
by_bundle_env={}
for cand in candidates:
    if len(exported)>=max_export: break
    bid=cand['bundleId'];pid=cand['pathID'];p=Path(cand['bundlePath'])
    try:
        env=by_bundle_env.get(bid)
        if env is None:
            env=UnityPy.load(str(p));by_bundle_env[bid]=env
        obj=next((o for o in list(getattr(env,'objects',[]) or []) if int(getattr(o,'path_id',0) or 0)==pid),None)
        if obj is None: raise LookupError('pathID_not_found')
        d=obj.read();im,fmt,data_len=decode(d)
        seq=len(exported)+1
        fn=f"{seq:03d}_b{bid}_p{pid}_{safe(cand['name'])}.png"
        fp=assets/fn;im.save(fp,'PNG',optimize=True)
        raw=fp.read_bytes();sha=hashlib.sha256(raw).hexdigest()
        exported.append({
          'id':f'b{bid}:p{pid}','file':fn,'src':'/lab/formation-texture-review/assets/'+fn,
          'bundleId':bid,'pathID':pid,'name':cand['name'],'width':cand['width'],'height':cand['height'],
          'textureFormat':fmt.name,'sourceImageBytes':data_len,'pngBytes':len(raw),'sha256':sha,
          'rank':seq,'score':cand['score'],'reasons':cand['reasons']})
        print('FORMATION_FIXED_REVIEW_PNG',f'#{seq:03d}',f"{cand['width']}x{cand['height']}",fmt.name,cand['name'])
    except Exception as e:
        failures.append({**cand,'error':f'{type(e).__name__}:{e}','traceback':traceback.format_exc(limit=3)})

manifest={
 'format':'WFGG_LASTWAR_FORMATION_FIXED_TEXTURE_REVIEW_MANIFEST_V1',
 'generatedFrom':'exact current Formation closure',
 'selection':{
   'rule':'geometry-first fixed-image review heuristic',
   'minWidth':480,'minHeight':480,'minArea':512*768,'aspectRatioRange':[0.45,2.40],
   'technicalNameTokensArePenaltyOnly':True,'maxExport':max_export,
   'important':'Review candidate only. Visual similarity does not prove runtime use.'},
 'counts':{'closureBundles':len(closure),'cachedBundles':len(bundle_paths),'texture2DSeen':texture_seen,'geometryCandidates':len(candidates),'exported':len(exported),'decodeFailures':len(failures)},
 'items':exported
}
(reviewp/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n','utf-8')
result={**manifest,'failures':failures[:100],'guardrails':{'exactFormationClosureOnly':True,'currentBuildCacheOnly':True,'globalGameScan':False,'historicalOffsetsReused':False,'candidatePromotion':False,'mainUntouched':True}}
outp.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n','utf-8')

lines=['WfGg Last War — FORMATION FIXED TEXTURE REVIEW V1','',
 f"closureBundles={len(closure)} cachedBundles={len(bundle_paths)} texture2DSeen={texture_seen} geometryCandidates={len(candidates)} exported={len(exported)} decodeFailures={len(failures)}",'',
 'EXPORTED LAB REVIEW IMAGES']
for r in exported:
    lines.append(f"  #{r['rank']:03d} score={r['score']} bundle={r['bundleId']} pathID={r['pathID']} size={r['width']}x{r['height']} format={r['textureFormat']} name={r['name']} file={r['file']}")
lines+=['','NEXT open /lab/lastwar-formation-texture-viewer.html and review Oui/Non.',
 'RULE: geometry/name ranking is review scope only, not evidence of runtime use.',
 'RULE: exact current Formation closure/cache only; no global game scan; main untouched.']
reportp.write_text('\n'.join(lines)+'\n','utf-8')
print('FORMATION_FIXED_REVIEW_OK',f'candidates={len(candidates)}',f'exported={len(exported)}',f'failed={len(failures)}')
print('FORMATION_FIXED_REVIEW_MANIFEST',reviewp/'manifest.json')
print('FORMATION_FIXED_REVIEW_REPORT',reportp)
PY

git add "$REVIEW" "$OUT"
if ! git diff --cached --quiet; then
  git commit -m "lab: publish fixed Formation texture review lot"
  git push origin "$BRANCH"
fi

echo "=== FORMATION FIXED TEXTURE REVIEW LOT TERMINE ==="
echo "Viewer: http://127.0.0.1:8787/lab/lastwar-formation-texture-viewer.html"
echo "Rapport: $REPORT"
echo "main/preview inchangés."
