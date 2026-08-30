#!/data/data/com.termux/files/usr/bin/bash
set -Eeuo pipefail

# WfGg Last War LAB — FORMATION PREBLURRED TEXTURE DIRECT DECODE V3
# Reuses ONLY the 24 exact objects already selected by V1.
# UnityPy parses Texture2D; texture2ddecoder decodes bytes directly.
# No Texture2DConverter / astc_encoder backend. No APK read. No closure rescan.

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BRANCH="portal-auth-lastwar-lab-v1"
META="$ROOT/frontend/lab/master-assets-v2/meta"
SRC="$META/formation-preblurred-texture-visual-extract-v1.json"
OUT="$META/formation-preblurred-texture-direct-decode-v3.json"
REPORT="$HOME/storage/downloads/WFGG_LASTWAR_FORMATION_PREBLURRED_TEXTURE_DIRECT_DECODE_V3.txt"
EXPORT="$HOME/storage/downloads/WFGG_LASTWAR_FORMATION_TEXTURE_VISUAL_CANDIDATES_V3"
ZIPOUT="$HOME/storage/downloads/WFGG_LASTWAR_FORMATION_TEXTURE_VISUAL_CANDIDATES_V3.zip"
VENV="$HOME/.cache/wfgg-unitypy-texture-export-v2"

