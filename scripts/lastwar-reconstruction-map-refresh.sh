#!/data/data/com.termux/files/usr/bin/bash
set -Eeuo pipefail

# WfGg Last War LAB — VISUAL RECONSTRUCTION MAP
# Merges the canonical graphics index, CLR discovery atlas and audit evidence into
# one typed graph. No AssetBundle rescan. No game mutation.

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BRANCH="portal-auth-lastwar-lab-v1"
IDX="$ROOT/frontend/lab/master-assets-v2/index"
META="$ROOT/frontend/lab/master-assets-v2/meta"
GRAPHICS="$IDX/lastwar-graphics-master-index-v1.json"
CODE="$IDX/lastwar-code-discovery-atlas-v1.json"
KNOWN="$IDX/lastwar-code-known-anchors-v1.json"
HISTORY="$IDX/lastwar-graphics-history-v002-0012-v1.json"
OUT="$IDX/lastwar-visual-reconstruction-map-v1.json"
DOT="$IDX/lastwar-visual-reconstruction-formation-v1.dot"
REPORT="$HOME/storage/downloads/WFGG_LASTWAR_VISUAL_RECONSTRUCTION_MAP.txt"

fail(){ printf 'ERREUR: %s\n' "$*" >&2; exit 1; }
cd "$ROOT"
[[ "$(git branch --show-current)" == "$BRANCH" ]] || fail "branche LAB incorrecte"
command -v python >/dev/null 2>&1 || fail "python absent"
[[ -s "$GRAPHICS" ]] || fail "graphics master index absent; run lastwar-graphics-master-index-refresh.sh"
[[ -s "$CODE" ]] || fail "code discovery atlas absent; run lastwar-code-discovery-atlas-refresh.sh"
mkdir -p "$IDX" "$(dirname "$REPORT")"

python - "$GRAPHICS" "$CODE" "$KNOWN" "$HISTORY" "$META" "$OUT" "$DOT" "$REPORT" <<'PY'
from pathlib import Path
from collections import defaultdict,deque,Counter
import json,sys,re,hashlib,time

graphics_p,code_p,known_p,history_p,meta_dir,out_p,dot_p,report_p=map(Path,sys.argv[1:9])
t0=time.time()
graphics=json.loads(graphics_p.read_text('utf-8'))
code=json.loads(code_p.read_text('utf-8'))
known=json.loads(known_p.read_text('utf-8')) if known_p.is_file() else {}
history=json.loads(history_p.read_text('utf-8')) if history_p.is_file() else {}

nodes={}; edges=[]; edge_seen=set(); aliases=defaultdict(set)
def add_node(nid,kind,label=None,**props):
    n=nodes.setdefault(nid,{'id':nid,'kind':kind,'label':label or nid})
    for k,v in props.items():
        if v not in (None,'',[],{}): n[k]=v
    return n
def add_edge(src,dst,rel,source='derived',confidence='candidate',**props):
    if src not in nodes or dst not in nodes:return
    key=(src,dst,rel,source)
    if key in edge_seen:return
    edge_seen.add(key)
    e={'from':src,'to':dst,'rel':rel,'source':source,'confidence':confidence}
    e.update({k:v for k,v in props.items() if v not in (None,'',[],{})})
    edges.append(e)

def ext_kind(path):
    lo=path.lower()
    for ext,kind in [('.prefab','prefab'),('.unity','scene'),('.mat','material'),('.shader','shader'),('.png','texture'),('.jpg','texture'),('.jpeg','texture'),('.tga','texture'),('.psd','texture'),('.exr','texture'),('.fbx','mesh-source'),('.obj','mesh-source'),('.mesh','mesh'),('.anim','animation'),('.controller','anim-controller'),('.playable','timeline'),('.rendertexture','render-target'),('.asset','unity-asset'),('.ogg','audio'),('.wav','audio')]:
        if lo.endswith(ext):return kind
    return 'asset'

# 1) Canonical catalog graph: bundle -> asset, bundle -> dependency.
bundle_by_id={}
for b in graphics.get('bundles',[]):
    bid=b['bundleId']; bn=f'bundle:{bid}'; bundle_by_id[bid]=b
    add_node(bn,'bundle',f'Bundle {bid}',bundleId=bid,logicalName=b.get('logicalName'),aliasName=b.get('aliasName'),declaredBytes=b.get('declaredBytes'),preferredExtraction=b.get('preferredExtraction'),evidenceFiles=b.get('evidenceFiles',[]))
    for ap in b.get('assetPaths',[]):
        an='asset:'+ap
        add_node(an,ext_kind(ap),Path(ap).name,assetPath=ap,bundleId=bid)
        add_edge(bn,an,'contains','gameres','exact')
        add_edge(an,bn,'stored_in','gameres','exact')
        aliases[Path(ap).name.lower()].add(an)
