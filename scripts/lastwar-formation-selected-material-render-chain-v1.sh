#!/data/data/com.termux/files/usr/bin/bash
set -Eeuo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BRANCH="portal-auth-lastwar-lab-v1"
META="$ROOT/frontend/lab/master-assets-v2/meta"
SUMMARY="$META/formation-ptr-exact-v4-summary-v1.json"
LOCAL="$ROOT/frontend/lab/local_assets/lastwar-formation-ptr-exact-v4/bundles"
OUT="$META/formation-selected-material-render-chain-v1.json"
REPORT="$HOME/storage/downloads/WFGG_LASTWAR_FORMATION_SELECTED_MATERIAL_RENDER_CHAIN_V1.txt"
CACHE="$HOME/.cache/wfgg-formation-material-chain-v1.sqlite"
UNITY_VERSION="2019.4.41f1"
MAX_DEPTH=4

fail(){ printf 'ERREUR: %s\n' "$*" >&2; exit 1; }
cd "$ROOT"
[[ "$(git branch --show-current)" == "$BRANCH" ]] || fail "branche LAB incorrecte"
[[ -s "$SUMMARY" ]] || fail "summary absent: $SUMMARY"
[[ -d "$LOCAL" ]] || fail "cache bundles V4 absent: $LOCAL"
command -v python >/dev/null 2>&1 || fail "python absent"
python - <<'PYCHK' >/dev/null 2>&1 || fail "UnityPy absent"
import UnityPy
PYCHK
mkdir -p "$(dirname "$REPORT")" "$(dirname "$CACHE")"
rm -f "$CACHE"

echo "MATERIAL_RENDER_CHAIN_V1_START"
echo "MATERIAL_RENDER_CHAIN_V1_PREFLIGHT_OK"

PYTHONUNBUFFERED=1 python - "$SUMMARY" "$LOCAL" "$OUT" "$REPORT" "$CACHE" "$UNITY_VERSION" "$MAX_DEPTH" <<'PY'
from __future__ import annotations
from pathlib import Path
from collections import defaultdict, deque
import json,re,sqlite3,sys
import UnityPy

sump,localp,outp,reportp,cachep=map(Path,sys.argv[1:6])
unity_version=sys.argv[6]; max_depth=int(sys.argv[7])
UnityPy.config.FALLBACK_UNITY_VERSION=unity_version

# Exact Material targets established by the direct Texture2D consumer scan V2.
MATERIALS=[
    {'name':'Terrain_Ground','bundleId':14169,'pathID':5462275938698525167},
    {'name':'O_terrain_grass02_3TextureNS1','bundleId':14169,'pathID':-58427823418694077},
    {'name':'O_terrain_road_01','bundleId':14169,'pathID':1806725993657708232},
    {'name':'O_terrain_road_02_nsj','bundleId':14169,'pathID':-1460172297484211456},
    {'name':'O_terrain_shamo_back','bundleId':14169,'pathID':142524935483900056},
]

print('MATERIAL_RENDER_CHAIN_V1_STAGE load-summary',flush=True)
sumj=json.loads(sump.read_text('utf-8'))
expected=set(int(x) for x in ((sumj.get('dependencySelection') or {}).get('selectedBundleIds') or []))
if len(expected)!=195: raise SystemExit(f'SUMMARY_CLOSURE_GUARD expected195 actual={len(expected)}')
bundle_files={}
for p in localp.glob('bundle-*.bundle'):
    m=re.fullmatch(r'bundle-(\d+)\.bundle',p.name)
    if m: bundle_files[int(m.group(1))]=p
missing=sorted(expected-set(bundle_files))
if missing: raise SystemExit(f'BUNDLE_CACHE_GUARD missing={len(missing)} sample={missing[:10]}')


def norm_file(s):
    s=str(s or '').replace('\\','/')
    return s.rsplit('/',1)[-1].lower() if s else ''

