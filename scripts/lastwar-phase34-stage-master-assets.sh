#!/data/data/com.termux/files/usr/bin/bash
set -Eeuo pipefail

# WfGg Last War LAB — PHASE 34
# STAGE AUTHENTIC MASTER ASSETS
# Uses only the graphics already recovered locally by Phase 33.
# No Last War network connection. No generated substitute graphics.

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
KIT="$ROOT/frontend/lab/local-assets/lastwar-kit-v1"
CAT="$KIT/catalog.json"
HMAP="$ROOT/frontend/lab/lastwar-hero-authoritative-map.js"
DEST="$ROOT/frontend/lab/master-assets-v1"
BRANCH="portal-auth-lastwar-lab-v1"

fail(){ printf 'ERREUR: %s\n' "$*" >&2; exit 1; }
command -v python >/dev/null 2>&1 || fail "python absent"
[[ -s "$CAT" ]] || fail "catalog.json absent: $CAT"
[[ -s "$HMAP" ]] || fail "mapping héros absent: $HMAP"

cd "$ROOT"
CURRENT="$(git branch --show-current 2>/dev/null || true)"
[[ "$CURRENT" == "$BRANCH" ]] || fail "branche active=$CURRENT ; attendu=$BRANCH"

rm -rf "$DEST"
mkdir -p "$DEST/heroes" "$DEST/ui" "$DEST/companions"

python - "$KIT" "$CAT" "$HMAP" "$DEST" <<'PY'
from pathlib import Path
from PIL import Image
import hashlib, json, os, re, shutil, sys

kit=Path(sys.argv[1])
cat_path=Path(sys.argv[2])
hmap_path=Path(sys.argv[3])
dest=Path(sys.argv[4])
cat=json.loads(cat_path.read_text(encoding='utf-8'))
rows=[x for x in cat.get('extractedAssets',[]) if isinstance(x,dict)]
marker='/lab/local-assets/lastwar-kit-v1/'

def stem(s):
    s=os.path.basename(str(s or '')).lower()
    return re.sub(r'\.(png|jpg|jpeg|webp|tga)$','',s)

def src_for(row):
    lp=str(row.get('localPath') or '')
    if marker not in lp:return None
    p=kit/lp.split(marker,1)[1]
    return p if p.is_file() else None

def score(row, target=None):
    w=int(row.get('width') or 0); h=int(row.get('height') or 0)
    n=stem(row.get('name'))
    v=0
    if target and n==target:v+=100000
    if w==158 and h==201:v+=12000
    if w==140 and h==140:v+=5000
    if w==154 and h==154:v+=4500
    if row.get('objectType')=='Sprite':v+=900
    if '_zw' in n:v-=8000
    v+=min(w,h)
    return v

def pick_exact(name):
    wanted=stem(name)
    cand=[r for r in rows if stem(r.get('name'))==wanted and src_for(r)]
    if not cand:return None
    return max(cand,key=lambda r:score(r,wanted))

def copy_exact(name,out_rel,required=True):
    row=pick_exact(name)
    if not row:
        if required:raise SystemExit(f'asset exact introuvable: {name}')
        return None
    src=src_for(row); out=dest/out_rel
    out.parent.mkdir(parents=True,exist_ok=True)
    shutil.copy2(src,out)
    return {'name':name,'source':str(row.get('localPath')),'file':str(out_rel),'width':row.get('width'),'height':row.get('height'),'sha256':hashlib.sha256(out.read_bytes()).hexdigest()}

# 31 authoritative queue portraits: one stable filename per heroId.
hmap=hmap_path.read_text(encoding='utf-8',errors='ignore')
hero_pairs=[(int(a),b) for a,b in re.findall(r"heroId:(\d+).*?queueIcon:'([^']+)'",hmap)]
hero_manifest=[]
missing=[]
for hid,icon in hero_pairs:
    row=pick_exact(icon)
    if not row:
        missing.append((hid,icon));continue
    src=src_for(row);out=dest/'heroes'/f'{hid}.png'
    shutil.copy2(src,out)
    hero_manifest.append({
      'heroId':hid,'icon':icon,'source':row.get('localPath'),'file':f'heroes/{hid}.png',
      'width':row.get('width'),'height':row.get('height'),'sha256':hashlib.sha256(out.read_bytes()).hexdigest()
    })
if missing:
    raise SystemExit('portraits exacts manquants: '+', '.join(f'{hid}:{icon}' for hid,icon in missing))

ui_manifest=[]
for name,out in [
 ('biandui_cheku_1','ui/formation-1.png'),
 ('biandui_cheku_2','ui/formation-2.png'),
 ('biandui_cheku_3','ui/formation-3.png'),
 ('biandui_cheku_4','ui/formation-4.png'),
 ('biandui_cheku_defend','ui/formation-defend.png'),
 ('cfm_biandui_xingxing_5','ui/star-full.png'),
 ('yingxiong_jineng_cfm_gouxuan','ui/selected-check.png'),
 ('sactx-1024x512-ETC2-UILWHeroSquad-93368788','ui/squad-atlas.png'),
 ('sactx-1024x2048-ASTC 5x5-UI_UILWHeroDetail-36bf2009','ui/hero-detail-atlas.png'),
 ('sactx-512x128-ASTC 5x5-LWUIFormation-796cbebe','ui/formation-atlas.png'),
 ('sactx-1024x512-ETC2-UI_UIFormationDefence-3650d5b1','ui/formation-defence-atlas.png'),
]:
    ui_manifest.append(copy_exact(name,out,True))

# Exact troop silhouettes cropped from the recovered UILWHeroSquad atlas.
atlas=Image.open(dest/'ui/squad-atlas.png').convert('RGBA')
# Coordinates are the alpha-component bounds in the authentic 1024x512 atlas.
for key,box in {
 'tank':(91,114,132,149),
 'aircraft':(536,250,598,292),
 'missile':(683,392,732,448),
}.items():
    crop=atlas.crop(box)
    out=dest/'ui'/f'type-{key}.png'
    crop.save(out,'PNG',optimize=True)
    ui_manifest.append({'name':f'UILWHeroSquad crop {key}','source':'ui/squad-atlas.png','file':f'ui/type-{key}.png','crop':box,'width':crop.width,'height':crop.height,'sha256':hashlib.sha256(out.read_bytes()).hexdigest()})

comp_manifest=[]
for name,out in [
 ('FX_wurenji_pifu04','companions/drone-162.png'),
 ('zxl_zhuzai_touxiang_04','companions/gorilla-47.png'),
]:
    comp_manifest.append(copy_exact(name,out,True))

manifest={
 'format':'WFGG_LASTWAR_MASTER_ASSETS_V1',
 'networkUsed':False,
 'generatedSubstituteGraphics':False,
 'heroCount':len(hero_manifest),
 'heroes':hero_manifest,
 'ui':ui_manifest,
 'companions':comp_manifest,
 'sourceCatalog':str(cat_path),
}
(dest/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
print(f"PHASE34_STAGE_OK heroes={len(hero_manifest)} ui={len(ui_manifest)} companions={len(comp_manifest)}")
PY

# Commit only the stable master-assets directory. The large forensic cache remains local/ignored.
git add -f frontend/lab/master-assets-v1
if git diff --cached --quiet -- frontend/lab/master-assets-v1; then
  echo "Aucun changement d'assets à committer."
else
  git commit -m "lab: add authentic Last War master UI assets"
fi

git push origin "$BRANCH"

echo "=== PHASE 34 TERMINEE ==="
echo "Assets officiels figés dans frontend/lab/master-assets-v1 sur $BRANCH."
echo "main n'a pas été modifiée."