for b in graphics.get('bundles',[]):
    src=f'bundle:{b["bundleId"]}'
    for dep in b.get('dependencyBundleIds',[]):
        dst=f'bundle:{dep}'
        if dst in nodes:add_edge(src,dst,'depends_on','gameres','exact')

# 2) Evidence files -> bundles/assets mentioned by the canonical index.
for ev in graphics.get('evidenceFiles',[]):
    eid='evidence:'+ev.get('basename','unknown')
    add_node(eid,'evidence',ev.get('basename','evidence'),format=ev.get('format'),sha256=ev.get('sha256'))
    for bid in ev.get('bundleIds',[]):
        bn=f'bundle:{bid}'
        if bn in nodes:add_edge(eid,bn,'mentions','audit-index','exact')

# 3) CLR graph: keep every method/type, but detailed strings/external targets stay compact.
type_by_rid={t['rid']:t for t in code.get('types',[])}
method_by_rid={m['rid']:m for m in code.get('methods',[])}
def type_name(t):return ((t.get('namespace')+'.') if t.get('namespace') else '')+t.get('name','')
def method_symbol(m):
    t=type_by_rid.get(m.get('typeRid'))
    return (type_name(t)+'.' if t else '')+m.get('name','')
for t in code.get('types',[]):
    tn=f'ctype:{t["rid"]}'; add_node(tn,'code-type',type_name(t),rid=t['rid'],status=t.get('status'),interest=t.get('interest'))
for m in code.get('methods',[]):
    mn=f'cmethod:{m["rid"]}'; add_node(mn,'code-method',method_symbol(m),rid=m['rid'],status=m.get('status'),score=m.get('score'),distanceToKnown=m.get('d'),tags=m.get('tags',[]),strings=m.get('strings',[]))
    tn=f'ctype:{m.get("typeRid")}'
    if tn in nodes:add_edge(tn,mn,'defines','clr','exact')
for a,b in code.get('internalEdges',[]):
    sa=f'cmethod:{a}'; sb=f'cmethod:{b}'
    if sa in nodes and sb in nodes:add_edge(sa,sb,'calls','clr-il','exact')

# External calls become shared nodes only when graphics/reconstruction relevant.
interesting_ext=re.compile(r'(scene|loadasset|addressable|assetbundle|instantiate|camera|render|shader|material|texture|mesh|animation|animator|playable|timeline|blit|culling)',re.I)
for x in code.get('externalCalls',[]):
    target=x.get('target','')
    if not interesting_ext.search(target):continue
    xid='external:'+target
    add_node(xid,'external-api',target,tags=x.get('tags',[]),classification=x.get('classification'))
    for rid in x.get('callerRids',[]):
        mn=f'cmethod:{rid}'
        if mn in nodes:add_edge(mn,xid,'calls_external','clr-il','exact')

# 4) String/path linkage from CLR to catalog. Exact asset paths are strong; basename/name matches are candidates.
path_lookup=graphics.get('lookup',{}).get('assetPathToBundleId',{})
known_strings=set(known.get('knownRuntimeStrings',[]))
for m in code.get('methods',[]):
    mn=f'cmethod:{m["rid"]}'
    for s in m.get('strings',[]):
        if s in path_lookup:
            an='asset:'+s
            if an in nodes:add_edge(mn,an,'references_asset_path','clr-string','exact')
            continue
        sl=s.strip().lower()
        # Runtime anchors are preserved even if they are not files.
        if s in known_strings or any(k.lower() in sl for k in ('formation','heroshow','camp_','grabcamera','worldcitygrass','formationrt','formationbg')):
            rn='runtime:'+s
            add_node(rn,'runtime-symbol',s)
            add_edge(mn,rn,'uses_runtime_string','clr-string','exact')
        # File basename/path-like string that can be matched uniquely in catalog.
        base=Path(s).name.lower() if ('/' in s or '.' in s) else sl
        hits=aliases.get(base,set())
        if len(hits)==1:
            add_edge(mn,next(iter(hits)),'references_asset_name','clr-string','candidate',literal=s)

# 5) Known runtime reconstruction facts.
def find_method_contains(substr):
    q=substr.lower(); return [f'cmethod:{m["rid"]}' for m in code.get('methods',[]) if q in method_symbol(m).lower()]
