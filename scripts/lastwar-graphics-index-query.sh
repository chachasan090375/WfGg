#!/data/data/com.termux/files/usr/bin/bash
set -Eeuo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
IDX="$ROOT/frontend/lab/master-assets-v2/meta/graphics-master-index-v1.json"
[[ -s "$IDX" ]] || { echo "Index absent: lance scripts/lastwar-graphics-master-index.sh" >&2; exit 1; }
[[ $# -gt 0 ]] || { echo "Usage: $0 <terme> [terme...]" >&2; exit 1; }
Q="$*"
python - "$IDX" "$Q" <<'PY'
from pathlib import Path
import json,sys,re
idx=json.loads(Path(sys.argv[1]).read_text('utf-8')); q=sys.argv[2].lower().strip()
terms=[x for x in re.split(r'\s+',q) if x]
def hit(s):
    s=str(s).lower();return all(t in s for t in terms)
rows=[]
for b in idx.get('bundles',[]):
    blob=' '.join([str(b.get('bundleId','')),b.get('logicalName',''),b.get('aliasName','')]+b.get('assetPaths',[]))
    if hit(blob):rows.append(('bundle',b))
for d in idx.get('discoveries',[]):
    blob=' '.join([d.get('file',''),str(d.get('format',''))]+d.get('names',[])+d.get('assetPaths',[])+[str(x) for x in d.get('bundleIds',[])])
    if hit(blob):rows.append(('discovery',d))
print(f"GRAPHICS_INDEX_QUERY query={q!r} matches={len(rows)}")
for typ,x in rows[:100]:
    if typ=='bundle':
        print(f"BUNDLE {x['bundleId']} logical={x.get('logicalName','')} alias={x.get('aliasName','')}")
        for loc in x.get('locations',[])[:4]:
            print(f"  LOCATION kind={loc.get('kind')} fragment={loc.get('fragment')} group={loc.get('group')} offset={loc.get('offset')} bytes={loc.get('intervalBytes')}")
        if x.get('dependencyBundleIds'):print('  DEPS',' '.join(map(str,x['dependencyBundleIds'])))
        if x.get('dependentBundleIds'):print('  USED_BY',' '.join(map(str,x['dependentBundleIds'][:60])))
        for p in x.get('assetPaths',[])[:60]:print('  ASSET',p)
    else:
        print(f"DISCOVERY file={x.get('file')} format={x.get('format')} bundles={','.join(map(str,x.get('bundleIds',[])[:60]))}")
        for p in x.get('assetPaths',[])[:30]:print('  ASSET',p)
        for n in x.get('names',[])[:30]:
            if hit(n):print('  NAME',n)
PY
