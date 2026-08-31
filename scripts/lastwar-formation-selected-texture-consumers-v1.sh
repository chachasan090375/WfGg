#!/data/data/com.termux/files/usr/bin/bash
set -Eeuo pipefail

# WfGg Last War LAB — exact consumers of the 8 human-selected Formation textures.
# No visual generation. Current extracted 195-bundle closure only. Game remains read-only.

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BRANCH="portal-auth-lastwar-lab-v1"
META="$ROOT/frontend/lab/master-assets-v2/meta"
HUMAN="$META/formation-visual-human-review-v2-result.json"
GRAPH="$META/formation-ptr-exact-v4.json"
SUMMARY="$META/formation-ptr-exact-v4-summary-v1.json"
GAMERES="$ROOT/frontend/lab/local_assets/lastwar-formation-native-recipe-v1/gameres"
BUNDLEDIR="$ROOT/frontend/lab/local_assets/lastwar-formation-ptr-exact-v4/bundles"
OUT="$META/formation-selected-texture-consumers-v1.json"
REPORT="$HOME/storage/downloads/WFGG_LASTWAR_FORMATION_SELECTED_TEXTURE_CONSUMERS_V1.txt"
UNITY_VERSION="2019.4.41f1"

fail(){ printf 'ERREUR: %s\n' "$*" >&2; exit 1; }
cd "$ROOT"
[[ "$(git branch --show-current)" == "$BRANCH" ]] || fail "branche LAB incorrecte"
for f in "$HUMAN" "$GRAPH" "$SUMMARY"; do [[ -s "$f" ]] || fail "fichier absent: $f"; done
[[ -d "$BUNDLEDIR" ]] || fail "dossier bundles V4 absent"
command -v python >/dev/null 2>&1 || fail "python absent"
python - <<'PYCHK' >/dev/null 2>&1 || fail "UnityPy absent"
import UnityPy
PYCHK
mkdir -p "$(dirname "$OUT")" "$(dirname "$REPORT")"

python - "$HUMAN" "$GRAPH" "$SUMMARY" "$GAMERES" "$BUNDLEDIR" "$OUT" "$REPORT" "$UNITY_VERSION" <<'PY'
from __future__ import annotations
from pathlib import Path
from collections import defaultdict,Counter,deque
import json,re,sys,time
import UnityPy

humanp,graphp,sump,gameresp,bundledir,outp,reportp=map(Path,sys.argv[1:8])
unity_version=sys.argv[8]
UnityPy.config.FALLBACK_UNITY_VERSION=unity_version
t0=time.time()

human=json.loads(humanp.read_text('utf-8'))
graph=json.loads(graphp.read_text('utf-8'))
summary=json.loads(sump.read_text('utf-8'))

# ---------- guards ----------
sel=human.get('retainedYes')
if not isinstance(sel,list) or len(sel)!=8:
    raise SystemExit(f'HUMAN_SELECTION_GUARD expected=8 actual={len(sel) if isinstance(sel,list) else "invalid"}')
nodes=graph.get('nodes');edges=graph.get('edges')
if not isinstance(nodes,list) or len(nodes)!=3209: raise SystemExit(f'GRAPH_NODES_GUARD expected=3209 actual={len(nodes) if isinstance(nodes,list) else "invalid"}')
if not isinstance(edges,list) or len(edges)!=8386: raise SystemExit(f'GRAPH_EDGES_GUARD expected=8386 actual={len(edges) if isinstance(edges,list) else "invalid"}')
if any(not isinstance(e,dict) or 'from' not in e or 'to' not in e for e in edges):
    raise SystemExit('GRAPH_EDGE_SCHEMA_GUARD expected from/to on every edge')
closure=((summary.get('dependencySelection') or {}).get('selectedBundleIds') or [])
closure=[int(x) for x in closure]
if len(closure)!=195 or len(set(closure))!=195: raise SystemExit(f'CLOSURE_GUARD expected=195 actual={len(set(closure))}')

bundle_paths={}
for bid in closure:
    p=bundledir/f'bundle-{bid}.bundle'
    if not p.is_file(): raise SystemExit(f'BUNDLE_MISSING bundle={bid} path={p}')
    try:
        with p.open('rb') as f:sig=f.read(7)
    except Exception as e: raise SystemExit(f'BUNDLE_READ_FAILED bundle={bid} {type(e).__name__}:{e}')
    if sig!=b'UnityFS': raise SystemExit(f'BUNDLE_SIGNATURE_GUARD bundle={bid} sig={sig!r}')
    bundle_paths[bid]=p

