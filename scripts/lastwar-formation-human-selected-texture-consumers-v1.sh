#!/data/data/com.termux/files/usr/bin/bash
set -Eeuo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BRANCH="portal-auth-lastwar-lab-v1"
META="$ROOT/frontend/lab/master-assets-v2/meta"
GRAPH="$META/formation-ptr-exact-v4.json"
SELECT="$META/formation-visual-human-review-v2-result.json"
SUMMARY="$META/formation-ptr-exact-v4-summary-v1.json"
LOCAL="$ROOT/frontend/lab/local_assets/lastwar-formation-ptr-exact-v4/bundles"
OUT="$META/formation-human-selected-texture-consumers-v1.json"
REPORT="$HOME/storage/downloads/WFGG_LASTWAR_FORMATION_HUMAN_SELECTED_TEXTURE_CONSUMERS_V1.txt"
UNITY_VERSION="2019.4.41f1"
MAX_DEPTH=6

fail(){ printf 'ERREUR: %s\n' "$*" >&2; exit 1; }
cd "$ROOT"
[[ "$(git branch --show-current)" == "$BRANCH" ]] || fail "branche LAB incorrecte"
for f in "$GRAPH" "$SELECT" "$SUMMARY"; do [[ -s "$f" ]] || fail "fichier absent: $f"; done
[[ -d "$LOCAL" ]] || fail "cache bundles V4 absent: $LOCAL"
command -v python >/dev/null 2>&1 || fail "python absent"
python - <<'PYCHK' >/dev/null 2>&1 || fail "UnityPy absent"
import UnityPy
PYCHK
mkdir -p "$(dirname "$REPORT")"

python - "$GRAPH" "$SELECT" "$SUMMARY" "$LOCAL" "$OUT" "$REPORT" "$UNITY_VERSION" "$MAX_DEPTH" <<'PY'
from __future__ import annotations
from pathlib import Path
from collections import defaultdict, deque
import json,re,sys,traceback
import UnityPy

graphp,selectp,sump,localp,outp,reportp=map(Path,sys.argv[1:7])
unity_version=sys.argv[7];max_depth=int(sys.argv[8])
UnityPy.config.FALLBACK_UNITY_VERSION=unity_version

g=json.loads(graphp.read_text('utf-8'))
sel=json.loads(selectp.read_text('utf-8'))
sumj=json.loads(sump.read_text('utf-8'))
nodes=g.get('nodes')
edges=g.get('edges')
if not isinstance(nodes,list) or not nodes:
    raise SystemExit(f'GRAPH_SCHEMA_ERROR nodes={type(nodes).__name__} count={len(nodes) if isinstance(nodes,list) else -1}')
if not isinstance(edges,list) or not edges:
    raise SystemExit(f'GRAPH_SCHEMA_ERROR edges={type(edges).__name__} count={len(edges) if isinstance(edges,list) else -1}')
retained=sel.get('retainedYes')
if not isinstance(retained,list) or len(retained)!=8:
    raise SystemExit(f'SELECTION_SCHEMA_ERROR retainedYes={len(retained) if isinstance(retained,list) else -1}')

# ---------- node indices ----------
node_by_id={}
by_file_pid=defaultdict(list)
by_pid=defaultdict(list)
by_name_pid=defaultdict(list)
for n in nodes:
    if not isinstance(n,dict): continue
    nid=n.get('id')
    if nid is not None: node_by_id[str(nid)]=n
    sf=str(n.get('serializedFile') or '')
    try: pid=int(n.get('pathID'))
    except Exception: continue
    by_file_pid[(sf,pid)].append(n)
    by_pid[pid].append(n)
    by_name_pid[(str(n.get('name') or ''),pid)].append(n)

# ---------- endpoint resolver, schema-tolerant but guarded ----------
SOURCE_KEYS=('source','src','from','fromId','sourceId','owner','ownerId','referrer','referrerId','a')
TARGET_KEYS=('target','dst','to','toId','targetId','referenced','referencedId','reference','child','childId','b')

