#!/data/data/com.termux/files/usr/bin/bash
set -Eeuo pipefail

# WfGg Last War LAB — reusable/cumulative graphics master index.
# Rebuilds stable reconstruction mappings from gameres + installed offset tables
# and folds every JSON discovery in master-assets-v2/meta into a searchable registry.
# Stable keys intentionally avoid device-specific /data/app paths.

PKG="com.fun.lastwar.gp"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BRANCH="portal-auth-lastwar-lab-v1"
GAMERES="$ROOT/frontend/lab/local_assets/lastwar-formation-native-recipe-v1/gameres"
META="$ROOT/frontend/lab/master-assets-v2/meta"
OUT="$META/graphics-master-index-v1.json"
TSV="$META/graphics-master-index-v1.tsv"
REPORT="$HOME/storage/downloads/WFGG_LASTWAR_GRAPHICS_MASTER_INDEX.txt"

fail(){ printf 'ERREUR: %s\n' "$*" >&2; exit 1; }
cd "$ROOT"
[[ "$(git branch --show-current)" == "$BRANCH" ]] || fail "branche LAB incorrecte"
[[ -s "$GAMERES" ]] || fail "gameres local absent"
command -v python >/dev/null 2>&1 || fail "python absent"
mkdir -p "$META" "$(dirname "$REPORT")"

mapfile -t APKS < <(cmd package path "$PKG" 2>/dev/null | sed -n 's/^package://p')

python - "$GAMERES" "$META" "$OUT" "$TSV" "$REPORT" "${APKS[@]}" <<'PY'
from __future__ import annotations
from pathlib import Path
from collections import defaultdict
import json,re,struct,sys,zipfile,hashlib,datetime

gameres=Path(sys.argv[1]); meta=Path(sys.argv[2]); out=Path(sys.argv[3]); tsv=Path(sys.argv[4]); report=Path(sys.argv[5]); apks=[Path(x) for x in sys.argv[6:]]
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
        bid=int(p[0]); b={
          'bundleId':bid,'logicalName':p[1],'declaredBytes':int(p[3]),
          'assetPathIds':[int(x) for x in p[4].split('|') if x],
          'dependencyBundleIds':[int(x) for x in p[5].split('|') if x],
          'groups':[x for x in p[6].split('|') if x],'aliasName':p[7]
        }
        b['assetPaths']=[paths[x] for x in b['assetPathIds'] if x in paths]
        bundles[bid]=b
    except:pass
bylogical={b['logicalName']:b for b in bundles.values()}
byalias={b['aliasName']:b for b in bundles.values() if b['aliasName']}
dependents=defaultdict(list)
for b in bundles.values():
    for d in b['dependencyBundleIds']:dependents[d].append(b['bundleId'])
for b in bundles.values():b['dependentBundleIds']=sorted(dependents.get(b['bundleId'],[]))

# Stable asset -> bundle reconstruction map.
asset_to_bundles=defaultdict(list)
for b in bundles.values():
    for p in b['assetPaths']:asset_to_bundles[p].append(b['bundleId'])
assets=[]
for p,bids in sorted(asset_to_bundles.items(),key=lambda kv:kv[0].lower()):
    assets.append({'path':p,'bundleIds':sorted(set(bids))})

# Installed bundle offset tables. Absolute APK paths are deliberately NOT persisted.
def read7(buf,pos):
    out=0;shift=0
    while True:
        if pos>=len(buf):raise ValueError('7bit EOF')
        x=buf[pos];pos+=1;out|=(x&0x7f)<<shift
        if not x&0x80:return out,pos
        shift+=7

def parse_table(buf):
    pos=0; fc=struct.unpack_from('<I',buf,pos)[0];pos+=4; gs=[]
    for gi in range(fc):
        ln,pos=read7(buf,pos); frag=buf[pos:pos+ln].decode('utf-8','replace');pos+=ln
        payload=struct.unpack_from('<I',buf,pos)[0];pos+=4
        cnt=struct.unpack_from('<I',buf,pos)[0];pos+=4; rows=[]
        for _ in range(cnt):
            ln,pos=read7(buf,pos); name=buf[pos:pos+ln].decode('utf-8','replace');pos+=ln
            off=struct.unpack_from('<Q',buf,pos)[0];pos+=8;rows.append((name,int(off)))
        gs.append({'group':gi,'fragment':frag,'payload':payload,'rows':rows})
    return gs