def file_name_of_obj(obj):
    af=getattr(obj,'assets_file',None)
    return str(getattr(af,'name','') or '')

def external_names(assets_file):
    out=[]
    exts=getattr(assets_file,'externals',None) or []
    for ex in exts:
        vals=[]
        for a in ('path','name','file_name','fileName'):
            try:
                v=getattr(ex,a,None)
                if v: vals.append(str(v))
            except Exception: pass
        out.append(vals)
    return out

def resolve_ref_name(source_af,file_id):
    if file_id==0: return [str(getattr(source_af,'name','') or '')]
    if file_id<0:return []
    ex=external_names(source_af); idx=file_id-1
    return ex[idx] if 0<=idx<len(ex) else []

def ptr_hits(tree,path='$'):
    if isinstance(tree,dict):
        fks=('m_FileID','fileID','fileId','m_FileId'); pks=('m_PathID','pathID','pathId','m_PathId')
        fk=next((k for k in fks if k in tree),None); pk=next((k for k in pks if k in tree),None)
        if fk is not None and pk is not None:
            try: yield path,int(tree[fk]),int(tree[pk])
            except Exception: pass
        for k,v in tree.items(): yield from ptr_hits(v,f'{path}.{k}')
    elif isinstance(tree,(list,tuple)):
        for i,v in enumerate(tree): yield from ptr_hits(v,f'{path}[{i}]')

def try_name(obj):
    try:
        v=obj.peek_name()
        if v:return str(v)
    except Exception:pass
    return ''

# Resolve exact Material serialized-file identities from bundle 14169.
print('MATERIAL_RENDER_CHAIN_V1_STAGE resolve-materials',flush=True)
env14169=UnityPy.load(str(bundle_files[14169]))
mat_targets=[]
for i,m in enumerate(MATERIALS,1):
    hits=[]
    for obj in list(getattr(env14169,'objects',[]) or []):
        if int(getattr(obj,'path_id',0) or 0)!=m['pathID']:continue
        typ=str(getattr(getattr(obj,'type',None),'name','') or '')
        if typ!='Material':continue
        hits.append(obj)
    if len(hits)!=1:raise SystemExit(f'MATERIAL_TARGET_RESOLUTION name={m["name"]} hits={len(hits)}')
    obj=hits[0]; nm=try_name(obj); sf=file_name_of_obj(obj)
    if nm and nm!=m['name']:raise SystemExit(f'MATERIAL_NAME_MISMATCH expected={m["name"]!r} actual={nm!r}')
    rec={**m,'serializedFile':sf,'fileKey':norm_file(sf)};mat_targets.append(rec)
    print('MATERIAL_RENDER_CHAIN_V1_TARGET',f'{i}/5',f'name={m["name"]}',f'pid={m["pathID"]}',f'file={sf}',flush=True)

