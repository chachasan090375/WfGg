#!/data/data/com.termux/files/usr/bin/env python
from pathlib import Path
from collections import defaultdict,deque
import argparse,json,sys
ROOT=Path(__file__).resolve().parents[1]
ATLAS=ROOT/'frontend/lab/master-assets-v2/index/lastwar-code-discovery-atlas-v1.json'

def load():
    if not ATLAS.is_file():
        print('ATLAS_ABSENT run: bash scripts/lastwar-code-discovery-atlas-refresh.sh');sys.exit(2)
    return json.loads(ATLAS.read_text('utf-8'))

def type_map(a):return {x['rid']:x for x in a.get('types',[])}
def symbol_for(a,m,tm=None):
    tm=tm or type_map(a);t=tm.get(m.get('typeRid'))
    if not t:return m['name']
    owner=((t.get('namespace')+'.') if t.get('namespace') else '')+t.get('name','')
    return owner+'.'+m['name']

def show_frontier(r,d_override=None):
    d=r.get('d') if d_override is None else d_override
    print(f"M:{r['rid']} status={r['status']} score={r['score']} distance={d} tags={','.join(r.get('tags',[])) or '-'}")
    print('symbol='+r.get('symbol',''))
    if r.get('strings'):print('strings='+json.dumps(r['strings'],ensure_ascii=False))
    if r.get('externalCalls'):print('externalCalls='+json.dumps(r['externalCalls'],ensure_ascii=False))
    print('callers='+('|'.join(map(str,r.get('callers',[]))) or '-'))
    print('callees='+('|'.join(map(str,r.get('callees',[]))) or '-'))

def main():
    ap=argparse.ArgumentParser(description='Query Last War CLR known/unknown discovery atlas')
    g=ap.add_mutually_exclusive_group(required=True)
    g.add_argument('--symbol',help='substring in type/method/external target')
    g.add_argument('--rid',type=int,help='MethodDef RID')
    g.add_argument('--unknown',action='store_true',help='top unknown frontier')
    g.add_argument('--tag',help='unknown frontier tag, e.g. scene-loader, asset-loader, render-camera')
    g.add_argument('--near',help='unknown methods within <=3 internal-call hops of this symbol substring')
    g.add_argument('--external',help='substring in external MemberRef target')
    ap.add_argument('--limit',type=int,default=40)
    args=ap.parse_args();a=load();front=a.get('frontier',[]);methods=a.get('methods',[]);types=a.get('types',[]);tm=type_map(a)
    out=[];specific_distance={}
    if args.unknown:out=front[:args.limit]
    elif args.tag:
        q=args.tag.lower();out=[r for r in front if q in [x.lower() for x in r.get('tags',[])]][:args.limit]
    elif args.rid:
        out=[r for r in front if r['rid']==args.rid]
        if not out:
            m=next((x for x in methods if x['rid']==args.rid),None)
            if m:
                print(f"M:{m['rid']} status={m['status']} score={m['score']} distance={m.get('d')} tags={','.join(m.get('tags',[])) or '-'}")
                print('symbol='+symbol_for(a,m,tm));return 0
    elif args.symbol:
        q=args.symbol.lower()
        out=[r for r in front if q in r.get('symbol','').lower() or q in json.dumps(r.get('strings',[]),ensure_ascii=False).lower()]
        if not out:
            mt=[m for m in methods if q in symbol_for(a,m,tm).lower()][:args.limit]
            for m in mt:print(f"M:{m['rid']} status={m['status']} score={m['score']} distance={m.get('d')} tags={','.join(m.get('tags',[])) or '-'} {symbol_for(a,m,tm)}")
            tt=[]
            for t in types:
                ft=((t.get('namespace')+'.') if t.get('namespace') else '')+t.get('name','')
                if q in ft.lower():tt.append((t,ft))
            for t,ft in tt[:args.limit]:print(f"T:{t['rid']} status={t['status']} interest={t['interest']} methods={t['methodStart']}-{t['methodEnd']} {ft}")
            return 0 if mt or tt else 1
    elif args.external:
        q=args.external.lower();rows=[x for x in a.get('externalCalls',[]) if q in x.get('target','').lower()][:args.limit]
        for x in rows:print(f"EXTERNAL classification={x['classification']} callers={x['callerCount']} tags={','.join(x.get('tags',[])) or '-'} {x['target']}\ncallerRids={'|'.join(map(str,x.get('callerRids',[])))}")
        return 0 if rows else 1
    elif args.near:
        q=args.near.lower();seed=[m['rid'] for m in methods if q in symbol_for(a,m,tm).lower()]
        if not seed:
            print('ANCHOR_NOT_FOUND');return 1
        adj=defaultdict(set)
        for x,y in a.get('internalEdges',[]):adj[x].add(y);adj[y].add(x)
        dq=deque(seed);specific_distance={r:0 for r in seed}
        while dq:
            x=dq.popleft();d=specific_distance[x]
            if d>=3:continue
            for y in adj.get(x,()):
                if y not in specific_distance:specific_distance[y]=d+1;dq.append(y)
        out=[r for r in front if r['rid'] in specific_distance and specific_distance[r['rid']]>0]
        out.sort(key=lambda r:(specific_distance[r['rid']],-r['score'],r['symbol']));out=out[:args.limit]
    if not out:
        print('NO_MATCH');return 1
    print(f'MATCHES={len(out)}')
    for i,r in enumerate(out):
        if i:print('\n---')
        show_frontier(r,specific_distance.get(r['rid']) if specific_distance else None)
    return 0
if __name__=='__main__':sys.exit(main())
