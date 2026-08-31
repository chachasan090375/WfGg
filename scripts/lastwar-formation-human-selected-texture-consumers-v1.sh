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
printf 'TEXTURE_CONSUMERS_START branch=%s\n' "$(git branch --show-current)"
[[ "$(git branch --show-current)" == "$BRANCH" ]] || fail "branche LAB incorrecte"
for f in "$GRAPH" "$SELECT" "$SUMMARY"; do [[ -s "$f" ]] || fail "fichier absent: $f"; done
[[ -d "$LOCAL" ]] || fail "cache bundles V4 absent: $LOCAL"
command -v python >/dev/null 2>&1 || fail "python absent"
python - <<'PYCHK' >/dev/null 2>&1 || fail "UnityPy absent"
import UnityPy
PYCHK
mkdir -p "$(dirname "$REPORT")"
printf 'TEXTURE_CONSUMERS_PREFLIGHT_OK\n'

PYTHONUNBUFFERED=1 python -u - "$GRAPH" "$SELECT" "$SUMMARY" "$LOCAL" "$OUT" "$REPORT" "$UNITY_VERSION" "$MAX_DEPTH" <<'PY'
from __future__ import annotations
from pathlib import Path
from collections import defaultdict, deque
import json,re,sys
import UnityPy

graphp,selectp,sump,localp,outp,reportp=map(Path,sys.argv[1:7])
unity_version=sys.argv[7];max_depth=int(sys.argv[8])
UnityPy.config.FALLBACK_UNITY_VERSION=unity_version

def log(*a): print(*a, flush=True)

log('TEXTURE_CONSUMERS_STAGE','load-json')
g=json.loads(graphp.read_text('utf-8'))
sel=json.loads(selectp.read_text('utf-8'))
sumj=json.loads(sump.read_text('utf-8'))
nodes=g.get('nodes');edges=g.get('edges')
if not isinstance(nodes,list) or not nodes: raise SystemExit('GRAPH_SCHEMA_ERROR nodes')
if not isinstance(edges,list) or not edges: raise SystemExit('GRAPH_SCHEMA_ERROR edges')
retained=sel.get('retainedYes')
if not isinstance(retained,list) or len(retained)!=8: raise SystemExit('SELECTION_SCHEMA_ERROR retainedYes')
log('TEXTURE_CONSUMERS_GRAPH_OK',f'nodes={len(nodes)}',f'edges={len(edges)}','selected=8')

node_by_id={};by_file_pid=defaultdict(list);by_pid=defaultdict(list);by_name_pid=defaultdict(list)
for n in nodes:
    if not isinstance(n,dict):continue
    nid=n.get('id')
    if nid is not None:node_by_id[str(nid)]=n
    sf=str(n.get('serializedFile') or '')
    try:pid=int(n.get('pathID'))
    except Exception:continue
    by_file_pid[(sf,pid)].append(n);by_pid[pid].append(n);by_name_pid[(str(n.get('name') or ''),pid)].append(n)

SOURCE_KEYS=('source','src','from','fromId','sourceId','owner','ownerId','referrer','referrerId','a')
TARGET_KEYS=('target','dst','to','toId','targetId','referenced','referencedId','reference','child','childId','b')
def resolve_scalar(v):
    if v is None:return None
    if isinstance(v,str):return v if v in node_by_id else None
    if isinstance(v,dict):
        for k in ('id','nodeId','node','objectId','refId'):
            x=v.get(k)
            if x is not None and str(x) in node_by_id:return str(x)
        sf=v.get('serializedFile') or v.get('file') or v.get('sourceFile');pv=v.get('pathID') if 'pathID' in v else v.get('m_PathID')
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
    sf=pv=None
    for k in (prefix+'SerializedFile',prefix+'File',prefix+'SourceFile'):
        if k in e:sf=e.get(k);break
    for k in (prefix+'PathID',prefix+'PathId',prefix+'Pid'):
        if k in e:pv=e.get(k);break
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
    return None,None,None,None,'unparsed'
def edge_label(e):
    vals=[]
    for k in ('field','fieldPath','path','property','propertyPath','kind','type','relation','label','slot','key'):
        v=e.get(k)
        if isinstance(v,(str,int,float,bool)) and str(v):vals.append(f'{k}={v}')
    return ';'.join(vals[:4]) or '-'