# One exact scan of all 195 bundles into an on-disk SQLite edge index.
print('MATERIAL_RENDER_CHAIN_V1_STAGE build-edge-index',flush=True)
db=sqlite3.connect(str(cachep))
db.execute('PRAGMA journal_mode=OFF');db.execute('PRAGMA synchronous=OFF');db.execute('PRAGMA temp_store=MEMORY')
db.execute('CREATE TABLE objects(file TEXT NOT NULL,pid INTEGER NOT NULL,bundle INTEGER NOT NULL,type TEXT,name TEXT,PRIMARY KEY(file,pid,bundle))')
db.execute('CREATE TABLE edges(target_file TEXT NOT NULL,target_pid INTEGER NOT NULL,source_file TEXT NOT NULL,source_pid INTEGER NOT NULL,source_bundle INTEGER NOT NULL,source_type TEXT,source_name TEXT,field TEXT,file_id INTEGER)')
db.execute('CREATE INDEX idx_edges_target ON edges(target_file,target_pid)')
db.execute('CREATE INDEX idx_edges_source ON edges(source_file,source_pid)')
ptr_total=0;object_total=0;tree_failures=[]
for pos,bid in enumerate(sorted(expected),1):
    print('MATERIAL_RENDER_CHAIN_V1_BUNDLE',f'{pos}/195',f'bundle={bid}',flush=True)
    try:env=UnityPy.load(str(bundle_files[bid]))
    except Exception as e:
        tree_failures.append({'bundleId':bid,'stage':'load','error':f'{type(e).__name__}:{e}'});continue
    edge_batch=[];obj_batch=[]
    for obj in list(getattr(env,'objects',[]) or []):
        object_total+=1
        af=getattr(obj,'assets_file',None);sf=norm_file(getattr(af,'name','') or '')
        if not sf:continue
        pid=int(getattr(obj,'path_id',0) or 0);typ=str(getattr(getattr(obj,'type',None),'name','') or '');name=try_name(obj)
        obj_batch.append((sf,pid,bid,typ,name))
        try:tree=obj.read_typetree()
        except Exception as e:
            if len(tree_failures)<400:tree_failures.append({'bundleId':bid,'stage':'typetree','file':sf,'pathID':str(pid),'type':typ,'name':name,'error':f'{type(e).__name__}:{e}'})
            continue
        for field,file_id,target_pid in ptr_hits(tree):
            ptr_total+=1
            if target_pid==0:continue
            names=resolve_ref_name(af,file_id)
            if not names:continue
            target_file=norm_file(names[0])
            if not target_file:continue
            edge_batch.append((target_file,target_pid,sf,pid,bid,typ,name,field,file_id))
    db.executemany('INSERT OR IGNORE INTO objects(file,pid,bundle,type,name) VALUES(?,?,?,?,?)',obj_batch)
    db.executemany('INSERT INTO edges(target_file,target_pid,source_file,source_pid,source_bundle,source_type,source_name,field,file_id) VALUES(?,?,?,?,?,?,?,?,?)',edge_batch)
    db.commit()
print('MATERIAL_RENDER_CHAIN_V1_INDEX_OK',f'objects={object_total}',f'ptrs={ptr_total}',f'failures={len(tree_failures)}',flush=True)

RENDER_TYPES={'MeshRenderer','SkinnedMeshRenderer','Terrain','Renderer','SpriteRenderer','LineRenderer','TrailRenderer','ParticleSystemRenderer'}
HIER_TYPES={'GameObject','Transform','RectTransform','PrefabInstance'}
META_TYPES={'AssetBundle'}

def classify(t):
    if t in RENDER_TYPES:return 'render'
    if t in HIER_TYPES:return 'hierarchy'
    if t in META_TYPES:return 'metadata'
    if t=='MonoBehaviour':return 'behaviour'
    return 'other'

def reverse_hits(file_key,pid):
    rows=db.execute('SELECT source_file,source_pid,source_bundle,source_type,source_name,field,file_id FROM edges WHERE target_file=? AND target_pid=?',(file_key,pid)).fetchall()
    return [{'sourceFile':r[0],'sourcePathID':str(r[1]),'sourceBundle':r[2],'sourceType':r[3] or '','sourceName':r[4] or '','field':r[5] or '','fileID':r[6]} for r in rows]

def outgoing_hits(file_key,pid):
    rows=db.execute('SELECT target_file,target_pid,source_bundle,source_type,source_name,field,file_id FROM edges WHERE source_file=? AND source_pid=?',(file_key,pid)).fetchall()
    return [{'targetFile':r[0],'targetPathID':str(r[1]),'sourceBundle':r[2],'sourceType':r[3] or '','sourceName':r[4] or '','field':r[5] or '','fileID':r[6]} for r in rows]

def obj_meta(file_key,pid):
    rows=db.execute('SELECT bundle,type,name FROM objects WHERE file=? AND pid=?',(file_key,pid)).fetchall()
    return [{'bundle':r[0],'type':r[1] or '','name':r[2] or ''} for r in rows]