locations=defaultdict(list); table_sources=[]
for apk in apks:
    try:
        with zipfile.ZipFile(apk) as z:
            ns=set(z.namelist())
            for kind,entry in [('logical','assets/AssetBundles/BundleOffsetTable.bytes'),('alias','assets/AssetBundles/AliasOffsetTable.bytes')]:
                if entry not in ns:continue
                raw=z.read(entry); table_sources.append({'apkFile':apk.name,'entry':entry,'sha256':hashlib.sha256(raw).hexdigest()})
                for g in parse_table(raw):
                    rows=sorted(g['rows'],key=lambda x:x[1])
                    for i,(name,off) in enumerate(rows):
                        nxt=rows[i+1][1] if i+1<len(rows) else None
                        b=(bylogical.get(name) if kind=='logical' else byalias.get(name))
                        if not b:continue
                        loc={'kind':kind,'group':g['group'],'fragment':g['fragment'],'offset':off,'nextOffset':nxt,'intervalBytes':(nxt-off if nxt is not None else None),'rowName':name}
                        locations[b['bundleId']].append(loc)
    except Exception:pass
for bid,b in bundles.items():
    # Deduplicate stable location records.
    seen=set(); locs=[]
    for x in locations.get(bid,[]):
        k=(x['kind'],x['group'],x['fragment'],x['offset'])
        if k not in seen:seen.add(k);locs.append(x)
    b['locations']=locs

# Fold every prior audit/discovery JSON into a generic searchable registry.
# We keep source path + format + selected stable identifiers and strings; raw files remain authoritative.
ignore={out.resolve()}

def collect(obj, acc, depth=0):
    if depth>12:return
    if isinstance(obj,dict):
        for k,v in obj.items():
            kl=str(k).lower()
            if kl in {'bundleid','bundleids'}:
                vals=v if isinstance(v,list) else [v]
                for z in vals:
                    if isinstance(z,int):acc['bundleIds'].add(z)
            if kl in {'assetpath','assetpaths','target','path'}:
                vals=v if isinstance(v,list) else [v]
                for z in vals:
                    if isinstance(z,str) and ('Assets/' in z or z.startswith('Assets/')):acc['assetPaths'].add(z)
            if kl in {'name','classname','script','gameobject','mesh','material','logicalname','aliasname','method','owner'}:
                vals=v if isinstance(v,list) else [v]
                for z in vals:
                    if isinstance(z,str) and 0<len(z)<=240:acc['names'].add(z)
            collect(v,acc,depth+1)
    elif isinstance(obj,list):
        for v in obj[:10000]:collect(v,acc,depth+1)

docs=[]
for f in sorted(meta.glob('*.json')):
    try:
        if f.resolve() in ignore:continue
        obj=json.loads(f.read_text('utf-8',errors='replace'))
    except:continue
    acc={'bundleIds':set(),'assetPaths':set(),'names':set()};collect(obj,acc)
    docs.append({'source':str(f.relative_to(meta.parent.parent.parent.parent)) if len(f.parts)>4 else f.name,
                 'file':f.name,'format':obj.get('format') if isinstance(obj,dict) else None,
                 'bundleIds':sorted(acc['bundleIds']),
                 'assetPaths':sorted(acc['assetPaths'])[:5000],
                 'names':sorted(acc['names'],key=str.lower)[:5000]})

# Search index: normalized token -> stable references. Kept compact by indexing full names/paths, not every word permutation.
def norm(s):return re.sub(r'\s+',' ',str(s).strip()).lower()
search_entries=[]
for b in bundles.values():
    search_entries.append({'type':'bundle','key':str(b['bundleId']),'text':norm(' '.join([b['logicalName'],b['aliasName']]+b['assetPaths']))})
