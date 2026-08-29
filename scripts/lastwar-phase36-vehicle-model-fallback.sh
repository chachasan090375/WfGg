#!/data/data/com.termux/files/usr/bin/bash
set -Eeuo pipefail

# WfGg Last War LAB — PHASE 36
# VEHICLE MODEL PARSER WITH EXACT UNITY FALLBACK
# CODE ONLY. OFFLINE ONLY. No Last War network connection.

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BRANCH="portal-auth-lastwar-lab-v1"
UNITY_VERSION="2019.4.41f1"
DL="$HOME/storage/downloads"
TMP="$ROOT/.tmp/lastwar-phase36-models"
DEST="$ROOT/frontend/lab/master-assets-v2/meta/vehicle-model-inventory-v2.json"
LOCAL="$ROOT/frontend/lab/local-assets/lastwar-vehicle-models-v2"

fail(){ printf 'ERREUR: %s\n' "$*" >&2; exit 1; }
command -v python >/dev/null 2>&1 || fail "python absent"
command -v unzip >/dev/null 2>&1 || fail "unzip absent"
cd "$ROOT"
[[ "$(git branch --show-current)" == "$BRANCH" ]] || fail "branche active incorrecte"

PARTS=(
  "$DL/WFGG_LASTWAR_MASTER_ASSETS_PART01.zip"
  "$DL/WFGG_LASTWAR_MASTER_ASSETS_PART02.zip"
  "$DL/WFGG_LASTWAR_MASTER_ASSETS_PART03.zip"
)
for p in "${PARTS[@]}"; do [[ -s "$p" ]] || fail "archive absente: $p"; done

rm -rf "$TMP" "$LOCAL"
mkdir -p "$TMP" "$LOCAL" "$(dirname "$DEST")"
for p in "${PARTS[@]}"; do
  unzip -q -o "$p" 'raw-bundles/models/*' -d "$TMP" || true
done

python - "$TMP/raw-bundles/models" "$DEST" "$LOCAL" "$UNITY_VERSION" <<'PY'
from pathlib import Path
import json, os, re, shutil, sys, traceback

modelroot=Path(sys.argv[1])
reportp=Path(sys.argv[2])
outroot=Path(sys.argv[3])
UNITY_VERSION=sys.argv[4]

try:
    import UnityPy
except Exception as e:
    raise SystemExit(f'UnityPy absent: {e}')

# Critical fix: the raw model bundles contain SerializedFiles whose internal
# version field is blank. This is the same condition solved successfully in
# Phase 30C/30D. The installed build was resolved as Unity 2019.4.41f1.
UnityPy.config.FALLBACK_UNITY_VERSION=UNITY_VERSION

TARGETS={
  50006:('Murphy',['murphy','audie_murphy','a_hero_murphy']),
  50007:('Williams',['williams','rick','a_hero_rick']),
  50008:('Marshall',['marshall','nimitz','a_hero_nimitz']),
  50009:('Kimberly',['kimberly','katyusha','a_hero_katyusha']),
  50010:('Stetmann',['stetmann','stetman','a_hero_stetman']),
  50019:('Carlie',['carlie','carly','a_hero_carly']),
  50021:('Lucius',['lucius','a_hero_lucius']),
  50018:('Schuyler',['schuyler','sally_ride','sallyride','a_hero_sally_ride']),
  50017:('DVA',['dva','d_va','a_hero_dva']),
  50020:('Morrison',['morrison','a_hero_morrison']),
  50013:('McGregor',['mcgregor','ewan_mcgregor','ewanmcgregor','a_hero_ewan_mcgregor']),
  50022:('Adam',['adam','a_hero_adam']),
  50015:('Swift',['swift','tom','a_hero_tom']),
  50016:('Tesla',['tesla','a_hero_tesla']),
  50014:('Fiona',['fiona','a_hero_fiona']),
}

files=sorted(modelroot.glob('*.bundle'))
if not files:
    raise SystemExit(f'aucun bundle modèle dans {modelroot}')

# Load bytes once for candidate ranking; filenames from Phase 33 already carry
# matched hero labels when known, but raw bytes are also searched for aliases.
raw_cache={}
def raw_lower(p):
    if p not in raw_cache:
        try: raw_cache[p]=p.read_bytes().lower()
        except Exception: raw_cache[p]=b''
    return raw_cache[p]