# ---------- current gameres catalog (metadata only) ----------
def parse_gameres(p:Path):
    if not p.is_file(): return {}
    text=p.read_text('utf-8',errors='replace')
    def section(name):
        m=re.search(rf'^\[{re.escape(name)}\]\s*$',text,re.M)
        if not m:return []
        s=m.end();n=re.search(r'^\[[^\]]+\]\s*$',text[s:],re.M);e=s+n.start() if n else len(text)
        return [x for x in text[s:e].splitlines() if x.strip()]
    dirs={}
    for ln in section('Directories'):
        try:i,p0=ln.split(',',1);dirs[int(i)]=p0
        except:pass
    paths={}
    for ln in section('Paths'):
        try:pid,did,n=ln.split(',',2);paths[int(pid)]=dirs[int(did)].rstrip('/')+'/'+n
        except:pass
    out={}
    for ln in section('Bundles'):
        q=ln.split(',')
        if len(q)<8:continue
        try:
            bid=int(q[0]);ids=[int(x) for x in q[4].split('|') if x]
            out[bid]={'bundleId':bid,'logicalName':q[1],'aliasName':q[7],'assetPaths':[paths[x] for x in ids if x in paths]}
        except:pass
    return out
catalog=parse_gameres(gameresp)

# ---------- helpers ----------
def af_name(af):
    for k in ('name','path'):
        v=getattr(af,k,None)
        if v:return str(v)
    return '<serialized-file>'
def af_clean(s):
    s=str(s).replace('\\','/').strip();s=re.sub(r'^archive:/+','',s,flags=re.I)
    return s.lower()
def otype(r):
    try:return str(r.type.name)
    except:return ''
def oname(r):
    try:
        v=r.peek_name();return '' if v is None else str(v)
    except:return ''
def ext_info(r,file_id):
    if file_id<=0:return None
    exts=getattr(r.assets_file,'externals',[]) or [];i=file_id-1
    if not (0<=i<len(exts)):return {'fileID':file_id,'invalidExternalIndex':True}
    ex=exts[i]
    return {'fileID':file_id,'path':str(getattr(ex,'path','')),'guid':str(getattr(ex,'guid','')) if getattr(ex,'guid',None) is not None else None}
def walk(v,path='$'):
    if isinstance(v,dict):
        if 'm_FileID' in v and 'm_PathID' in v:
            try:yield path,int(v.get('m_FileID') or 0),int(v.get('m_PathID') or 0)
            except:pass
        for k,z in v.items():yield from walk(z,path+'.'+str(k))
    elif isinstance(v,(list,tuple)):
        for i,z in enumerate(v):yield from walk(z,f'{path}[{i}]')

def bundle_meta(bid):
    r=catalog.get(int(bid),{})
    return {'bundleId':int(bid),'logicalName':r.get('logicalName'),'aliasName':r.get('aliasName'),'assetPaths':r.get('assetPaths',[])}

# ---------- inventory each current closure bundle ----------
# Exact source-bundle attribution comes from the bundle being loaded, not a name guess.
serialized_to_bundles=defaultdict(set)
serialized_aliases=defaultdict(set)
objmeta={}
readers_by_key={}
bundle_stats={}

for i,bid in enumerate(closure,1):
    p=bundle_paths[bid]
    try:env=UnityPy.load(str(p))
    except Exception as e:raise SystemExit(f'UNITYPY_LOAD_FAILED bundle={bid} {type(e).__name__}:{e}')
    objs=list(getattr(env,'objects',[]) or [])
    sfiles=set()
    for r in objs:
        sf=af_clean(af_name(r.assets_file));sfiles.add(sf)
        key=(sf,int(r.path_id))
        # If identical serialized object key occurs in multiple physical bundles, preserve ambiguity.
        objmeta.setdefault(key,[]).append({'bundleId':bid,'serializedFile':af_name(r.assets_file),'pathID':str(int(r.path_id)),'type':otype(r),'name':oname(r)})
        readers_by_key.setdefault((bid,sf,int(r.path_id)),r)
    for sf in sfiles:
        serialized_to_bundles[sf].add(bid);serialized_aliases[sf].add(sf);serialized_aliases[Path(sf).name].add(sf)
    bundle_stats[str(bid)]={'objects':len(objs),'serializedFiles':sorted(sfiles)}
    if i%25==0:print('FORMATION_TEXTURE_CONSUMERS_INVENTORY',f'{i}/195')