def resolve_scalar(v):
    if v is None:return None
    if isinstance(v,str):
        if v in node_by_id:return v
        return None
    if isinstance(v,dict):
        for k in ('id','nodeId','node','objectId','refId'):
            x=v.get(k)
            if x is not None and str(x) in node_by_id:return str(x)
        sf=v.get('serializedFile') or v.get('file') or v.get('sourceFile')
        pv=v.get('pathID') if 'pathID' in v else v.get('m_PathID')
        if sf is not None and pv is not None:
            try:
                hits=by_file_pid.get((str(sf),int(pv)),[])
                if len(hits)==1:return str(hits[0].get('id'))
            except Exception:pass
    return None

def endpoint_from_keys(e,keys):
    for k in keys:
        if k in e:
            x=resolve_scalar(e.get(k))
            if x:return x,k
    return None,None

def composite_endpoint(e,prefix):
    sf=None;pv=None
    for k in (prefix+'SerializedFile',prefix+'File',prefix+'SourceFile'):
        if k in e: sf=e.get(k);break
    for k in (prefix+'PathID',prefix+'PathId',prefix+'Pid'):
        if k in e: pv=e.get(k);break
    if sf is not None and pv is not None:
        try:
            h=by_file_pid.get((str(sf),int(pv)),[])
            if len(h)==1:return str(h[0].get('id'))
        except Exception:pass
    return None

def discover_pair(e):
    s,sk=endpoint_from_keys(e,SOURCE_KEYS);t,tk=endpoint_from_keys(e,TARGET_KEYS)
    if not s:s=composite_endpoint(e,'source') or composite_endpoint(e,'from') or composite_endpoint(e,'owner')
    if not t:t=composite_endpoint(e,'target') or composite_endpoint(e,'to') or composite_endpoint(e,'referenced')
    if s and t:return s,t,sk,tk,'named'
    # Fallback only when exactly two node ids can be recovered from top-level values.
    found=[]
    for k,v in e.items():
        x=resolve_scalar(v)
        if x and x not in [q[0] for q in found]:found.append((x,k))
    if len(found)==2:
        # Try semantic key order, otherwise do NOT invent direction.
        a,b=found
        ak=a[1].lower();bk=b[1].lower()
        if any(z in ak for z in ('source','from','owner','referrer','src')) and any(z in bk for z in ('target','to','referenced','dst')):
            return a[0],b[0],a[1],b[1],'fallback-semantic'
        if any(z in bk for z in ('source','from','owner','referrer','src')) and any(z in ak for z in ('target','to','referenced','dst')):
            return b[0],a[0],b[1],a[1],'fallback-semantic'
    return None,None,None,None,'unparsed'

def edge_label(e):
    vals=[]
    for k in ('field','fieldPath','path','property','propertyPath','kind','type','relation','label','slot','key'):
        v=e.get(k)
        if isinstance(v,(str,int,float,bool)) and str(v):vals.append(f'{k}={v}')
    return ';'.join(vals[:4]) or '-'

incoming=defaultdict(list);outgoing=defaultdict(list)
parsed=0;unparsed_samples=[];modes=defaultdict(int)
for i,e in enumerate(edges):
    if not isinstance(e,dict):continue
    s,t,sk,tk,mode=discover_pair(e);modes[mode]+=1
    if s and t:
        parsed+=1
        rec={'edgeIndex':i,'source':s,'target':t,'label':edge_label(e),'sourceKey':sk,'targetKey':tk}
        incoming[t].append(rec);outgoing[s].append(rec)
    elif len(unparsed_samples)<5:
        unparsed_samples.append({'edgeIndex':i,'keys':list(e.keys())[:30],'sample':{k:e[k] for k in list(e.keys())[:12]}})