log('TEXTURE_CONSUMERS_STAGE','parse-edges')
incoming=defaultdict(list);parsed=0
for i,e in enumerate(edges):
    if not isinstance(e,dict):continue
    s,t,sk,tk,mode=discover_pair(e)
    if s and t:
        parsed+=1;incoming[t].append({'edgeIndex':i,'source':s,'target':t,'label':edge_label(e),'sourceKey':sk,'targetKey':tk})
parse_ratio=parsed/max(1,len(edges))
log('TEXTURE_CONSUMERS_EDGES_OK',f'parsed={parsed}/{len(edges)}',f'ratio={parse_ratio:.3f}')
if parse_ratio<0.90:raise SystemExit(f'EDGE_SCHEMA_GUARD parsed={parsed}/{len(edges)} ratio={parse_ratio:.3f}')

bundle_files={}
for p in localp.glob('bundle-*.bundle'):
    m=re.fullmatch(r'bundle-(\d+)\.bundle',p.name)
    if m:bundle_files[int(m.group(1))]=p
expected=set(int(x) for x in ((sumj.get('dependencySelection') or {}).get('selectedBundleIds') or []))
if len(expected)!=195:raise SystemExit(f'SUMMARY_CLOSURE_GUARD expected195 actual={len(expected)}')
if not expected.issubset(bundle_files):raise SystemExit(f'BUNDLE_CACHE_GUARD missing={len(expected-set(bundle_files))}')
log('TEXTURE_CONSUMERS_STAGE','map-serialized-files','bundles=195')
sf_to_bundles=defaultdict(set);bundle_errors=[]
for pos,bid in enumerate(sorted(expected),1):
    log('TEXTURE_CONSUMERS_BUNDLE',f'{pos}/195',f'bundle={bid}')
    p=bundle_files[bid]
    try:
        env=UnityPy.load(str(p))
        for obj in list(getattr(env,'objects',[]) or []):
            nm=str(getattr(getattr(obj,'assets_file',None),'name','') or '')
            if nm:sf_to_bundles[nm].add(bid)
        fs=getattr(env,'files',None)
        if isinstance(fs,dict):
            for k,v in fs.items():
                for nm in (str(k or ''),str(getattr(v,'name','') or '')):
                    if nm:sf_to_bundles[nm].add(bid)
    except Exception as ex:bundle_errors.append({'bundleId':bid,'error':f'{type(ex).__name__}:{ex}'})
log('TEXTURE_CONSUMERS_BUNDLEMAP_OK',f'serializedFiles={len(sf_to_bundles)}',f'errors={len(bundle_errors)}')

def bundle_ids_for_node(n):return sorted(sf_to_bundles.get(str(n.get('serializedFile') or ''),set()))
def node_summary(n):return {'id':str(n.get('id')),'serializedFile':str(n.get('serializedFile') or ''),'bundleIds':bundle_ids_for_node(n),'pathID':str(n.get('pathID')),'type':str(n.get('type') or ''),'name':str(n.get('name') or '')}

log('TEXTURE_CONSUMERS_STAGE','trace-selected')
results=[]
for ix,item in enumerate(retained,1):
    name=str(item['name']);pid=int(str(item['pathIDExact']));declared_bid=int(item['bundleId'])
    log('TEXTURE_CONSUMERS_TEXTURE',f'{ix}/8',f'bundle={declared_bid}',name)
    hits=[n for n in by_name_pid.get((name,pid),[]) if str(n.get('type'))=='Texture2D']
    if not hits:hits=[n for n in by_pid.get(pid,[]) if str(n.get('type'))=='Texture2D' and str(n.get('name') or '')==name]
    preferred=[n for n in hits if declared_bid in bundle_ids_for_node(n)]
    if len(preferred)==1:target=preferred[0]
    elif len(hits)==1:target=hits[0]
    else:results.append({'selection':item,'resolution':'AMBIGUOUS_OR_MISSING','candidateNodes':[node_summary(n) for n in hits]});continue
    target_id=str(target['id']);direct=[]
    for er in incoming.get(target_id,[]):direct.append({'referrer':node_summary(node_by_id[er['source']]),'edgeLabel':er['label'],'edgeIndex':er['edgeIndex']})
    q=deque([(target_id,0)]);seen={target_id:0};reachable=set()
    while q:
        cur,d=q.popleft()
        if d>=max_depth:continue
        for er in incoming.get(cur,[]):
            src=er['source'];nd=d+1
            if nd<seen.get(src,999):seen[src]=nd;reachable.add(src);q.append((src,nd))
    consumers=[]
    for nid in reachable:consumers.append({'depth':seen[nid],'node':node_summary(node_by_id[nid])})
    consumers.sort(key=lambda x:(x['depth'],x['node']['type'],x['node']['name']))
    results.append({'selection':item,'resolution':'EXACT','target':node_summary(target),'directReferrers':direct,'directConsumerBundleIds':sorted({b for d in direct for b in d['referrer']['bundleIds']}),'reachableConsumerBundleIdsDepthLe6':sorted({b for c in consumers for b in c['node']['bundleIds']}),'consumers':consumers[:200]})

