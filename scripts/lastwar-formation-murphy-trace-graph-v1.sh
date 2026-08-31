#!/data/data/com.termux/files/usr/bin/bash
set -Eeuo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BRANCH="portal-auth-lastwar-lab-v1"
ATLAS="$ROOT/frontend/lab/master-assets-v2/index/lastwar-code-discovery-atlas-v1.json"
GFX="$ROOT/frontend/lab/master-assets-v2/index/lastwar-graphics-master-index-v1.json"
RUNTIME="$ROOT/frontend/lab/master-assets-v2/meta/current15-runtime-pack-v1.json"
META="$ROOT/frontend/lab/master-assets-v2/meta"
DYN="$META/formation-dynamic-binding-bridge-v1.json"
OUT="$META/formation-murphy-trace-graph-v1.json"
REPORT="$HOME/storage/downloads/WFGG_LASTWAR_FORMATION_MURPHY_TRACE_GRAPH_V1.txt"
fail(){ printf 'ERREUR: %s\n' "$*" >&2; exit 1; }
cd "$ROOT"
[[ "$(git branch --show-current)" == "$BRANCH" ]] || fail "branche LAB incorrecte"
[[ -s "$ATLAS" ]] || fail "atlas code absent: $ATLAS"
[[ -s "$GFX" ]] || fail "index graphique absent: $GFX"
[[ -s "$RUNTIME" ]] || fail "runtime pack absent: $RUNTIME"
command -v python >/dev/null 2>&1 || fail "python absent"
mkdir -p "$(dirname "$OUT")" "$(dirname "$REPORT")"

# Réutilise le pont C# ciblé s'il peut être produit localement. Échec non bloquant :
# le graphe principal fonctionne avec l'atlas déjà construit.
if [[ ! -s "$DYN" && -s "$ROOT/scripts/lastwar-formation-dynamic-binding-bridge-v1.sh" && -s "$HOME/storage/downloads/WFGG_LASTWAR_Assembly-CSharp_recovered.dll" ]]; then
  bash "$ROOT/scripts/lastwar-formation-dynamic-binding-bridge-v1.sh" >/dev/null 2>&1 || true
fi

PYTHONUNBUFFERED=1 python - "$ATLAS" "$GFX" "$RUNTIME" "$META" "$DYN" "$OUT" "$REPORT" <<'PY'
from __future__ import annotations
from pathlib import Path
from collections import defaultdict,deque
import json,re,sys

atlas_p,gfx_p,runtime_p,meta_dir,dyn_p,out_p,report_p=map(Path,sys.argv[1:])

def load(p,default=None):
    try:return json.loads(p.read_text('utf-8'))
    except:return {} if default is None else default

a=load(atlas_p); g=load(gfx_p); runtime=load(runtime_p)
types=a.get('types') or []; methods=a.get('methods') or []
type_by={int(t.get('rid')):t for t in types if t.get('rid') is not None}
method_by={int(m.get('rid')):m for m in methods if m.get('rid') is not None}

def tname(t):
    if not t:return ''
    ns=str(t.get('namespace') or ''); n=str(t.get('name') or '')
    return (ns+'.' if ns else '')+n

def symbol(m):
    return (tname(type_by.get(int(m.get('typeRid') or 0)))+'.' if m.get('typeRid') is not None else '')+str(m.get('name') or '')

def mstrings(m):
    s=m.get('strings') or []
    if isinstance(s,str):return [s]
    return [str(x) for x in s if x is not None]

# -------- Call graph, tolerant of the atlas' historical edge encodings --------
out_adj=defaultdict(set); in_adj=defaultdict(set)
for e in a.get('internalEdges') or []:
    x=y=None
    if isinstance(e,(list,tuple)) and len(e)>=2:
        x,y=e[0],e[1]
    elif isinstance(e,dict):
        for k in ('callerRid','caller','from','src','source'):
            if e.get(k) is not None: x=e[k]; break
        for k in ('calleeRid','callee','to','dst','target'):
            if e.get(k) is not None: y=e[k]; break
    try:
        x=int(x);y=int(y)
    except:continue
    if x in method_by and y in method_by:
        out_adj[x].add(y);in_adj[y].add(x)

ext_by=defaultdict(set)
for ex in a.get('externalCalls') or []:
    if not isinstance(ex,dict):continue
    target=str(ex.get('target') or ex.get('symbol') or ex.get('name') or '')
    callers=ex.get('callerRids')
    if callers is None: callers=[ex.get('callerRid') or ex.get('caller')]
    if not isinstance(callers,(list,tuple,set)):callers=[callers]
    for r in callers:
        try:r=int(r)
        except:continue
        if target:ext_by[r].add(target)

