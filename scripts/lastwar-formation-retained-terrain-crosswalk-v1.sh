#!/data/data/com.termux/files/usr/bin/bash
set -Eeuo pipefail

# WfGg Last War LAB — exact crosswalk of the 8 human-retained Formation textures.
# Read-only against game assets. No historical physical offsets. No inferred graph edge schema.

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BRANCH="portal-auth-lastwar-lab-v1"
META="$ROOT/frontend/lab/master-assets-v2/meta"
HUMAN="$META/formation-visual-human-review-v2-result.json"
GRAPH="$META/formation-ptr-exact-v4.json"
SUMMARY="$META/formation-ptr-exact-v4-summary-v1.json"
REPORT="$HOME/storage/downloads/WFGG_LASTWAR_FORMATION_RETAINED_TERRAIN_CROSSWALK_V1.txt"
JSONOUT="$HOME/storage/downloads/WFGG_LASTWAR_FORMATION_RETAINED_TERRAIN_CROSSWALK_V1.json"
UNITY_VERSION="2019.4.41f1"

fail(){ printf 'ERREUR: %s\n' "$*" >&2; exit 1; }
cd "$ROOT"
[[ "$(git branch --show-current)" == "$BRANCH" ]] || fail "branche LAB incorrecte"
for f in "$HUMAN" "$GRAPH" "$SUMMARY"; do [[ -s "$f" ]] || fail "fichier absent: $f"; done
command -v python >/dev/null 2>&1 || fail "python absent"
python - <<'PYCHK' >/dev/null 2>&1 || fail "UnityPy absent"
import UnityPy
PYCHK
mkdir -p "$(dirname "$REPORT")"

python - "$HUMAN" "$GRAPH" "$SUMMARY" "$REPORT" "$JSONOUT" "$UNITY_VERSION" <<'PY'
from __future__ import annotations
from pathlib import Path
from collections import defaultdict,Counter
import json,re,sys,traceback
import UnityPy

humanp,graphp,sump,reportp,jsonoutp=map(Path,sys.argv[1:6])
unity_version=sys.argv[6]
UnityPy.config.FALLBACK_UNITY_VERSION=unity_version
root=humanp.parents[4]

human=json.loads(humanp.read_text('utf-8'))
graph=json.loads(graphp.read_text('utf-8'))
summary=json.loads(sump.read_text('utf-8'))

# ---------- mandatory structural guards ----------
if not isinstance(graph,dict): raise SystemExit('GRAPH_SCHEMA_ERROR top-level-not-object')
nodes=graph.get('nodes');edges=graph.get('edges')
if not isinstance(nodes,list) or not nodes: raise SystemExit('GRAPH_SCHEMA_ERROR nodes missing/nonempty-list expected')
if not isinstance(edges,list) or not edges: raise SystemExit('GRAPH_SCHEMA_ERROR edges missing/nonempty-list expected')
if len(nodes)!=3209: raise SystemExit(f'GRAPH_COUNT_GUARD nodes expected=3209 actual={len(nodes)}')
if len(edges)!=8386: raise SystemExit(f'GRAPH_COUNT_GUARD edges expected=8386 actual={len(edges)}')
sel=human.get('retainedYes')
if not isinstance(sel,list) or len(sel)!=8: raise SystemExit(f'HUMAN_SELECTION_GUARD expected=8 actual={len(sel) if isinstance(sel,list) else "invalid"}')

node_by_id={}
for n in nodes:
    if not isinstance(n,dict) or 'id' not in n: raise SystemExit('GRAPH_SCHEMA_ERROR node without id')
    k=str(n['id'])
    if k in node_by_id: raise SystemExit(f'GRAPH_SCHEMA_ERROR duplicate node id {k}')
    node_by_id[k]=n
node_ids=set(node_by_id)