# Resolve an external serialized path to one observed serialized-file identity.
def resolve_external_serialized(ep):
    clean=af_clean(ep);hits=set(serialized_aliases.get(clean,set()))|set(serialized_aliases.get(Path(clean).name,set()))
    if len(hits)==1:return next(iter(hits)),None
    if not hits:return None,'external_serialized_file_not_loaded'
    return None,f'external_serialized_file_ambiguous count={len(hits)}'

# ---------- exact target identities ----------
targets={}
for x in sel:
    bid=int(x['bundleId']);pid=int(str(x['pathIDExact']));name=str(x['name'])
    candidates=[]
    for (b,sf,pid0),r in readers_by_key.items():
        if b==bid and pid0==pid and otype(r)=='Texture2D' and oname(r)==name:candidates.append((sf,r))
    if len(candidates)!=1:
        raise SystemExit(f'TARGET_IDENTITY_GUARD name={name!r} bundle={bid} pathID={pid} matches={len(candidates)}')
    sf,_=candidates[0];key=(sf,pid)
    targets[key]={**x,'pathIDExact':str(pid),'serializedFile':sf,'targetKey':sf+'#'+str(pid)}

# ---------- scan serialized PPtrs in relevant source types across ALL 195 bundles ----------
SOURCE_TYPES={
 'Material','TerrainLayer','TerrainData','Terrain','MeshRenderer','SkinnedMeshRenderer','Renderer',
 'ParticleSystemRenderer','TrailRenderer','LineRenderer','SpriteRenderer','MeshFilter','GameObject','Transform',
 'MonoBehaviour','LODGroup','MeshCollider','PrefabInstance'
}
all_edges=[];incoming=defaultdict(list);scan_fail=[];scanned_objects=0;pptrs=0;unresolved_external=Counter()

for i,bid in enumerate(closure,1):
    p=bundle_paths[bid];env=UnityPy.load(str(p));objs=list(getattr(env,'objects',[]) or [])
    for r in objs:
        typ=otype(r)
        if typ not in SOURCE_TYPES:continue
        scanned_objects+=1;ssf=af_clean(af_name(r.assets_file));src=(ssf,int(r.path_id))
        try:tree=r.read_typetree()
        except Exception as e:
            scan_fail.append({'bundleId':bid,'serializedFile':ssf,'pathID':str(int(r.path_id)),'type':typ,'name':oname(r),'error':f'{type(e).__name__}:{e}'})
            continue
        for fp,fid,pid in walk(tree):
            if pid==0:continue
            pptrs+=1
            if fid==0:dsf=ssf;derr=None;ext=None
            else:
                ext=ext_info(r,fid);dsf,derr=resolve_external_serialized((ext or {}).get('path') or '')
            if dsf is None:
                unresolved_external[(derr,str((ext or {}).get('path') or ''))]+=1;continue
            dst=(dsf,pid)
            # Keep only links whose destination exists in our observed closure inventory or is a selected target.
            if dst not in objmeta and dst not in targets:continue
            em={
              'from':{'serializedFile':ssf,'pathID':str(int(r.path_id)),'type':typ,'name':oname(r),'bundleId':bid},
              'to':{'serializedFile':dsf,'pathID':str(pid)},
              'fieldPath':fp,'fileID':fid,'external':ext,
              'proof':'serialized_pptr_current_195_bundle_closure'
            }
            dm=objmeta.get(dst,[])
            # Type/name only when all observed copies agree; never guess among divergent copies.
            if dm:
                types=sorted(set(str(z.get('type') or '') for z in dm));names=sorted(set(str(z.get('name') or '') for z in dm))
                if len(types)==1:em['to']['type']=types[0]
                if len(names)==1:em['to']['name']=names[0]
                em['to']['bundleIds']=sorted(set(int(z['bundleId']) for z in dm))
            all_edges.append(em);incoming[dst].append(em)
    if i%25==0:print('FORMATION_TEXTURE_CONSUMERS_SCAN',f'{i}/195',f'pptrs={pptrs}',f'keptEdges={len(all_edges)}')

# V4 graph membership/correlation, exact schema from->to.
gnode={(af_clean(n.get('serializedFile','')),int(n.get('pathID') or 0)):n for n in nodes if isinstance(n,dict) and n.get('pathID') is not None}
gedge={(str(e['from']),str(e['to']),str(e.get('fieldPath') or ''),int(e.get('fileID') or 0),int(e.get('pathID') or 0)) for e in edges}