for mid in find_method_contains('HeroShowSetting.Update'):
    for s in ('Camp_<level>','GrabCamera'):
        rn='runtime:'+s; add_node(rn,'runtime-symbol',s)
        add_edge(mid,rn,'finds_or_creates','reverse-engineered-runtime','exact')
for mid in find_method_contains('HeroShowSetting.Setting'):
    rn='runtime:URP shadowDistance + SH globals';add_node(rn,'runtime-setting','URP shadowDistance + SH globals')
    add_edge(mid,rn,'configures','reverse-engineered-runtime','exact')
for mid in find_method_contains('WorldCamera.AutoFocus'):
    for s in ('CamZoomFormation','CamZoomFocusFormationRotation'):
        rn='runtime:'+s;add_node(rn,'runtime-setting',s);add_edge(mid,rn,'uses','reverse-engineered-runtime','exact')

# 6) Import selected audit candidate relations without upgrading them to facts.
for jf in sorted(meta_dir.glob('*.json')):
    if jf.name in {out_p.name}:continue
    try:o=json.loads(jf.read_text('utf-8'))
    except:continue
    fmt=str(o.get('format','')) if isinstance(o,dict) else ''
    evid='evidence:'+jf.name
    if evid not in nodes:add_node(evid,'evidence',jf.name,format=fmt)
    if fmt=='WFGG_LASTWAR_HEROSHOW_SCENE_LOADER_AUDIT_V1':
        for c in o.get('catalogCandidates',[])[:300]:
            ap=c.get('assetPath');bid=c.get('bundleId')
            an='asset:'+str(ap)
            if an in nodes:
                add_edge(evid,an,'candidate','audit','candidate',score=c.get('score'))
                # Formation/HeroShow candidate cluster node.
                cn='cluster:Formation-HeroShow';add_node(cn,'cluster','Formation / HeroShow')
                add_edge(cn,an,'candidate_contains','audit-score','candidate',score=c.get('score'))

# 7) Historical authority remains evidence, never silently treated as current exact offsets.
if history:
    hn='history:V002-0012';add_node(hn,'history-checkpoint','Archive maître V002 → incrémental 0012')
    for p,desc in history.get('phaseRegistry',{}).items():
        pn='history-phase:'+str(p);add_node(pn,'history-phase','Phase '+str(p),description=desc);add_edge(hn,pn,'contains','historical-index','exact')

# 8) Derived visual families: connect assets by immediate parent folder, useful for discovering siblings.
family_members=defaultdict(list)
for nid,n in list(nodes.items()):
    if nid.startswith('asset:'):
        ap=n.get('assetPath',''); parent=str(Path(ap).parent)
        if parent and parent!='.': family_members[parent].append(nid)
for parent,members in family_members.items():
    if len(members)<2:continue
    fn='family:'+parent;add_node(fn,'asset-family',parent,memberCount=len(members))
    for an in members:add_edge(fn,an,'groups','path-family','exact')

# Adjacency indexes for fast reconstruction traversals.
outgoing=defaultdict(list);incoming=defaultdict(list)
for i,e in enumerate(edges):outgoing[e['from']].append(i);incoming[e['to']].append(i)

# Formation seed slice for DOT and quick QA.
seed_ids=[]
for nid,n in nodes.items():
    txt=(n.get('label','')+' '+str(n.get('assetPath',''))).lower()
    if any(k in txt for k in ('uiheropvpformationpanel','heroshowblend','formationbg','formationrt','camp_<level>','grabcamera')):seed_ids.append(nid)
seen=set(seed_ids);q=deque((x,0) for x in seed_ids)
while q:
    cur,d=q.popleft()
    if d>=2:continue
    for ei in outgoing.get(cur,[])+incoming.get(cur,[]):
        e=edges[ei];other=e['to'] if e['from']==cur else e['from']
        if other not in seen and len(seen)<450:seen.add(other);q.append((other,d+1))

def safe(s):return str(s).replace('\\','\\\\').replace('"','\\"')
dot=['digraph WFGG_Formation_Reconstruction {','  rankdir=LR;','  node [shape=box,fontname="sans-serif",fontsize=9];']
for nid in sorted(seen):
    n=nodes[nid]; label=safe(n.get('label',nid));kind=n.get('kind','')
    dot.append(f'  "{safe(nid)}" [label="{label}\\n[{safe(kind)}]"];')
for e in edges:
    if e['from'] in seen and e['to'] in seen:
        dot.append(f'  "{safe(e["from"])}" -> "{safe(e["to"])}" [label="{safe(e["rel"])} / {safe(e["confidence"])}"];')
