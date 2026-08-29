#!/data/data/com.termux/files/usr/bin/bash
set -Eeuo pipefail

# WfGg Last War LAB — PHASE 38
# Re-select authentic vehicle scenes with vehicle geometry as the primary signal.
# CODE ONLY. OFFLINE ONLY. No Last War network connection.

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BRANCH="portal-auth-lastwar-lab-v1"
INV="$ROOT/frontend/lab/master-assets-v2/meta/vehicle-model-inventory-v2.json"
OUT="$ROOT/frontend/lab/master-assets-v2/meta/vehicle-scene-selection-v2.json"
REPORT="$HOME/storage/downloads/WFGG_LASTWAR_PHASE38_TRUE_VEHICLE_SELECTION.txt"

fail(){ printf 'ERREUR: %s\n' "$*" >&2; exit 1; }
command -v python >/dev/null 2>&1 || fail "python absent"
[[ -s "$INV" ]] || fail "inventaire Phase 36 absent: $INV"
cd "$ROOT"
[[ "$(git branch --show-current)" == "$BRANCH" ]] || fail "branche active incorrecte"

python - "$INV" "$OUT" "$REPORT" <<'PY'
from pathlib import Path
import json,re,sys

inv=json.loads(Path(sys.argv[1]).read_text(encoding='utf-8'))
outp=Path(sys.argv[2]); reportp=Path(sys.argv[3])

def norm(s):
    return re.sub(r'[^a-z0-9]+','_',str(s or '').lower()).strip('_')

SPECIAL={
  50006:['murphy','audie_murphy'],50007:['williams','rick'],50008:['marshall','nimitz'],
  50009:['kimberly','katyusha'],50010:['stetmann','stetman'],50013:['mcgregor','ewan_mcgregor'],
  50014:['fiona'],50015:['swift','tom'],50016:['tesla'],50017:['dva','d_va'],
  50018:['schuyler','sally_ride'],50019:['carlie','carly'],50020:['morrison'],50021:['lucius'],50022:['adam']
}

VEHICLE_STRONG=(
 'wheel','wheels','tire','tyre','chassis','turret','track','tracks','tank','vehicle','car','truck',
 'missile','rocket','launcher','aircraft','airplane','plane','helicopter','helic','rotor','propeller',
 'cannon','barrel','body_car','carbody','car_body','engine','cockpit','wing','landinggear','landing_gear',
 'frontwheel','rearwheel','wheel_l','wheel_r','履带','车轮'
)
VEHICLE_MEDIUM=('body','gun','weapon','armor','armour','door','hood','bumper','axle','suspension','seat')
EFFECT_TOKENS=(
 'eff_','effect','particle','trail','smoke','glow','bullet','hit','skill','buff','decal','ring','fire','fx_',
 'lightning','explosion','muzzle','yanwu','guiji','hudun','zidan','zhuanwu'
)
HUMANOID_TOKENS=(
 'finger','wrist','elbow','knee','ankle','toes','hip_','shoulder','scapula','spine','neck','head','hand_',
 'soldier','bubing','body_m','root_m','upperarm','forearm','thigh','calf','skeleton','bone'
)

# Names from geometry-bearing fields only. Materials/textures are supporting evidence,
# never enough to call a bundle the vehicle scene.
def geometry_names(b):
    out=[]
    for k in ('gameObjects','meshes','renderers','transforms'):
        for x in b.get(k) or []:
            if isinstance(x,dict): out.extend(str(v) for v in x.values())
            else: out.append(str(x))
    for k in ('meshFilters','skinnedRenderers'):
        for x in b.get(k) or []:
            if isinstance(x,dict): out.extend(str(v) for v in x.values())
    return out

def support_names(b):
    out=[]
    for k in ('animators','animationClips','materials','textures'):
        for x in b.get(k) or []:
            if isinstance(x,dict): out.extend(str(v) for v in x.values())
            else: out.append(str(x))
    return out

def aliases(hero):
    hid=int(hero.get('heroId') or 0)
    vals=[hero.get('name') or '']+(hero.get('aliases') or [])+SPECIAL.get(hid,[])
    return sorted({norm(x) for x in vals if norm(x)},key=len,reverse=True)

