#!/data/data/com.termux/files/usr/bin/bash
set -Eeuo pipefail

# WfGg Last War LAB — PREBLURRED / PREBAKED FORMATION TEXTURE VISUAL EXTRACT V1
# Scope: exact V4 Formation closure only. Prefer already-carved current-build bundles.
# No global game scan, no historical offsets, no candidate promotion.

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BRANCH="portal-auth-lastwar-lab-v1"
META="$ROOT/frontend/lab/master-assets-v2/meta"
V4="$META/formation-ptr-exact-v4.json"
SUMMARY="$META/formation-ptr-exact-v4-summary-v1.json"
CAND="$META/formation-preblurred-texture-candidates-v1.json"
OUT="$META/formation-preblurred-texture-visual-extract-v1.json"
REPORT="$HOME/storage/downloads/WFGG_LASTWAR_FORMATION_PREBLURRED_TEXTURE_VISUAL_EXTRACT_V1.txt"
EXPORT="$HOME/storage/downloads/WFGG_LASTWAR_FORMATION_TEXTURE_VISUAL_CANDIDATES_V1"
ZIPOUT="$HOME/storage/downloads/WFGG_LASTWAR_FORMATION_TEXTURE_VISUAL_CANDIDATES_V1.zip"
UNITY_VERSION="2019.4.41f1"

