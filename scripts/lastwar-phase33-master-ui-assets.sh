#!/data/data/com.termux/files/usr/bin/bash
set -Eeuo pipefail

# WfGg Last War LAB — PHASE 33
# MASTER UI ASSET RECOVERY
# OFFLINE ONLY. Reads the installed Last War APK/splits already present on the phone.
# Purpose: recover the authentic raster/UI assets needed to reproduce the two master
# references (Hero list card + Formation/Team screen), then package the binaries for review.
# No Last War network connection. No gameplay automation. No credentials/account data.

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BASE="$ROOT/scripts/lastwar-phase30b-node-payload-extraction.sh"
RUNNER="$ROOT/scripts/lastwar-phase30d-engine-version-discovery.sh"
KIT_DIR="$ROOT/frontend/lab/local-assets/lastwar-kit-v1"
DOWNLOADS="${HOME}/storage/downloads"
TMP="$ROOT/scripts/.lastwar-phase33-master-assets.$$"
OUT="$DOWNLOADS/WFGG_LASTWAR_PHASE33_MASTER_UI_ASSETS_REDACTED.txt"
PACK_PREFIX="$DOWNLOADS/WFGG_LASTWAR_MASTER_ASSETS"

cleanup(){ rm -f "$TMP"; }
trap cleanup EXIT

die(){ printf 'ERREUR: %s\n' "$*" >&2; exit 1; }
command -v python >/dev/null 2>&1 || die "python Termux absent"
[[ -s "$BASE" ]] || die "Phase 30B introuvable: $BASE"
[[ -s "$RUNNER" ]] || die "Phase 30D introuvable: $RUNNER"
[[ -s "$KIT_DIR/catalog.json" ]] || die "Kit graphique absent: $KIT_DIR/catalog.json"

rm -rf "$KIT_DIR/master-assets-raw"
mkdir -p "$KIT_DIR/master-assets-raw/ui" "$KIT_DIR/master-assets-raw/models"
rm -f "${PACK_PREFIX}"_PART*.zip

cp "$BASE" "$TMP"
python - "$TMP" <<'PY'
from pathlib import Path
import sys
p=Path(sys.argv[1])
s=p.read_text(encoding='utf-8')

# Keep the proven decoder/UnityPy pipeline, but make the candidate contract specific
# to the two real Last War UI screens supplied as master references.
repls={
 'WFGG_LASTWAR_PHASE30B_NODE_PAYLOAD_EXTRACTION_REDACTED.txt':'WFGG_LASTWAR_PHASE33_MASTER_UI_ASSETS_REDACTED.txt',
 'MAX_CANDIDATES_TO_LOAD=520':'MAX_CANDIDATES_TO_LOAD=2600',
 'MAX_EXPORTED=1200':'MAX_EXPORTED=2600',
 'MAX_OUTPUT_BYTES=350*1024*1024':'MAX_OUTPUT_BYTES=450*1024*1024',
 'PHASE30B_DONE':'PHASE33_DONE',
 'WfGg Last War LAB — PHASE 30B NODE PAYLOAD EXTRACTION':'WfGg Last War LAB — PHASE 33 MASTER UI ASSET RECOVERY',
 '=== PHASE 30B TERMINEE ===':'=== PHASE 33 EXTRACTION TERMINEE ===',
}
for a,b in repls.items():
    if a not in s:
        raise SystemExit(f'point de patch absent: {a}')
    s=s.replace(a,b)

# Replace the broad historical category scan by the precise families seen in the
# installed gameres catalogue and in the two master screens.
a=s.index('CATEGORY_TERMS={')
b=s.index('LOWER_TERMS=',a)
new_categories=r'''CATEGORY_TERMS={
 "heroes":["heroiconsbig","heroiconssmall","hero_icon_","lw_herobody","halfbody","herohead","headicon"] + all_aliases,
 "drone":["hero_icon_drone","item_uav_equip_","fx_wurenji_pifu","uav","drone"],
 "dominator":["dominator","zxl_zhuzai","gorilla"],
 "ui":[
   "lwuiformation","uilwherosquad","uilwsquadequip","uiformationdefence",
   "formationdispatchtask","uilwheroexhibit","uilwherodetail","lwhero/formation",
   "formationpreset","heroqualityicon","herotypeicon","qualityicon","qualityframe",
   "hero_frame","rankicon","staricon","heroiconsbig","heroiconssmall"
 ],
 "equipment":["lw_equip","equip_icon","unique_weapon","weapon_icon","equipment"],
 "models":["models/cars","_art_lastwar/models","a_hero_","queue_model_path","heroimg_model"]
}
'''
s=s[:a]+new_categories+s[b:]

