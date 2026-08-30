#!/data/data/com.termux/files/usr/bin/env python
from __future__ import annotations
from pathlib import Path
import argparse,json,sys

ROOT=Path(__file__).resolve().parents[1]
INDEX=ROOT/'frontend/lab/master-assets-v2/index/lastwar-graphics-master-index-v1.json'

def load():
    if not INDEX.is_file():
        raise SystemExit('Index absent: lancer scripts/lastwar-graphics-master-index-refresh.sh')
    return json.loads(INDEX.read_text('utf-8'))

def show(r):
    print(f"bundleId={r['bundleId']}")
    print(f"logical={r.get('logicalName','')}")
    print(f"alias={r.get('aliasName','')}")
    print(f"declaredBytes={r.get('declaredBytes','')}")
    print('assets:')
    for p in r.get('assetPaths',[]):print('  '+p)
    print('dependencies='+('|'.join(map(str,r.get('dependencyBundleIds',[]))) or '-'))
    print('dependents='+('|'.join(map(str,r.get('dependentBundleIds',[]))) or '-'))
    p=r.get('preferredExtraction')
    if p:
        print('extraction:')
        for k in ('identity','physicalApk','fragmentEntry','group','tableFragment','offset','end','spanBytes','physicalMatchConfidence'):
            if k in p:print(f'  {k}={p[k]}')
    else: print('extraction: unresolved on this installed build')
    ev=r.get('evidenceFiles',[])
    print('evidence='+('|'.join(ev) or '-'))

def main():
    ap=argparse.ArgumentParser(description='Query WfGg Last War graphics master index')
    g=ap.add_mutually_exclusive_group(required=True)
    g.add_argument('--asset',help='exact asset path')
    g.add_argument('--contains',help='substring in asset/logical/alias')
    g.add_argument('--bundle',type=int,help='bundle id')
    g.add_argument('--evidence',help='metadata JSON basename substring')
    args=ap.parse_args(); idx=load(); recs=idx['bundles']; hits=[]
    if args.asset:
        bid=idx['lookup']['assetPathToBundleId'].get(args.asset)
        if bid is not None:hits=[r for r in recs if r['bundleId']==bid]
    elif args.bundle is not None:hits=[r for r in recs if r['bundleId']==args.bundle]
    elif args.contains:
        q=args.contains.lower()
        for r in recs:
            hay=[r.get('logicalName',''),r.get('aliasName',''),*r.get('assetPaths',[])]
            if any(q in str(x).lower() for x in hay):hits.append(r)
    elif args.evidence:
        q=args.evidence.lower();hits=[r for r in recs if any(q in x.lower() for x in r.get('evidenceFiles',[]))]
    if not hits:
        print('NO_MATCH');return 1
    print(f'MATCHES={len(hits)}')
    for i,r in enumerate(hits[:100],1):
        if i>1:print('\n---')
        show(r)
    if len(hits)>100:print(f'\nTRUNCATED={len(hits)-100}')
    return 0

if __name__=='__main__':sys.exit(main())