# -------- Exact anchors learned from the Formation work --------
formation_terms=[
 'UIHeroPVPFormationPanel','FormationRT','FormationBg','FormationContent','SlotAreas','HeroInfoBars',
 'Assets/Main/Prefabs/UI/UIHero/LWHero/UIHeroPVPFormationPanel.prefab'
]
murphy_terms=['A_Hero_Audie_01','A_Hero_Audie','Murphy','50006']
try:
    murphy=next((h for h in runtime.get('heroes',[]) if int(h.get('heroId',0))==50006),{})
except: murphy={}
if murphy.get('queueModelPath'):murphy_terms.append(str(murphy['queueModelPath']))

behaviour_patterns={
 'rawimage_texture':('rawimage.set_texture','rawimage::set_texture','rawimage.settexture','rawimage::settexture'),
 'camera_target':('camera.set_targettexture','camera::set_targettexture','set_targettexture'),
 'rendertexture':('rendertexture',),
 'instantiate':('object.instantiate','object::instantiate','instantiate'),
 'asset_load':('loadasset','load_asset','resources.load','assetbundle.load'),
 'lua_boundary':('xlua','luaenv','luaui','lua','customloader'),
}

def exact_hits(m,terms):
    hay='\n'.join(mstrings(m)).lower()
    return [t for t in terms if t.lower() in hay]

def behaviour(rid):
    hay='\n'.join(sorted(ext_by.get(rid,set()))).lower()
    cats=[]
    for c,ps in behaviour_patterns.items():
        if any(p in hay for p in ps):cats.append(c)
    return cats

formation_seeds=[];murphy_seeds=[];rows=[]
for rid,m in method_by.items():
    fh=exact_hits(m,formation_terms); mh=exact_hits(m,murphy_terms); bc=behaviour(rid); sym=symbol(m)
    slow=sym.lower()
    semantic=[]
    if 'formation' in slow or ('hero' in slow and ('pvp' in slow or 'ui' in slow)):semantic.append('formation_symbol')
    if any(x in slow for x in ('hero','model','preview','showhero','vehicle')):semantic.append('hero_symbol')
    if fh:formation_seeds.append(rid)
    if mh:murphy_seeds.append(rid)
    if fh or mh or bc or semantic:
        rows.append({'rid':rid,'symbol':sym,'formationHits':fh,'murphyHits':mh,'behaviours':bc,'semantic':semantic,'externalCalls':sorted(ext_by.get(rid,set()))})

# -------- Distances / paths --------
def multi_dist(starts,adj,maxd=8):
    d={};q=deque()
    for s in starts:
        if s in method_by:d[s]=0;q.append(s)
    while q:
        x=q.popleft()
        if d[x]>=maxd:continue
        for y in adj.get(x,()):
            if y not in d:d[y]=d[x]+1;q.append(y)
    return d

def one_path(starts,target,adj,maxd=8):
    starts=[s for s in starts if s in method_by]
    q=deque(starts);prev={s:None for s in starts};depth={s:0 for s in starts}
    while q:
        x=q.popleft()
        if x==target:
            p=[]
            while x is not None:p.append(x);x=prev[x]
            return list(reversed(p))
        if depth[x]>=maxd:continue
        for y in adj.get(x,()):
            if y not in prev:prev[y]=x;depth[y]=depth[x]+1;q.append(y)
    return []

fd_f=multi_dist(formation_seeds,out_adj);fd_r=multi_dist(formation_seeds,in_adj)
md_f=multi_dist(murphy_seeds,out_adj);md_r=multi_dist(murphy_seeds,in_adj)

# Score bridge candidates by exact evidence + rendering/loading behaviour + graph proximity.
scored=[]
for r in rows:
    rid=r['rid'];score=0;why=[]
    if r['formationHits']:score+=100+10*len(r['formationHits']);why.append('exact Formation string')
    if r['murphyHits']:score+=100+10*len(r['murphyHits']);why.append('exact Murphy/model string')
    weights={'rawimage_texture':55,'camera_target':55,'rendertexture':40,'instantiate':35,'asset_load':28,'lua_boundary':24}
    for c in r['behaviours']:score+=weights.get(c,10);why.append(c)
    if 'formation_symbol' in r['semantic']:score+=20;why.append('formation symbol')
    if 'hero_symbol' in r['semantic']:score+=10;why.append('hero/model symbol')
    fdist=min(fd_f.get(rid,99),fd_r.get(rid,99))
    mdist=min(md_f.get(rid,99),md_r.get(rid,99))
    if fdist<99:score+=max(0,30-4*fdist);why.append(f'Formation graph d={fdist}')
    if mdist<99:score+=max(0,30-4*mdist);why.append(f'Murphy graph d={mdist}')
    if score:
        x=dict(r);x.update(score=score,formationDistance=None if fdist==99 else fdist,murphyDistance=None if mdist==99 else mdist,why=why)
        scored.append(x)
