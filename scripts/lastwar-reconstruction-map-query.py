#!/data/data/com.termux/files/usr/bin/env python
from pathlib import Path
from collections import deque,defaultdict
import argparse,json,sys

ROOT=Path(__file__).resolve().parents[1]
MAP=ROOT/'frontend/lab/master-assets-v2/index/lastwar-visual-reconstruction-map-v1.json'
CERT=ROOT/'frontend/lab/master-assets-v2/index/lastwar-render-certification-v1.json'
POLICY=ROOT/'frontend/lab/master-assets-v2/index/lastwar-render-fidelity-policy-v1.json'

def load_json(p):
    if not p.is_file(): return None
    return json.loads(p.read_text('utf-8'))

def load_map():
    a=load_json(MAP)
    if not a:
        print('MAP_ABSENT run: bash scripts/lastwar-reconstruction-map-refresh.sh');sys.exit(2)
    return a

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

def certificate_for(root):
    c=load_json(CERT) or {}
    return next((x for x in c.get('certificates',[]) if x.get('root')==root),None)

def print_recipe_gate(starts):
    policy=load_json(POLICY) or {}
    ok=[]; blocked=[]
    for root in starts:
        cert=certificate_for(root)
        if cert and cert.get('status')=='CERTIFIED_PIXEL_FAITHFUL' and cert.get('recipeAllowed') is True and cert.get('certifiedRecipe'):
            ok.append(cert)
        else:
            blocked.append((root,cert))
    if blocked:
        print('RENDER_RECIPE_BLOCKED')
        print('targetPolicy='+policy.get('target','PIXEL_FAITHFUL_NO_INVENTION'))
        print('reason=No final recipe is emitted while any render-relevant relationship/value remains unproven.')
        for root,cert in blocked:
            print('\nROOT '+root)
            if not cert:
                print('status=UNCERTIFIED')
                print('missing=No render certificate exists for this exact root.')
                continue
            print('status='+cert.get('status','UNCERTIFIED'))
            print('recipeAllowed='+str(bool(cert.get('recipeAllowed'))).lower())
            for x in cert.get('explicitlyNotProven',[]):print('UNPROVEN '+x)
        print('\nRULE No guessed/default/substitute/heuristic value may be inserted. Candidates and bundle-level dependencies are discovery aids only.')
        return None
    return ok

def print_certified_recipe(certs):
    print('=== CERTIFIED PIXEL-FAITHFUL RENDER RECIPE ===')
    for cert in certs:
        print('\nROOT '+cert['root'])
        print('status=CERTIFIED_PIXEL_FAITHFUL')
        for step in cert.get('certifiedRecipe',[]):
            if isinstance(step,dict):
                print('STEP '+json.dumps(step,ensure_ascii=False,sort_keys=True))
            else: print('STEP '+str(step))
    return 0

def main():
    ap=argparse.ArgumentParser(description='Query WfGg Last War visual reconstruction graph')
    g=ap.add_mutually_exclusive_group(required=True)
    g.add_argument('--asset',help='exact asset path')
    g.add_argument('--bundle',type=int)
    g.add_argument('--rid',type=int,help='CLR MethodDef RID')
    g.add_argument('--contains',help='substring in node id/label/path')
    ap.add_argument('--depth',type=int,default=2)
    ap.add_argument('--exact-only',action='store_true',help='graph exploration: keep edges marked exact by their source; not equivalent to render certification')
    ap.add_argument('--ingredients',action='store_true',help='exploratory ingredient neighborhood; never presented as a render recipe')
    ap.add_argument('--recipe',action='store_true',help='emit recipe ONLY when an exact root has CERTIFIED_PIXEL_FAITHFUL certificate; otherwise refuse')
    ap.add_argument('--limit',type=int,default=250)
    args=ap.parse_args();a=load_map();nodes={n['id']:n for n in a['nodes']};edges=a['edges']
    starts=[x for x in choose_start(a,args) if x in nodes]
    if not starts:print('NO_START_NODE');return 1

    if args.recipe:
        certs=print_recipe_gate(starts)
        if certs is None:return 3
        return print_certified_recipe(certs)

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

    if args.ingredients:
        kinds=('scene','prefab','material','shader','texture','mesh','mesh-source','animation','anim-controller','timeline','render-target','runtime-symbol','runtime-setting','code-method','bundle','evidence')
        by=defaultdict(list)
        for nid,d in sorted(seen.items(),key=lambda x:(x[1],x[0])):
            n=nodes[nid];k=n.get('kind')
            if k in kinds:by[k].append((d,nid,n))
        print('\n=== DISCOVERY INGREDIENTS — NOT A RENDER RECIPE ===')
        print('WARNING Bundle dependency, path family, co-location and candidate edges do not prove per-object visual use.')
        for k in kinds:
            rows=by.get(k,[])
            if not rows:continue
            print(f'[{k}] count={len(rows)}')
            for d,nid,n in rows[:80]:
                extra=n.get('assetPath') or n.get('logicalName') or ''
                print(f'  d={d} {nid} {n.get("label","")} {extra}')
        cand=[e for e in sedges if e.get('confidence')!='exact']
        if cand:
            print('\n[CANDIDATE EDGES — DISCOVERY ONLY]')
            for e in cand[:80]:print(f"  {e['from']} --{e['rel']}--> {e['to']} source={e.get('source')} confidence={e.get('confidence')}")
        return 0

    print('\n=== NODES ===')
    for nid,d in sorted(seen.items(),key=lambda x:(x[1],nodes[x[0]].get('kind',''),x[0])):
        n=nodes[nid];print(f'd={d} {nid} kind={n.get("kind")} label={n.get("label")}')
    print('\n=== EDGES ===')
    for e in sedges[:args.limit*3]:print(f"{e['from']} --{e['rel']}[{e.get('confidence')}/{e.get('source')}]--> {e['to']}")
    return 0

if __name__=='__main__':sys.exit(main())
