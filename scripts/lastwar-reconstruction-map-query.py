#!/data/data/com.termux/files/usr/bin/env python
from pathlib import Path
from collections import deque,defaultdict
import argparse,json,sys

ROOT=Path(__file__).resolve().parents[1]
MAP=ROOT/'frontend/lab/master-assets-v2/index/lastwar-visual-reconstruction-map-v1.json'

def load():
    if not MAP.is_file():
        print('MAP_ABSENT run: bash scripts/lastwar-reconstruction-map-refresh.sh');sys.exit(2)
    return json.loads(MAP.read_text('utf-8'))

def choose_start(a,args):
    nodes={n['id']:n for n in a['nodes']}
    if args.asset:
        nid=a.get('lookup',{}).get('assetPathToNode',{}).get(args.asset)
        return [nid] if nid else []
    if args.bundle is not None:
        nid=a.get('lookup',{}).get('bundleIdToNode',{}).get(str(args.bundle))
        return [nid] if nid else []
    if args.rid is not None:
        nid=a.get('lookup',{}).get('methodRidToNode',{}).get(str(args.rid))
        return [nid] if nid else []
    if args.contains:
        q=args.contains.lower();return [nid for nid,n in nodes.items() if q in (n.get('label','')+' '+str(n.get('assetPath',''))+' '+nid).lower()]
    return []

def main():
    ap=argparse.ArgumentParser(description='Query WfGg Last War visual reconstruction graph')
    g=ap.add_mutually_exclusive_group(required=True)
    g.add_argument('--asset',help='exact asset path')
    g.add_argument('--bundle',type=int)
    g.add_argument('--rid',type=int,help='CLR MethodDef RID')
    g.add_argument('--contains',help='substring in node id/label/path')
    ap.add_argument('--depth',type=int,default=2)
    ap.add_argument('--exact-only',action='store_true')
    ap.add_argument('--recipe',action='store_true',help='summarize visual reconstruction ingredients')
    ap.add_argument('--limit',type=int,default=250)
    args=ap.parse_args();a=load();nodes={n['id']:n for n in a['nodes']};edges=a['edges']
    starts=[x for x in choose_start(a,args) if x in nodes]
    if not starts:print('NO_START_NODE');return 1
    out=defaultdict(list);inc=defaultdict(list)
    for i,e in enumerate(edges):
        if args.exact_only and e.get('confidence')!='exact':continue
        out[e['from']].append((i,e));inc[e['to']].append((i,e))
    seen={x:0 for x in starts};q=deque(starts)
    while q and len(seen)<args.limit:
        cur=q.popleft();d=seen[cur]
        if d>=args.depth:continue
        for _,e in out.get(cur,[])+inc.get(cur,[]):
            nxt=e['to'] if e['from']==cur else e['from']
            if nxt not in seen:
                seen[nxt]=d+1;q.append(nxt)
    selected=set(seen)
    sedges=[e for e in edges if e['from'] in selected and e['to'] in selected and (not args.exact_only or e.get('confidence')=='exact')]
    print(f'STARTS={len(starts)} NODES={len(selected)} EDGES={len(sedges)} depth={args.depth} exactOnly={args.exact_only}')
    for s in starts[:20]:
        n=nodes[s];print(f'START {s} kind={n.get("kind")} label={n.get("label")}')
    if args.recipe:
        kinds=('scene','prefab','material','shader','texture','mesh','mesh-source','animation','anim-controller','timeline','render-target','runtime-symbol','runtime-setting','code-method','bundle','evidence')
        by=defaultdict(list)
        for nid,d in sorted(seen.items(),key=lambda x:(x[1],x[0])):
            n=nodes[nid];k=n.get('kind')
            if k in kinds:by[k].append((d,nid,n))
        print('\n=== RECONSTRUCTION RECIPE ===')
        for k in kinds:
            rows=by.get(k,[])
            if not rows:continue
            print(f'[{k}] count={len(rows)}')
            for d,nid,n in rows[:80]:
                extra=n.get('assetPath') or n.get('logicalName') or ''
                print(f'  d={d} {nid} {n.get("label","")} {extra}')
        candidates=[e for e in sedges if e.get('confidence')!='exact']
        if candidates:
            print('\n[CANDIDATE EDGES — VERIFY BEFORE PIXEL RECONSTRUCTION]')
            for e in candidates[:80]:print(f"  {e['from']} --{e['rel']}--> {e['to']} source={e.get('source')} confidence={e.get('confidence')}")
        return 0
    print('\n=== NODES ===')
    for nid,d in sorted(seen.items(),key=lambda x:(x[1],nodes[x[0]].get('kind',''),x[0])):
        n=nodes[nid];print(f'd={d} {nid} kind={n.get("kind")} label={n.get("label")}')
    print('\n=== EDGES ===')
    for e in sedges[:args.limit*3]:print(f"{e['from']} --{e['rel']}[{e.get('confidence')}/{e.get('source')}]--> {e['to']}")
    return 0

if __name__=='__main__':sys.exit(main())