parse_ratio=parsed/max(1,len(edges))
if parse_ratio < 0.90:
    diag={'format':'WFGG_FORMATION_TEXTURE_CONSUMER_TRACE_SCHEMA_ERROR','nodes':len(nodes),'edges':len(edges),'parsedEdges':parsed,'parseRatio':parse_ratio,'modes':dict(modes),'unparsedSamples':unparsed_samples}
    outp.write_text(json.dumps(diag,ensure_ascii=False,indent=2)+'\n','utf-8')
    reportp.write_text('SCHEMA_EDGE_PARSE_INSUFFICIENT\n'+json.dumps(diag,ensure_ascii=False,indent=2)+'\n','utf-8')
    raise SystemExit(f'EDGE_SCHEMA_GUARD parsed={parsed}/{len(edges)} ratio={parse_ratio:.3f}')

# ---------- map serialized files back to exact cached bundle ids ----------
bundle_files={}
for p in localp.glob('bundle-*.bundle'):
    m=re.fullmatch(r'bundle-(\d+)\.bundle',p.name)
    if m:bundle_files[int(m.group(1))]=p
expected=set(int(x) for x in ((sumj.get('dependencySelection') or {}).get('selectedBundleIds') or []))
if len(expected)!=195:raise SystemExit(f'SUMMARY_CLOSURE_GUARD expected195 actual={len(expected)}')
if not expected.issubset(bundle_files):raise SystemExit(f'BUNDLE_CACHE_GUARD missing={len(expected-set(bundle_files))}')

sf_to_bundles=defaultdict(set);bundle_to_sfs=defaultdict(set);bundle_errors=[]
for pos,bid in enumerate(sorted(expected),1):
    p=bundle_files[bid]
    try:
        env=UnityPy.load(str(p))
        # Object assets_file names are the serialized file identities used by the graph.
        for obj in list(getattr(env,'objects',[]) or []):
            af=getattr(obj,'assets_file',None)
            nm=str(getattr(af,'name','') or '')
            if nm:
                sf_to_bundles[nm].add(bid);bundle_to_sfs[bid].add(nm)
        # Also inspect env.files keys because some bundles have sparse/no objects in a file.
        fs=getattr(env,'files',None)
        if isinstance(fs,dict):
            for k,v in fs.items():
                for nm in (str(k or ''),str(getattr(v,'name','') or '')):
                    if nm:
                        sf_to_bundles[nm].add(bid);bundle_to_sfs[bid].add(nm)
    except Exception as ex:
        bundle_errors.append({'bundleId':bid,'error':f'{type(ex).__name__}:{ex}'})
    if pos%25==0:print('TEXTURE_CONSUMERS_BUNDLEMAP',f'{pos}/195',f'serializedFiles={len(sf_to_bundles)}')

def bundle_ids_for_node(n):
    sf=str(n.get('serializedFile') or '')
    return sorted(sf_to_bundles.get(sf,set()))

def node_summary(n):
    return {'id':str(n.get('id')),'serializedFile':str(n.get('serializedFile') or ''),'bundleIds':bundle_ids_for_node(n),
            'pathID':str(n.get('pathID')),'type':str(n.get('type') or ''),'name':str(n.get('name') or '')}

