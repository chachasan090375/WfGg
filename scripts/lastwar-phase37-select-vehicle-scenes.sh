#!/data/data/com.termux/files/usr/bin/bash
set -Eeuo pipefail

# WfGg Last War LAB — PHASE 37
# Select the authentic vehicle scene/prefab for each active hero from Phase 36.
# CODE ONLY. OFFLINE ONLY. No Last War network connection.

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BRANCH="portal-auth-lastwar-lab-v1"
INV="$ROOT/frontend/lab/master-assets-v2/meta/vehicle-model-inventory-v2.json"
OUT="$ROOT/frontend/lab/master-assets-v2/meta/vehicle-scene-selection.json"
REPORT="$HOME/storage/downloads/WFGG_LASTWAR_PHASE37_VEHICLE_SCENE_SELECTION.txt"

fail(){ printf 'ERREUR: %s\n' "$*" >&2; exit 1; }
command -v python >/dev/null 2>&1 || fail "python absent"
[[ -s "$INV" ]] || fail "inventaire Phase 36 absent: $INV"
cd "$ROOT"
[[ "$(git branch --show-current)" == "$BRANCH" ]] || fail "branche active incorrecte"

python - "$INV" "$OUT" "$REPORT" <<'PY'
from pathlib import Path
import json,re,sys

invp=Path(sys.argv[1]); outp=Path(sys.argv[2]); reportp=Path(sys.argv[3])
inv=json.loads(invp.read_text(encoding='utf-8'))

# Generic Unity names that must not be interpreted as hero identity.
GENERIC={
 'mesh','renderer','meshrenderer','skinnedmeshrenderer','animator','animation','animationclip',
 'material','texture','texture2d','gameobject','transform','root','model','prefab','car','vehicle',
 'body','wheel','wheels','turret','weapon','gun','shadow','lod0','lod1','lod2','default'
}

def norm(s): return re.sub(r'[^a-z0-9]+','_',str(s or '').lower()).strip('_')

def aliases_for(hero):
    vals=[]
    vals.extend(hero.get('aliases') or [])
    vals.append(hero.get('name') or '')
    out=[]
    for a in vals:
        n=norm(a)
        if not n: continue
        out.append(n)
        if n.startswith('a_hero_'): out.append(n[7:])
        if n.startswith('hero_'): out.append(n[5:])
    # Important real/internal aliases already established in the project.
    special={
      50006:['murphy','audie_murphy'],
      50007:['williams','rick'],
      50008:['marshall','nimitz'],
      50009:['kimberly','katyusha'],
      50010:['stetmann','stetman'],
      50013:['mcgregor','ewan_mcgregor'],
      50014:['fiona'],
      50015:['swift','tom'],
      50016:['tesla'],
      50017:['dva','d_va'],
      50018:['schuyler','sally_ride'],
      50019:['carlie','carly'],
      50020:['morrison'],
      50021:['lucius'],
      50022:['adam'],
    }
    out.extend(special.get(int(hero.get('heroId') or 0),[]))
    return sorted({norm(x) for x in out if norm(x) and norm(x) not in GENERIC},key=len,reverse=True)

def flatten_names(bundle):
    out=[]
    for key in ('gameObjects','meshes','renderers','animators','animationClips','materials','textures','transforms'):
        for x in bundle.get(key) or []:
            if isinstance(x,dict):
                out.extend(str(v) for v in x.values())
            else: out.append(str(x))
    for key in ('meshFilters','skinnedRenderers'):
        for x in bundle.get(key) or []:
            if isinstance(x,dict): out.extend(str(v) for v in x.values())
    return out

def token_match(name,alias):
    n=norm(name); a=norm(alias)
    if not n or not a:return False
    if a in n:return True
    # token sequence fallback, e.g. SallyRide vs Sally_Ride
    return a.replace('_','') in n.replace('_','')

def classify(bundle,aliases):
    fields={}
    for key in ('gameObjects','meshes','renderers','animators','animationClips','materials','textures','transforms'):
        vals=bundle.get(key) or []
        names=[]
        for x in vals:
            if isinstance(x,dict): names.extend(str(v) for v in x.values())
            else:names.append(str(x))
        fields[key]=names
    for key in ('meshFilters','skinnedRenderers'):
        names=[]
        for x in bundle.get(key) or []:
            if isinstance(x,dict): names.extend(str(v) for v in x.values())
        fields[key]=names

    weights={
      'gameObjects':800,'transforms':650,'meshes':700,'meshFilters':700,
      'renderers':650,'skinnedRenderers':750,'animators':850,'animationClips':900,
      'materials':420,'textures':320
    }
    score=0; evidence=[]; matched_aliases=set()
    for key,names in fields.items():
        for name in names:
            hits=[a for a in aliases if token_match(name,a)]
            if not hits:continue
            best=max(hits,key=len); matched_aliases.add(best)
            score += weights[key] + min(250,len(best)*12)
            evidence.append({'kind':key,'name':name,'alias':best})

    # Scene-bearing evidence. Hero-specific names plus actual renderable content wins.
    mesh_count=len(bundle.get('meshes') or [])
    renderer_count=len(bundle.get('renderers') or [])+len(bundle.get('skinnedRenderers') or [])
    anim_count=len(bundle.get('animationClips') or [])+len(bundle.get('animators') or [])
    if evidence and mesh_count: score += 1200 + min(mesh_count,40)*20
    if evidence and renderer_count: score += 1400 + min(renderer_count,40)*18
    if evidence and anim_count: score += 900 + min(anim_count,30)*15

    allnames=' '.join(flatten_names(bundle)).lower()
    vehicle_tokens=('wheel','chassis','turret','track','tank','car','vehicle','missile','aircraft','rotor','body')
    vehicle_hits=[x for x in vehicle_tokens if x in allnames]
    if evidence and vehicle_hits: score += 900 + len(vehicle_hits)*90

    # Shared atlas/effect-only bundles are not the scene root.
    if not mesh_count and not renderer_count: score -= 3000
    if evidence and all(e['kind'] in ('materials','textures') for e in evidence): score -= 1500

    return score,evidence,vehicle_hits,mesh_count,renderer_count,anim_count