def graph_node_for(key):return gnode.get(key)
def annotate_root_graph(e):
    sk=(af_clean(e['from']['serializedFile']),int(e['from']['pathID']));tk=(af_clean(e['to']['serializedFile']),int(e['to']['pathID']))
    sn=graph_node_for(sk);tn=graph_node_for(tk)
    if not sn or not tn:return False
    sig=(str(sn['id']),str(tn['id']),str(e.get('fieldPath') or ''),int(e.get('fileID') or 0),int(e['to']['pathID']))
    return sig in gedge
for e in all_edges:e['alsoInV4RootGraph']=annotate_root_graph(e)

# ---------- reverse usage chains from each selected Texture2D ----------
# Follow incoming serialized refs; every hop means source object directly references previous destination.
MAX_HOPS=5
results=[];all_consumer_bundles=set()

for tkey,t in targets.items():
    direct=list(incoming.get(tkey,[]))
    chains=[];q=deque()
    seen={(tkey,0)}
    for e in direct:q.append((e,1,[e]))
    while q:
        e,hop,path=q.popleft();src=(af_clean(e['from']['serializedFile']),int(e['from']['pathID']))
        chains.append({'hop':hop,'edge':e,'chain':[{'type':z['from'].get('type'),'name':z['from'].get('name'),'bundleId':z['from'].get('bundleId'),'fieldPath':z.get('fieldPath')} for z in path]})
        if hop>=MAX_HOPS:continue
        state=(src,hop)
        if state in seen:continue
        seen.add(state)
        for up in incoming.get(src,[]):q.append((up,hop+1,[*path,up]))
    cb=sorted(set(int(c['edge']['from']['bundleId']) for c in chains))
    all_consumer_bundles.update(cb)
    direct_b=sorted(set(int(e['from']['bundleId']) for e in direct))
    results.append({
      'texture':t,
      'storageBundle':bundle_meta(int(t['bundleId'])),
      'directConsumerCount':len(direct),
      'directConsumerBundles':[bundle_meta(x) for x in direct_b],
      'allUpstreamConsumerBundles':[bundle_meta(x) for x in cb],
      'directConsumers':direct,
      'reverseChains':chains,
      'v4RootGraphTargetPresent':graph_node_for(tkey) is not None,
      'status':'EXACT_SERIALIZED_CONSUMERS_FOUND' if direct else 'NO_SERIALIZED_CONSUMER_IN_195_CLOSURE'
    })

# Dedup kept edges in output by exact source/dest/field tuple.
def esig(e):
    return (e['from']['bundleId'],e['from']['serializedFile'],e['from']['pathID'],e['to']['serializedFile'],e['to']['pathID'],e['fieldPath'],e['fileID'])
uniq={esig(e):e for e in all_edges};all_edges=list(uniq.values())

out={
 'format':'WFGG_LASTWAR_FORMATION_SELECTED_TEXTURE_CONSUMERS_V1',
 'scope':{'bundleClosureCount':195,'source':'formation-ptr-exact-v4-summary-v1.json','currentExtractedBundlesOnly':True},
 'selectionCount':8,
 'summary':{
   'texturesWithDirectConsumers':sum(1 for r in results if r['directConsumerCount']>0),
   'texturesWithoutDirectConsumers':sum(1 for r in results if r['directConsumerCount']==0),
   'uniqueConsumerBundleIds':sorted(all_consumer_bundles),
   'scannedRelevantObjects':scanned_objects,'serializedPPtrsObserved':pptrs,'keptResolvedEdges':len(all_edges),
   'typetreeFailures':len(scan_fail),'elapsedSeconds':round(time.time()-t0,2)
 },
 'results':results,
 'diagnostics':{
   'sourceTypesScanned':sorted(SOURCE_TYPES),'bundleStats':bundle_stats,'typetreeFailures':scan_fail[:200],
   'unresolvedExternalSerializedFiles':[{'count':n,'reason':k[0],'externalPath':k[1]} for k,n in unresolved_external.most_common(100)]
 },
 'guardrails':{
   'labBranchOnly':True,'mainUntouched':True,'gameAssetsReadOnly':True,'historicalPhysicalOffsetsUsed':False,
   'selectedTargetIdentityExact':True,'serializedPPtrProofOnly':True,'candidatePromotion':False,'generatedVisuals':False,
   'absenceMeaning':'NO_SERIALIZED_CONSUMER_IN_195_CLOSURE does not prove absence outside this closure or runtime/dynamic use'
 }
}
outp.write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n','utf-8')