# Trace each material. Reverse traversal only expands semantic render/hierarchy objects.
print('MATERIAL_RENDER_CHAIN_V1_STAGE trace-material-consumers',flush=True)
results=[];global_render_bundles=defaultdict(set);global_render_objects=defaultdict(set)
for mi,m in enumerate(mat_targets,1):
    start=(m['fileKey'],int(m['pathID']))
    direct=reverse_hits(*start)
    print('MATERIAL_RENDER_CHAIN_V1_MATERIAL',f'{mi}/5',f'name={m["name"]}',f'directRefs={len(direct)}',flush=True)
    q=deque([(start,0,[{'type':'Material','name':m['name'],'bundle':14169,'file':start[0],'pathID':str(start[1])}] )])
    visited={start};chains=[];semantic_nodes={};metadata_hits=[]
    while q:
        (tf,tp),depth,path=q.popleft()
        if depth>=max_depth:continue
        for h in reverse_hits(tf,tp):
            cls=classify(h['sourceType']); key=(h['sourceFile'],int(h['sourcePathID']))
            node={'class':cls,'type':h['sourceType'],'name':h['sourceName'],'bundle':h['sourceBundle'],'file':h['sourceFile'],'pathID':h['sourcePathID'],'field':h['field']}
            newpath=[node]+path
            if cls=='metadata':
                metadata_hits.append({'depth':depth+1,'node':node,'path':newpath});continue
            # Keep all direct non-metadata refs, but only expand render/hierarchy objects.
            if depth==0 or cls in ('render','hierarchy'):
                semantic_nodes[key]={'depth':depth+1,**node}
                chains.append({'depth':depth+1,'path':newpath})
            if cls in ('render','hierarchy') and key not in visited:
                visited.add(key);q.append((key,depth+1,newpath))
    # Enrich direct renderers with their own m_GameObject pointer when present.
    renderer_gameobjects=[]
    for key,n in list(semantic_nodes.items()):
        if n['class']!='render':continue
        outs=outgoing_hits(key[0],key[1])
        go_ptrs=[x for x in outs if 'm_GameObject' in x['field']]
        for g in go_ptrs:
            metas=obj_meta(g['targetFile'],int(g['targetPathID']))
            renderer_gameobjects.append({'renderer':n,'gameObjectTarget':g,'gameObjectMeta':metas})
        global_render_bundles[n['bundle']].add(m['name']);global_render_objects[n['bundle']].add((n['type'],n['name'],n['pathID']))
    result={'material':m,'directReferrers':direct,'semanticConsumers':sorted(semantic_nodes.values(),key=lambda x:(x['depth'],x['bundle'],x['type'],x['name'],x['pathID'])),
            'rendererGameObjects':renderer_gameobjects,'metadataReferences':metadata_hits,'chains':chains[:250]}
    results.append(result)

bundle_agg=[]
for bid,names in global_render_bundles.items():
    bundle_agg.append({'bundleId':bid,'materials':sorted(names),'renderObjects':[{'type':a,'name':b,'pathID':c} for a,b,c in sorted(global_render_objects[bid])]})
bundle_agg.sort(key=lambda x:(-len(x['materials']),x['bundleId']))

out={'format':'WFGG_LASTWAR_FORMATION_SELECTED_MATERIAL_RENDER_CHAIN_V1','method':'single current 195-bundle PPtr index + reverse material consumer tracing; AssetBundle metadata separated from semantic render/hierarchy consumers',
     'materials':mat_targets,'results':results,'renderBundleAggregate':bundle_agg,
     'counts':{'closureBundles':195,'materials':5,'objectsIndexed':object_total,'ptrsScanned':ptr_total,'readFailures':len(tree_failures),'renderConsumerBundles':len(bundle_agg)},
     'readFailures':tree_failures,
     'guardrails':{'labBranchOnly':True,'mainUntouched':True,'historicalOffsetsReused':False,'runtimeUseProof':False,'generatedVisuals':False}}