# ---------- resolve exact selected targets ----------
results=[]
for item in retained:
    name=str(item['name']);pid=int(str(item['pathIDExact']));declared_bid=int(item['bundleId'])
    hits=[n for n in by_name_pid.get((name,pid),[]) if str(n.get('type'))=='Texture2D']
    if not hits:
        hits=[n for n in by_pid.get(pid,[]) if str(n.get('type'))=='Texture2D' and str(n.get('name') or '')==name]
    # Prefer node whose serializedFile maps to declared bundle; never silently choose if still ambiguous.
    preferred=[n for n in hits if declared_bid in bundle_ids_for_node(n)]
    if len(preferred)==1:target=preferred[0]
    elif len(hits)==1:target=hits[0]
    else:
        results.append({'selection':item,'resolution':'AMBIGUOUS_OR_MISSING','candidateNodes':[node_summary(n) for n in hits]})
        continue
    target_id=str(target['id'])

    direct=[]
    for er in incoming.get(target_id,[]):
        src=node_by_id[er['source']]
        direct.append({'referrer':node_summary(src),'edgeLabel':er['label'],'edgeIndex':er['edgeIndex']})

    # Reverse BFS: every path is a serialized dependency chain consumer -> ... -> texture.
    q=deque([(target_id,0,[target_id])]);seen_depth={target_id:0};chains=[];reachable=set()
    while q:
        cur,d,path=q.popleft()
        if d>=max_depth:continue
        for er in incoming.get(cur,[]):
            src=er['source']
            if src in path:continue
            nd=d+1;reachable.add(src)
            newpath=[src]+path
            chains.append({'depth':nd,'edgeLabel':er['label'],'nodeIds':newpath})
            if nd < seen_depth.get(src,999):
                seen_depth[src]=nd;q.append((src,nd,newpath))

    # Keep useful endpoints and all direct chains. Consumers are ranked by semantic render relevance then depth.
    render_types={'Material','TerrainData','Terrain','MeshRenderer','SkinnedMeshRenderer','Renderer','Mesh','GameObject','Prefab','SceneAsset','MonoBehaviour'}
    consumer_rows=[]
    for nid in reachable:
        n=node_by_id[nid];consumer_rows.append({'depth':seen_depth.get(nid),'node':node_summary(n),'renderRelevant':str(n.get('type')) in render_types})
    consumer_rows.sort(key=lambda x:(not x['renderRelevant'],x['depth'] if x['depth'] is not None else 99,x['node']['type'],x['node']['name']))

    compact_chains=[]
    for c in sorted(chains,key=lambda x:(x['depth'],x['nodeIds'])):
        if c['depth']>4:continue
        ns=[node_summary(node_by_id[nid]) for nid in c['nodeIds']]
        if c['depth']==1 or any(x['type'] in render_types for x in ns[:-1]):
            compact_chains.append({'depth':c['depth'],'nodes':ns,'lastEdgeLabel':c['edgeLabel']})
        if len(compact_chains)>=80:break

    all_consumer_bundles=sorted({b for x in consumer_rows for b in x['node']['bundleIds']})
    direct_bundles=sorted({b for x in direct for b in x['referrer']['bundleIds']})
    results.append({'selection':item,'resolution':'EXACT','target':node_summary(target),
                    'declaredStorageBundleMatch':declared_bid in bundle_ids_for_node(target),
                    'directReferrers':direct,'directConsumerBundleIds':direct_bundles,
                    'reachableConsumerBundleIdsDepthLe6':all_consumer_bundles,
                    'consumers':consumer_rows[:160],'chains':compact_chains})

# Aggregate bundle usage across all eight.
bundle_usage=defaultdict(lambda:{'textures':set(),'direct':set(),'indirect':set(),'types':set(),'objects':set()})
for r in results:
    if r.get('resolution')!='EXACT':continue
    tex=r['selection']['name']
    for d in r['directReferrers']:
        for b in d['referrer']['bundleIds']:
            u=bundle_usage[b];u['textures'].add(tex);u['direct'].add(tex);u['types'].add(d['referrer']['type']);u['objects'].add(d['referrer']['name'])
    for c in r['consumers']:
        for b in c['node']['bundleIds']:
            u=bundle_usage[b];u['textures'].add(tex);u['indirect'].add(tex);u['types'].add(c['node']['type']);u['objects'].add(c['node']['name'])
agg=[]
for bid,u in bundle_usage.items():
    agg.append({'bundleId':bid,'textures':sorted(u['textures']),'directTextureRefs':sorted(u['direct']),'indirectTextureReachability':sorted(u['indirect']),
                'consumerTypes':sorted(u['types']),'consumerObjects':sorted(x for x in u['objects'] if x)[:80]})
agg.sort(key=lambda x:(-len(x['textures']),-len(x['directTextureRefs']),x['bundleId']))

out={'format':'WFGG_LASTWAR_FORMATION_HUMAN_SELECTED_TEXTURE_CONSUMERS_V1',
     'sourceSelection':str(selectp.relative_to(selectp.parents[4])) if len(selectp.parents)>4 else str(selectp),
     'graph':{'nodes':len(nodes),'edges':len(edges),'parsedEdges':parsed,'parseRatio':round(parse_ratio,6),'endpointModes':dict(modes)},
     'bundleMapping':{'closureBundles':len(expected),'serializedFilesMapped':len(sf_to_bundles),'bundleErrors':bundle_errors},
     'results':results,'aggregateConsumerBundles':agg,
     'guardrails':{'humanSelectionIsNotRuntimeProof':True,'reverseGraphReachabilityIsSerializedReferenceEvidence':True,'candidatePromotion':False,'labOnly':True,'mainUntouched':True}}
