#!/data/data/com.termux/files/usr/bin/bash
set -Eeuo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BRANCH="portal-auth-lastwar-lab-v1"
GAMERES="$ROOT/frontend/lab/local_assets/lastwar-formation-native-recipe-v1/gameres"
OUT="$ROOT/frontend/lab/master-assets-v2/meta/heroshow-material-dependents-v1.json"
REPORT="$HOME/storage/downloads/WFGG_LASTWAR_HEROSHOW_MATERIAL_DEPENDENTS.txt"
PY="${TMPDIR:-$HOME/.cache}/wfgg-heroshow-material-dependents.py"
TARGET=14169

fail(){ printf 'ERREUR: %s\n' "$*" >&2; exit 1; }
cd "$ROOT"
[[ "$(git branch --show-current)" == "$BRANCH" ]] || fail "branche LAB incorrecte"
[[ -s "$GAMERES" ]] || fail "gameres local absent"
command -v python >/dev/null 2>&1 || fail "python absent"
mkdir -p "$(dirname "$OUT")" "$(dirname "$REPORT")" "$(dirname "$PY")"

cat > "$PY" <<'PYEOF'
from pathlib import Path
import json,re,sys

gameres=Path(sys.argv[1]); outp=Path(sys.argv[2]); reportp=Path(sys.argv[3]); target=int(sys.argv[4])
text=gameres.read_text('utf-8')
def section(name):
    m=re.search(rf'^\[{re.escape(name)}\]\s*$',text,re.M)
    if not m:return []
    s=m.end(); n=re.search(r'^\[[^\]]+\]\s*$',text[s:],re.M); e=s+n.start() if n else len(text)
    return [x for x in text[s:e].splitlines() if x.strip()]
dirs={}
for ln in section('Directories'):
    try:i,p=ln.split(',',1); dirs[int(i)]=p
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
        bid=int(p[0]); bundles[bid]={'bundleId':bid,'logicalName':p[1],'declaredBytes':int(p[3]),'assetPathIds':[int(x) for x in p[4].split('|') if x],'dependencyBundleIds':[int(x) for x in p[5].split('|') if x],'groups':p[6].split('|') if p[6] else [],'aliasName':p[7]}
    except:pass
for b in bundles.values(): b['assetPaths']=[paths.get(x) for x in b['assetPathIds'] if paths.get(x)]

def compact(b):
    return {k:b[k] for k in ('bundleId','logicalName','declaredBytes','dependencyBundleIds','groups','aliasName','assetPaths')}

targetBundle=bundles.get(target)
direct=[b for b in bundles.values() if target in b['dependencyBundleIds']]
second=[]
directIds={b['bundleId'] for b in direct}
for b in bundles.values():
    if any(d in directIds for d in b['dependencyBundleIds']): second.append(b)

noise=re.compile(r'/(sound|audio|localization)/|hero_show_sound|\.wav$|\.mp3$',re.I)
visual_ext=re.compile(r'\.(unity|prefab|fbx|asset|mat|shader|rendertexture|controller)$',re.I)
visual=[]
for b in direct:
    p=[x for x in b['assetPaths'] if not noise.search(x)]
    if not p: continue
    score=0
    for x in p:
        xl=x.lower()
        if xl.endswith('.unity'): score+=1000
        elif xl.endswith('.prefab'): score+=400
        elif xl.endswith('.fbx'): score+=250
        elif xl.endswith('.asset'): score+=160
        elif xl.endswith('.mat'): score+=80
        if any(k in xl for k in ('hero','show','display','formation','garage','hangar','world','scene','camera','terrain','grass','rock','stone','ground','environment')): score+=120
        if '/ui/' in xl: score-=60
    if any(visual_ext.search(x) for x in p): score+=80
    visual.append({'score':score,**compact(b),'nonAudioAssetPaths':p})
visual.sort(key=lambda r:(-r['score'],r['bundleId']))

summary={'format':'WFGG_LASTWAR_HEROSHOW_MATERIAL_DEPENDENTS_V1','targetBundleId':target,'targetBundle':compact(targetBundle) if targetBundle else None,'directDependentCount':len(direct),'secondLevelCount':len(second),'visualDependentCount':len(visual),'visualDependents':visual,'directDependents':[compact(x) for x in direct],'secondLevelParents':[compact(x) for x in second]}
outp.write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n','utf-8')
lines=['WfGg Last War — HEROSHOW MATERIAL DEPENDENTS','',f'target={target} direct={len(direct)} visual={len(visual)} second={len(second)}','']
if targetBundle:
    lines += ['TARGET']+[f'  {p}' for p in targetBundle['assetPaths']]+['']
for r in visual[:60]:
    lines.append(f"VISUAL score={r['score']} bundle={r['bundleId']} bytes={r['declaredBytes']} logical={r['logicalName']}")
    for p in r['nonAudioAssetPaths'][:80]: lines.append('  '+p)
    lines.append('  deps='+','.join(map(str,r['dependencyBundleIds'])))
reportp.write_text('\n'.join(lines)+'\n','utf-8')
print('HEROSHOW_DEPENDENTS_OK',f'target={target}',f'direct={len(direct)}',f'visual={len(visual)}',f'second={len(second)}')
for r in visual[:20]: print('HEROSHOW_VISUAL',f"score={r['score']}",f"bundle={r['bundleId']}",(r['nonAudioAssetPaths'] or [''])[0])
print('HEROSHOW_DEPENDENTS_JSON',outp)
print('HEROSHOW_DEPENDENTS_REPORT',reportp)
PYEOF

python "$PY" "$GAMERES" "$OUT" "$REPORT" "$TARGET"
rm -f "$PY"

git add scripts/lastwar-heroshow-material-dependents.sh "$OUT"
if ! git diff --cached --quiet; then
  git commit -m "lab: trace HeroShow material dependents"
  git push origin "$BRANCH"
fi

echo "=== HEROSHOW MATERIAL DEPENDENTS TERMINE ==="
echo "JSON: $OUT"
echo "Rapport: $REPORT"
echo "Preview inchangee. main non modifiee."