# ---------- infer the REAL edge endpoint fields from observed data ----------
def endpoint_id(v):
    if isinstance(v,(str,int)):
        s=str(v)
        return s if s in node_ids else None
    if isinstance(v,dict):
        # common wrappers first, then any scalar field; exactly one node-id match required
        vals=[]
        for k in ('id','nodeId','nodeID','node','objectId','objectID','ref','value'):
            if k in v:
                z=endpoint_id(v[k])
                if z: vals.append(z)
        if not vals:
            for z0 in v.values():
                if isinstance(z0,(str,int)):
                    z=endpoint_id(z0)
                    if z: vals.append(z)
        vals=list(dict.fromkeys(vals))
        return vals[0] if len(vals)==1 else None
    return None

field_stats={}
all_edge_keys=Counter()
for e in edges:
    if not isinstance(e,dict): continue
    for k,v in e.items():
        all_edge_keys[k]+=1
        z=endpoint_id(v)
        if z: field_stats.setdefault(k,Counter())[z]+=1

cands=[]
for k,c in field_stats.items():
    present=all_edge_keys[k]
    hits=sum(c.values())
    if present and hits/present>=0.90:
        cands.append((k,hits,present,hits/present))

source_words=('source','from','src','owner','parent','origin')
target_words=('target','to','dst','dest','ref','child')
def semantic_score(k,words):
    q=k.lower()
    return sum(3 if q==w else 1 for w in words if w in q)

pairs=[]
for a,ah,ap,ar in cands:
    for b,bh,bp,br in cands:
        if a==b: continue
        valid=0;total=0
        for e in edges:
            if not isinstance(e,dict) or a not in e or b not in e: continue
            total+=1
            if endpoint_id(e[a]) and endpoint_id(e[b]): valid+=1
        if total:
            ratio=valid/total
            sem=semantic_score(a,source_words)+semantic_score(b,target_words)-semantic_score(a,target_words)-semantic_score(b,source_words)
            pairs.append((ratio,valid,total,sem,a,b))
pairs.sort(reverse=True)
if not pairs:
    raise SystemExit('EDGE_SCHEMA_UNRESOLVED no endpoint pair validates against node ids')
best=pairs[0]
# Require near-total validation and either semantic direction evidence or only one strong unordered pair.
ratio,valid,total,sem,src_field,dst_field=best
if ratio<0.98 or valid < int(len(edges)*0.95):
    raise SystemExit(f'EDGE_SCHEMA_UNRESOLVED best={src_field}->{dst_field} valid={valid}/{total} ratio={ratio:.6f}')
if sem<0:
    # reverse if names clearly say the opposite
    src_field,dst_field=dst_field,src_field
    sem=-sem
if sem==0:
    # An unordered pair can identify connectivity but NOT direction. Preserve that explicitly.
    direction_proven=False
else:
    direction_proven=True

resolved_edges=[]
for i,e in enumerate(edges):
    s=endpoint_id(e.get(src_field));t=endpoint_id(e.get(dst_field))
    if not s or not t: raise SystemExit(f'EDGE_SCHEMA_VALIDATION_FAILED edge={i}')
    resolved_edges.append((s,t,e))

incoming=defaultdict(list);outgoing=defaultdict(list)
for s,t,e in resolved_edges:
    outgoing[s].append((t,e));incoming[t].append((s,e))
    if not direction_proven:
        outgoing[t].append((s,e));incoming[s].append((t,e))

# ---------- locate exact current bundle files for the 8 chosen textures ----------
# Same cache root used by the visual review. No physical APK offsets are consulted here.
local_roots=[
    root/'frontend/lab/local_assets',
    root/'frontend/lab/master-assets-v2/local_assets',
]
bundle_paths={}
needed_bundles={int(x['bundleId']) for x in sel}
for lr in local_roots:
    if not lr.is_dir(): continue
    for p in lr.rglob('bundle-*.bundle'):
        m=re.fullmatch(r'bundle-(\d+)\.bundle',p.name)
        if m and int(m.group(1)) in needed_bundles:
            bundle_paths.setdefault(int(m.group(1)),p)