# ---------- compact text report ----------
lines=['WfGg Last War — SELECTED FORMATION TEXTURE CONSUMERS V1','',
       f"textures=8 withDirectConsumer={out['summary']['texturesWithDirectConsumers']} withoutDirectConsumer={out['summary']['texturesWithoutDirectConsumers']} uniqueConsumerBundles={','.join(map(str,out['summary']['uniqueConsumerBundleIds'])) or '-'}",
       f"closureBundles=195 relevantObjects={scanned_objects} pptrsObserved={pptrs} keptEdges={len(all_edges)} typetreeFailures={len(scan_fail)} elapsedSeconds={out['summary']['elapsedSeconds']}",
       'RULE: exact serialized PPtr references in current 195-bundle Formation closure only.','RULE: no visual generation; no historical offset; no candidate promotion.','']
for r in results:
    t=r['texture'];lines.append(f"TARGET {t['name']} storageBundle={t['bundleId']} pathID={t['pathIDExact']} serializedFile={t['serializedFile']}")
    lines.append(f"  STATUS={r['status']} directConsumers={r['directConsumerCount']} rootGraphTarget={str(r['v4RootGraphTargetPresent']).lower()}")
    if r['directConsumers']:
        lines.append('  DIRECT:')
        for e in r['directConsumers']:
            f=e['from'];lines.append(f"    bundle={f['bundleId']} type={f.get('type')} name={f.get('name')!r} pathID={f.get('pathID')} field={e.get('fieldPath')} alsoInV4={str(e.get('alsoInV4RootGraph')).lower()}")
    else:lines.append('  DIRECT: NONE IN 195-BUNDLE SERIALIZED CLOSURE')
    lines.append('  CONSUMER_BUNDLES='+(','.join(str(x['bundleId']) for x in r['allUpstreamConsumerBundles']) or '-'))
    # Compact only distinct interesting upstream objects, shortest hop first.
    shown=set();lines.append('  UPSTREAM:')
    for c in sorted(r['reverseChains'],key=lambda z:z['hop']):
        e=c['edge'];f=e['from'];sig=(c['hop'],f['bundleId'],f.get('type'),f.get('name'),f.get('pathID'))
        if sig in shown:continue
        shown.add(sig)
        lines.append(f"    hop={c['hop']} bundle={f['bundleId']} type={f.get('type')} name={f.get('name')!r} pathID={f.get('pathID')} field={e.get('fieldPath')}")
        if len(shown)>=40:lines.append('    ... truncated in TXT; full JSON contains all chains');break
    if not shown:lines.append('    NONE')
    lines.append('')
lines += ['UNIQUE CONSUMER BUNDLES']
for bid in sorted(all_consumer_bundles):
    bm=bundle_meta(bid);lines.append(f"  bundle={bid} logical={bm.get('logicalName') or '-'}")
    for ap in bm.get('assetPaths',[])[:20]:lines.append('    asset='+ap)
lines += ['',f'JSON={outp}',f'REPORT={reportp}']
reportp.write_text('\n'.join(lines)+'\n','utf-8')

print('FORMATION_SELECTED_TEXTURE_CONSUMERS_OK',f"textures=8",f"withDirect={out['summary']['texturesWithDirectConsumers']}",f"consumerBundles={len(all_consumer_bundles)}",f"pptrs={pptrs}")
for r in results:
    print('FORMATION_SELECTED_TEXTURE_TARGET',r['texture']['name'],f"storage={r['texture']['bundleId']}",f"direct={r['directConsumerCount']}",'consumers='+(','.join(str(x['bundleId']) for x in r['allUpstreamConsumerBundles']) or '-'))
print('FORMATION_SELECTED_TEXTURE_JSON',outp)
print('FORMATION_SELECTED_TEXTURE_REPORT',reportp)
PY

git add "$OUT"
if ! git diff --cached --quiet; then
  git commit -m "lab: record exact selected Formation texture consumers"
  git push origin "$BRANCH"
fi
printf '%s\n' '=== SELECTED FORMATION TEXTURE CONSUMERS TERMINE ===' "Rapport: $REPORT" "JSON: $OUT" 'Aucun visuel genere.'