fail(){ printf 'ERREUR: %s\n' "$*" >&2; exit 1; }
cd "$ROOT"
[[ "$(git branch --show-current)" == "$BRANCH" ]] || fail "branche LAB incorrecte"
for f in "$V4" "$SUMMARY" "$CAND"; do [[ -s "$f" ]] || fail "fichier absent: $f"; done
command -v python >/dev/null 2>&1 || fail "python absent"
python - <<'PYCHK' >/dev/null 2>&1 || fail "UnityPy/Pillow absents dans Python Termux"
import UnityPy
from PIL import Image,ImageDraw
PYCHK
mkdir -p "$EXPORT" "$(dirname "$OUT")" "$(dirname "$REPORT")"
rm -f "$EXPORT"/*.png "$EXPORT"/*.jpg "$ZIPOUT" 2>/dev/null || true

python - "$V4" "$SUMMARY" "$CAND" "$OUT" "$REPORT" "$EXPORT" "$UNITY_VERSION" <<'PY'
from __future__ import annotations
from pathlib import Path
from collections import defaultdict
import hashlib,json,re,sys,traceback
import UnityPy
from PIL import Image,ImageDraw,ImageOps

v4p,sump,candp,outp,reportp,exportp=map(Path,sys.argv[1:7]); unity_version=sys.argv[7]
UnityPy.config.FALLBACK_UNITY_VERSION=unity_version
g=json.loads(v4p.read_text('utf-8')); s=json.loads(sump.read_text('utf-8')); c=json.loads(candp.read_text('utf-8'))
closure={int(x) for x in ((s.get('dependencySelection') or {}).get('selectedBundleIds') or [])}
if len(closure)!=195: raise SystemExit(f'FORMATION_CLOSURE_COUNT_MISMATCH expected=195 actual={len(closure)}')
if int(((s.get('counts') or {}).get('objects') or 0))!=3209: raise SystemExit('FORMATION_V4_OBJECT_COUNT_MISMATCH')
exportp.mkdir(parents=True,exist_ok=True)

# Exact current-build bundle files recorded by V4 take priority.
bundle_paths={}
for r in ((g.get('extraction') or {}).get('bundles') or []):
    try: bid=int(r.get('bundleId')); p=Path(str(r.get('path') or ''))
    except: continue
    if bid in closure and p.is_file(): bundle_paths[bid]=p
# V4 inherited the proven V2 local cache. Use it only as a current-build cache fallback.
roots=[v4p.parents[2]/'local_assets'/'lastwar-formation-ptr-exact-v2'/'bundles',
       v4p.parents[2]/'local_assets'/'lastwar-formation-ptr-exact-v4'/'bundles']
for root in roots:
    if not root.is_dir(): continue
    for p in root.glob('bundle-*.bundle'):
        m=re.fullmatch(r'bundle-(\d+)\.bundle',p.name)
        if m and int(m.group(1)) in closure: bundle_paths.setdefault(int(m.group(1)),p)
if len(bundle_paths)<50:
    raise SystemExit(f'CURRENT_CLOSURE_BUNDLE_CACHE_INSUFFICIENT found={len(bundle_paths)} expectedMany=true rerunFormationPPtrV4IfNeeded=true')

# Candidate-name score from the metadata-only V1 audit.
path_scores=defaultdict(int); path_sources=defaultdict(list)
def basename_name(v):
    b=Path(str(v).replace('\\','/')).name
    return re.sub(r'\.(png|jpe?g|tga|psd|exr|hdr|webp|bmp|tiff?)$','',b,flags=re.I)
for bucket in ('preblurKeywordCandidates','topImageCandidates'):
    for x in c.get(bucket) or []:
        try: bid=int(x.get('bundleId')); sc=int(x.get('score') or 0); v=str(x.get('value') or '')
        except: continue
        if bid not in closure or not v: continue
        n=basename_name(v)
        if n:
            path_scores[n.lower()]=max(path_scores[n.lower()],sc)
            if len(path_sources[n.lower()])<6:path_sources[n.lower()].append({'bundleId':bid,'path':v,'score':sc})

# Strong seeds observed as exact V4 graph Texture2D/Sprite names or plausible large-world/UI names.
SEEDS={x.lower() for x in [
 'cfm_tongyon_quanping_di_1','lrb_plan_bg','Common_img_shade','Common_bg_moveCity','icon_mainUImap',
 'cfm_tongyon_quanping_erji_chen','FX_common_diban_hui','zyf_tongmenglichengbei_ditu','lyp_yingxiong_biaoqianyeditu',
 'MixWorldMap_basecolor','MixWorldMap_basecolor1','MixWorldMap_basecolor_2','S1CityContaminate_basecolor',
 'O_ground_zhucheng_02n_drzc','O_env_ground','O_env_ground_snowsj','O_terrain_new01_D','O_terrain_new03_D',
 'O_terrain_desert_01','O_terrain_grass01_D','O_terrain_grass04_D','O_terrain_snow_D_drzc'
]}
POS=re.compile(r'(quanping|background|\bbg\b|shade|diban|plan|world|map|terrain|city|ground|scene|formation|blur|screen)',re.I)
NEG=re.compile(r'(normal|noise|mask|splat|height|lightning|glow|smoke|trail|ring|decal|icon|button|btn|emoji|font|avatar|head|progress|jindutiao)',re.I)

def safe_name(s):
    z=re.sub(r'[^A-Za-z0-9._-]+','_',s).strip('._')
    return z[:100] or 'texture'

def tex_score(name,w,h):
    nl=name.lower(); sc=path_scores.get(nl,0)
    reasons=[]
    if nl in SEEDS: sc+=100;reasons.append('seed')
    if POS.search(name): sc+=28;reasons.append('background-like-name')
    if NEG.search(name): sc-=36;reasons.append('small/effect-map-name-penalty')
    area=max(0,w)*max(0,h)
    if w>=512 and h>=512: sc+=36;reasons.append('large-2d')
    elif max(w,h)>=512 and min(w,h)>=256: sc+=22;reasons.append('medium-large-2d')
    if area>=1024*1024: sc+=30;reasons.append('megapixel')
    elif area>=512*512: sc+=18;reasons.append('quarter-megapixel')
    ar=(max(w,h)/max(1,min(w,h))) if w and h else 99
    if ar<=2.4 and min(w,h)>=512: sc+=10;reasons.append('screen-plausible-aspect')
    return sc,reasons

rows=[]; bundle_errors=[]; texture_count=0
for bid,p in sorted(bundle_paths.items()):
    try:
        env=UnityPy.load(str(p))
    except Exception as e:
        bundle_errors.append({'bundleId':bid,'path':str(p),'error':f'{type(e).__name__}:{e}'});continue
    for obj in list(getattr(env,'objects',[]) or []):
        typ=getattr(getattr(obj,'type',None),'name','')
        if typ!='Texture2D': continue
        texture_count+=1
        try: name=str(obj.peek_name() or '')
        except: name=''
        if not name: continue
        # Cheap prefilter by exact candidate-name registry, seed, or background-like token.
        nl=name.lower()
        if nl not in SEEDS and nl not in path_scores and not POS.search(name): continue
        try:
            data=obj.read(); w=int(getattr(data,'m_Width',0) or getattr(data,'width',0) or 0); h=int(getattr(data,'m_Height',0) or getattr(data,'height',0) or 0)
        except Exception as e:
            rows.append({'bundleId':bid,'bundlePath':str(p),'pathID':int(obj.path_id),'name':name,'readError':f'{type(e).__name__}:{e}','score':path_scores.get(nl,0)});continue
        sc,reasons=tex_score(name,w,h)
        rows.append({'bundleId':bid,'bundlePath':str(p),'pathID':int(obj.path_id),'name':name,'width':w,'height':h,'score':sc,'reasons':reasons,'indexSources':path_sources.get(nl,[])})

# Stable exact-object dedupe and ranking.
ded={}
for r in rows: ded[(r.get('bundleId'),r.get('pathID'))]=r
rows=list(ded.values());rows.sort(key=lambda r:(-int(r.get('score') or -999),-(int(r.get('width') or 0)*int(r.get('height') or 0)),r.get('name','')))
selected=[r for r in rows if not r.get('readError')][:24]
if not selected: raise SystemExit('NO_VISUAL_TEXTURE_CANDIDATES_AFTER_EXACT_CLOSURE_INSPECTION')

# Reload only selected bundles and export exact Texture2D objects.
sel_by_bundle=defaultdict(list)
for r in selected: sel_by_bundle[r['bundleId']].append(r)
exported=[]
for bid,rs in sorted(sel_by_bundle.items()):
    p=bundle_paths[bid]
    try: env=UnityPy.load(str(p))
    except Exception as e:
        for r in rs:r['exportError']=f'{type(e).__name__}:{e}'
        continue
    wanted={int(r['pathID']):r for r in rs}
    for obj in list(getattr(env,'objects',[]) or []):
        if int(getattr(obj,'path_id',0) or 0) not in wanted:continue
        r=wanted[int(obj.path_id)]
        try:
            d=obj.read();im=d.image
            if im is None:raise ValueError('Texture2D.image is None')
            if im.mode not in ('RGB','RGBA'):im=im.convert('RGBA')
            fn=f"{len(exported)+1:02d}_b{bid}_p{int(obj.path_id)}_{safe_name(r['name'])}.png"
            fp=exportp/fn;im.save(fp,'PNG')
            raw=fp.read_bytes();r['exportFile']=fn;r['exportSha256']=hashlib.sha256(raw).hexdigest();r['exportBytes']=len(raw);exported.append(r)
        except Exception as e:r['exportError']=f'{type(e).__name__}:{e}'

# Contact sheet for rapid human comparison. No transformation beyond thumbnailing/labeling.
thumbs=[]
for r in exported:
    try:
        im=Image.open(exportp/r['exportFile']).convert('RGB'); im.thumbnail((260,200),Image.Resampling.LANCZOS)
        thumbs.append((r,im.copy()))
    except:pass
if thumbs:
    cols=3; cellw=300; cellh=250; rowsn=(len(thumbs)+cols-1)//cols
    sheet=Image.new('RGB',(cols*cellw,rowsn*cellh),'white');draw=ImageDraw.Draw(sheet)
    for i,(r,im) in enumerate(thumbs):
        x=(i%cols)*cellw;y=(i//cols)*cellh
        sheet.paste(im,(x+(cellw-im.width)//2,y+8))
        label=f"#{i+1:02d} b{r['bundleId']} {r['width']}x{r['height']}\n{r['name'][:42]}"
        draw.multiline_text((x+8,y+212),label,fill='black',spacing=2)
    sf=exportp/'CONTACT_SHEET.png';sheet.save(sf,'PNG')
    sheet_sha=hashlib.sha256(sf.read_bytes()).hexdigest()
else:sheet_sha=None

result={'format':'WFGG_LASTWAR_FORMATION_PREBLURRED_TEXTURE_VISUAL_EXTRACT_V1',
 'sources':{'ptrGraph':str(v4p),'ptrSummary':str(sump),'candidateIndex':str(candp)},
 'scope':{'closureBundleCount':len(closure),'currentCachedBundlesInspected':len(bundle_paths),'texture2DObjectsSeen':texture_count,'rankedRows':len(rows),'selectedForExport':len(selected),'exported':len(exported)},
 'rankedCandidates':rows[:120],'exportedCandidates':exported,'bundleErrors':bundle_errors[:80],
 'contactSheet':{'file':str(exportp/'CONTACT_SHEET.png'),'sha256':sheet_sha} if sheet_sha else None,
 'conclusion':{'nextStrategy':'human_compare_exported_exact_textures_to_real_formation_capture','fixedTextureHypothesisStillOpen':True},
 'guardrails':{'exactFormationClosureOnly':True,'currentBuildCachedBundlesOnly':True,'apkRead':False,'historicalOffsetsReused':False,'candidatePromotion':False,'mainUntouched':True,'previewUntouched':True}}
outp.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n','utf-8')

lines=['WfGg Last War — FORMATION PREBLURRED TEXTURE VISUAL EXTRACT V1','',
 f"closureBundles={len(closure)} cachedBundlesInspected={len(bundle_paths)} texture2DSeen={texture_count} ranked={len(rows)} selected={len(selected)} exported={len(exported)}",
 f"contactSheet={str(exportp/'CONTACT_SHEET.png') if sheet_sha else 'NONE'}",
 'nextStrategy=human_compare_exported_exact_textures_to_real_formation_capture','',
 'EXPORTED EXACT TEXTURES']
if exported:
    for i,r in enumerate(exported,1):
        lines.append(f"  #{i:02d} score={r['score']} bundle={r['bundleId']} pathID={r['pathID']} size={r['width']}x{r['height']} name={r['name']} file={r['exportFile']} sha256={r['exportSha256']}")
else:lines.append('  NONE')
lines+=['','TOP RANKED INCLUDING EXPORT FAILURES']
for r in rows[:40]:lines.append(f"  score={r.get('score')} bundle={r.get('bundleId')} pathID={r.get('pathID')} size={r.get('width')}x{r.get('height')} name={r.get('name')} error={r.get('readError') or r.get('exportError') or '-'}")
lines+=['','NEXT human_compare_exported_exact_textures_to_real_formation_capture',
 'RULE: exact Formation closure current-build cache only; no global game scan.',
 'RULE: visual ranking is heuristic; exported candidate is not proof until compared to the real Formation capture.',
 'RULE: no APK read in this pass; no historical physical offset reused; main/preview untouched.']
reportp.write_text('\n'.join(lines)+'\n','utf-8')
print('FORMATION_PREBLUR_VISUAL_OK',f'cachedBundles={len(bundle_paths)}',f'textures={texture_count}',f'exported={len(exported)}')
for i,r in enumerate(exported[:24],1):print('FORMATION_PREBLUR_VISUAL',f'#{i:02d}',f"{r['width']}x{r['height']}",r['name'],r['exportFile'])
print('FORMATION_PREBLUR_VISUAL_CONTACT',exportp/'CONTACT_SHEET.png')
print('FORMATION_PREBLUR_VISUAL_REPORT',reportp)
print('FORMATION_PREBLUR_VISUAL_JSON',outp)
PY

# Zip exact exports for easy upload/inspection.
python - "$EXPORT" "$ZIPOUT" <<'PYZIP'
from pathlib import Path
import sys,zipfile
src=Path(sys.argv[1]);out=Path(sys.argv[2])
with zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED) as z:
    for p in sorted(src.glob('*.png')):z.write(p,p.name)
print('FORMATION_PREBLUR_VISUAL_ZIP',out)
PYZIP

git add "$OUT"
if ! git diff --cached --quiet; then
  git commit -m "lab: record exact Formation texture visual candidates"
  git push origin "$BRANCH"
fi

echo "=== FORMATION PREBLURRED TEXTURE VISUAL EXTRACT TERMINE ==="
echo "Rapport: $REPORT"
echo "Planche: $EXPORT/CONTACT_SHEET.png"
echo "ZIP: $ZIPOUT"
echo "main/preview inchangés."
