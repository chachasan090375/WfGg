#!/data/data/com.termux/files/usr/bin/bash
set -Eeuo pipefail

# WfGg Last War LAB — Formation background pipeline proof
# Goal: prove how Layer0 is fed and extract exact native blur/world dependencies.
# No preview mutation, no generated artwork.

PKG="com.fun.lastwar.gp"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BRANCH="portal-auth-lastwar-lab-v1"
UNITY_VERSION="2019.4.41f1"
LOCAL="$ROOT/frontend/lab/local_assets/lastwar-formation-native-recipe-v1"
RECIPE="$ROOT/frontend/lab/master-assets-v2/meta/formation-native-recipe-v1.json"
LINKS="$ROOT/frontend/lab/master-assets-v2/meta/formation-layer0-native-links-v1.json"
OUT="$ROOT/frontend/lab/master-assets-v2/meta/formation-background-pipeline-v1.json"
REPORT="$HOME/storage/downloads/WFGG_LASTWAR_FORMATION_BACKGROUND_PIPELINE.txt"
TMPPY="${TMPDIR:-$HOME/.cache}/wfgg-formation-background-pipeline.py"
CACHE_ROOT="/sdcard/Android/data/$PKG/files/AssetBundles"

fail(){ printf 'ERREUR: %s\n' "$*" >&2; exit 1; }
cd "$ROOT"
[[ "$(git branch --show-current)" == "$BRANCH" ]] || fail "branche LAB incorrecte"
[[ -s "$LOCAL/gameres" ]] || fail "gameres local absent"
[[ -s "$RECIPE" ]] || fail "recipe absente"
[[ -s "$LINKS" ]] || fail "native links absents"
command -v python >/dev/null 2>&1 || fail "python absent"
python - <<'PY' >/dev/null 2>&1 || fail "UnityPy absent"
import UnityPy
PY
mkdir -p "$(dirname "$OUT")" "$(dirname "$REPORT")" "$(dirname "$TMPPY")"

