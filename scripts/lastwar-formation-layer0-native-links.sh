#!/data/data/com.termux/files/usr/bin/bash
set -Eeuo pipefail

# WfGg Last War LAB — FORMATION LAYER0 NATIVE LINKS
# Reduces the already-extracted native Formation recipe to the exact UI links
# around FormationContent / FormationBg / FormationRT. No ADB/network/game read.

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BRANCH="portal-auth-lastwar-lab-v1"
SRC="$ROOT/frontend/lab/master-assets-v2/meta/formation-native-recipe-v1.json"
OUT="$ROOT/frontend/lab/master-assets-v2/meta/formation-layer0-native-links-v1.json"
REPORT="$HOME/storage/downloads/WFGG_LASTWAR_FORMATION_LAYER0_NATIVE_LINKS.txt"

fail(){ printf 'ERREUR: %s\n' "$*" >&2; exit 1; }
cd "$ROOT"
[[ "$(git branch --show-current)" == "$BRANCH" ]] || fail "branche LAB incorrecte"
[[ -s "$SRC" ]] || fail "manifest natif absent: $SRC"
command -v python >/dev/null 2>&1 || fail "python absent"
mkdir -p "$(dirname "$OUT")" "$(dirname "$REPORT")"

python - "$SRC" "$OUT" "$REPORT" <<'PY'
from __future__ import annotations
import json,sys,re
from pathlib import Path

src,outp,reportp=map(Path,sys.argv[1:4])
d=json.loads(src.read_text('utf-8'))

TARGET_NAMES={'FormationContent','Bg','FormationBg','FormationRT'}
H=d.get('hierarchy') or []
M=d.get('monoBehaviours') or []

by_pid={x.get('pathId'):x for x in H if x.get('pathId') is not None}
by_go={x.get('gameObjectPathId'):x for x in H if x.get('gameObjectPathId') is not None}
target_nodes=[x for x in H if x.get('name') in TARGET_NAMES]
if not any(x.get('name')=='FormationBg' for x in target_nodes):
    raise SystemExit('FormationBg absent du manifest')
if not any(x.get('name')=='FormationRT' for x in target_nodes):
    raise SystemExit('FormationRT absent du manifest')

target_go_ids={int(x['gameObjectPathId']) for x in target_nodes if x.get('gameObjectPathId') is not None}
target_tr_ids={int(x['pathId']) for x in target_nodes if x.get('pathId') is not None}
target_ids=target_go_ids|target_tr_ids

# Include the immediate parent/children context without dragging the whole 436-node tree.
context_ids=set(target_tr_ids)
for x in target_nodes:
    p=x.get('parent')
    if p not in (None,0): context_ids.add(p)
    for c in x.get('children') or []: context_ids.add(c)
context=[by_pid[i] for i in context_ids if i in by_pid]
context.sort(key=lambda x:(x.get('depth',999),x.get('name','')))

def contains_target(v):
    if isinstance(v,dict):
        # Unity PPtr shape.
        p=v.get('m_PathID')
        if isinstance(p,int) and p in target_ids:return True
        p=v.get('ptrPathId')
        if isinstance(p,int) and p in target_ids:return True
        return any(contains_target(x) for x in v.values())
    if isinstance(v,list):return any(contains_target(x) for x in v)
    return False

def collect_ptrs(v,path=''):
    out=[]
    if isinstance(v,dict):
        if 'm_PathID' in v and isinstance(v.get('m_PathID'),int):
            out.append({'path':path,'fileId':v.get('m_FileID'),'pathId':v.get('m_PathID')})
        elif 'ptrPathId' in v and isinstance(v.get('ptrPathId'),int):
            out.append({'path':path,'pathId':v.get('ptrPathId'),'name':v.get('ptrName')})
        for k,x in v.items():
            if isinstance(x,(dict,list)):
                out.extend(collect_ptrs(x,f'{path}.{k}' if path else str(k)))
    elif isinstance(v,list):
        for i,x in enumerate(v):
            if isinstance(x,(dict,list)):out.extend(collect_ptrs(x,f'{path}[{i}]'))
    return out

def pick_raw_fields(tree):
    if not isinstance(tree,dict):return {}
    keys=('m_Enabled','m_Material','m_Color','m_RaycastTarget','m_Maskable','m_Texture','m_UVRect')
    return {k:tree.get(k) for k in keys if k in tree}

target_monos=[]
linked_monos=[]
for m in M:
    tree=m.get('typetree')
    rec={
        'pathId':m.get('pathId'),
        'gameObject':m.get('gameObject'),
        'script':m.get('script'),
        'fields':pick_raw_fields(tree),
        'pointers':collect_ptrs(tree)[:300],
        'error':m.get('error')
    }
    if m.get('gameObject') in TARGET_NAMES:
        target_monos.append(rec)
    elif contains_target(tree):
        linked_monos.append(rec)