# UI candidates first, then queue/vehicle models, then exact character/companion assets.
a=s.index('def candidate_priority(c):')
b=s.index('\nstats=Counter()',a)
new_priority=r'''def candidate_priority(c):
    names=set(hero_names_from_hits(c["hits"]))
    cats=set(c["hits"])
    if "ui" in cats:return (0,c["start"])
    if "models" in cats and (names & active_names):return (1,c["start"])
    if names & active_names:return (2,c["start"])
    if "drone" in cats:return (3,c["start"])
    if "dominator" in cats:return (4,c["start"])
    if "heroes" in cats:return (5,c["start"])
    if "models" in cats:return (6,c["start"])
    return (7,c["start"])
'''
s=s[:a]+new_priority+s[b:]

# Persistent raw bundle cache. If a SpriteAtlas cannot be decoded perfectly on Android,
# these authentic UnityFS bundles are still available for desktop-side forensic extraction.
needle='extract_root=os.path.join(kit_dir,"extracted")\nfor sub in ("heroes","drone","dominator","ui","equipment","other"):\n    os.makedirs(os.path.join(extract_root,sub),exist_ok=True)\n'
insert=needle+r'''raw_master_root=os.path.join(kit_dir,"master-assets-raw")
raw_ui_root=os.path.join(raw_master_root,"ui")
raw_model_root=os.path.join(raw_master_root,"models")
os.makedirs(raw_ui_root,exist_ok=True)
os.makedirs(raw_model_root,exist_ok=True)
RAW_UI_MAX=180*1024*1024
RAW_MODEL_MAX=180*1024*1024
raw_ui_bytes=0
raw_model_bytes=0
raw_bundle_rows=[]
'''
if s.count(needle)!=1:
    raise SystemExit('point de patch raw root introuvable')
s=s.replace(needle,insert,1)

# Do not export generic textures from model bundles. For a real UI-atlas candidate,
# however, export every Sprite/Texture2D even when the object name itself is generic.
needle='def save_image(img,name,objtype,candidate,path_id):\n    global output_bytes\n'
insert=r'''def phase33_wanted_asset(name,candidate):
    low=str(name or '').lower()
    cats=set(candidate.get("hits",{}))
    bad=('eff_','effect','smoke','noise','trail','particle','normalmap','lightmap')
    if "ui" in cats:
        return not any(x in low for x in ('smoke','particle','trail'))
    if "heroes" in cats:
        return (('hero_icon_' in low or 'halfbody' in low or 'herohead' in low or 'headicon' in low or 'portrait' in low)
                and not any(x in low for x in bad+('zhuanwu','lrb_','ljq_icon','weapon')))
    if "drone" in cats:
        return any(x in low for x in ('icon','head','portrait','fx_wurenji_pifu','item_uav_equip')) and not any(x in low for x in bad)
    if "dominator" in cats:
        return any(x in low for x in ('icon','head','portrait','pic','avatar','zxl_zhuzai')) and not any(x in low for x in bad)
    return False

def save_image(img,name,objtype,candidate,path_id):
    global output_bytes
    if not phase33_wanted_asset(name,candidate):
        return False
'''
if s.count(needle)!=1:
    raise SystemExit('point de patch save_image introuvable')
s=s.replace(needle,insert,1)

# Preserve authentic raw UnityFS bytes for the exact UI bundles and active-hero model bundles.
needle='            size,nodes,data=decode_bundle(f,c["start"],total,True)\n            with tempfile.TemporaryDirectory(prefix="wfgg-u-node-") as td:\n'
insert=r'''            size,nodes,data=decode_bundle(f,c["start"],total,True)
            cats=set(c.get("hits",{}))
            names=set(hero_names_from_hits(c.get("hits",{})))
            raw_kind=None
            if "ui" in cats and raw_ui_bytes < RAW_UI_MAX:
                raw_kind="ui"
            elif "models" in cats and (names & active_names) and raw_model_bytes < RAW_MODEL_MAX:
                raw_kind="models"
            if raw_kind:
                f.seek(c["start"])
                raw_bundle=f.read(size)
                safe_names='-'.join(sorted(names & active_names))[:80] or 'generic'
                raw_name=f"{c['start']:08x}_{size}_{safe_names}.bundle"
                raw_dir=raw_ui_root if raw_kind=="ui" else raw_model_root
                raw_path=os.path.join(raw_dir,raw_name)
                if not os.path.exists(raw_path):
                    with open(raw_path,"wb") as rb: rb.write(raw_bundle)
                    if raw_kind=="ui": raw_ui_bytes += len(raw_bundle)
                    else: raw_model_bytes += len(raw_bundle)
                    raw_bundle_rows.append({"kind":raw_kind,"offset":c["start"],"bytes":len(raw_bundle),"names":sorted(names),"hits":c.get("hits",{}),"file":raw_name})
            with tempfile.TemporaryDirectory(prefix="wfgg-u-node-") as td:
'''
if s.count(needle)!=1:
    raise SystemExit(f'point de patch raw bundle inattendu ({s.count(needle)})')