selection={
  'format':'WFGG_LASTWAR_VEHICLE_SCENE_SELECTION_V1',
  'networkUsed':False,
  'sourceFormat':inv.get('format'),
  'fallbackUnityVersion':inv.get('fallbackUnityVersion'),
  'heroes':[]
}

lines=[]
lines.append('WfGg Last War LAB — PHASE 37 VEHICLE SCENE SELECTION')
lines.append('OFFLINE ONLY · code/data report · no generated artwork')
lines.append(f"fallbackUnityVersion={inv.get('fallbackUnityVersion')}")
lines.append('')

for hero in inv.get('heroes') or []:
    hid=int(hero.get('heroId') or 0); aliases=aliases_for(hero)
    scored=[]
    for b in hero.get('bundles') or []:
        score,evidence,vhits,mc,rc,ac=classify(b,aliases)
        if score>0:
            scored.append({
              'file':b.get('file'),'bytes':b.get('bytes'),'score':score,
              'meshCount':mc,'rendererCount':rc,'animationObjectCount':ac,
              'vehicleTokens':vhits,
              'identityEvidence':evidence[:40],
              'gameObjects':(b.get('gameObjects') or [])[:120],
              'meshes':(b.get('meshes') or [])[:120],
              'meshFilters':(b.get('meshFilters') or [])[:120],
              'renderers':(b.get('renderers') or [])[:120],
              'skinnedRenderers':(b.get('skinnedRenderers') or [])[:120],
              'animators':(b.get('animators') or [])[:80],
              'animationClips':(b.get('animationClips') or [])[:120],
              'materials':(b.get('materials') or [])[:120],
              'textures':(b.get('textures') or [])[:120],
            })
    scored.sort(key=lambda x:(x['score'],x['rendererCount'],x['meshCount'],x['animationObjectCount'],x.get('bytes') or 0),reverse=True)
    top=scored[:5]
    confidence='none'
    if top:
        if len(top)==1: confidence='high' if top[0]['score']>=5000 else 'medium'
        else:
            ratio=top[0]['score']/max(1,top[1]['score'])
            if top[0]['score']>=7000 and ratio>=1.35:confidence='high'
            elif top[0]['score']>=4000:confidence='medium'
            else:confidence='low'
    row={
      'heroId':hid,'name':hero.get('name'),'aliases':aliases,
      'candidateBundleCount':hero.get('candidateCount'),
      'phase36MeshCount':hero.get('meshCount'),
      'phase36RendererCount':hero.get('rendererCount'),
      'phase36AnimationClipCount':hero.get('animationClipCount'),
      'selectionConfidence':confidence,
      'selected':top[0] if top else None,
      'alternates':top[1:5]
    }
    selection['heroes'].append(row)
    lines.append(f"HERO {hid} {hero.get('name')} confidence={confidence} aliases={','.join(aliases)}")
    if top:
        for i,x in enumerate(top,1):
            ev=' | '.join(f"{e['kind']}:{e['name']}~{e['alias']}" for e in x['identityEvidence'][:6])
            lines.append(f"  #{i} score={x['score']} meshes={x['meshCount']} renderers={x['rendererCount']} animObjects={x['animationObjectCount']} file={x['file']}")
            if x['vehicleTokens']:lines.append('     vehicleTokens='+','.join(x['vehicleTokens']))
            if ev:lines.append('     evidence='+ev)
    else:
        lines.append('  NO_IDENTITY_SCENE_SELECTED')
    lines.append('')

selection['selectedCount']=sum(1 for x in selection['heroes'] if x['selected'])
selection['highConfidenceCount']=sum(1 for x in selection['heroes'] if x['selectionConfidence']=='high')
selection['mediumOrHighCount']=sum(1 for x in selection['heroes'] if x['selectionConfidence'] in ('high','medium'))
outp.write_text(json.dumps(selection,ensure_ascii=False,indent=2),encoding='utf-8')
lines.append(f"selectedCount={selection['selectedCount']}/15")
lines.append(f"highConfidence={selection['highConfidenceCount']}/15")
lines.append(f"mediumOrHigh={selection['mediumOrHighCount']}/15")
reportp.write_text('\n'.join(lines)+'\n',encoding='utf-8')
print('PHASE37_OK',f"selected={selection['selectedCount']}/15",f"high={selection['highConfidenceCount']}/15",f"mediumOrHigh={selection['mediumOrHighCount']}/15")
PY

git add -f frontend/lab/master-assets-v2/meta/vehicle-scene-selection.json scripts/lastwar-phase37-select-vehicle-scenes.sh
if git diff --cached --quiet -- frontend/lab/master-assets-v2/meta/vehicle-scene-selection.json scripts/lastwar-phase37-select-vehicle-scenes.sh; then
  echo "Aucun changement à committer."
else
  git commit -m "lab: select authentic Last War vehicle scenes"
fi
git push origin "$BRANCH"

echo "=== PHASE 37 TERMINEE ==="
echo "Rapport court: Téléchargements/WFGG_LASTWAR_PHASE37_VEHICLE_SCENE_SELECTION.txt"
echo "Sélection versionnée: frontend/lab/master-assets-v2/meta/vehicle-scene-selection.json"
echo "Ne lance pas encore la page Escouades."
echo "main non modifiée."