# Keep only serialized strings that can explain the RT/background rendering path.
RX=re.compile(r'formation|render.?texture|uiblur|blur|camera|world|terrain|splat',re.I)
raw=[]
for r in d.get('rawKeywordHits') or []:
    hits=[x for x in (r.get('hits') or []) if RX.search(str(x))]
    if hits:
        raw.append({
            'bundleId':r.get('bundleId'),
            'source':r.get('source'),
            'hits':hits[:250]
        })

# The exact Environment/Build/Formation family is retained separately so it is
# not accidentally confused with the world/RT background path.
family=[]
for b in d.get('nativeFormationFamily') or []:
    family.append({
        'bundleId':b.get('bundleId'),
        'logicalName':b.get('logicalName'),
        'assetPaths':b.get('assetPaths') or []
    })

summary={
  'format':'WFGG_LASTWAR_FORMATION_LAYER0_NATIVE_LINKS_V1',
  'sourceManifest':'formation-native-recipe-v1.json',
  'networkUsed':False,
  'adbUsed':False,
  'generatedArtwork':False,
  'targetNames':sorted(TARGET_NAMES),
  'targetGameObjectPathIds':sorted(target_go_ids),
  'targetTransformPathIds':sorted(target_tr_ids),
  'hierarchyContext':context,
  'targetMonoBehaviours':target_monos,
  'monoBehavioursReferencingTargets':linked_monos,
  'renderingKeywordStrings':raw,
  'nativeBuildFormationFamily':family,
  'classification':{
      'nativeBuildFormationFamily':'separate formation-build/platform asset family; do not assume Layer0 world background',
      'FormationBg':'UI RawImage candidate for Formation background',
      'FormationRT':'UI RawImage candidate for runtime render target'
  },
  'guardrails':{
      'sourceIsExistingNativeRecipeOnly':True,
      'mainUntouched':True,
      'noPreviewMutation':True
  }
}
outp.write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n','utf-8')

lines=[
 'WfGg Last War — FORMATION LAYER0 NATIVE LINKS',
 'REDUCTION DU MANIFEST NATIF EXISTANT — AUCUN NOUVEL ACCES AU JEU',
 '',
 f'hierarchyTargets={len(target_nodes)} context={len(context)}',
 f'targetMonoBehaviours={len(target_monos)} linkedMonoBehaviours={len(linked_monos)}',
 '',
 'TARGET HIERARCHY'
]
for x in context:
    lines.append(f"  depth={x.get('depth')} name={x.get('name')} tr={x.get('pathId')} go={x.get('gameObjectPathId')} parent={x.get('parent')} pos={x.get('localPosition')} scale={x.get('localScale')}")
lines+=['','TARGET MONOBEHAVIOURS']
for m in target_monos:
    lines.append(f"  GO={m['gameObject']} script={m['script']} pathId={m['pathId']}")
    f=m.get('fields') or {}
    for k,v in f.items():lines.append('    '+k+'='+json.dumps(v,ensure_ascii=False))
lines+=['','MONOBEHAVIOURS REFERENCING TARGETS']
for m in linked_monos:
    lines.append(f"  GO={m['gameObject']} script={m['script']} pathId={m['pathId']}")
    for p in m.get('pointers') or []:
        if p.get('pathId') in target_ids:lines.append('    TARGET_PTR '+json.dumps(p,ensure_ascii=False))
if not linked_monos:lines.append('  none')
lines+=['','RENDERING KEYWORD STRINGS']
for r in raw:
    lines.append(f"  bundle={r['bundleId']} source={r['source']}")
    for h in r['hits']:lines.append('    '+str(h)[:500])
reportp.write_text('\n'.join(lines)+'\n','utf-8')

print('FORMATION_LAYER0_NATIVE_LINKS_OK',f'targets={len(target_nodes)}',f'targetMono={len(target_monos)}',f'linkedMono={len(linked_monos)}')
print('FORMATION_LAYER0_NATIVE_LINKS_JSON',outp)
print('FORMATION_LAYER0_NATIVE_LINKS_REPORT',reportp)
PY

git add scripts/lastwar-formation-layer0-native-links.sh "$OUT"
if ! git diff --cached --quiet; then
  git commit -m "lab: reduce Formation Layer0 native links"
  git push origin "$BRANCH"
fi

echo "=== FORMATION LAYER0 NATIVE LINKS TERMINEE ==="
echo "JSON: $OUT"
echo "Rapport: $REPORT"
echo "main non modifiée."