s=s.replace(needle,insert,1)

# Atlas bundles may contain both Sprite and Texture2D objects. Keep both for UI candidates.
needle='                if not sprites:\n                    for obj in objects:\n'
repl='                if (not sprites) or ("ui" in c.get("hits",{})):\n                    for obj in objects:\n'
if s.count(needle)!=1:
    raise SystemExit(f'point de patch Texture2D inattendu ({s.count(needle)})')
s=s.replace(needle,repl,1)

# Persist raw-bundle metadata into the catalog and the report.
needle='catalog["decodedByPhase30NodeFallback"]=True\n'
repl='catalog["decodedByPhase30NodeFallback"]=True\ncatalog["phase33MasterRawBundles"]=raw_bundle_rows\n'
if s.count(needle)!=1:
    raise SystemExit('point de patch catalog phase33 absent')
s=s.replace(needle,repl,1)

needle='    o.write("GAME DATA LOCAL ONLY · custom UnityFS decode -> node payloads -> UnityPy\\n\\n")\n'
repl=(needle+
 '    o.write("TARGET=MASTER HERO CARD + MASTER FORMATION SCREEN\\n")\n'
 '    o.write("UI_FAMILIES=lwuiformation,uilwherosquad,uilwsquadequip,uiformationdefence,uilwheroexhibit,uilwherodetail\\n")\n'
 '    o.write(f"rawUiBundleBytes={raw_ui_bytes} rawModelBundleBytes={raw_model_bytes} rawBundles={len(raw_bundle_rows)}\\n\\n")\n')
if s.count(needle)!=1:
    raise SystemExit('point de patch rapport phase33 absent')
s=s.replace(needle,repl,1)

p.write_text(s,encoding='utf-8')
PY

chmod 700 "$TMP"
echo "=== PHASE 33 · RECUPERATION DES ASSETS MAITRES ==="
echo "Extraction locale des vrais atlas UI, portraits et compagnons + conservation des bundles UI/modèles."
echo "Aucune connexion Last War ne sera effectuée."

WFGG_PHASE30B_SRC="$TMP" bash "$RUNNER"

# Package only useful authentic assets. Parts stay below ~45 MiB for easy upload.
python - "$ROOT" "$KIT_DIR" "$OUT" "$PACK_PREFIX" <<'PY'
import json, os, re, sys, zipfile, hashlib
from pathlib import Path
root=Path(sys.argv[1]); kit=Path(sys.argv[2]); report=Path(sys.argv[3]); prefix=Path(sys.argv[4])
cat_path=kit/'catalog.json'
cat=json.loads(cat_path.read_text(encoding='utf-8'))
assets=[x for x in cat.get('extractedAssets',[]) if isinstance(x,dict)]

hero_map=(root/'frontend/lab/lastwar-hero-authoritative-map.js').read_text(encoding='utf-8',errors='ignore')
comp_map=(root/'frontend/lab/lastwar-companion-authoritative-map.js').read_text(encoding='utf-8',errors='ignore')
hero_targets={x.lower() for x in re.findall(r"(?:queueIcon|halfIcon):'([^']+)'",hero_map)}
comp_targets={x.lower() for x in re.findall(r"icon:'([^']+)'",comp_map)}

def stem(v):
    return re.sub(r'\.(?:png|jpg|jpeg|tga|webp)$','',os.path.basename(str(v or '')),flags=re.I).lower()

def local_file(row):
    lp=str(row.get('localPath') or '')
    marker='/lab/local-assets/lastwar-kit-v1/'
    if marker not in lp:return None
    rel=lp.split(marker,1)[1]
    p=kit/rel
    return p if p.is_file() else None