dot.append('}')
dot_p.write_text('\n'.join(dot)+'\n','utf-8')

kind_counts=Counter(n['kind'] for n in nodes.values()); rel_counts=Counter(e['rel'] for e in edges); conf_counts=Counter(e['confidence'] for e in edges)
result={
 'format':'WFGG_LASTWAR_VISUAL_RECONSTRUCTION_MAP_V1',
 'purpose':'Typed graph to reconstruct visual screens from assets, bundles, dependencies, code/runtime links and historical evidence.',
 'generatedSeconds':round(time.time()-t0,3),
 'sources':{'graphicsMasterIndex':graphics_p.name,'codeDiscoveryAtlas':code_p.name,'knownAnchors':known_p.name,'history':history_p.name if history_p.is_file() else None},
 'counts':{'nodes':len(nodes),'edges':len(edges),'nodeKinds':dict(kind_counts),'relations':dict(rel_counts),'confidence':dict(conf_counts)},
 'confidenceSemantics':{
   'exact':'Direct catalog/CLR/runtime evidence.',
   'candidate':'Useful proximity or audit candidate; must be verified before pixel-faithful reconstruction.'
 },
 'sourceSemantics':{
   'gameres':'Canonical catalog containment/dependency.',
   'clr-il':'Compiled code call relation.',
   'clr-string':'Literal string/path relation from code.',
   'reverse-engineered-runtime':'Runtime behavior established by prior IL analysis.',
   'audit':'Prior audit evidence.',
   'path-family':'Sibling grouping only, not a runtime dependency.'
 },
 'nodes':list(nodes.values()),
 'edges':edges,
 'lookup':{
   'assetPathToNode':{n.get('assetPath'):nid for nid,n in nodes.items() if n.get('assetPath')},
   'bundleIdToNode':{str(n.get('bundleId')):nid for nid,n in nodes.items() if n.get('kind')=='bundle'},
   'methodRidToNode':{str(n.get('rid')):nid for nid,n in nodes.items() if n.get('kind')=='code-method'},
   'outgoingEdgeIndexes':dict(outgoing),
   'incomingEdgeIndexes':dict(incoming)
 },
 'reconstructionPolicy':[
   'Start from exact screen/prefab asset when known.',
   'Traverse stored_in/depends_on/contains first.',
   'Prioritize material/texture/mesh/animation/scene nodes from dependency bundles.',
   'Use CLR exact links to identify runtime-created cameras/render targets and scene loaders.',
   'Candidate/path-family edges are discovery hints only and must not be treated as exact visual composition.',
   'Persist newly verified serialized/runtime references as exact edges in a metadata audit, then rebuild this map.'
 ]
}
out_p.write_text(json.dumps(result,ensure_ascii=False,separators=(',',':'))+'\n','utf-8')
report=[
 'WfGg Last War — VISUAL RECONSTRUCTION MAP','',
 f'nodes={len(nodes)} edges={len(edges)} generatedSeconds={result["generatedSeconds"]}',
 'nodeKinds='+json.dumps(dict(kind_counts),ensure_ascii=False),
 'relations='+json.dumps(dict(rel_counts),ensure_ascii=False),
 'confidence='+json.dumps(dict(conf_counts),ensure_ascii=False),
 f'graph={out_p}',f'formationDot={dot_p}','',
 'ENTRY: exact asset -> bundle -> dependency bundles -> visual asset kinds -> CLR/runtime links -> evidence.',
 'RULE: candidate edges are never equivalent to exact edges.'
]
report_p.write_text('\n'.join(report)+'\n','utf-8')
print('LASTWAR_VISUAL_RECONSTRUCTION_MAP_OK',f'nodes={len(nodes)}',f'edges={len(edges)}',f'exact={conf_counts.get("exact",0)}',f'candidate={conf_counts.get("candidate",0)}')
print('LASTWAR_VISUAL_RECONSTRUCTION_MAP_JSON',out_p)
print('LASTWAR_VISUAL_RECONSTRUCTION_MAP_DOT',dot_p)
print('LASTWAR_VISUAL_RECONSTRUCTION_MAP_REPORT',report_p)
PY

git add "$OUT" "$DOT"
if ! git diff --cached --quiet; then
  git commit -m "lab: refresh visual reconstruction map"
fi
git push origin "$BRANCH"
printf '%s\n' '=== VISUAL RECONSTRUCTION MAP TERMINE ===' "JSON: $OUT" "DOT: $DOT" "Rapport: $REPORT"
