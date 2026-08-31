#!/data/data/com.termux/files/usr/bin/bash
set -Eeuo pipefail

# WfGg Last War LAB — Human visual fixed-image search V2
# Implements the six requested review optimizations continuously:
# 1 atlas/sprite-reference rejection, 2 grid review, 3 comparison display modes,
# 4 current-index external pass, 5 yes/no/unsure, 6 analytics for ordering only.

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BRANCH="portal-auth-lastwar-lab-v1"
META="$ROOT/frontend/lab/master-assets-v2/meta"
INDEXDIR="$ROOT/frontend/lab/master-assets-v2/index"
SUMMARY="$META/formation-ptr-exact-v4-summary-v1.json"
GINDEX="$INDEXDIR/lastwar-graphics-master-index-v1.json"
V1MAN="$ROOT/frontend/lab/formation-texture-review/manifest.json"
HUMAN1="$META/formation-fixed-texture-review-human-v1.json"
REF="$ROOT/frontend/lab/master-assets-v2/background/formation-layer0-world-baked.webp"
REVIEW="$ROOT/frontend/lab/formation-texture-review-v2"
ASSETS="$REVIEW/assets"
MANIFEST="$REVIEW/manifest.json"
OUT="$META/formation-visual-human-search-v2.json"
REPORT="$HOME/storage/downloads/WFGG_LASTWAR_FORMATION_VISUAL_HUMAN_SEARCH_V2.txt"
CACHE="$HOME/.cache/wfgg-formation-visual-human-v2"
UNITY_VERSION="2019.4.41f1"
MAX_CLOSURE=60
MAX_EXTERNAL=40
DECODE_POOL=120
EXTERNAL_BUNDLE_LIMIT=80