missing=needed_bundles-set(bundle_paths)
if missing: raise SystemExit('BUNDLE_CACHE_GUARD missing='+','.join(map(str,sorted(missing))))

# Helpers for exact local serialized PPtr scan.
def sf_name(obj):
    try:return str(obj.assets_file.name)
    except Exception:
        try:return str(obj.assets_file)
        except Exception:return ''

def obj_type(obj):
    try:return str(obj.type.name)
    except Exception:return ''

def obj_name(obj):
    try:return str(obj.peek_name() or '')
    except Exception:
        try:return str(getattr(obj.read(),'m_Name','') or '')
        except Exception:return ''

def walk_pptrs(v,path='$'):
    if isinstance(v,dict):
        if 'm_PathID' in v and 'm_FileID' in v:
            try: yield path,int(v.get('m_FileID') or 0),int(v.get('m_PathID') or 0)
            except Exception: pass
        for k,z in v.items():
            yield from walk_pptrs(z,f'{path}.{k}')
    elif isinstance(v,list):
        for i,z in enumerate(v): yield from walk_pptrs(z,f'{path}[{i}]')

# Load only 4 selected bundles and build local same-serialized-file PPtr adjacency.
envs={};objmeta={};local_in=defaultdict(list);local_scan_stats={}
for bid,p in sorted(bundle_paths.items()):
    env=UnityPy.load(str(p));envs[bid]=env
    objs=list(getattr(env,'objects',[]) or [])
    ok=fail=pp=0
    for o in objs:
        sf=sf_name(o);key=(bid,sf,int(o.path_id))
        objmeta[key]={'bundleId':bid,'serializedFile':sf,'pathID':str(int(o.path_id)),'type':obj_type(o),'name':obj_name(o)}
        try:
            tree=o.read_typetree();ok+=1
            for fieldpath,fileid,pathid in walk_pptrs(tree):
                pp+=1
                # fileID 0 is an exact same-serialized-file PPtr.
                if fileid==0 and pathid!=0:
                    local_in[(bid,sf,pathid)].append({'ownerKey':key,'fieldPath':fieldpath,'fileID':0})
        except Exception:
            fail+=1
    local_scan_stats[str(bid)]={'objects':len(objs),'typetreeRead':ok,'typetreeFailed':fail,'pptrsObserved':pp}

# ---------- exact selection resolution + graph and local crosswalk ----------
interesting={'Material','Mesh','TerrainData','GameObject','Transform','MeshRenderer','SkinnedMeshRenderer','Renderer','SpriteRenderer','Terrain','MonoBehaviour'}

def compact_node(n):
    return {k:n.get(k) for k in ('id','serializedFile','pathID','type','name') if k in n}

def edge_meta(e):
    out={}
    for k,v in e.items():
        if k in (src_field,dst_field): continue
        if isinstance(v,(str,int,float,bool)) or v is None: out[k]=v
    return out

def graph_neighbors(nid):
    direct=[]
    seen=set()
    for other,e in incoming.get(nid,[]):
        sig=('in',other,json.dumps(edge_meta(e),sort_keys=True,default=str))
        if sig in seen:continue
        seen.add(sig);direct.append({'direction':'incoming' if direction_proven else 'connected','node':compact_node(node_by_id[other]),'edge':edge_meta(e)})
    for other,e in outgoing.get(nid,[]):
        sig=('out',other,json.dumps(edge_meta(e),sort_keys=True,default=str))
        if sig in seen:continue
        seen.add(sig);direct.append({'direction':'outgoing' if direction_proven else 'connected','node':compact_node(node_by_id[other]),'edge':edge_meta(e)})
    return direct