outp.write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n','utf-8')

lines=['WfGg Last War — HUMAN SELECTED FORMATION TEXTURE CONSUMERS V1','',
       f'graphNodes={len(nodes)} graphEdges={len(edges)} parsedEdges={parsed} parseRatio={parse_ratio:.6f}',
       f'closureBundles={len(expected)} serializedFilesMapped={len(sf_to_bundles)} bundleMapErrors={len(bundle_errors)}','']
for r in results:
    it=r['selection'];lines.append('='*88);lines.append(f"TEXTURE {it['name']}")
    lines.append(f"storageBundleDeclared={it['bundleId']} pathIDExact={it['pathIDExact']}")
    lines.append(f"resolution={r.get('resolution')}")
    if r.get('resolution')!='EXACT':
        lines.append(f"candidateNodes={len(r.get('candidateNodes',[]))}");continue
    t=r['target'];lines.append(f"targetSerializedFile={t['serializedFile']} mappedStorageBundles={','.join(map(str,t['bundleIds'])) or '-'} storageBundleMatch={r['declaredStorageBundleMatch']}")
    lines.append(f"directReferrers={len(r['directReferrers'])} directConsumerBundles={','.join(map(str,r['directConsumerBundleIds'])) or '-'}")
    for d in r['directReferrers'][:40]:
        n=d['referrer'];lines.append(f"  DIRECT bundle={','.join(map(str,n['bundleIds'])) or '-'} type={n['type']} name={n['name'] or '-'} sf={n['serializedFile']} pathID={n['pathID']} edge={d['edgeLabel']}")
    lines.append(f"reachableConsumerBundlesDepthLe6={','.join(map(str,r['reachableConsumerBundleIdsDepthLe6'])) or '-'}")
    lines.append('  MOST_RELEVANT_CONSUMERS')
    for c in r['consumers'][:40]:
        n=c['node'];lines.append(f"    depth={c['depth']} relevant={c['renderRelevant']} bundle={','.join(map(str,n['bundleIds'])) or '-'} type={n['type']} name={n['name'] or '-'} pathID={n['pathID']}")
lines+=['','='*88,'AGGREGATE CONSUMER BUNDLES']
for a in agg:
    lines.append(f"bundle={a['bundleId']} textures={len(a['textures'])} direct={len(a['directTextureRefs'])} names={' | '.join(a['textures'])}")
    lines.append(f"  types={' | '.join(a['consumerTypes']) or '-'}")
    if a['consumerObjects']:lines.append(f"  objects={' | '.join(a['consumerObjects'][:20])}")
lines+=['','RULE: this report answers serialized bundle/object usage in the exact Formation V4 graph.','RULE: reverse reachability is evidence of serialized dependency, not proof that the runtime actively renders every reachable asset.','RULE: no visual generated; main untouched.']
reportp.write_text('\n'.join(lines)+'\n','utf-8')
print('FORMATION_TEXTURE_CONSUMERS_OK',f'textures={sum(1 for r in results if r.get("resolution")=="EXACT")}/8',f'aggregateBundles={len(agg)}')
print('FORMATION_TEXTURE_CONSUMERS_REPORT',reportp)
print('FORMATION_TEXTURE_CONSUMERS_JSON',outp)
PY

git add "$OUT"
if ! git diff --cached --quiet; then
  git commit -m "lab: record exact consumer bundles for selected Formation textures"
  git push origin "$BRANCH"
fi

echo "=== FORMATION HUMAN SELECTED TEXTURE CONSUMERS TERMINE ==="
echo "Rapport: $REPORT"
echo "JSON: $OUT"
echo "Aucun visuel. main inchangé."