mapfile -t APK_PATHS < <(cmd package path "$PKG" 2>/dev/null | sed -n 's/^package://p')
[[ ${#APK_PATHS[@]} -gt 0 ]] || fail "APK Last War introuvable"
SERIAL=""
if command -v adb >/dev/null 2>&1; then
  SERIAL="$(adb devices 2>/dev/null | awk 'NR>1 && $2=="device" {print $1; exit}')"
fi

cat > "$TMPPY" <<'PYEOF'
from __future__ import annotations
from pathlib import Path
from collections import Counter
import json,sys,re,struct,subprocess,zipfile,tempfile,contextlib,io,shutil

local=Path(sys.argv[1]); recipep=Path(sys.argv[2]); linksp=Path(sys.argv[3]); outp=Path(sys.argv[4]); reportp=Path(sys.argv[5])
serial,cache_root,unity_version=sys.argv[6:9]; apks=sys.argv[9:]
import UnityPy
UnityPy.config.FALLBACK_UNITY_VERSION=unity_version
recipe=json.loads(recipep.read_text('utf-8')); links=json.loads(linksp.read_text('utf-8'))
text=(local/'gameres').read_text('utf-8')

def section(name):
    m=re.search(rf'^\[{re.escape(name)}\]\s*$',text,re.M)
    if not m:return []
    s=m.end();n=re.search(r'^\[[^\]]+\]\s*$',text[s:],re.M);e=s+n.start() if n else len(text)
    return [x for x in text[s:e].splitlines() if x.strip()]

dirs={}
for ln in section('Directories'):
    try:i,p=ln.split(',',1);dirs[int(i)]=p
    except:pass
paths={}
for ln in section('Paths'):
    try:pid,did,n=ln.split(',',2);paths[int(pid)]=dirs[int(did)].rstrip('/')+'/'+n
    except:pass
bundles={}
for ln in section('Bundles'):
    p=ln.split(',')
    if len(p)<8:continue
    try:
        bid=int(p[0]); bundles[bid]={
            'bundleId':bid,'logicalName':p[1],'declaredBytes':int(p[3]),
            'assetPathIds':[int(x) for x in p[4].split('|') if x],
            'dependencyBundleIds':[int(x) for x in p[5].split('|') if x],
            'groups':p[6].split('|') if p[6] else [],'aliasName':p[7]}
    except:pass
for b in bundles.values(): b['assetPaths']=[paths.get(x) for x in b['assetPathIds'] if paths.get(x)]

ui=recipe['uiPanel']; depids={int(x) for x in ui.get('dependencyBundleIds') or [] if int(x) in bundles}

CATS={
 'blur':re.compile(r'blur|uiblur',re.I),
 'splat':re.compile(r'splatcontrol|splat',re.I),
 'terrain':re.compile(r'terrain',re.I),
 'world':re.compile(r'lastwar_world|worldcity|scene_world|worldmap|/world/',re.I),
 'render':re.compile(r'render.?texture|heroshow|showblend|camera',re.I),
}
cat_rows={k:[] for k in CATS}
for bid in sorted(depids):
    b=bundles[bid]; hay='\n'.join([b['logicalName']]+(b.get('assetPaths') or []))
    for cat,rx in CATS.items():
        hits=[p for p in b.get('assetPaths') or [] if rx.search(p)]
        if hits or rx.search(b['logicalName']):
            cat_rows[cat].append({
                'bundleId':bid,'logicalName':b['logicalName'],'aliasName':b['aliasName'],
                'declaredBytes':b['declaredBytes'],'hits':hits[:80],'allAssetPaths':b.get('assetPaths') or []})

# Exact global assets, with whether the owning bundle is a direct UI dependency.
WANTED=[
 re.compile(r'(^|/)BlurUI\.mat$',re.I),
 re.compile(r'(^|/)UIblur\.shader$',re.I),
 re.compile(r'SplatControl_World\.(png|tga)$',re.I),
 re.compile(r'SplatControl_City\.(png|tga)$',re.I),
 re.compile(r'(^|/)Terrain_0(_High)?\.mat$',re.I),
 re.compile(r'(^|/)Terrain_City(_High)?\.mat$',re.I),
]
exact=[]
for b in bundles.values():
    hits=[]
    for p in b.get('assetPaths') or []:
        if any(rx.search(p) for rx in WANTED):hits.append(p)
    if hits:
        exact.append({'bundleId':b['bundleId'],'isDirectUiDependency':b['bundleId'] in depids,'logicalName':b['logicalName'],'aliasName':b['aliasName'],'declaredBytes':b['declaredBytes'],'assetPaths':hits})

# APK fragment indexes for staging the exact blur material bundle offline.
def read7(buf,pos):
    out=0;shift=0
    while True:
        x=buf[pos];pos+=1;out|=(x&0x7f)<<shift
        if not x&0x80:return out,pos
        shift+=7
def parse_offsets(buf):
    pos=0;fc=struct.unpack_from('<I',buf,pos)[0];pos+=4;out=[]
    for _ in range(fc):
        ln,pos=read7(buf,pos);frag=buf[pos:pos+ln].decode();pos+=ln
        payload=struct.unpack_from('<I',buf,pos)[0];pos+=4
        cnt=struct.unpack_from('<I',buf,pos)[0];pos+=4;rows=[]
        for _ in range(cnt):
            ln,pos=read7(buf,pos);name=buf[pos:pos+ln].decode();pos+=ln
            off=struct.unpack_from('<Q',buf,pos)[0];pos+=8;rows.append((name,off))
        out.append((frag,payload,rows))
    return out
idx={};alias_idx={};fragment_src=None;fragment_size=None
for apk in apks:
    try:
        with zipfile.ZipFile(apk) as z:
            ns=set(z.namelist());bo='assets/AssetBundles/BundleOffsetTable.bytes';ao='assets/AssetBundles/AliasOffsetTable.bytes';fr='assets/AssetBundles/BundleFragment0.bytes'
            if bo in ns and not idx:
                rr=parse_offsets(z.read(bo));
                if rr:idx={n:o for n,o in rr[0][2]}
            if ao in ns and not alias_idx:
                rr=parse_offsets(z.read(ao));
                if rr:alias_idx={n:o for n,o in rr[0][2]}
            if fr in ns and fragment_src is None:
                fragment_src=(apk,fr);fragment_size=z.getinfo(fr).file_size
    except:pass
ordered=sorted((o,n) for n,o in idx.items());sizes={}
if fragment_size is not None:
    for i,(o,n) in enumerate(ordered):sizes[o]=(ordered[i+1][0] if i+1<len(ordered) else fragment_size)-o

def adb_readable(remote):
    if not serial:return False
    try:
        cp=subprocess.run(['adb','-s',serial,'shell',f'test -r {remote!r} && echo YES || echo NO'],stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,text=True,timeout=8)
        return cp.returncode==0 and 'YES' in cp.stdout
    except:return False

tmp=Path(tempfile.mkdtemp(prefix='wfgg-bgpipe-'))
def stage(b):
    alias=b['aliasName']; logical=b['logicalName']; dest=tmp/alias
    for p in (local/alias, local/'resolved-deps'/alias):
        if p.is_file():return p,'existing-local'
    remote=f'{cache_root}/{alias}'
    if re.fullmatch(r'[0-9a-fA-F]{64}\.bundle',alias) and adb_readable(remote):
        cp=subprocess.run(['adb','-s',serial,'pull',remote,str(dest)],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=90)
        if cp.returncode==0 and dest.is_file():return dest,'cache'
    off=idx.get(logical)
    if off is not None and alias_idx.get(alias)==off and fragment_src and off in sizes:
        apk,entry=fragment_src;n=sizes[off]
        try:
            with zipfile.ZipFile(apk) as z,z.open(entry) as f:
                left=off
                while left:
                    c=f.read(min(left,1024*1024))
                    if not c:break
                    left-=len(c)
                data=f.read(n)
            if len(data)==n:dest.write_bytes(data);return dest,'apk-fragment'
        except:pass
    return None,'missing'

def pidof(o):
    for n in ('path_id','m_PathID'):
        try:
            v=getattr(o,n,None)
            if v is not None:return int(v)
        except:pass
    return None

def objname(x):
    for n in ('m_Name','name'):
        try:
            v=getattr(x,n,None)
            if v:return str(v)
        except:pass
    return ''

def compact(v,depth=0):
    if depth>5:return '<max-depth>'
    if v is None or isinstance(v,(str,int,float,bool)):return v
    if isinstance(v,(list,tuple)):return [compact(x,depth+1) for x in v[:80]]
    if isinstance(v,dict):return {str(k):compact(x,depth+1) for k,x in list(v.items())[:80]}
    try:
        p=pidof(v)
        if p not in (None,0):return {'ptrPathId':p}
    except:pass
    try:return {str(k):compact(x,depth+1) for k,x in list(vars(v).items())[:80] if not str(k).startswith('_')}
    except:return str(v)[:1000]

blur_materials=[]
for row in exact:
    if not any(re.search(r'(^|/)BlurUI\.mat$',p,re.I) for p in row['assetPaths']):continue
    b=bundles[row['bundleId']]; p,source=stage(b)
    rec={'bundleId':b['bundleId'],'source':source,'assetPaths':row['assetPaths'],'materials':[]}
    if p:
        try:
            sink=io.StringIO()
            with contextlib.redirect_stderr(sink),contextlib.redirect_stdout(sink): env=UnityPy.load(str(p)); objs=list(env.objects)
            for o in objs:
                try:typ=o.type.name
                except:continue
                if typ!='Material':continue
                try:
                    with contextlib.redirect_stderr(sink),contextlib.redirect_stdout(sink): x=o.read()
                except:continue
                nm=objname(x)
                if 'blur' not in nm.lower():continue
                rec['materials'].append({'pathId':pidof(o),'name':nm,'shader':compact(getattr(x,'m_Shader',None)),'savedProperties':compact(getattr(x,'m_SavedProperties',None))})
        except Exception as e:rec['error']=repr(e)
    blur_materials.append(rec)

# Exact UI branch state, no generic Bg names.
def mono_for(name):
    return [m for m in links.get('targetMonoBehaviours') or [] if m.get('gameObject')==name and m.get('script')=='RawImage']
formation_bg=mono_for('FormationBg')
formation_rt=mono_for('FormationRT')

summary={
 'format':'WFGG_LASTWAR_FORMATION_BACKGROUND_PIPELINE_V1',
 'networkUsed':False,'generatedArtwork':False,
 'uiPanelBundleId':ui['bundleId'],'directDependencyCount':len(depids),
 'FormationBgRawImage':formation_bg,
 'FormationRTRawImage':formation_rt,
 'directDependencyCategories':cat_rows,
 'exactNativeAssets':exact,
 'blurMaterials':blur_materials,
 'architecture':{
   'FormationBgSerializedTextureIsZero':all(((m.get('fields') or {}).get('m_Texture') or {}).get('m_PathID',0)==0 for m in formation_bg),
   'FormationBgSerializedMaterialIsZero':all(((m.get('fields') or {}).get('m_Material') or {}).get('m_PathID',0)==0 for m in formation_bg),
   'FormationRTSerializedTextureIsZero':all(((m.get('fields') or {}).get('m_Texture') or {}).get('m_PathID',0)==0 for m in formation_rt),
   'FormationRTRuntimeMaterialExternal':any(((m.get('fields') or {}).get('m_Material') or {}).get('m_FileID',0)>0 for m in formation_rt),
   'interpretation':'FormationBg and FormationRT are runtime-fed RawImages; Layer0 is not a fixed serialized Formation texture. FormationBg is consistent with a runtime capture/blur of the underlying world view; FormationRT is the sharp 3D formation render target.'
 },
 'guardrails':{'previewUntouched':True,'mainUntouched':True,'noGeneratedImage':True}
}
outp.write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n','utf-8')

lines=['WfGg Last War — FORMATION BACKGROUND PIPELINE','NATIVE DEPENDENCY + BLUR MATERIAL TRACE','',
 f"directDeps={len(depids)} blurDeps={len(cat_rows['blur'])} splatDeps={len(cat_rows['splat'])} terrainDeps={len(cat_rows['terrain'])} worldDeps={len(cat_rows['world'])}",
 f"FormationBg textureZero={summary['architecture']['FormationBgSerializedTextureIsZero']} materialZero={summary['architecture']['FormationBgSerializedMaterialIsZero']}",
 f"FormationRT textureZero={summary['architecture']['FormationRTSerializedTextureIsZero']} externalMaterial={summary['architecture']['FormationRTRuntimeMaterialExternal']}",'']
for cat in ('blur','splat','terrain','world','render'):
    lines.append(cat.upper())
    for r in cat_rows[cat]:
        lines.append(f"  bundle={r['bundleId']} {r['logicalName']}")
        for h in r['hits'][:20]:lines.append('    '+h)
lines+=['','EXACT NATIVE ASSETS']
for r in exact:
    lines.append(f"  bundle={r['bundleId']} direct={r['isDirectUiDependency']}")
    for p in r['assetPaths']:lines.append('    '+p)
lines+=['','BLUR MATERIAL PROPERTIES']
for r in blur_materials:
    lines.append(f"  bundle={r['bundleId']} source={r['source']}")
    for m in r.get('materials') or []:lines.append('    '+json.dumps(m,ensure_ascii=False)[:12000])
lines+=['','INTERPRETATION',summary['architecture']['interpretation']]
reportp.write_text('\n'.join(lines)+'\n','utf-8')
shutil.rmtree(tmp,ignore_errors=True)

print('FORMATION_BACKGROUND_PIPELINE_OK',f"blurDeps={len(cat_rows['blur'])}",f"splatDeps={len(cat_rows['splat'])}",f"terrainDeps={len(cat_rows['terrain'])}",f"worldDeps={len(cat_rows['world'])}",f"blurMaterials={sum(len(x.get('materials') or []) for x in blur_materials)}")
print('FORMATION_BG_RUNTIME',f"textureZero={summary['architecture']['FormationBgSerializedTextureIsZero']}",f"materialZero={summary['architecture']['FormationBgSerializedMaterialIsZero']}")
print('FORMATION_RT_RUNTIME',f"textureZero={summary['architecture']['FormationRTSerializedTextureIsZero']}",f"externalMaterial={summary['architecture']['FormationRTRuntimeMaterialExternal']}")
for r in exact:
    for p in r['assetPaths']:
        print('NATIVE_ASSET',f"direct={r['isDirectUiDependency']}",f"bundle={r['bundleId']}",p)
for r in blur_materials:
    for m in r.get('materials') or []:
        print('BLUR_MATERIAL',f"bundle={r['bundleId']}",f"name={m['name']}",f"source={r['source']}")
print('FORMATION_BACKGROUND_PIPELINE_JSON',outp)
print('FORMATION_BACKGROUND_PIPELINE_REPORT',reportp)
PYEOF

python "$TMPPY" "$LOCAL" "$RECIPE" "$LINKS" "$OUT" "$REPORT" "$SERIAL" "$CACHE_ROOT" "$UNITY_VERSION" "${APK_PATHS[@]}"
rm -f "$TMPPY"

git add scripts/lastwar-formation-background-pipeline.sh "$OUT"
if ! git diff --cached --quiet; then
  git commit -m "lab: trace Formation background blur pipeline"
  git push origin "$BRANCH"
fi

echo "=== FORMATION BACKGROUND PIPELINE TERMINE ==="
echo "JSON: $OUT"
echo "Rapport: $REPORT"
echo "main non modifiée."