scored.sort(key=lambda x:(-x['score'],x['symbol']))

# Compact shortest call paths from exact Formation anchors to high-value behaviour methods.
paths=[]
for cand in scored[:80]:
    rid=cand['rid']
    if rid in formation_seeds:continue
    p=one_path(formation_seeds,rid,out_adj,7)
    direction='Formation -> candidate'
    if not p:
        p=one_path(formation_seeds,rid,in_adj,7);direction='candidate -> Formation (reverse traversal)'
    if p:
        paths.append({'direction':direction,'targetRid':rid,'target':cand['symbol'],'score':cand['score'],'rids':p,'symbols':[symbol(method_by[x]) for x in p]})
    if len(paths)>=12:break

# -------- Asset dependency graph --------
bundles=g.get('bundles') or []
bybid={}
dep=defaultdict(set); rev=defaultdict(set)
for b in bundles:
    if not isinstance(b,dict) or b.get('bundleId') is None:continue
    try:bid=int(b['bundleId'])
    except:continue
    bybid[bid]=b
    ids=b.get('dependencyBundleIds') or b.get('dependencies') or []
    if isinstance(ids,dict):ids=list(ids.values())
    for x in ids:
        try:x=int(x)
        except:continue
        dep[bid].add(x);rev[x].add(bid)
# Supplement with stored dependentBundleIds when present.
for bid,b in bybid.items():
    for x in b.get('dependentBundleIds') or []:
        try:x=int(x)
        except:continue
        rev[bid].add(x);dep[x].add(bid)

def bhay(b):
    vals=[b.get('logicalName',''),b.get('aliasName',''),b.get('sourceFile','')]+list(b.get('assetPaths') or [])
    return '\n'.join(map(str,vals)).lower()
murphy_bundles=sorted({bid for bid,b in bybid.items() if any(t.lower() in bhay(b) for t in murphy_terms if len(t)>3)} | {17859,26626,26629,26631,26633,26634})
murphy_bundles=[x for x in murphy_bundles if x in bybid]

def bundle_path(src,dsts,maxd=12):
    dsts=set(dsts);q=deque([src]);prev={src:None}
    while q:
        x=q.popleft()
        if x in dsts and x!=src:
            p=[]
            while x is not None:p.append(x);x=prev[x]
            return list(reversed(p))
        # undirected dependency traceability: who depends on whom is useful in both directions
        for y in dep.get(x,set())|rev.get(x,set()):
            if y not in prev and len(prev)<200000:
                prev[y]=x;q.append(y)
    return []
asset_route=bundle_path(6933,murphy_bundles)

def bdesc(bid):
    b=bybid.get(bid,{})
    return {'bundleId':bid,'logicalName':b.get('logicalName',''),'aliasName':b.get('aliasName',''),'assetPaths':(b.get('assetPaths') or [])[:4]}

# -------- Reuse all previous Formation JSON evidence, no bundle rescans --------
def scalar_matches(obj,needles,path='$',out=None,limit=500):
    if out is None:out=[]
    if len(out)>=limit:return out
    if isinstance(obj,dict):
        for k,v in obj.items():scalar_matches(v,needles,path+'.'+str(k),out,limit)
    elif isinstance(obj,list):
        for i,v in enumerate(obj):scalar_matches(v,needles,f'{path}[{i}]',out,limit)
    elif isinstance(obj,(str,int,float,bool)):
        s=str(obj);low=(path+' '+s).lower()
        hs=[n for n in needles if n.lower() in low]
        if hs:out.append({'path':path,'value':s[:500],'hits':hs})
    return out
meta_evidence=[]
for p in sorted(meta_dir.glob('formation-*.json')):
    if p==out_p:continue
    obj=load(p,default={})
    ms=scalar_matches(obj,formation_terms+murphy_terms+['RawImage','RenderTexture','Camera','targetTexture','ArabicMirror'],limit=120)
    if ms:meta_evidence.append({'file':p.name,'matches':ms[:40]})

dyn=load(dyn_p,default={}) if dyn_p.is_file() else {}
dyn_matches=scalar_matches(dyn,formation_terms+murphy_terms+['XLua','LuaUIFormLogic','CustomLoaderImpl'],limit=120) if dyn else []