def clean(s):
    return re.sub(r'[^a-z0-9]+','_',str(s or '').lower()).strip('_')

def candidate_score(p, display, aliases):
    name=p.name.lower()
    raw=raw_lower(p)
    score=0
    if display.lower() in name: score+=12000
    for a in aliases:
        al=a.lower()
        if al in name: score+=9000+len(al)
        if al.encode() in raw: score+=3500+len(al)
    # model/prefab semantic hints
    for token in (b'mesh',b'meshrenderer',b'skinnedmeshrenderer',b'animator',b'animationclip',b'prefab'):
        if token in raw: score+=120
    return score

def read_obj(reader):
    try: return reader.read()
    except Exception:
        try: return reader.parse_as_object()
        except Exception: return None

def obj_name(data, fallback=''):
    return str(getattr(data,'m_Name','') or getattr(data,'name','') or fallback or '')

def linked_name(ptr):
    if not ptr: return ''
    try:
        d=ptr.read() if hasattr(ptr,'read') else ptr.deref_parse_as_object()
        return obj_name(d)
    except Exception:
        return ''

def unique(seq):
    out=[]; seen=set()
    for x in seq:
        x=str(x or '')
        if not x or x in seen: continue
        seen.add(x); out.append(x)
    return out

inventory={
  'format':'WFGG_LASTWAR_VEHICLE_MODEL_INVENTORY_V2',
  'networkUsed':False,
  'engine':'Unity',
  'fallbackUnityVersion':UNITY_VERSION,
  'bundleCount':len(files),
  'heroes':[]
}

for hid,(display,aliases) in TARGETS.items():
    ranked=[]
    for p in files:
        s=candidate_score(p,display,aliases)
        if s>0: ranked.append((s,p.stat().st_size,p))
    ranked.sort(key=lambda x:(x[0],x[1]),reverse=True)

    hero={
      'heroId':hid,'name':display,'aliases':aliases,
      'candidateCount':len(ranked),'parsedBundles':0,'parseErrors':0,
      'meshCount':0,'rendererCount':0,'animationClipCount':0,'animatorCount':0,
      'materialCount':0,'textureCount':0,'gameObjectCount':0,
      'bundles':[]
    }

    # Parse enough high-ranking candidates to identify the actual vehicle scene.
    for score,_,p in ranked[:40]:
        item={
          'file':p.name,'bytes':p.stat().st_size,'candidateScore':score,
          'gameObjects':[],'meshes':[],'meshFilters':[],'renderers':[],
          'skinnedRenderers':[],'animators':[],'animationClips':[],
          'materials':[],'textures':[],'transforms':[],'errors':[]
        }
        try:
            UnityPy.config.FALLBACK_UNITY_VERSION=UNITY_VERSION
            env=UnityPy.load(str(p))
            hero['parsedBundles']+=1
            for reader in env.objects:
                typ=getattr(reader.type,'name',str(reader.type))
                if typ not in {
                  'GameObject','Transform','Mesh','MeshFilter','MeshRenderer',
                  'SkinnedMeshRenderer','Renderer','Animator','Animation','AnimationClip',
                  'AnimatorController','Material','Texture2D'
                }:
                    continue
                d=read_obj(reader)
                if d is None: continue
                nm=obj_name(d,typ)
                if typ=='GameObject':
                    item['gameObjects'].append(nm)
                elif typ=='Transform':
                    go=linked_name(getattr(d,'m_GameObject',None))
                    item['transforms'].append(go or nm)
                elif typ=='Mesh':
                    item['meshes'].append(nm)
                elif typ=='MeshFilter':
                    go=linked_name(getattr(d,'m_GameObject',None))
                    mesh=linked_name(getattr(d,'m_Mesh',None))
                    item['meshFilters'].append({'gameObject':go,'mesh':mesh})
                elif typ in ('MeshRenderer','Renderer'):
                    go=linked_name(getattr(d,'m_GameObject',None))
                    item['renderers'].append(go or nm)
                elif typ=='SkinnedMeshRenderer':
                    go=linked_name(getattr(d,'m_GameObject',None))
                    mesh=linked_name(getattr(d,'m_Mesh',None))
                    item['skinnedRenderers'].append({'gameObject':go or nm,'mesh':mesh})
                elif typ=='Animator':
                    go=linked_name(getattr(d,'m_GameObject',None))
                    item['animators'].append(go or nm)
                elif typ=='AnimationClip':
                    item['animationClips'].append(nm)
                elif typ=='Material':
                    item['materials'].append(nm)
                elif typ=='Texture2D':
                    item['textures'].append(nm)

            for key in ('gameObjects','meshes','renderers','animators','animationClips','materials','textures','transforms'):
                item[key]=unique(item[key])

            searchable=' '.join(
                item['gameObjects']+item['meshes']+item['renderers']+
                [x.get('gameObject','')+' '+x.get('mesh','') for x in item['skinnedRenderers']]+
                item['animators']+item['animationClips']+item['materials']+item['textures']
            ).lower()
            semantic=0
            for a in aliases:
                if a.lower() in searchable: semantic=max(semantic,5000+len(a))
            if any(x in searchable for x in ('car','tank','vehicle','chassis','wheel','turret','missile','aircraft','hero_')):
                semantic+=600
            item['semanticScore']=semantic

        except Exception as e:
            hero['parseErrors']+=1
            item['errors'].append(repr(e))

        has_scene=bool(item['meshes'] or item['renderers'] or item['skinnedRenderers'] or item['animationClips'] or item['animators'])
        if has_scene or item['semanticScore'] or item['errors']:
            hero['bundles'].append(item)

    # Prefer actual scene-bearing bundles in report.
    hero['bundles'].sort(key=lambda x:(
        bool(x['meshes'] or x['renderers'] or x['skinnedRenderers']),
        x.get('semanticScore',0),
        len(x['animationClips']),len(x['meshes']),x['candidateScore']
    ),reverse=True)
    hero['bundles']=hero['bundles'][:18]

    for item in hero['bundles']:
        hero['meshCount']+=len(item['meshes'])
        hero['rendererCount']+=len(item['renderers'])+len(item['skinnedRenderers'])
        hero['animationClipCount']+=len(item['animationClips'])
        hero['animatorCount']+=len(item['animators'])
        hero['materialCount']+=len(item['materials'])
        hero['textureCount']+=len(item['textures'])
        hero['gameObjectCount']+=len(item['gameObjects'])

    hero['engineRendered3D']=bool(hero['meshCount'] or hero['rendererCount'])
    hero['hasAnimationData']=bool(hero['animationClipCount'] or hero['animatorCount'])
    inventory['heroes'].append(hero)
    print(
      f"MODEL {hid} {display}: candidates={hero['candidateCount']} parsed={hero['parsedBundles']} "
      f"errors={hero['parseErrors']} meshes={hero['meshCount']} renderers={hero['rendererCount']} "
      f"animClips={hero['animationClipCount']} animators={hero['animatorCount']}"
    )