def local_referrers(key,depth=1):
    out=[]
    frontier=[(key,0)]
    visited={key}
    while frontier:
        target,d=frontier.pop(0)
        if d>=depth:continue
        for r in local_in.get(target,[]):
            owner=r['ownerKey'];meta=objmeta.get(owner,{})
            out.append({'hop':d+1,'target':{'bundleId':target[0],'serializedFile':target[1],'pathID':str(target[2])},'owner':meta,'fieldPath':r['fieldPath'],'fileID':0})
            if owner not in visited:
                visited.add(owner);frontier.append((owner,d+1))
    return out

results=[]
for x in sel:
    bid=int(x['bundleId']);pid=int(str(x['pathIDExact']));expected_name=str(x['name']);env=envs[bid]
    matches=[o for o in list(getattr(env,'objects',[]) or []) if int(getattr(o,'path_id',0) or 0)==pid]
    if len(matches)!=1:
        results.append({'selection':x,'status':'TARGET_BUNDLE_OBJECT_UNRESOLVED','bundleObjectMatches':len(matches)});continue
    tobj=matches[0];actual_type=obj_type(tobj);actual_name=obj_name(tobj);sf=sf_name(tobj)
    if actual_type!='Texture2D' or actual_name!=expected_name:
        results.append({'selection':x,'status':'TARGET_IDENTITY_MISMATCH','actual':{'type':actual_type,'name':actual_name,'serializedFile':sf}});continue

    # Exact graph node: serializedFile + exact pathID + type + exact name.
    gm=[n for n in nodes if str(n.get('serializedFile',''))==sf and str(n.get('pathID'))==str(pid) and str(n.get('type',''))=='Texture2D' and str(n.get('name',''))==expected_name]
    # If graph's serializedFile naming convention differs, do NOT silently fall back to pathID/name as proof; report candidates separately.
    weak=[n for n in nodes if str(n.get('pathID'))==str(pid) and str(n.get('type',''))=='Texture2D' and str(n.get('name',''))==expected_name]
    graph_status='EXACT_GRAPH_NODE' if len(gm)==1 else 'GRAPH_NODE_NOT_EXACTLY_RESOLVED'
    graph_direct=graph_neighbors(str(gm[0]['id'])) if len(gm)==1 else []

    lkey=(bid,sf,pid)
    lrefs=local_referrers(lkey,2)
    results.append({
        'selection':x,
        'status':'OK',
        'bundleIdentity':{'serializedFile':sf,'pathIDExact':str(pid),'type':actual_type,'name':actual_name},
        'graph':{'status':graph_status,'exactMatches':len(gm),'samePathNameTypeCandidates':[compact_node(n) for n in weak[:10]],'directNeighbors':graph_direct},
        'localSerializedPPtr':{'authority':'exact fileID=0 same-serialized-file only','directAndTwoHop':lrefs},
    })

out={
 'format':'WFGG_LASTWAR_FORMATION_RETAINED_TERRAIN_CROSSWALK_V1',
 'graphSchema':{
   'topLevelKeys':sorted(graph.keys()),'nodeCount':len(nodes),'edgeCount':len(edges),
   'sampleNodeKeys':sorted(nodes[0].keys()) if isinstance(nodes[0],dict) else [],
   'sampleEdgeKeys':sorted(edges[0].keys()) if isinstance(edges[0],dict) else [],
   'endpointCandidates':[{'field':k,'hits':h,'present':p,'ratio':r} for k,h,p,r in cands],
   'resolvedSourceField':src_field,'resolvedTargetField':dst_field,'directionProvenFromFieldSemantics':direction_proven,
   'validatedEdges':valid,'validationTotal':total,'validationRatio':ratio,
 },
 'selectionCount':len(sel),'bundleScanStats':local_scan_stats,'results':results,
 'guardrails':{
   'labBranchOnly':True,'mainUntouched':True,'gameAssetsReadOnly':True,'historicalPhysicalOffsetsUsed':False,
   'edgeSchemaInferredOnlyAfterNodeIdValidation':True,'candidateRelationPromotedToExact':False,
   'localPPtrScope':'fileID=0 same serialized file only','generatedVisuals':False
 }
}
jsonoutp.write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n','utf-8')

