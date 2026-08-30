#!/data/data/com.termux/files/usr/bin/bash
set -Eeuo pipefail

# WfGg Last War LAB — Formation Texture RAW fallback V1
# Android-safe fallback: reads exact current-build cached Texture2D objects but
# never calls Texture2D.image / Texture2DConverter. Exports raw image payload +
# exact metadata for off-device decoding and verification.

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BRANCH="portal-auth-lastwar-lab-v1"
META="$ROOT/frontend/lab/master-assets-v2/meta"
V1="$META/formation-preblurred-texture-visual-extract-v1.json"
SUMMARY="$META/formation-ptr-exact-v4-summary-v1.json"
OUT="$META/formation-texture-raw-fallback-v1.json"
EXPORT="$HOME/storage/downloads/WFGG_LASTWAR_FORMATION_TEXTURE_RAW_V1"
ZIPOUT="$HOME/storage/downloads/WFGG_LASTWAR_FORMATION_TEXTURE_RAW_V1.zip"
REPORT="$HOME/storage/downloads/WFGG_LASTWAR_FORMATION_TEXTURE_RAW_V1.txt"

fail(){ printf 'ERREUR: %s\n' "$*" >&2; exit 1; }
cd "$ROOT"
[[ "$(git branch --show-current)" == "$BRANCH" ]] || fail "branche LAB incorrecte"
[[ -s "$V1" ]] || fail "resultat visual V1 absent: $V1"
[[ -s "$SUMMARY" ]] || fail "summary V4 absent"
command -v python >/dev/null 2>&1 || fail "python absent"
python - <<'PYCHK' >/dev/null 2>&1 || fail "UnityPy/Pillow systeme absents"
import UnityPy
from PIL import Image
PYCHK
mkdir -p "$EXPORT" "$(dirname "$OUT")"
rm -rf "$EXPORT"/* "$ZIPOUT" 2>/dev/null || true

python - "$V1" "$SUMMARY" "$OUT" "$EXPORT" "$REPORT" <<'PY'
from __future__ import annotations
from pathlib import Path
from collections import defaultdict
import hashlib,json,re,struct,sys
import UnityPy
from PIL import Image

v1p,sump,outp,exportp,reportp=map(Path,sys.argv[1:])
v1=json.loads(v1p.read_text('utf-8')); s=json.loads(sump.read_text('utf-8'))
closure={int(x) for x in ((s.get('dependencySelection') or {}).get('selectedBundleIds') or [])}
if len(closure)!=195: raise SystemExit(f'CLOSURE_MISMATCH {len(closure)}')
exportp.mkdir(parents=True,exist_ok=True)

# Current-build cache only; same cache proven by PPtr V4/V1 visual audit.
bundle_paths={}
roots=[v1p.parents[2]/'local_assets'/'lastwar-formation-ptr-exact-v2'/'bundles',
       v1p.parents[2]/'local_assets'/'lastwar-formation-ptr-exact-v4'/'bundles']
for root in roots:
    if not root.is_dir(): continue
    for p in root.glob('bundle-*.bundle'):
        m=re.fullmatch(r'bundle-(\d+)\.bundle',p.name)
        if m and int(m.group(1)) in closure: bundle_paths.setdefault(int(m.group(1)),p)
if len(bundle_paths)<50: raise SystemExit(f'CACHE_INSUFFICIENT {len(bundle_paths)}')

ranked=list(v1.get('rankedCandidates') or [])
# Preserve the exact top 32 from V1 and force the specific UI/background names
# that may rank below terrain textures but are relevant to the fixed-image hypothesis.
SEEDS={x.lower() for x in [
 'cfm_tongyon_quanping_di_1','lrb_plan_bg','Common_img_shade','Common_bg_moveCity','icon_mainUImap',
 'cfm_tongyon_quanping_erji_chen','FX_common_diban_hui','zyf_tongmenglichengbei_ditu',
 'lyp_yingxiong_biaoqianyeditu','MixWorldMap_basecolor','MixWorldMap_basecolor1','MixWorldMap_basecolor_2',
 'S1CityContaminate_basecolor','O_env_ground','O_env_ground_snowsj','O_ground_zhucheng_02n_drzc',
 'O_terrain_new01_D','O_terrain_new03_D','O_terrain_desert_01','O_terrain_grass01_D','O_terrain_grass04_D'
]}
sel=[]; seen=set()
for r in ranked:
    key=(int(r.get('bundleId') or -1),int(r.get('pathID') or 0))
    if key in seen: continue
    if len(sel)<32 or str(r.get('name') or '').lower() in SEEDS:
        sel.append(dict(r));seen.add(key)
for r in ranked:
    if str(r.get('name') or '').lower() in SEEDS:
        key=(int(r.get('bundleId') or -1),int(r.get('pathID') or 0))
        if key not in seen: sel.append(dict(r));seen.add(key)

try:
    from UnityPy.enums import TextureFormat
except Exception:
    TextureFormat=None

def fmt_name(v):
    try:
        i=int(v)
        if TextureFormat is not None:return TextureFormat(i).name
        return str(i)
    except:return str(v)

def safe(s):
    z=re.sub(r'[^A-Za-z0-9._-]+','_',str(s)).strip('._')
    return z[:90] or 'texture'

def direct_decode(raw,w,h,fmt):
    # Android-safe pure Pillow only for truly uncompressed layouts.
    f=str(fmt)
    try:
        if f=='RGB24': return Image.frombytes('RGB',(w,h),raw,'raw','RGB').transpose(Image.Transpose.FLIP_TOP_BOTTOM)
        if f=='RGBA32': return Image.frombytes('RGBA',(w,h),raw,'raw','RGBA').transpose(Image.Transpose.FLIP_TOP_BOTTOM)
        if f=='ARGB32': return Image.frombytes('RGBA',(w,h),raw,'raw','ARGB').transpose(Image.Transpose.FLIP_TOP_BOTTOM)
        if f=='BGRA32': return Image.frombytes('RGBA',(w,h),raw,'raw','BGRA').transpose(Image.Transpose.FLIP_TOP_BOTTOM)
        if f in ('Alpha8','R8'):
            return Image.frombytes('L',(w,h),raw[:w*h]).transpose(Image.Transpose.FLIP_TOP_BOTTOM)
    except Exception:
        return None
    return None

by_bundle=defaultdict(list)
for r in sel:
    bid=int(r.get('bundleId') or -1); pid=int(r.get('pathID') or 0)
    if bid in bundle_paths: by_bundle[bid].append((pid,r))

rows=[]; pngs=[]
for bid, items in sorted(by_bundle.items()):
    env=UnityPy.load(str(bundle_paths[bid])); wanted={pid:r for pid,r in items}
    for obj in list(getattr(env,'objects',[]) or []):
        pid=int(getattr(obj,'path_id',0) or 0)
        if pid not in wanted: continue
        base=wanted[pid]; rec={'bundleId':bid,'pathID':pid,'name':base.get('name'),'score':base.get('score'),'bundlePath':str(bundle_paths[bid])}
        try:
            d=obj.read(); w=int(getattr(d,'m_Width',0) or 0); h=int(getattr(d,'m_Height',0) or 0)
            fv=getattr(d,'m_TextureFormat',None); fn=fmt_name(fv)
            rec.update(width=w,height=h,textureFormatValue=(int(fv) if fv is not None else None),textureFormat=fn)
            raw=d.get_image_data()
            raw=bytes(raw)
            stem=f"b{bid}_p{pid}_{safe(rec['name'])}"
            bp=exportp/(stem+'.bin');bp.write_bytes(raw)
            rec['rawFile']=bp.name;rec['rawBytes']=len(raw);rec['rawSha256']=hashlib.sha256(raw).hexdigest()
            # Optional direct PNG for uncompressed formats only.
            im=direct_decode(raw,w,h,fn)
            if im is not None:
                pp=exportp/(stem+'.png');im.save(pp,'PNG');rec['directPng']=pp.name;pngs.append((rec,pp))
            # Record stream metadata if present; identity only, no offsets reused elsewhere.
            sd=getattr(d,'m_StreamData',None)
            if sd is not None:
                rec['streamData']={'offset':getattr(sd,'offset',None),'size':getattr(sd,'size',None),'path':getattr(sd,'path',None)}
        except Exception as e:
            rec['error']=f'{type(e).__name__}:{e}'
        rows.append(rec)

# Metadata is included inside the ZIP so decoding can be reproduced off Android.
meta={'format':'WFGG_LASTWAR_FORMATION_TEXTURE_RAW_V1','unityPyVersion':getattr(UnityPy,'__version__','unknown'),
      'scope':{'closureBundles':len(closure),'cachedBundles':len(bundle_paths),'selectedObjects':len(sel),'rawExported':sum(1 for r in rows if r.get('rawFile')),'directPngs':len(pngs)},
      'textures':rows,
      'guardrails':{'exactCurrentFormationClosureOnly':True,'Texture2DImageCalled':False,'Texture2DConverterCalled':False,'historicalOffsetsReused':False,'mainUntouched':True,'previewUntouched':True}}
(exportp/'METADATA.json').write_text(json.dumps(meta,ensure_ascii=False,indent=2)+'\n','utf-8')
outp.write_text(json.dumps(meta,ensure_ascii=False,indent=2)+'\n','utf-8')

lines=['WfGg Last War — FORMATION TEXTURE RAW FALLBACK V1','',
 f"unityPy={meta['unityPyVersion']} closureBundles={len(closure)} cachedBundles={len(bundle_paths)} selected={len(sel)} rawExported={meta['scope']['rawExported']} directPngs={len(pngs)}",'',
 'EXACT RAW TEXTURES']
for i,r in enumerate(rows,1):
    lines.append(f"  #{i:02d} bundle={r.get('bundleId')} pathID={r.get('pathID')} size={r.get('width')}x{r.get('height')} format={r.get('textureFormat')} rawBytes={r.get('rawBytes')} name={r.get('name')} error={r.get('error') or '-'}")
lines+=['','NEXT upload WFGG_LASTWAR_FORMATION_TEXTURE_RAW_V1.zip for off-Android decoding and visual comparison.',
 'RULE: no Texture2D.image / Texture2DConverter call; exact raw payload only.',
 'RULE: current Formation closure/cache only; no global scan; main/preview untouched.']
reportp.write_text('\n'.join(lines)+'\n','utf-8')
print('FORMATION_TEXTURE_RAW_OK',f"raw={meta['scope']['rawExported']}",f"directPng={len(pngs)}")
for r in rows:
    if r.get('rawFile'): print('FORMATION_TEXTURE_RAW',r['textureFormat'],f"{r['width']}x{r['height']}",r['name'],r['rawFile'])
print('FORMATION_TEXTURE_RAW_REPORT',reportp)
print('FORMATION_TEXTURE_RAW_DIR',exportp)
PY

python - "$EXPORT" "$ZIPOUT" <<'PYZIP'
from pathlib import Path
import sys,zipfile
src=Path(sys.argv[1]);out=Path(sys.argv[2])
with zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED) as z:
    for p in sorted(src.iterdir()):
        if p.is_file(): z.write(p,p.name)
print('FORMATION_TEXTURE_RAW_ZIP',out,out.stat().st_size)
PYZIP

git add "$OUT"
if ! git diff --cached --quiet; then
  git commit -m "lab: record Android-safe raw Formation texture export"
  git push origin "$BRANCH"
fi

echo "=== FORMATION TEXTURE RAW FALLBACK TERMINE ==="
echo "Rapport: $REPORT"
echo "ZIP: $ZIPOUT"
echo "main/preview inchangés."
