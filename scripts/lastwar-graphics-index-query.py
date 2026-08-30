#!/data/data/com.termux/files/usr/bin/env python
from __future__ import annotations
from pathlib import Path
import argparse,json,sys

ROOT=Path(__file__).resolve().parents[1]
INDEX=ROOT/'frontend/lab/master-assets-v2/index/lastwar-graphics-master-index-v1.json'
HISTORY=ROOT/'frontend/lab/master-assets-v2/index/lastwar-graphics-history-v002-0012-v1.json'

def load_json(p:Path):
    return json.loads(p.read_text('utf-8')) if p.is_file() else None

def show_current(r):
    print('source=current-installed-index')
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

def history_hits(h,args):
    if not h:return []
    out=[]; a=h.get('historicalAuthority0012',{})
    # World roots/families and 31 hero prefab paths are authoritative named historical entries.
    entries=[]
    form=a.get('formation',{})
    for x in form.get('layer0',{}).get('worldRoots',[]):entries.append({'kind':'world-root',**x})
    for x in form.get('layer0',{}).get('worldFamilies',[]):entries.append({'kind':'world-family',**x})
    for x in a.get('heroModelPaths',[]):entries.append({'kind':'hero-model',**x})
    if args.asset:
        q=args.asset.lower();out=[x for x in entries if str(x.get('assetPath',x.get('path',''))).lower()==q]
    elif args.bundle is not None:
        for x in entries:
            if x.get('bundleId')==args.bundle or args.bundle in x.get('bundleIds',[]):out.append(x)
    elif args.contains:
        q=args.contains.lower()
        for x in entries:
            if q in json.dumps(x,ensure_ascii=False).lower():out.append(x)
        if q in json.dumps(h.get('phaseRegistry',{}),ensure_ascii=False).lower():out.append({'kind':'phase-registry','matches':q})
    elif args.evidence:
        q=args.evidence.lower()
        if q in json.dumps(h,ensure_ascii=False).lower():out.append({'kind':'history-index','match':q})
    return out

def show_history(x,h):
    print('source=history-V002-0012')
    print('historical=true currentOffsetsMustBeReResolved=true')
    for k,v in x.items():
        if isinstance(v,(list,dict)):print(f'{k}='+json.dumps(v,ensure_ascii=False))
        else:print(f'{k}={v}')
    print('historyCoverage='+h.get('coverage',{}).get('latestHistoricalCheckpoint','0012'))

def main():
    ap=argparse.ArgumentParser(description='Query WfGg Last War graphics current + historical index')
    g=ap.add_mutually_exclusive_group(required=True)
    g.add_argument('--asset',help='exact asset path')
    g.add_argument('--contains',help='substring in asset/logical/alias/history')
    g.add_argument('--bundle',type=int,help='bundle id')
    g.add_argument('--evidence',help='metadata/history evidence substring')
    args=ap.parse_args(); idx=load_json(INDEX);hist=load_json(HISTORY)
    current=[]
    if idx:
        recs=idx.get('bundles',[])
        if args.asset:
            bid=idx.get('lookup',{}).get('assetPathToBundleId',{}).get(args.asset)
            if bid is not None:current=[r for r in recs if r['bundleId']==bid]
        elif args.bundle is not None:current=[r for r in recs if r['bundleId']==args.bundle]
        elif args.contains:
            q=args.contains.lower()
            current=[r for r in recs if any(q in str(x).lower() for x in [r.get('logicalName',''),r.get('aliasName',''),*r.get('assetPaths',[])])]
        elif args.evidence:
            q=args.evidence.lower();current=[r for r in recs if any(q in x.lower() for x in r.get('evidenceFiles',[]))]
    hh=history_hits(hist,args)
    total=len(current)+len(hh)
    if not total:
        if not idx:print('WARNING current index absent: run scripts/lastwar-graphics-master-index-refresh.sh')
        print('NO_MATCH');return 1
    print(f'MATCHES={total} current={len(current)} historical={len(hh)}')
    first=True
    for r in current[:100]:
        if not first:print('\n---');first=False
        show_current(r)
    for x in hh[:100]:
        if not first:print('\n---')
        first=False;show_history(x,hist)
    return 0

if __name__=='__main__':sys.exit(main())