fail(){ printf 'ERREUR: %s\n' "$*" >&2; exit 1; }
cd "$ROOT"
[[ "$(git branch --show-current)" == "$BRANCH" ]] || fail "branche LAB incorrecte"
[[ -s "$SRC" ]] || fail "résultat V1 absent: $SRC"
[[ -x "$VENV/bin/python" ]] || fail "venv V2 absent: $VENV"
mkdir -p "$EXPORT" "$(dirname "$REPORT")" "$(dirname "$OUT")"
rm -f "$EXPORT"/*.png "$ZIPOUT" 2>/dev/null || true

# Do NOT import UnityPy.export.Texture2DConverter here: that is the Android failure boundary.
if ! "$VENV/bin/python" - <<'PYCHK'
import UnityPy
import texture2ddecoder
from PIL import Image, ImageDraw
from UnityPy.enums import TextureFormat
print('FORMATION_TEXTURE_V3_PREFLIGHT', 'UnityPy='+getattr(UnityPy,'__version__','unknown'), 'texture2ddecoder=OK', 'Pillow=OK')
PYCHK
then
  fail "préflight direct decoder impossible"
fi

"$VENV/bin/python" - "$SRC" "$OUT" "$REPORT" "$EXPORT" <<'PY'
from __future__ import annotations
from pathlib import Path
from collections import defaultdict
import hashlib, json, re, sys, traceback
import UnityPy
import texture2ddecoder as t2d
from PIL import Image, ImageDraw
from UnityPy.enums import TextureFormat

srcp,outp,reportp,exportp=map(Path,sys.argv[1:5])
src=json.loads(srcp.read_text('utf-8'))
scope=src.get('scope') or {}
if int(scope.get('closureBundleCount') or 0)!=195:
    raise SystemExit('V1_SCOPE_MISMATCH closureBundleCount')
if int(scope.get('selectedForExport') or 0)!=24:
    raise SystemExit(f"V1_SELECTED_COUNT_MISMATCH expected=24 actual={scope.get('selectedForExport')}")

# V1 ranked rows are the frozen selection authority; do not re-rank.
ranked=src.get('rankedCandidates') or []
selected=[]
for r in ranked:
    if r.get('readError'): continue
    selected.append(dict(r))
    if len(selected)==24: break
if len(selected)!=24:
    raise SystemExit(f'V1_SELECTED_ROWS_UNAVAILABLE actual={len(selected)}')

for r in selected:
    p=Path(str(r.get('bundlePath') or ''))
    if not p.is_file():
        raise SystemExit(f"SELECTED_BUNDLE_MISSING bundle={r.get('bundleId')} path={p}")

# ---------- direct decoder, intentionally independent from UnityPy.export ----------
def bgra_image(raw: bytes,w:int,h:int):
    return Image.frombytes('RGBA',(w,h),raw,'raw','BGRA')

def decode_raw_uncompressed(data:bytes,w:int,h:int,name:str):
    if name=='RGBA32': return Image.frombytes('RGBA',(w,h),data[:w*h*4],'raw','RGBA')
    if name=='BGRA32': return Image.frombytes('RGBA',(w,h),data[:w*h*4],'raw','BGRA')
    if name=='ARGB32': return Image.frombytes('RGBA',(w,h),data[:w*h*4],'raw','ARGB')
    if name=='RGB24': return Image.frombytes('RGB',(w,h),data[:w*h*3],'raw','RGB').convert('RGBA')
    if name in ('Alpha8','R8'):
        im=Image.frombytes('L',(w,h),data[:w*h],'raw','L')
        return Image.merge('RGBA',(im,im,im,Image.new('L',(w,h),255)))
    raise NotImplementedError(name)

def decode_texture(d):
    w=int(d.m_Width); h=int(d.m_Height)
    fmt=TextureFormat(int(d.m_TextureFormat))
    name=fmt.name
    data=bytes(d.get_image_data())
    # Crunch first, then route decoded compressed blocks by nominal family.
    if 'Crunched' in name:
        try: data=t2d.unpack_unity_crunch(data)
        except Exception: data=t2d.unpack_crunch(data)
        name=name.replace('Crunched','')
    if name.startswith('ASTC'):
        m=re.search(r'(\d+)x(\d+)',name)
        if not m: raise NotImplementedError('ASTC block size absent: '+name)
        raw=t2d.decode_astc(data,w,h,int(m.group(1)),int(m.group(2)))
        im=bgra_image(raw,w,h)
    elif name in ('ETC_RGB4','ETC_RGB4_3DS'):
        im=bgra_image(t2d.decode_etc1(data,w,h),w,h)
    elif name=='ETC2_RGB':
        im=bgra_image(t2d.decode_etc2(data,w,h),w,h)
    elif name=='ETC2_RGBA1':
        im=bgra_image(t2d.decode_etc2a1(data,w,h),w,h)
    elif name=='ETC2_RGBA8':
        im=bgra_image(t2d.decode_etc2a8(data,w,h),w,h)
    elif name in ('DXT1','DXT1Crunched'):
        im=bgra_image(t2d.decode_bc1(data,w,h),w,h)
    elif name in ('DXT5','DXT5Crunched'):
        im=bgra_image(t2d.decode_bc3(data,w,h),w,h)
    elif name=='BC4': im=bgra_image(t2d.decode_bc4(data,w,h),w,h)
    elif name=='BC5': im=bgra_image(t2d.decode_bc5(data,w,h),w,h)
    elif name=='BC6H': im=bgra_image(t2d.decode_bc6(data,w,h),w,h)
    elif name=='BC7': im=bgra_image(t2d.decode_bc7(data,w,h),w,h)
    elif name=='ATC_RGB4': im=bgra_image(t2d.decode_atc_rgb4(data,w,h),w,h)
    elif name=='ATC_RGBA8': im=bgra_image(t2d.decode_atc_rgba8(data,w,h),w,h)
    elif name=='EAC_R': im=bgra_image(t2d.decode_eacr(data,w,h),w,h)
    elif name=='EAC_R_SIGNED': im=bgra_image(t2d.decode_eacr_signed(data,w,h),w,h)
    elif name=='EAC_RG': im=bgra_image(t2d.decode_eacrg(data,w,h),w,h)
    elif name=='EAC_RG_SIGNED': im=bgra_image(t2d.decode_eacrg_signed(data,w,h),w,h)
    elif name in ('RGBA32','BGRA32','ARGB32','RGB24','Alpha8','R8'):
        im=decode_raw_uncompressed(data,w,h,name)
    else:
        raise NotImplementedError('DIRECT_DECODER_FORMAT '+name)
    # Match UnityPy's normal Texture2D image orientation.
    return im.transpose(Image.Transpose.FLIP_TOP_BOTTOM),fmt,len(data)

def safe(s):
    z=re.sub(r'[^A-Za-z0-9._-]+','_',str(s)).strip('._')
    return (z[:90] or 'texture')

by_bundle=defaultdict(list)
for r in selected: by_bundle[int(r['bundleId'])].append(r)
exported=[]; failures=[]
for bid,rs in sorted(by_bundle.items()):
    p=Path(rs[0]['bundlePath'])
    try: env=UnityPy.load(str(p))
    except Exception as e:
        for r in rs: failures.append({**r,'stage':'bundle-load','error':f'{type(e).__name__}:{e}'})
        continue
    wanted={int(r['pathID']):r for r in rs}
    found=set()
    for obj in list(getattr(env,'objects',[]) or []):
        pid=int(getattr(obj,'path_id',0) or 0)
        if pid not in wanted: continue
        found.add(pid); r=wanted[pid]
        try:
            d=obj.read()
            fmt=TextureFormat(int(d.m_TextureFormat)); data_len=len(bytes(d.get_image_data()))
            im,fmt2,data_len2=decode_texture(d)
            fn=f"{len(exported)+1:02d}_b{bid}_p{pid}_{safe(r.get('name'))}.png"
            fp=exportp/fn; im.save(fp,'PNG')
            raw=fp.read_bytes()
            rec={**r,'textureFormat':fmt.name,'textureFormatValue':int(fmt.value),'sourceImageBytes':data_len,
                 'exportFile':fn,'exportSha256':hashlib.sha256(raw).hexdigest(),'exportBytes':len(raw)}
            exported.append(rec)
            print('FORMATION_TEXTURE_V3_EXPORTED',f"#{len(exported):02d}",f"{r.get('width')}x{r.get('height')}",fmt.name,r.get('name'))
        except Exception as e:
            fmt_name=None; fmt_val=None; data_len=None
            try:
                d=obj.read(); f=TextureFormat(int(d.m_TextureFormat)); fmt_name=f.name; fmt_val=int(f.value); data_len=len(bytes(d.get_image_data()))
            except Exception: pass
            failures.append({**r,'stage':'direct-decode','textureFormat':fmt_name,'textureFormatValue':fmt_val,
                             'sourceImageBytes':data_len,'error':f'{type(e).__name__}:{e}','traceback':traceback.format_exc(limit=4)})
    for pid,r in wanted.items():
        if pid not in found: failures.append({**r,'stage':'object-lookup','error':'pathID_not_found_in_bundle'})

# Contact sheet from actual decoded bytes.
sheet_sha=None
if exported:
    thumbs=[]
    for r in exported:
        im=Image.open(exportp/r['exportFile']).convert('RGB'); im.thumbnail((260,200),Image.Resampling.LANCZOS)
        thumbs.append((r,im.copy()))
    cols=3; cw=300; ch=265; rn=(len(thumbs)+cols-1)//cols
    sheet=Image.new('RGB',(cols*cw,rn*ch),'white'); dr=ImageDraw.Draw(sheet)
    for i,(r,im) in enumerate(thumbs):
        x=(i%cols)*cw; y=(i//cols)*ch
        sheet.paste(im,(x+(cw-im.width)//2,y+8))
        lab=f"#{i+1:02d} b{r['bundleId']} {r.get('width')}x{r.get('height')} {r['textureFormat']}\n{str(r.get('name'))[:38]}"
        dr.multiline_text((x+8,y+212),lab,fill='black',spacing=2)
    sp=exportp/'CONTACT_SHEET.png'; sheet.save(sp,'PNG'); sheet_sha=hashlib.sha256(sp.read_bytes()).hexdigest()

result={
 'format':'WFGG_LASTWAR_FORMATION_PREBLURRED_TEXTURE_DIRECT_DECODE_V3',
 'sourceSelection':str(srcp),
 'counts':{'selectedFrozenFromV1':len(selected),'bundlesOpened':len(by_bundle),'exported':len(exported),'failed':len(failures)},
 'exported':exported,'failures':failures,
 'contactSheet':({'file':str(exportp/'CONTACT_SHEET.png'),'sha256':sheet_sha} if sheet_sha else None),
 'conclusion':{'nextStrategy':'human_compare_direct_decoded_textures_to_real_formation_capture' if exported else 'inspect_texture_formats_or_decoder_install_failure'},
 'guardrails':{'v1SelectionFrozen':True,'closureRescan':False,'apkRead':False,'bundleScanBeyondSelected':False,'Texture2DConverterUsed':False,'astcEncoderUsed':False,'mainUntouched':True,'previewUntouched':True}
}
outp.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n','utf-8')

lines=['WfGg Last War — FORMATION PREBLURRED TEXTURE DIRECT DECODE V3','',
 f"selectedFrozenFromV1={len(selected)} bundlesOpened={len(by_bundle)} exported={len(exported)} failed={len(failures)}",
 f"contactSheet={str(exportp/'CONTACT_SHEET.png') if sheet_sha else 'NONE'}",
 'nextStrategy='+result['conclusion']['nextStrategy'],'','EXPORTED DIRECT-DECODE TEXTURES']
if exported:
    for i,r in enumerate(exported,1):
        lines.append(f"  #{i:02d} score={r.get('score')} bundle={r['bundleId']} pathID={r['pathID']} size={r.get('width')}x{r.get('height')} format={r['textureFormat']} name={r.get('name')} file={r['exportFile']} sha256={r['exportSha256']}")
else: lines.append('  NONE')
lines+=['','FAILURES']
if failures:
    for r in failures:
        lines.append(f"  bundle={r.get('bundleId')} pathID={r.get('pathID')} size={r.get('width')}x{r.get('height')} format={r.get('textureFormat')} name={r.get('name')} stage={r.get('stage')} error={r.get('error')}")
else: lines.append('  NONE')
lines+=['','RULE: exact 24-object V1 selection reused; no re-ranking or closure rescan.',
        'RULE: direct texture2ddecoder path; UnityPy Texture2DConverter/astc_encoder not used.',
        'RULE: no APK read; main/preview untouched.']
reportp.write_text('\n'.join(lines)+'\n','utf-8')
print('FORMATION_TEXTURE_V3_SUMMARY',f'exported={len(exported)}',f'failed={len(failures)}')
print('FORMATION_TEXTURE_V3_CONTACT',exportp/'CONTACT_SHEET.png' if sheet_sha else 'NONE')
print('FORMATION_TEXTURE_V3_REPORT',reportp)
PY

"$VENV/bin/python" - "$EXPORT" "$ZIPOUT" <<'PYZIP'
from pathlib import Path
import sys,zipfile
src=Path(sys.argv[1]);out=Path(sys.argv[2])
with zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED) as z:
    for p in sorted(src.glob('*.png')): z.write(p,p.name)
print('FORMATION_TEXTURE_V3_ZIP',out,'files='+str(len(list(src.glob('*.png')))))
PYZIP

git add "$OUT"
if ! git diff --cached --quiet; then
  git commit -m "lab: direct-decode selected Formation textures on Android"
  git push origin "$BRANCH"
fi

echo "=== FORMATION PREBLURRED TEXTURE DIRECT DECODE V3 TERMINE ==="
echo "Rapport: $REPORT"
echo "Planche: $EXPORT/CONTACT_SHEET.png"
echo "ZIP: $ZIPOUT"
echo "main/preview inchangés."