fail(){ printf 'ERREUR: %s\n' "$*" >&2; exit 1; }
cd "$ROOT"
[[ "$(git branch --show-current)" == "$BRANCH" ]] || fail "branche LAB incorrecte"
for f in "$SUMMARY" "$GINDEX" "$REF"; do [[ -s "$f" ]] || fail "fichier absent: $f"; done
command -v python >/dev/null 2>&1 || fail "python absent"
python - <<'PYCHK' >/dev/null 2>&1 || fail "UnityPy/texture2ddecoder/Pillow absents"
import UnityPy,texture2ddecoder
from PIL import Image,ImageOps
PYCHK
mkdir -p "$ASSETS" "$CACHE" "$(dirname "$REPORT")"
rm -f "$ASSETS"/*.png "$MANIFEST" 2>/dev/null || true

python - "$SUMMARY" "$GINDEX" "$V1MAN" "$HUMAN1" "$REF" "$REVIEW" "$OUT" "$REPORT" "$CACHE" "$UNITY_VERSION" "$MAX_CLOSURE" "$MAX_EXTERNAL" "$DECODE_POOL" "$EXTERNAL_BUNDLE_LIMIT" <<'PY'
from __future__ import annotations
from pathlib import Path
from collections import Counter,defaultdict
import hashlib,json,math,re,sys,traceback,zipfile
import UnityPy
import texture2ddecoder as t2d
from PIL import Image,ImageOps
from UnityPy.enums import TextureFormat

(sump,indexp,v1manp,human1p,refp,reviewp,outp,reportp,cachep)=map(Path,sys.argv[1:10])
unity_version=sys.argv[10];max_closure=int(sys.argv[11]);max_external=int(sys.argv[12]);decode_pool=int(sys.argv[13]);external_bundle_limit=int(sys.argv[14])
UnityPy.config.FALLBACK_UNITY_VERSION=unity_version
assets=reviewp/'assets';assets.mkdir(parents=True,exist_ok=True);cachep.mkdir(parents=True,exist_ok=True)
s=json.loads(sump.read_text('utf-8'));idx=json.loads(indexp.read_text('utf-8'))
closure={int(x) for x in ((s.get('dependencySelection') or {}).get('selectedBundleIds') or [])}
if len(closure)!=195: raise SystemExit(f'CLOSURE_MISMATCH expected=195 actual={len(closure)}')

# Human rejection authority: all 25 exported V1 images were visually rejected as atlases/icon packs.
human_reject=set()
if human1p.is_file() and v1manp.is_file():
    try:
        h=json.loads(human1p.read_text('utf-8'));m=json.loads(v1manp.read_text('utf-8'))
        if (h.get('humanObservation') or {}).get('reviewerDecisionForAll25')=='NO':
            for x in m.get('items',[]): human_reject.add((int(x['bundleId']),int(x['pathID'])))
    except Exception: pass

# Current-build bundle cache. We inventory names only; no historical offsets.
bundle_paths={}
local_root=sump.parents[2]/'local_assets'
if local_root.is_dir():
    for p in local_root.rglob('bundle-*.bundle'):
        m=re.fullmatch(r'bundle-(\d+)\.bundle',p.name)
        if m: bundle_paths.setdefault(int(m.group(1)),p)
closure_paths={bid:p for bid,p in bundle_paths.items() if bid in closure}
if len(closure_paths)!=195: raise SystemExit(f'CACHE_CLOSURE_MISMATCH expected=195 actual={len(closure_paths)}')

ATLAS_NAME=re.compile(r'(^sactx[-_])|sprite.?atlas|(^|[_-])atlas([_.-]|$)',re.I)
TECH=re.compile(r'(^|[_\-])(n|normal)([_\-]|$)|noise|mask|splat|control|ctrl|lightmap|rough|metal|height|flow|distort|ramp|particle|lut|shadow|gradient',re.I)
VISUAL=re.compile(r'background|(^|[_\-])bg([_\-.]|$)|world|city|scene|map|ground|terrain|formation|environment|env_|landscape|loading|battle|pvp|show',re.I)
SMALL_UI=re.compile(r'icon|avatar|badge|button|btn_|font|emoji|mark|rank|commonui|heroicon',re.I)

def pid(ptr):
    if ptr is None:return None
    for a in ('path_id','m_PathID','pathID'):
        try:
            v=getattr(ptr,a)
            if v is not None:return int(v)
        except Exception:pass
    if isinstance(ptr,dict):
        for k in ('m_PathID','pathID','path_id'):
            if k in ptr:
                try:return int(ptr[k])
                except:pass
    return None

def sprite_texture_counts(env):
    direct=Counter();atlas=Counter();sprite_total=0;atlas_total=0
    for obj in list(getattr(env,'objects',[]) or []):
        typ=getattr(getattr(obj,'type',None),'name','')
        if typ=='Sprite':
            sprite_total+=1
            try:
                d=obj.read();rd=getattr(d,'m_RD',None) or getattr(d,'m_RenderData',None)
                if rd is not None:
                    for a in ('texture','alphaTexture','m_Texture','m_AlphaTexture'):
                        q=pid(getattr(rd,a,None))
                        if q:direct[q]+=1
            except Exception:pass
        elif typ=='SpriteAtlas':
            atlas_total+=1
            try:
                d=obj.read();mp=getattr(d,'m_RenderDataMap',None)
                vals=[]
                if isinstance(mp,dict):vals=list(mp.values())
                elif isinstance(mp,(list,tuple)):vals=list(mp)
                for rd in vals:
                    for a in ('texture','alphaTexture','m_Texture','m_AlphaTexture'):
                        q=pid(getattr(rd,a,None))
                        if q:atlas[q]+=1
            except Exception:pass
    return direct,atlas,sprite_total,atlas_total

def geometry_ok(w,h):
    if w<384 or h<320:return False
    if w*h<262144:return False
    r=w/h
    return 0.35<=r<=3.20

def pre_score(name,w,h,srefs,arefs):
    r=w/h;score=0;reasons=[]
    area=w*h
    score+=min(140,int(math.log2(max(1,area/(384*384))+1)*42));reasons.append('geometry')
    if 0.55<=r<=1.75:score+=24;reasons.append('broad-screen-region-ratio')
    elif 0.40<=r<=2.40:score+=10;reasons.append('permissive-ratio')
    if VISUAL.search(name or ''):score+=24;reasons.append('visual-name-hint')
    if TECH.search(name or ''):score-=65;reasons.append('technical-map-penalty')
    if SMALL_UI.search(name or ''):score-=38;reasons.append('small-ui-name-penalty')
    if srefs==1:score-=12;reasons.append('one-sprite-reference')
    return score,reasons

def scan_bundle(bid,p,scope):
    rows=[];stats={}
    try:env=UnityPy.load(str(p))
    except Exception as e:return rows,{'loadError':f'{type(e).__name__}:{e}'}
    direct,atlas,sprite_total,atlas_total=sprite_texture_counts(env)
    stats={'sprites':sprite_total,'spriteAtlases':atlas_total}
    for obj in list(getattr(env,'objects',[]) or []):
        if getattr(getattr(obj,'type',None),'name','')!='Texture2D':continue
        try:
            d=obj.read();w=int(getattr(d,'m_Width',0) or 0);h=int(getattr(d,'m_Height',0) or 0)
            if not geometry_ok(w,h):continue
            try:name=str(obj.peek_name() or getattr(d,'m_Name','') or '')
            except:name=str(getattr(d,'m_Name','') or '')
            pathid=int(obj.path_id);srefs=int(direct.get(pathid,0));arefs=int(atlas.get(pathid,0))
            packed_name=bool(ATLAS_NAME.search(name or ''))
            atlas_likely=packed_name or srefs>=2 or arefs>=1
            score,reasons=pre_score(name,w,h,srefs,arefs)
            if packed_name:reasons.append('packed-atlas-name')
            if srefs>=2:reasons.append(f'spriteRefs={srefs}')
            if arefs:reasons.append(f'spriteAtlasRefs={arefs}')
            rows.append({'scope':scope,'bundleId':bid,'bundlePath':str(p),'pathID':pathid,'name':name,'width':w,'height':h,
                         'textureFormat':TextureFormat(int(d.m_TextureFormat)).name,'spriteRefs':srefs,'spriteAtlasRefs':arefs,
                         'atlasLikely':atlas_likely,'preScore':score,'reasons':reasons})
        except Exception:pass
    return rows,stats

# ---------- Pass A: exact 195-bundle closure ----------
closure_rows=[];closure_bundle_stats={}
for n,(bid,p) in enumerate(sorted(closure_paths.items()),1):
    rs,st=scan_bundle(bid,p,'formation-closure');closure_rows.extend(rs);closure_bundle_stats[str(bid)]=st
    if n%25==0:print('FORMATION_VISUAL_V2_SCAN',f'closureBundles={n}/195',f'geometryRows={len(closure_rows)}')

# Apply exact human rejection and atlas gate before any image is shown again.
closure_eligible=[r for r in closure_rows if (r['bundleId'],r['pathID']) not in human_reject and not r['atlasLikely']]
closure_eligible.sort(key=lambda r:(-r['preScore'],-r['width']*r['height'],r['bundleId'],r['pathID']))

# ---------- Pass B: outside closure, current graphics index only ----------
# Current index determines which external bundles may be considered. No history/old offsets.
EXT_HINT=re.compile(r'formation|background|(^|[/_.-])bg([/_.-]|$)|world|scene|city|environment|terrain|ground|landscape|loading|battle|pvp|show|texture',re.I)
EXT_NEG=re.compile(r'icon|avatar|emoji|font|button|badge|sprite.?atlas|uilwcommon',re.I)
external_index=[]
for rec in idx.get('bundles',[]):
    try:bid=int(rec.get('bundleId'))
    except:continue
    if bid in closure:continue
    texts=[str(rec.get('logicalName') or ''),str(rec.get('aliasName') or ''),*[str(x) for x in rec.get('assetPaths',[])]]
    blob=' | '.join(texts);sc=0;why=[]
    if EXT_HINT.search(blob):sc+=30;why.append('current-index-visual-hint')
    if any(re.search(r'\.(png|jpe?g|tga|psd|exr|hdr|webp|bmp|tiff?)$',x,re.I) for x in texts):sc+=22;why.append('image-extension')
    if EXT_NEG.search(blob):sc-=28;why.append('ui-atlas-penalty')
    if sc<=0:continue
    external_index.append({'bundleId':bid,'score':sc,'record':rec,'reasons':why})
external_index.sort(key=lambda x:(-x['score'],x['bundleId']))
external_index=external_index[:external_bundle_limit]

# Resolve current preferredExtraction only when the referenced current APK/file is locally readable.
def resolve_physical(v):
    if not v:return None
    p=Path(str(v)).expanduser()
    cands=[p,Path.home()/'storage/downloads'/p.name,Path.home()/'storage/shared/Download'/p.name,ROOT/p]
    for q in cands:
        if q.is_file():return q
    return None

def materialize_current_index(row):
    bid=row['bundleId']
    if bid in bundle_paths:return bundle_paths[bid], 'cached-current'
    rec=row['record'];pe=rec.get('preferredExtraction') or {}
    phys=resolve_physical(pe.get('physicalApk'))
    if not phys:return None,'current-physical-source-unavailable'
    try:
        off=int(pe.get('offset') or 0);span=pe.get('spanBytes')
        if span is None:
            end=pe.get('end');span=(int(end)-off) if end is not None else None
        span=int(span) if span is not None else None
        if span is None or span<=0 or span>67108864:return None,'current-span-invalid'
        out=cachep/f'external-bundle-{bid}.bundle'
        entry=pe.get('fragmentEntry')
        if entry:
            with zipfile.ZipFile(phys,'r') as zf:
                with zf.open(str(entry),'r') as f:
                    try:f.seek(off)
                    except Exception:
                        if off: _=f.read(off)
                    data=f.read(span)
        else:
            with phys.open('rb') as f:f.seek(off);data=f.read(span)
        if len(data)!=span:return None,f'current-short-read-{len(data)}-of-{span}'
        out.write_bytes(data)
        # Validation is mandatory before using current extracted bytes.
        _=UnityPy.load(str(out))
        return out,'current-index-preferredExtraction'
    except Exception as e:
        return None,f'current-extraction-error:{type(e).__name__}:{e}'

external_rows=[];external_resolution=[]
for row in external_index:
    p,how=materialize_current_index(row);external_resolution.append({'bundleId':row['bundleId'],'indexScore':row['score'],'resolution':how})
    if not p:continue
    rs,st=scan_bundle(row['bundleId'],p,'current-index-external');external_rows.extend(rs)
external_eligible=[r for r in external_rows if not r['atlasLikely']]
external_eligible.sort(key=lambda r:(-r['preScore'],-r['width']*r['height'],r['bundleId'],r['pathID']))

# ---------- Exact asset decoding ----------
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
    else:raise NotImplementedError('DIRECT_DECODER_FORMAT '+name)
    return im.transpose(Image.Transpose.FLIP_TOP_BOTTOM),fmt,len(data)

def safe(s):
    z=re.sub(r'[^A-Za-z0-9._-]+','_',str(s)).strip('._')
    return z[:68] or 'texture'

ref=Image.open(refp).convert('RGB')
# Non-authoritative low-frequency comparison used ONLY for ordering.
def signature(im):
    x=ImageOps.fit(im.convert('RGB'),(24,24),method=Image.Resampling.BILINEAR,centering=(.5,.5))
    return list(x.getdata())
refsig=signature(ref)
def similarity(im):
    sig=signature(im);acc=0
    for a,b in zip(sig,refsig):
        acc+=(a[0]-b[0])**2+(a[1]-b[1])**2+(a[2]-b[2])**2
    rms=math.sqrt(acc/(len(sig)*3));return round(max(0.0,100.0-(rms/255.0*100.0)),2)

def decode_pool_rows(rows,scope_limit):
    exported=[];fails=[];envs={}
    for cand in rows[:decode_pool]:
        if len(exported)>=scope_limit*2:break
        bid=cand['bundleId'];p=Path(cand['bundlePath']);pid0=cand['pathID']
        try:
            env=envs.get((bid,str(p)))
            if env is None:env=UnityPy.load(str(p));envs[(bid,str(p))]=env
            obj=next((o for o in list(getattr(env,'objects',[]) or []) if int(getattr(o,'path_id',0) or 0)==pid0),None)
            if obj is None:raise LookupError('pathID_not_found')
            im,fmt,data_len=decode(obj.read());sim=similarity(im)
            rec={**cand,'textureFormat':fmt.name,'sourceImageBytes':data_len,'referenceSimilarity':sim,
                 'orderScore':round(cand['preScore']+sim*.45,2),'referenceAuthority':'comparison-only; not runtime proof'}
            rec['_image']=im;exported.append(rec)
        except Exception as e:fails.append({**cand,'error':f'{type(e).__name__}:{e}'})
    exported.sort(key=lambda r:(-r['orderScore'],-r['referenceSimilarity'],-r['preScore']))
    return exported[:scope_limit],fails

closure_dec,closure_fail=decode_pool_rows(closure_eligible,max_closure)
external_dec,external_fail=decode_pool_rows(external_eligible,max_external)
selected=closure_dec+external_dec

# Publish actual decoded PNGs after final ranking. No synthesized/reconstructed image is created.
items=[]
for seq,r in enumerate(selected,1):
    im=r.pop('_image');fn=f"{seq:03d}_{'C' if r['scope']=='formation-closure' else 'E'}_b{r['bundleId']}_p{r['pathID']}_{safe(r['name'])}.png"
    fp=assets/fn;im.save(fp,'PNG',optimize=True);raw=fp.read_bytes()
    items.append({**r,'id':f"{r['scope']}:b{r['bundleId']}:p{r['pathID']}",'rank':seq,'file':fn,
                  'src':'/lab/formation-texture-review-v2/assets/'+fn,'pngBytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()})
    print('FORMATION_VISUAL_V2_PNG',f'#{seq:03d}',r['scope'],f"{r['width']}x{r['height']}",f"sprites={r['spriteRefs']}",r['name'])

manifest={
 'format':'WFGG_LASTWAR_FORMATION_VISUAL_HUMAN_SEARCH_MANIFEST_V2',
 'reference':{'path':'/lab/master-assets-v2/background/formation-layer0-world-baked.webp','authority':'comparison/ranking only; baked reference is not native-pipeline proof'},
 'review':{'gridPageSize':12,'votes':['yes','no','unsure'],'finalDefault':'yes-only','displayModes':['fit','native','cover','user-blur']},
 'selection':{'atlasRule':'default review excludes sactx/sprite-atlas names, Texture2D with >=2 direct Sprite refs, or SpriteAtlas render-data refs',
              'humanV1RejectedExcluded':len(human_reject),'analyticsDecisionAuthority':False,'analyticsUse':'ordering only',
              'externalPass':'current graphics index only; current preferredExtraction attempted only when current physical source is readable'},
 'counts':{'closureBundles':len(closure),'closureGeometry':len(closure_rows),'closureStandaloneEligible':len(closure_eligible),'closureShown':len(closure_dec),
           'externalIndexBundlesConsidered':len(external_index),'externalBundlesResolved':sum(1 for x in external_resolution if not x['resolution'].startswith('current-') or x['resolution'] in ('cached-current','current-index-preferredExtraction')),
           'externalGeometry':len(external_rows),'externalStandaloneEligible':len(external_eligible),'externalShown':len(external_dec),'items':len(items)},
 'items':items,
 'externalResolution':external_resolution,
 'notes':['Human visual vote remains the decision authority.','Similarity score only changes review order.','No V002-0012 physical offset is reused.','No generated/mock image is part of this review lot.']
}
(reviewp/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n','utf-8')
result={**manifest,'diagnostics':{'closureDecodeFailures':closure_fail[:100],'externalDecodeFailures':external_fail[:100],'atlasExcludedClosure':sum(1 for r in closure_rows if r['atlasLikely'])},
        'guardrails':{'labBranchOnly':True,'mainUntouched':True,'currentGraphicsIndexQueried':True,'historicalOffsetsReused':False,'candidatePromotion':False,'generatedVisuals':False}}
outp.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n','utf-8')

lines=['WfGg Last War — FORMATION VISUAL HUMAN SEARCH V2','',
 f"closureBundles=195 closureGeometry={len(closure_rows)} closureStandaloneEligible={len(closure_eligible)} closureShown={len(closure_dec)} atlasExcluded={sum(1 for r in closure_rows if r['atlasLikely'])}",
 f"humanV1RejectedExcluded={len(human_reject)} externalIndexBundlesConsidered={len(external_index)} externalGeometry={len(external_rows)} externalStandaloneEligible={len(external_eligible)} externalShown={len(external_dec)}",
 f"reviewItems={len(items)}",'',
 'REVIEW ORDER (analytics only; human decision authority)']
for r in items:lines.append(f"  #{r['rank']:03d} scope={r['scope']} order={r['orderScore']} similarity={r['referenceSimilarity']} spriteRefs={r['spriteRefs']} atlasRefs={r['spriteAtlasRefs']} bundle={r['bundleId']} pathID={r['pathID']} size={r['width']}x{r['height']} name={r['name']}")
lines+=['','EXTERNAL PASS RESOLUTION']
for x in external_resolution:lines.append(f"  bundle={x['bundleId']} indexScore={x['indexScore']} resolution={x['resolution']}")
lines+=['','NEXT open /lab/lastwar-formation-texture-viewer.html?v=2','RULE: analytics orders only; it never decides or proves runtime use.','RULE: atlas-like and the 25 human-rejected V1 images are not re-presented by default.','RULE: current graphics index only for external pass; no historical physical offset reused.','RULE: actual decoded game textures only; no generated visual.']
reportp.write_text('\n'.join(lines)+'\n','utf-8')
print('FORMATION_VISUAL_V2_OK',f'items={len(items)}',f'closure={len(closure_dec)}',f'external={len(external_dec)}')
print('FORMATION_VISUAL_V2_MANIFEST',reviewp/'manifest.json')
print('FORMATION_VISUAL_V2_REPORT',reportp)
PY

git add "$REVIEW" "$OUT"
if ! git diff --cached --quiet; then
  git commit -m "lab: publish continuous human visual Formation review V2"
  git push origin "$BRANCH"
fi

echo "=== FORMATION VISUAL HUMAN SEARCH V2 TERMINE ==="
echo "Viewer: http://127.0.0.1:8787/lab/lastwar-formation-texture-viewer.html?v=2"
echo "Rapport: $REPORT"
echo "main/preview inchangés. Aucun visuel généré."
