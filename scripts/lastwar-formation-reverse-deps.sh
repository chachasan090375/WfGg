#!/data/data/com.termux/files/usr/bin/bash
set -Eeuo pipefail

# WfGg Last War LAB — FORMATION REVERSE DEPENDENCY GRAPH
# Uses the already-pulled current gameres catalogue only.
# Goal: find bundles/scenes/configs that instantiate or own the real
# UIHeroPVPFormationPanel (bundle 6933), then climb several reverse levels.

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BRANCH="portal-auth-lastwar-lab-v1"
LOCAL="$ROOT/frontend/lab/local_assets/lastwar-formation-native-recipe-v1"
GAMERES="$LOCAL/gameres"
OUT="$ROOT/frontend/lab/master-assets-v2/meta/formation-reverse-deps-v1.json"
REPORT="$HOME/storage/downloads/WFGG_LASTWAR_FORMATION_REVERSE_DEPS.txt"

fail(){ printf 'ERREUR: %s\n' "$*" >&2; exit 1; }
cd "$ROOT"
[[ "$(git branch --show-current)" == "$BRANCH" ]] || fail "branche LAB incorrecte"
[[ -s "$GAMERES" ]] || fail "gameres local absent; relancer lastwar-formation-native-recipe.sh"
command -v python >/dev/null 2>&1 || fail "python absent"
mkdir -p "$(dirname "$OUT")" "$(dirname "$REPORT")"

python - "$GAMERES" "$OUT" "$REPORT" <<'PY'
from __future__ import annotations
from pathlib import Path
from collections import defaultdict,deque
import json,re,sys

gameres,outp,reportp=map(Path,sys.argv[1:4])
text=gameres.read_text('utf-8',errors='replace')

def section(name):
    m=re.search(rf'^\[{re.escape(name)}\]\s*$',text,re.M)
    if not m:return []
    s=m.end(); n=re.search(r'^\[[^\]]+\]\s*$',text[s:],re.M); e=s+n.start() if n else len(text)
    return [x for x in text[s:e].splitlines() if x.strip()]

dirs={}
for ln in section('Directories'):
    try:i,p=ln.split(',',1);dirs[int(i)]=p
    except:pass
paths={}
for ln in section('Paths'):
    try:pid,did,n=ln.split(',',2); paths[int(pid)]=dirs[int(did)].rstrip('/')+'/'+n
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
          'groups':p[6].split('|') if p[6] else [],'aliasName':p[7]
        }
    except:pass
for b in bundles.values(): b['assetPaths']=[paths.get(i) for i in b['assetPathIds'] if paths.get(i)]

# Resolve target by exact asset path rather than trusting a hard-coded id.
target_path='Assets/Main/Prefabs/UI/UIHero/LWHero/UIHeroPVPFormationPanel.prefab'
targets=[b for b in bundles.values() if target_path in b.get('assetPaths',[])]
if not targets: raise SystemExit('bundle UIHeroPVPFormationPanel introuvable dans gameres')
target=targets[0]; target_id=target['bundleId']

rev=defaultdict(list)
for b in bundles.values():
    for dep in b.get('dependencyBundleIds') or []: rev[dep].append(b['bundleId'])

# Breadth-first reverse graph, depth 5. This is broad enough to expose the
# owning screen/scene/config while remaining deterministic and compact.
max_depth=5
seen={target_id:0}; q=deque([target_id]); edges=[]
while q:
    cur=q.popleft(); d=seen[cur]
    if d>=max_depth: continue
    for parent in rev.get(cur,[]):
        edges.append({'from':parent,'to':cur,'depth':d+1})
        if parent not in seen:
            seen[parent]=d+1; q.append(parent)