outp.write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n','utf-8')

lines=['WfGg Last War — SELECTED MATERIAL RENDER CHAIN V1','',
       f'closureBundles=195 materials=5 objectsIndexed={object_total} ptrsScanned={ptr_total} readFailures={len(tree_failures)} renderConsumerBundles={len(bundle_agg)}','']
for r in results:
    m=r['material'];lines.append('='*100);lines.append(f"MATERIAL {m['name']} bundle=14169 pathID={m['pathID']} serializedFile={m['serializedFile']}")
    sem=r['semanticConsumers'];render=[x for x in sem if x['class']=='render'];hier=[x for x in sem if x['class']=='hierarchy']
    lines.append(f"directRefs={len(r['directReferrers'])} renderConsumers={len(render)} hierarchyConsumers={len(hier)} metadataRefs={len(r['metadataReferences'])}")
    for x in render:lines.append(f"  RENDER depth={x['depth']} bundle={x['bundle']} type={x['type']} name={x['name'] or '-'} pathID={x['pathID']} via={x['field']}")
    for g in r['rendererGameObjects']:
        rr=g['renderer'];tg=g['gameObjectTarget'];meta=' | '.join(f"bundle={z['bundle']} type={z['type']} name={z['name'] or '-'}" for z in g['gameObjectMeta']) or '-'
        lines.append(f"    GAMEOBJECT_FROM_RENDERER rendererBundle={rr['bundle']} renderer={rr['name'] or rr['type']} -> file={tg['targetFile']} pathID={tg['targetPathID']} meta={meta}")
    for x in hier[:80]:lines.append(f"  HIER depth={x['depth']} bundle={x['bundle']} type={x['type']} name={x['name'] or '-'} pathID={x['pathID']} via={x['field']}")
    # keep metadata compact: useful for bundle/prefab containment but not render proof
    for x in r['metadataReferences'][:20]:
        n=x['node'];lines.append(f"  META depth={x['depth']} bundle={n['bundle']} type={n['type']} name={n['name'] or '-'} pathID={n['pathID']} via={n['field']}")
lines+=['','RENDER BUNDLE AGGREGATE']
for b in bundle_agg:
    lines.append(f"bundle={b['bundleId']} materials={len(b['materials'])}/5 names={' | '.join(b['materials'])}")
    for o in b['renderObjects'][:80]:lines.append(f"  render type={o['type']} name={o['name'] or '-'} pathID={o['pathID']}")
lines+=['','DIAGNOSTICS',f'readFailures={len(tree_failures)}']
for e in tree_failures[:80]:lines.append('  '+json.dumps(e,ensure_ascii=False))
lines+=['','RULE: AssetBundle preload/container references are metadata and are reported separately.','RULE: RENDER lines are direct/indirect serialized consumer chains rooted at the five exact Materials.','RULE: serialized reachability is stronger than bundle co-location but is not runtime-use proof.','RULE: current cached 195-bundle closure only; no historical offsets reused.','RULE: no visual generated.']
reportp.write_text('\n'.join(lines)+'\n','utf-8')
print('MATERIAL_RENDER_CHAIN_V1_OK',f'renderConsumerBundles={len(bundle_agg)}',f'readFailures={len(tree_failures)}',flush=True)
print('MATERIAL_RENDER_CHAIN_V1_REPORT',reportp,flush=True)
print('MATERIAL_RENDER_CHAIN_V1_JSON',outp,flush=True)
db.close()
PY

git add "$OUT"
if ! git diff --cached --quiet; then
  git commit -m "lab: record selected Formation material render chains V1"
  git push origin "$BRANCH"
fi

echo "=== MATERIAL RENDER CHAIN V1 TERMINE ==="
echo "Rapport: $REPORT"
echo "main/preview inchangés. Aucun visuel généré."