bundle_usage=defaultdict(lambda:{'textures':set(),'direct':set(),'types':set(),'objects':set()})
for r in results:
    if r.get('resolution')!='EXACT':continue
    tex=r['selection']['name']
    for d in r['directReferrers']:
        for b in d['referrer']['bundleIds']:
            u=bundle_usage[b];u['textures'].add(tex);u['direct'].add(tex);u['types'].add(d['referrer']['type']);u['objects'].add(d['referrer']['name'])
    for c in r['consumers']:
        for b in c['node']['bundleIds']:
            u=bundle_usage[b];u['textures'].add(tex);u['types'].add(c['node']['type']);u['objects'].add(c['node']['name'])
agg=[]
for bid,u in bundle_usage.items():agg.append({'bundleId':bid,'textures':sorted(u['textures']),'directTextureRefs':sorted(u['direct']),'consumerTypes':sorted(u['types']),'consumerObjects':sorted(x for x in u['objects'] if x)[:80]})
agg.sort(key=lambda x:(-len(x['textures']),-len(x['directTextureRefs']),x['bundleId']))
out={'format':'WFGG_LASTWAR_FORMATION_HUMAN_SELECTED_TEXTURE_CONSUMERS_V1','graph':{'nodes':len(nodes),'edges':len(edges),'parsedEdges':parsed},'selectedTextures':results,'bundleUsageAcrossEight':agg,'bundleMapErrors':bundle_errors,'guardrails':{'labBranchOnly':True,'mainUntouched':True,'noGeneratedVisuals':True,'candidatePromotion':False}}
outp.write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n','utf-8')
lines=['WfGg Last War — HUMAN SELECTED TEXTURE CONSUMERS V1','',f'graphNodes={len(nodes)} graphEdges={len(edges)} parsedEdges={parsed}',f'selected={len(results)} exact={sum(r.get("resolution")=="EXACT" for r in results)}','']
for r in results:
    s=r['selection'];lines+=['='*90,f"TEXTURE {s['name']} storageBundle={s['bundleId']} pathID={s['pathIDExact']}",f"resolution={r.get('resolution')}"]
    if r.get('resolution')=='EXACT':
        lines.append('directConsumerBundles='+(','.join(map(str,r['directConsumerBundleIds'])) or '-'));lines.append('reachableConsumerBundlesDepthLe6='+(','.join(map(str,r['reachableConsumerBundleIdsDepthLe6'])) or '-'))
        for d in r['directReferrers'][:30]:
            n=d['referrer'];lines.append(f"  DIRECT type={n['type']} name={n['name']} bundles={','.join(map(str,n['bundleIds'])) or '-'} sf={n['serializedFile']} pathID={n['pathID']} edge={d['edgeLabel']}")
lines+=['','BUNDLE AGGREGATE']
for a in agg:lines.append(f"bundle={a['bundleId']} textures={len(a['textures'])}/8 direct={len(a['directTextureRefs'])} types={','.join(a['consumerTypes'])} names={' | '.join(a['textures'])}")
lines+=['','RULE: bundles reported are resolved from current cached V4 bundle serialized-file identities.','RULE: reverse graph reachability is serialized dependency evidence, not runtime-use proof.','RULE: no visual generated.']
reportp.write_text('\n'.join(lines)+'\n','utf-8')
log('TEXTURE_CONSUMERS_OK',f'exact={sum(r.get("resolution")=="EXACT" for r in results)}/8',f'bundles={len(agg)}')
log('TEXTURE_CONSUMERS_REPORT',reportp)
PY

git add "$OUT"
if ! git diff --cached --quiet; then
  git commit -m "lab: trace human-selected Formation texture consumers"
  git push origin "$BRANCH"
fi

echo "=== TEXTURE CONSUMER TRACE TERMINE ==="
echo "Rapport: $REPORT"