def contains_alias(text, aa):
    flat=norm(text).replace('_','')
    return [a for a in aa if a.replace('_','') in flat]

def token_hits(names,tokens):
    joined=' '.join(norm(x) for x in names)
    return sorted({t for t in tokens if norm(t) in joined})

def classify(hero,b):
    aa=aliases(hero)
    geom=geometry_names(b); supp=support_names(b)
    geom_join=' '.join(geom).lower(); supp_join=' '.join(supp).lower(); fname=str(b.get('file') or '').lower()
    mc=len(b.get('meshes') or [])
    rc=len(b.get('renderers') or [])+len(b.get('skinnedRenderers') or [])
    ac=len(b.get('animationClips') or [])+len(b.get('animators') or [])

    strong=token_hits(geom,VEHICLE_STRONG)
    medium=token_hits(geom,VEHICLE_MEDIUM)
    effects=token_hits(geom+supp,EFFECT_TOKENS)
    humanoid=token_hits(geom,HUMANOID_TOKENS)
    geom_alias=[]
    for n in geom:
        hs=contains_alias(n,aa)
        if hs: geom_alias.append((n,max(hs,key=len)))
    file_alias=contains_alias(fname,aa)

    # Vehicle scene score: geometry first, identity second.
    score=0
    score += min(mc,80)*35 + min(rc,120)*28
    if strong: score += 5500 + len(strong)*450
    if len(strong)>=2: score += 2200
    if medium: score += min(len(medium),6)*180
    if geom_alias: score += 1500 + min(len(geom_alias),6)*260
    if file_alias: score += 900
    if ac and (strong or medium): score += min(ac,40)*25

    # Hard penalties for VFX/humanoid bundles that fooled Phase 37.
    effect_ratio=sum(1 for n in geom if any(t in n.lower() for t in EFFECT_TOKENS))/max(1,len(geom))
    human_ratio=sum(1 for n in geom if any(t in n.lower() for t in HUMANOID_TOKENS))/max(1,len(geom))
    if effect_ratio>0.28: score -= 6500
    elif effect_ratio>0.12: score -= 2500
    if human_ratio>0.18: score -= 5000
    elif human_ratio>0.08: score -= 1800
    if not strong: score -= 3500
    if mc==0 or rc==0: score -= 5000

    # Quality gates. A candidate without real vehicle terms cannot be high confidence.
    if strong and mc>0 and rc>0 and effect_ratio<0.18 and human_ratio<0.12:
        if len(strong)>=2 and score>=6500: confidence='high'
        elif score>=4200: confidence='medium'
        else: confidence='low'
    else:
        confidence='low' if score>0 else 'none'

    return {
      'file':b.get('file'),'bytes':b.get('bytes'),'score':score,'confidence':confidence,
      'meshCount':mc,'rendererCount':rc,'animationObjectCount':ac,
      'vehicleStrongTokens':strong,'vehicleMediumTokens':medium,
      'effectTokens':effects,'humanoidTokens':humanoid,
      'effectRatio':round(effect_ratio,4),'humanoidRatio':round(human_ratio,4),
      'fileIdentityAliases':file_alias,
      'geometryIdentityEvidence':[{'name':n,'alias':a} for n,a in geom_alias[:20]],
      'gameObjects':(b.get('gameObjects') or [])[:100],
      'meshes':(b.get('meshes') or [])[:100],
      'meshFilters':(b.get('meshFilters') or [])[:100],
      'renderers':(b.get('renderers') or [])[:100],
      'skinnedRenderers':(b.get('skinnedRenderers') or [])[:100],
      'animators':(b.get('animators') or [])[:60],
      'animationClips':(b.get('animationClips') or [])[:80],
      'materials':(b.get('materials') or [])[:80],
      'textures':(b.get('textures') or [])[:80],
    }

