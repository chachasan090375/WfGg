#!/data/data/com.termux/files/usr/bin/bash
set -Eeuo pipefail

# WfGg Last War LAB — PHASE 35
# PIXEL MASTER: stage exact UI sprites + inspect/export authentic vehicle models.
# CODE ONLY. No mock artwork. No Last War network connection.

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BRANCH="portal-auth-lastwar-lab-v1"
KIT="$ROOT/frontend/lab/local-assets/lastwar-kit-v1"
CAT="$KIT/catalog.json"
DEST="$ROOT/frontend/lab/master-assets-v2"
VEH_LOCAL="$ROOT/frontend/lab/local-assets/lastwar-vehicle-models-v1"
DL="$HOME/storage/downloads"
TMP="$ROOT/.tmp/lastwar-phase35-master-unpack"

fail(){ printf 'ERREUR: %s\n' "$*" >&2; exit 1; }
command -v python >/dev/null 2>&1 || fail "python absent"
command -v unzip >/dev/null 2>&1 || fail "unzip absent"
[[ -s "$CAT" ]] || fail "catalog.json absent: $CAT"
cd "$ROOT"
[[ "$(git branch --show-current)" == "$BRANCH" ]] || fail "branche active incorrecte"

PARTS=(
  "$DL/WFGG_LASTWAR_MASTER_ASSETS_PART01.zip"
  "$DL/WFGG_LASTWAR_MASTER_ASSETS_PART02.zip"
  "$DL/WFGG_LASTWAR_MASTER_ASSETS_PART03.zip"
)
for p in "${PARTS[@]}"; do [[ -s "$p" ]] || fail "archive absente: $p"; done

rm -rf "$TMP" "$DEST" "$VEH_LOCAL"
mkdir -p "$TMP" "$DEST/ui" "$DEST/meta" "$VEH_LOCAL"
for p in "${PARTS[@]}"; do unzip -q -o "$p" -d "$TMP"; done

python - "$KIT" "$CAT" "$DEST" <<'PY'
from pathlib import Path
import hashlib, json, os, re, shutil, sys

kit=Path(sys.argv[1]); catp=Path(sys.argv[2]); dest=Path(sys.argv[3])
cat=json.loads(catp.read_text(encoding='utf-8'))
rows=[x for x in cat.get('extractedAssets',[]) if isinstance(x,dict)]
marker='/lab/local-assets/lastwar-kit-v1/'

def stem(s):
    return re.sub(r'\.(png|jpg|jpeg|webp|tga)$','',os.path.basename(str(s or '')).lower())

def src(row):
    lp=str(row.get('localPath') or '')
    if marker not in lp:return None
    p=kit/lp.split(marker,1)[1]
    return p if p.is_file() else None

def pick(name):
    w=stem(name)
    cand=[r for r in rows if stem(r.get('name'))==w and src(r)]
    if not cand:return None
    def score(r):
        v=0
        if r.get('objectType')=='Sprite':v+=1000
        v+=min(int(r.get('width') or 0),int(r.get('height') or 0))
        return v
    return max(cand,key=score)

def copy(name,out,required=True):
    r=pick(name)
    if not r:
        if required: raise SystemExit(f'asset exact introuvable: {name}')
        return None
    s=src(r); o=dest/out; o.parent.mkdir(parents=True,exist_ok=True); shutil.copy2(s,o)
    return {'name':name,'file':out,'source':r.get('localPath'),'width':r.get('width'),'height':r.get('height'),'sha256':hashlib.sha256(o.read_bytes()).hexdigest()}

assets=[]
# Native formation platform textures (not CSS reconstructions).
for name,out in [
 ('A_build_formation_0_D','ui/formation-ground-0.png'),
 ('A_build_formation_01_D','ui/formation-ground-1.png'),
 ('A_build_formation_02_D','ui/formation-ground-2.png'),
 ('A_build_formation_03_D','ui/formation-ground-3.png'),
 ('A_build_formation_04_D','ui/formation-ground-4.png'),
 ('A_build_formation_05_D','ui/formation-ground-5.png'),
]: assets.append(copy(name,out))

# Exact hero role badges used by Last War cards.
for name,out in [
 ('cfm_yingxiong_tubiao_shuxing1','ui/role-1.png'),
 ('cfm_yingxiong_tubiao_shuxing2','ui/role-2.png'),
 ('cfm_yingxiong_tubiao_shuxing3','ui/role-3.png'),
]: assets.append(copy(name,out))

# Exact squad / formation icons present in the recovered game assets.
for n in range(1,5):
    assets.append(copy(f'cfm_yingxiong_biandui_tubiao_{n}',f'ui/squad-control-{n}.png'))