# -------- Verdict / next hop --------
exact_both=[x for x in scored if x['formationHits'] and x['murphyHits']]
render_near=[x for x in scored if x['formationDistance'] is not None and any(c in x['behaviours'] for c in ('rawimage_texture','camera_target','rendertexture','instantiate','asset_load'))]
if exact_both:
    verdict='DIRECT_CODE_BRIDGE_CANDIDATE'
    next_action='Inspect the top exact-both method and its immediate callers/callees only.'
elif render_near:
    verdict='CODE_BEHAVIOUR_BRIDGE_CANDIDATES'
    next_action='Inspect only the top rendering/loading methods nearest the Formation anchors; do not scan more bundles.'
elif formation_seeds:
    verdict='FORMATION_CODE_ANCHORS_WITHOUT_RENDER_BRIDGE'
    next_action='Follow callers of the exact Formation string methods until the first Lua/loader boundary, then trace that loaded Lua module.'
else:
    verdict='NO_STATIC_CSHARP_FORMATION_ANCHOR_LIKELY_DYNAMIC_LUA'
    next_action='Trace the XLua loader/package index directly; the asset side is already resolved and further graphics scans are low-value.'

result={
 'format':'WFGG_LASTWAR_FORMATION_MURPHY_TRACE_GRAPH_V1',
 'anchors':{
   'formation':{'bundleId':6933,'gameObject':'FormationRT','panel':'UIHeroPVPFormationPanel','runtimeTextureSerialized':False,'methodSeedRids':formation_seeds},
   'murphy':{'heroId':50006,'name':'Murphy','queueModelPath':murphy.get('queueModelPath'),'rendererMode':murphy.get('rendererMode'),'bundleIds':murphy_bundles,'methodSeedRids':murphy_seeds}
 },
 'assetRoute':[bdesc(x) for x in asset_route],
 'code':{'methodCount':len(method_by),'internalEdgeCount':sum(len(v) for v in out_adj.values()),'formationSeedCount':len(formation_seeds),'murphySeedCount':len(murphy_seeds),'topCandidates':scored[:30],'shortPaths':paths},
 'previousEvidence':meta_evidence,
 'dynamicBindingEvidence':dyn_matches[:80],
 'verdict':verdict,'nextAction':next_action,
 'guardrails':{'labOnly':True,'mainUntouched':True,'noBundleRescan':True,'reuseExistingIndexes':True}
}
out_p.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n','utf-8')

lines=[]
lines.append('FORMATION_MURPHY_TRACE_GRAPH_V1_READY')
lines.append(f"code methods={len(method_by)} edges={sum(len(v) for v in out_adj.values())} formationSeeds={len(formation_seeds)} murphySeeds={len(murphy_seeds)}")
lines.append('--- ASSET TRACE ---')
lines.append('Formation: bundle 6933 / UIHeroPVPFormationPanel / FormationRT(RawImage, texture runtime)')
lines.append(f"Murphy: hero=50006 model={murphy.get('queueModelPath','?')} rendererMode={murphy.get('rendererMode','?')} bundles={','.join(map(str,murphy_bundles)) or 'NONE'}")
if asset_route:
    lines.append('assetRoute='+' -> '.join(str(x) for x in asset_route))
    for x in asset_route:
        b=bybid.get(x,{})
        lines.append(f"  {x}: {b.get('logicalName') or b.get('aliasName') or '-'}")
else:lines.append('assetRoute=NO_SHORT_UNDIRECTED_ROUTE_IN_INDEX')
lines.append('--- EXACT CODE ANCHORS ---')
if formation_seeds:
    for r in formation_seeds[:20]:lines.append(f"FORMATION rid={r} {symbol(method_by[r])} strings={exact_hits(method_by[r],formation_terms)}")
else:lines.append('FORMATION NONE')
if murphy_seeds:
    for r in murphy_seeds[:20]:lines.append(f"MURPHY rid={r} {symbol(method_by[r])} strings={exact_hits(method_by[r],murphy_terms)}")
else:lines.append('MURPHY NONE')
lines.append('--- TOP BRIDGE METHODS ---')
for x in scored[:15]:
    lines.append(f"score={x['score']} rid={x['rid']} fDist={x['formationDistance']} mDist={x['murphyDistance']} {x['symbol']} :: {','.join(x['why'])}")
    for ex in x['externalCalls'][:6]:lines.append('  CALL '+ex)
lines.append('--- SHORTEST CALL PATHS ---')
if not paths:lines.append('NONE')
for p in paths[:10]:lines.append(f"score={p['score']} {p['direction']} :: "+' -> '.join(p['symbols']))
lines.append('--- VERDICT ---')
lines.append(verdict)
lines.append('NEXT='+next_action)
lines.append(f'JSON={out_p}')
text='\n'.join(lines)+'\n'
report_p.write_text(text,'utf-8')
print(text,end='')
PY