selected=[];manifest=[];seen=set()
for row in assets:
    catname=str(row.get('category') or '')
    n=stem(row.get('name'))
    take=False
    reason=''
    if catname=='ui': take=True;reason='ui_atlas_export'
    elif catname=='heroes' and n in hero_targets: take=True;reason='authoritative_hero_icon'
    elif catname in ('drone','dominator') and n in comp_targets: take=True;reason='authoritative_companion_icon'
    if not take:continue
    p=local_file(row)
    if not p:continue
    key=str(p.resolve())
    if key in seen:continue
    seen.add(key)
    arc=f"raster/{catname}/{p.name}"
    selected.append((p,arc))
    manifest.append({k:row.get(k) for k in ('name','objectType','category','heroName','mappingBasis','bundleOffset','pathId','width','height','bytes','localPath')}|{'reason':reason})

# Raw authentic UnityFS bundles captured for unresolved atlas/model work.
for kind in ('ui','models'):
    d=kit/'master-assets-raw'/kind
    if d.is_dir():
        for p in sorted(d.glob('*.bundle')):
            selected.append((p,f'raw-bundles/{kind}/{p.name}'))

meta_dir=kit/'master-assets-meta'
meta_dir.mkdir(parents=True,exist_ok=True)
manifest_path=meta_dir/'MASTER_ASSET_MANIFEST.json'
manifest_path.write_text(json.dumps({
    'format':'WFGG_LASTWAR_MASTER_ASSET_PACKAGE_V1',
    'networkUsed':False,
    'rasterAssets':manifest,
    'rawBundles':cat.get('phase33MasterRawBundles',[]),
    'heroTargetCount':len(hero_targets),
    'companionTargetCount':len(comp_targets)
},ensure_ascii=False,indent=2),encoding='utf-8')

meta=[
 (manifest_path,'metadata/MASTER_ASSET_MANIFEST.json'),
 (cat_path,'metadata/catalog.json'),
 (root/'frontend/lab/lastwar-hero-authoritative-map.js','metadata/lastwar-hero-authoritative-map.js'),
 (root/'frontend/lab/lastwar-companion-authoritative-map.js','metadata/lastwar-companion-authoritative-map.js'),
 (root/'scripts/lastwar-phase33-master-ui-assets.sh','metadata/lastwar-phase33-master-ui-assets.sh')
]
if report.is_file():meta.append((report,'metadata/WFGG_LASTWAR_PHASE33_MASTER_UI_ASSETS_REDACTED.txt'))

# Deduplicate and create <=45 MiB logical parts. Metadata is repeated in every part.
uniq=[];seen=set()
for p,a in selected:
    if not p.is_file():continue
    k=(str(p.resolve()),a)
    if k in seen:continue
    seen.add(k);uniq.append((p,a))
MAX=45*1024*1024
parts=[];cur=[];cur_size=0
for p,a in sorted(uniq,key=lambda x:x[1]):
    sz=p.stat().st_size
    if cur and cur_size+sz>MAX:
        parts.append(cur);cur=[];cur_size=0
    cur.append((p,a));cur_size+=sz
if cur or not parts:parts.append(cur)

rows=[]
for i,items in enumerate(parts,1):
    out=Path(f'{prefix}_PART{i:02d}.zip')
    with zipfile.ZipFile(out,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for p,a in meta:
            if p.is_file():z.write(p,a)
        for p,a in items:z.write(p,a)
    h=hashlib.sha256(out.read_bytes()).hexdigest()
    rows.append((out,out.stat().st_size,h,len(items)))

index=Path(f'{prefix}_INDEX.txt')
with index.open('w',encoding='utf-8') as f:
    f.write('WfGg Last War — MASTER ASSET PACKAGE\n')
    f.write('OFFLINE installed-game extraction; no account data; no network use.\n')
    f.write(f'rasterSelected={len(manifest)} heroTargets={len(hero_targets)} companionTargets={len(comp_targets)}\n')
    f.write(f'rawBundles={len(cat.get("phase33MasterRawBundles",[]))}\n')
    for out,sz,h,n in rows:f.write(f'{out.name}\tbytes={sz}\tfiles={n}\tsha256={h}\n')
print('=== ASSET_PACKAGE_READY ===')
print(index)
for out,sz,h,n in rows:print(f'{out}  ({sz} bytes, {n} assets)')
PY

echo
echo "=== PHASE 33 TERMINEE ==="
echo "Envoie-moi WFGG_LASTWAR_MASTER_ASSETS_INDEX.txt et TOUS les WFGG_LASTWAR_MASTER_ASSETS_PARTxx.zip présents dans Téléchargements."
echo "Je n'implémente aucun nouveau rendu avant inspection de ces assets."