inventory['engineRendered3D']=any(h['engineRendered3D'] for h in inventory['heroes'])
inventory['animationDataPresent']=any(h['hasAnimationData'] for h in inventory['heroes'])
inventory['heroesWith3D']=[h['heroId'] for h in inventory['heroes'] if h['engineRendered3D']]
inventory['heroesWithAnimation']=[h['heroId'] for h in inventory['heroes'] if h['hasAnimationData']]

reportp.write_text(json.dumps(inventory,ensure_ascii=False,indent=2),encoding='utf-8')
print('PHASE36_OK',
      f"engine3D={inventory['engineRendered3D']}",
      f"animationData={inventory['animationDataPresent']}",
      f"heroes3D={len(inventory['heroesWith3D'])}",
      f"heroesAnim={len(inventory['heroesWithAnimation'])}")
PY

# Keep only parser output in Git. Raw bundles remain outside Git.
cat > "$LOCAL/.gitignore" <<'EOF'
*
!.gitignore
EOF

git add -f frontend/lab/master-assets-v2/meta/vehicle-model-inventory-v2.json scripts/lastwar-phase36-vehicle-model-fallback.sh
if git diff --cached --quiet -- frontend/lab/master-assets-v2/meta/vehicle-model-inventory-v2.json scripts/lastwar-phase36-vehicle-model-fallback.sh; then
  echo "Aucun changement à committer."
else
  git commit -m "lab: parse vehicle models with Unity 2019 fallback"
fi
git push origin "$BRANCH"

echo "=== PHASE 36 TERMINEE ==="
echo "Inventaire corrigé: frontend/lab/master-assets-v2/meta/vehicle-model-inventory-v2.json"
echo "Ne lance pas encore la page Escouades."
echo "main non modifiée."