RX=re.compile(r'formation|hero|pvp|show|camera|render|scene|world|team|squad|deploy|battle|army|uihero|lwhero',re.I)
rows=[]
for bid,depth in sorted(seen.items(),key=lambda kv:(kv[1],kv[0])):
    b=bundles[bid]
    hay=' '.join([b.get('logicalName','')]+(b.get('assetPaths') or []))
    score=0
    for term,w in [('formation',10),('pvp',8),('uihero',7),('lwhero',7),('camera',6),('render',6),('scene',5),('show',4),('hero',3),('team',2),('squad',2)]:
        if term in hay.lower():score+=w
    if depth==0:score+=100
    rows.append({
      'depth':depth,'score':score,'bundleId':bid,'logicalName':b['logicalName'],
      'declaredBytes':b['declaredBytes'],'groups':b['groups'],'aliasName':b['aliasName'],
      'assetPaths':b['assetPaths'],'directDependencies':b['dependencyBundleIds'],
      'keywordMatch':bool(RX.search(hay))
    })

interesting=[r for r in rows if r['depth']==0 or r['keywordMatch'] or r['score']>0]
interesting.sort(key=lambda r:(r['depth'],-r['score'],r['bundleId']))

# Also capture direct dependencies of the target with names useful for the
# RenderTexture path, because controller assets can live on either side.
direct=[]
for bid in target.get('dependencyBundleIds') or []:
    b=bundles.get(bid)
    if not b:continue
    hay=' '.join([b.get('logicalName','')]+(b.get('assetPaths') or []))
    if RX.search(hay):
        direct.append({'bundleId':bid,'logicalName':b['logicalName'],'declaredBytes':b['declaredBytes'],'assetPaths':b['assetPaths'],'groups':b['groups'],'aliasName':b['aliasName']})

summary={
 'format':'WFGG_LASTWAR_FORMATION_REVERSE_DEPS_V1',
 'networkUsed':False,'adbUsed':False,'generatedArtwork':False,
 'target':target,'reverseDepth':max_depth,
 'reverseNodeCount':len(rows),'reverseEdgeCount':len(edges),
 'edges':edges,'interestingReverseNodes':interesting,
 'interestingDirectDependencies':direct,
 'guardrails':{'gameresOnly':True,'previewUntouched':True,'mainUntouched':True}
}
outp.write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n','utf-8')

lines=[
 'WfGg Last War — FORMATION REVERSE DEPENDENCY GRAPH',
 'CURRENT GAMERES ONLY — NO GAME/ADB/NETWORK READ', '',
 f"targetBundle={target_id} reverseNodes={len(rows)} reverseEdges={len(edges)} depth={max_depth}",
 '', 'INTERESTING REVERSE NODES'
]
for r in interesting:
    lines.append(f"  depth={r['depth']} score={r['score']} bundle={r['bundleId']} bytes={r['declaredBytes']} logical={r['logicalName']}")
    for p in r['assetPaths'][:30]:lines.append('    '+p)
lines+=['','INTERESTING DIRECT DEPENDENCIES']
for r in direct:
    lines.append(f"  bundle={r['bundleId']} bytes={r['declaredBytes']} logical={r['logicalName']}")
    for p in r['assetPaths'][:30]:lines.append('    '+p)
reportp.write_text('\n'.join(lines)+'\n','utf-8')

print('FORMATION_REVERSE_DEPS_OK',f'target={target_id}',f'nodes={len(rows)}',f'edges={len(edges)}',f'interesting={len(interesting)}',f'directInteresting={len(direct)}')
for r in interesting[:25]:
    ap=(r['assetPaths'][0] if r['assetPaths'] else '-')
    print('REVERSE_CANDIDATE',f"depth={r['depth']}",f"score={r['score']}",f"bundle={r['bundleId']}",ap)
print('FORMATION_REVERSE_DEPS_JSON',outp)
print('FORMATION_REVERSE_DEPS_REPORT',reportp)
PY

git add scripts/lastwar-formation-reverse-deps.sh "$OUT"
if ! git diff --cached --quiet; then
  git commit -m "lab: trace Formation reverse dependencies"
  git push origin "$BRANCH"
fi

echo "=== FORMATION REVERSE DEPS TERMINE ==="
echo "JSON: $OUT"
echo "Rapport: $REPORT"
echo "main non modifiée."