for i,d in enumerate(docs):
    search_entries.append({'type':'discovery','key':d['file'],'text':norm(' '.join(d['names']+d['assetPaths']))})

summary={
 'format':'WFGG_LASTWAR_GRAPHICS_MASTER_INDEX_V1',
 'generatedUtc':datetime.datetime.now(datetime.timezone.utc).isoformat(),
 'source':{'gameresRelative':'frontend/lab/local_assets/lastwar-formation-native-recipe-v1/gameres','gameresSha256':hashlib.sha256(gameres.read_bytes()).hexdigest(),'package': 'com.fun.lastwar.gp','offsetTables':table_sources},
 'counts':{'directories':len(dirs),'paths':len(paths),'bundles':len(bundles),'assets':len(assets),'discoveryDocuments':len(docs),'bundlesWithLocations':sum(bool(b['locations']) for b in bundles.values())},
 'reconstructionContract':{
   'stableBundleKeys':['bundleId','logicalName','aliasName'],
   'stableLocationKeys':['fragment','group','offset','intervalBytes'],
   'assetKey':'Assets/... path',
   'dependencyKeys':['dependencyBundleIds','dependentBundleIds'],
   'note':'Absolute /data/app APK paths are intentionally excluded; resolve current APKs with cmd package path com.fun.lastwar.gp.'
 },
 'bundles':[bundles[k] for k in sorted(bundles)],
 'assets':assets,
 'discoveries':docs,
 'searchEntries':search_entries
}
out.write_text(json.dumps(summary,ensure_ascii=False,separators=(',',':'))+'\n','utf-8')

# Human/grep-friendly durable table.
rows=['assetPath\tbundleId\tlogicalName\taliasName\tfragment\tgroup\toffset\tbytes\tdependencies\tdependents']
for b in summary['bundles']:
    loc=(b['locations'][0] if b['locations'] else {})
    aps=b['assetPaths'] or ['']
    for ap in aps:
        rows.append('\t'.join(map(str,[ap,b['bundleId'],b['logicalName'],b['aliasName'],loc.get('fragment',''),loc.get('group',''),loc.get('offset',''),loc.get('intervalBytes',''),'|'.join(map(str,b['dependencyBundleIds'])),'|'.join(map(str,b['dependentBundleIds']))])))
tsv.write_text('\n'.join(rows)+'\n','utf-8')

lines=['WfGg Last War — GRAPHICS MASTER INDEX','',f"bundles={summary['counts']['bundles']} assets={summary['counts']['assets']} locations={summary['counts']['bundlesWithLocations']} discoveries={summary['counts']['discoveryDocuments']}",f"gameresSha256={summary['source']['gameresSha256']}",'','RECONSTRUCTION KEYS','bundleId + logicalName + aliasName','fragment + group + offset + intervalBytes','Assets/... path','dependencyBundleIds + dependentBundleIds','','Files:',str(out),str(tsv)]
report.write_text('\n'.join(lines)+'\n','utf-8')
print('GRAPHICS_MASTER_INDEX_OK',f"bundles={summary['counts']['bundles']}",f"assets={summary['counts']['assets']}",f"locations={summary['counts']['bundlesWithLocations']}",f"discoveries={summary['counts']['discoveryDocuments']}")
print('GRAPHICS_MASTER_INDEX_JSON',out)
print('GRAPHICS_MASTER_INDEX_TSV',tsv)
print('GRAPHICS_MASTER_INDEX_REPORT',report)
PY

git add "$OUT" "$TSV" scripts/lastwar-graphics-master-index.sh
if ! git diff --cached --quiet; then
  git commit -m "lab: refresh reusable graphics master index"
  git push origin "$BRANCH"
fi

echo "=== GRAPHICS MASTER INDEX TERMINE ==="
echo "JSON: $OUT"
echo "TSV : $TSV"
echo "Rapport: $REPORT"