lines=[]
lines += ['WfGg Last War — RETAINED FORMATION TERRAIN CROSSWALK V1','']
lines += [f'graphNodes={len(nodes)} graphEdges={len(edges)} selectedTextures={len(sel)}']
lines += [f'edgeSchema={src_field}->{dst_field} directionProven={str(direction_proven).lower()} validation={valid}/{total} ratio={ratio:.6f}']
lines += [f'topLevelKeys={"|".join(sorted(graph.keys()))}',f'sampleNodeKeys={"|".join(sorted(nodes[0].keys()))}',f'sampleEdgeKeys={"|".join(sorted(edges[0].keys()))}','']
for i,r in enumerate(results,1):
    x=r['selection'];lines.append(f'[{i}/8] {x["name"]} bundle={x["bundleId"]} pathIDExact={x["pathIDExact"]}')
    lines.append(f'  status={r["status"]}')
    if r['status']=='OK':
        b=r['bundleIdentity'];lines.append(f'  bundleObject=EXACT serializedFile={b["serializedFile"]} type={b["type"]}')
        g=r['graph'];lines.append(f'  graphStatus={g["status"]} exactMatches={g["exactMatches"]} directNeighbors={len(g["directNeighbors"])}')
        for q in g['directNeighbors']:
            n=q['node'];lines.append(f'    GRAPH {q["direction"]} type={n.get("type","")} name={n.get("name","")} pathID={n.get("pathID","")} sf={n.get("serializedFile","")} edge={json.dumps(q["edge"],ensure_ascii=False,sort_keys=True)}')
        lr=r['localSerializedPPtr']['directAndTwoHop'];lines.append(f'  localSameFilePPtrRefs={len(lr)}')
        for q in lr:
            o=q['owner'];mark='*' if o.get('type') in interesting else '-'
            lines.append(f'    {mark} PPtr hop={q["hop"]} ownerType={o.get("type","")} ownerName={o.get("name","")} ownerPathID={o.get("pathID","")} field={q["fieldPath"]}')
    lines.append('')

# Machine-decidable next strategy, without claiming absent where scope is narrower.
exact_graph=sum(1 for r in results if r.get('status')=='OK' and r.get('graph',{}).get('status')=='EXACT_GRAPH_NODE')
local_direct=sum(sum(1 for q in r.get('localSerializedPPtr',{}).get('directAndTwoHop',[]) if q.get('hop')==1) for r in results)
lines += [f'SUMMARY exactGraphTextures={exact_graph}/8 localDirectSameFileReferrers={local_direct}']
if exact_graph or local_direct:
    lines.append('NEXT inspect exact Material/Terrain/Renderer/scene relations surfaced above; do not infer unlisted cross-file relations.')
else:
    lines.append('NEXT selected textures are not connected by the exact graph/same-file PPtr scopes tested here; trace current bundle dependency fileID mappings or return to runtime composition path.')
lines += ['RULE graph relationships are reported only after endpoint schema validates against all node ids.',
          'RULE local serialized PPtr relationships are exact only for fileID=0 within the same serialized file.',
          'RULE no historical physical offset reused; game assets read-only; main untouched.']
reportp.write_text('\n'.join(lines)+'\n','utf-8')
print('FORMATION_RETAINED_TERRAIN_CROSSWALK_V1_OK',f'graphExact={exact_graph}/8',f'localDirectRefs={local_direct}')
print('REPORT',reportp)
print('JSON',jsonoutp)
PY

echo "=== FORMATION RETAINED TERRAIN CROSSWALK V1 TERMINE ==="
echo "Rapport: $REPORT"
echo "JSON: $JSONOUT"
echo "main inchangé; assets jeu lecture seule."