out={
  'format':'WFGG_LASTWAR_TRUE_VEHICLE_SCENE_SELECTION_V2','networkUsed':False,
  'sourceFormat':inv.get('format'),'fallbackUnityVersion':inv.get('fallbackUnityVersion'),'heroes':[]
}
lines=[
 'WfGg Last War LAB — PHASE 38 TRUE VEHICLE SCENE SELECTION',
 'OFFLINE ONLY · vehicle geometry required · VFX/humanoid candidates penalized',
 f"fallbackUnityVersion={inv.get('fallbackUnityVersion')}",'']

for hero in inv.get('heroes') or []:
    ranked=[classify(hero,b) for b in hero.get('bundles') or []]
    ranked.sort(key=lambda x:(x['score'],len(x['vehicleStrongTokens']),x['rendererCount'],x['meshCount']),reverse=True)
    # Only accept candidates that actually contain strong vehicle geometry terms.
    accepted=[x for x in ranked if x['vehicleStrongTokens'] and x['meshCount']>0 and x['rendererCount']>0 and x['score']>0]
    selected=accepted[0] if accepted else None
    conf=selected['confidence'] if selected else 'none'
    row={
      'heroId':hero.get('heroId'),'name':hero.get('name'),'selectionConfidence':conf,
      'selected':selected,'alternates':accepted[1:5],
      'rejectedTop':ranked[:3] if not selected else []
    }
    out['heroes'].append(row)
    lines.append(f"HERO {hero.get('heroId')} {hero.get('name')} confidence={conf}")
    for i,x in enumerate(accepted[:5],1):
        lines.append(
          f"  #{i} score={x['score']} mesh={x['meshCount']} renderer={x['rendererCount']} anim={x['animationObjectCount']} "
          f"strong={','.join(x['vehicleStrongTokens']) or '-'} effectRatio={x['effectRatio']} humanRatio={x['humanoidRatio']} file={x['file']}"
        )
    if not accepted:
        lines.append('  NO_TRUE_VEHICLE_CANDIDATE')
        for x in ranked[:3]:
            lines.append(
              f"  rejected score={x['score']} strong={','.join(x['vehicleStrongTokens']) or '-'} "
              f"effectRatio={x['effectRatio']} humanRatio={x['humanoidRatio']} file={x['file']}"
            )
    lines.append('')

out['selectedCount']=sum(1 for x in out['heroes'] if x['selected'])
out['highConfidenceCount']=sum(1 for x in out['heroes'] if x['selectionConfidence']=='high')
out['mediumOrHighCount']=sum(1 for x in out['heroes'] if x['selectionConfidence'] in ('high','medium'))
out['unresolvedHeroIds']=[x['heroId'] for x in out['heroes'] if not x['selected']]
outp.write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf-8')
lines += [
 f"selectedCount={out['selectedCount']}/15",
 f"highConfidence={out['highConfidenceCount']}/15",
 f"mediumOrHigh={out['mediumOrHighCount']}/15",
 'unresolvedHeroIds='+','.join(map(str,out['unresolvedHeroIds']))
]
reportp.write_text('\n'.join(lines)+'\n',encoding='utf-8')
print('PHASE38_OK',f"selected={out['selectedCount']}/15",f"high={out['highConfidenceCount']}/15",f"mediumOrHigh={out['mediumOrHighCount']}/15",f"unresolved={len(out['unresolvedHeroIds'])}")
PY

git add -f frontend/lab/master-assets-v2/meta/vehicle-scene-selection-v2.json scripts/lastwar-phase38-select-true-vehicle-scenes.sh
if git diff --cached --quiet -- frontend/lab/master-assets-v2/meta/vehicle-scene-selection-v2.json scripts/lastwar-phase38-select-true-vehicle-scenes.sh; then
  echo "Aucun changement à committer."
else
  git commit -m "lab: require true vehicle geometry for scene selection"
fi
git push origin "$BRANCH"

echo "=== PHASE 38 TERMINEE ==="
echo "Rapport: Téléchargements/WFGG_LASTWAR_PHASE38_TRUE_VEHICLE_SELECTION.txt"
echo "Ne lance pas encore la page Escouades."
echo "main non modifiée."