for name,out in [
 ('zyf_biandui_tanke_xiao','ui/type-tank-small.png'),
 ('zyf_biandui_tanke_da','ui/type-tank-large.png'),
 ('zyf_biandui_feiji_xiao','ui/type-aircraft-small.png'),
 ('zyf_biandui_feiji_da','ui/type-aircraft-large.png'),
 ('zyf_biandui_daodan_xiao','ui/type-missile-small.png'),
 ('zyf_biandui_daodan_da','ui/type-missile-large.png'),
 ('lrb_wurenji_xinpian_icon','ui/drone-chip-icon.png'),
 ('fu_juexing_xiaosuozi','ui/lock.png'),
 ('zxl_biandui_fanhui','ui/back.png'),
 ('zxl_biandui_huadong','ui/drag.png'),
]: assets.append(copy(name,out,False))

assets=[a for a in assets if a]
manifest={'format':'WFGG_LASTWAR_PIXEL_MASTER_UI_V2','networkUsed':False,'generatedSubstituteGraphics':False,'assets':assets}
(dest/'meta'/'ui-manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
print(f'PHASE35_UI_OK assets={len(assets)}')
PY

python - "$TMP" "$VEH_LOCAL" "$DEST/meta/vehicle-model-inventory.json" <<'PY'
from pathlib import Path
import json, os, re, sys, traceback
try:
    import UnityPy
except Exception as e:
    raise SystemExit(f'UnityPy absent: {e}')

root=Path(sys.argv[1]); outroot=Path(sys.argv[2]); reportp=Path(sys.argv[3])
modelroot=root/'raw-bundles'/'models'
if not modelroot.is_dir(): raise SystemExit(f'dossier modèles absent: {modelroot}')

TARGETS={
  50006:('Murphy',['a_hero_murphy','audie_murphy','murphy']),
  50007:('Williams',['a_hero_rick','rick']),
  50008:('Marshall',['a_hero_nimitz','nimitz']),
  50009:('Kimberly',['a_hero_katyusha','katyusha']),
  50010:('Stetmann',['a_hero_stetman','stetman']),
  50019:('Carlie',['a_hero_carly','a_hero_carlie','carly','carlie']),
  50021:('Lucius',['a_hero_lucius','lucius']),
  50018:('Schuyler',['a_hero_sally_ride','sally_ride','schuyler']),
  50017:('DVA',['a_hero_dva','hero_dva']),
  50020:('Morrison',['a_hero_morrison','morrison']),
  50013:('McGregor',['a_hero_ewan_mcgregor','ewan_mcgregor','mcgregor']),
  50022:('Adam',['a_hero_adam','adam']),
  50015:('Swift',['a_hero_tom','hero_tom']),
  50016:('Tesla',['a_hero_tesla','tesla']),
  50014:('Fiona',['a_hero_fiona','fiona']),
}

def lowbytes(p):
    try:return p.read_bytes().lower()
    except:return b''

def textmatch(s, aliases):
    s=(s or '').lower()
    return max([len(a) for a in aliases if a in s] or [0])

def read_obj(reader):
    try:return reader.read()
    except Exception:
        try:return reader.parse_as_object()
        except Exception:return None

inventory={'format':'WFGG_LASTWAR_VEHICLE_MODEL_INVENTORY_V1','networkUsed':False,'engine':'Unity','heroes':[]}
for hid,(display,aliases) in TARGETS.items():
    encoded=[a.encode() for a in aliases]
    candidates=[]
    for p in modelroot.glob('*.bundle'):
        raw=lowbytes(p)
        hit=max([len(a) for a,b in zip(aliases,encoded) if b in raw] or [0])
        if hit:
            candidates.append((hit,p.stat().st_size,p))
    # exact A_Hero aliases first, then richest candidate.
    candidates.sort(key=lambda x:(x[0],x[1]),reverse=True)
    hero={'heroId':hid,'name':display,'aliases':aliases,'candidateCount':len(candidates),'bundles':[],'animationClipCount':0,'meshCount':0,'rendererCount':0}
    for _,_,p in candidates[:24]:
        item={'file':p.name,'bytes':p.stat().st_size,'gameObjects':[],'meshes':[],'renderers':[],'animations':[],'materials':[],'textures':[],'errors':[]}
        try:
            env=UnityPy.load(str(p))
            for obj in env.objects:
                typ=getattr(obj.type,'name',str(obj.type))
                if typ not in ('GameObject','Mesh','MeshRenderer','SkinnedMeshRenderer','Renderer','AnimationClip','Animator','AnimatorController','Material','Texture2D'):
                    continue
                d=read_obj(obj)
                if d is None: continue
                name=str(getattr(d,'m_Name','') or getattr(d,'name','') or '')
                if typ=='GameObject' and name:item['gameObjects'].append(name)
                elif typ=='Mesh' and name:item['meshes'].append(name)
                elif typ in ('MeshRenderer','SkinnedMeshRenderer','Renderer'):
                    gname=''
                    try:
                        gp=getattr(d,'m_GameObject',None)
                        if gp:
                            go=gp.read() if hasattr(gp,'read') else gp.deref_parse_as_object()
                            gname=str(getattr(go,'m_Name','') or getattr(go,'name','') or '')
                    except Exception: pass
                    item['renderers'].append(gname or name or typ)
                elif typ=='AnimationClip' and name:item['animations'].append(name)
                elif typ=='Material' and name:item['materials'].append(name)
                elif typ=='Texture2D' and name:item['textures'].append(name)
        except Exception as e:
            item['errors'].append(repr(e))
        # Keep a bundle if its parsed names reinforce the hero match or if it has renderable content.
        searchable=' '.join(item['gameObjects']+item['meshes']+item['renderers']+item['animations']+item['materials']+item['textures'])
        score=textmatch(searchable,aliases)
        item['score']=score
        if score or item['meshes'] or item['renderers'] or item['animations']:
            hero['bundles'].append(item)
    hero['bundles'].sort(key=lambda x:(x.get('score',0),len(x['renderers']),len(x['meshes']),len(x['animations']),x['bytes']),reverse=True)
    # Export only top matching bundles into ignored local-assets; never fake a vehicle.
    exportdir=outroot/str(hid); exportdir.mkdir(parents=True,exist_ok=True)
    for item in hero['bundles'][:4]:
        p=modelroot/item['file']
        try:
            env=UnityPy.load(str(p))
            bundle_dir=exportdir/p.stem; bundle_dir.mkdir(parents=True,exist_ok=True)
            for obj in env.objects:
                typ=getattr(obj.type,'name',str(obj.type))
                d=read_obj(obj)
                if d is None: continue
                nm=re.sub(r'[^A-Za-z0-9_.-]+','_',str(getattr(d,'m_Name','') or getattr(d,'name','') or typ)).strip('_')[:120] or typ
                if typ=='Mesh':
                    try:
                        txt=d.export()
                        (bundle_dir/f'{nm}_{getattr(obj,"path_id",0)}.obj').write_text(txt,encoding='utf-8',newline='')
                    except Exception as e:item['errors'].append(f'mesh-export:{nm}:{e!r}')
                elif typ in ('MeshRenderer','SkinnedMeshRenderer','Renderer'):
                    try:
                        d.export(str(bundle_dir/f'renderer_{getattr(obj,"path_id",0)}'))
                    except Exception as e:item['errors'].append(f'renderer-export:{nm}:{e!r}')
            item['exportDir']=str(bundle_dir.relative_to(outroot))
        except Exception as e:item['errors'].append(f'export-bundle:{e!r}')
    hero['animationClipCount']=sum(len(x['animations']) for x in hero['bundles'])
    hero['meshCount']=sum(len(x['meshes']) for x in hero['bundles'])
    hero['rendererCount']=sum(len(x['renderers']) for x in hero['bundles'])
    hero['engineRendered3D']=bool(hero['meshCount'] or hero['rendererCount'])
    hero['hasAnimationData']=bool(hero['animationClipCount'])
    inventory['heroes'].append(hero)
    print(f"MODEL {hid} {display}: candidates={hero['candidateCount']} meshes={hero['meshCount']} renderers={hero['rendererCount']} anim={hero['animationClipCount']}")

inventory['engineRendered3D']=any(h['engineRendered3D'] for h in inventory['heroes'])
inventory['animationDataPresent']=any(h['hasAnimationData'] for h in inventory['heroes'])
reportp.parent.mkdir(parents=True,exist_ok=True)
reportp.write_text(json.dumps(inventory,ensure_ascii=False,indent=2),encoding='utf-8')
print(f"PHASE35_MODEL_OK engine3D={inventory['engineRendered3D']} animationData={inventory['animationDataPresent']}")
PY

# Keep exported OBJ/material/texture forensic files local and ignored.
mkdir -p "$VEH_LOCAL"
cat > "$VEH_LOCAL/.gitignore" <<'EOF'
*
!.gitignore
EOF

git add -f frontend/lab/master-assets-v2 scripts/lastwar-phase35-pixel-master.sh
if git diff --cached --quiet -- frontend/lab/master-assets-v2 scripts/lastwar-phase35-pixel-master.sh; then
  echo "Aucun changement à committer."
else
  git commit -m "lab: stage pixel master UI and vehicle model inventory"
fi
git push origin "$BRANCH"

echo "=== PHASE 35 TERMINEE ==="
echo "UI exacte: frontend/lab/master-assets-v2"
echo "Modèles exportés localement: frontend/lab/local-assets/lastwar-vehicle-models-v1"
echo "Inventaire 3D: frontend/lab/master-assets-v2/meta/vehicle-model-inventory.json"
echo "main non modifiée."
