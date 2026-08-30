#!/data/data/com.termux/files/usr/bin/bash
set -Eeuo pipefail

# WfGg Last War LAB — trace XLua -> loader -> storage boundary from the EXISTING CLR atlas.
# No APK read, no DLL rescan, no bundle extraction, no preview/main modification.

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BRANCH="portal-auth-lastwar-lab-v1"
INDEX="$ROOT/frontend/lab/master-assets-v2/index"
META="$ROOT/frontend/lab/master-assets-v2/meta"
ATLAS="$INDEX/lastwar-code-discovery-atlas-v1.json"
CROSS="$META/formation-xlua-index-crosswalk-v1.json"
OUT="$META/formation-xlua-loader-storage-boundary-v1.json"
REPORT="$HOME/storage/downloads/WFGG_LASTWAR_FORMATION_XLUA_LOADER_STORAGE_BOUNDARY_V1.txt"

fail(){ printf 'ERREUR: %s\n' "$*" >&2; exit 1; }
cd "$ROOT"
[[ "$(git branch --show-current)" == "$BRANCH" ]] || fail "branche LAB incorrecte"
[[ -s "$ATLAS" ]] || fail "atlas CLR absent: $ATLAS"
[[ -s "$CROSS" ]] || fail "crosswalk XLua absent: $CROSS"
command -v python >/dev/null 2>&1 || fail "python absent"
mkdir -p "$(dirname "$OUT")" "$(dirname "$REPORT")"

python - "$ATLAS" "$CROSS" "$OUT" "$REPORT" <<'PY'
from pathlib import Path
from collections import defaultdict, deque
import json,re,sys

atlas_p,cross_p,out_p,report_p=map(Path,sys.argv[1:])
a=json.loads(atlas_p.read_text('utf-8'))
cross=json.loads(cross_p.read_text('utf-8'))

types=a.get('types') or []
methods=a.get('methods') or []
external=a.get('externalCalls') or []
internal=a.get('internalEdges') or []
tm={int(x['rid']):x for x in types if x.get('rid') is not None}
mm={int(x['rid']):x for x in methods if x.get('rid') is not None}


def owner(rid):
    m=mm.get(int(rid)) or {}; t=tm.get(int(m.get('typeRid') or 0)) or {}
    return ((str(t.get('namespace'))+'.') if t.get('namespace') else '')+str(t.get('name') or '')

def symbol(rid):
    m=mm.get(int(rid)) or {}; o=owner(rid)
    return (o+'.' if o else '')+str(m.get('name') or f'M:{rid}')

def strings(rid):
    vals=(mm.get(int(rid)) or {}).get('strings') or []
    if not isinstance(vals,list): vals=[vals]
    out=[]
    for v in vals:
        if isinstance(v,str): out.append(v)
        elif isinstance(v,dict):
            for k in ('string','value','text'):
                if isinstance(v.get(k),str): out.append(v[k]); break
    return out

# Exact MethodDef call graph from the atlas.
callees=defaultdict(set); callers=defaultdict(set); und=defaultdict(set)
for e in internal:
    if not isinstance(e,(list,tuple)) or len(e)<2: continue
    try:x,y=int(e[0]),int(e[1])
    except Exception: continue
    callees[x].add(y); callers[y].add(x); und[x].add(y); und[y].add(x)

# Exact external MemberRef targets by caller MethodDef.
ext_by_method=defaultdict(set)
for row in external:
    tgt=str(row.get('target') or '')
    for x in row.get('callerRids') or []:
        try: ext_by_method[int(x)].add(tgt)
        except Exception: pass

lua_needles=(
    'xlua','luaenv','luatable','luafunction','luabase','objecttranslator','luadll',
    'dostring','loadstring','addloader','customloader','lua.load','lua.lua',
    'luaL_load'.lower(),'lua_pcall','lua_getglobal','lua_setglobal','require'
)
storage_needles=(
    'textasset','assetbundle.loadasset','assetbundle.load','resources.load','resourcemanager',
    'resourceprovider','assetmanager','file.readallbytes','file.readalltext','file.open',
    'streamreader','memorystream','binaryreader','ziparchive','zipfile','unitywebrequest',
    'downloadhandler','www.','system.io.file','system.io.stream'
)
loader_needles=('loader','loadscript','loadlua','getlua','luaasset','scriptasset','scriptloader')
formation_needles=('formation','pvpformation','heroformation','heroshow','formationrt','formationbg')
path_markers=('.lua','.luac','.bytes','.txt','.zip','/lua/','\\lua\\','lua/','scripts/','script/')


def hits_any(text,needles):
    low=text.lower(); return [n for n in needles if n.lower() in low]

def method_row(rid):
    sym=symbol(rid); ss=strings(rid); ex=sorted(ext_by_method.get(rid,set()))
    blob=' '.join([sym]+ss+ex)
    lua_hits=hits_any(blob,lua_needles)
    storage_hits=hits_any(blob,storage_needles)
    loader_hits=hits_any(blob,loader_needles)
    form_hits=hits_any(blob,formation_needles)
    path_strings=[]
    for s in ss:
        sl=s.lower()
        if any(m.lower() in sl for m in path_markers) or re.search(r'(^|[\\/])[A-Za-z0-9_.-]+[\\/][A-Za-z0-9_./\\-]+$',s):
            path_strings.append(s)
    return {
        'rid':rid,'stableId':f'M:{rid}','symbol':sym,'owner':owner(rid),
        'luaHits':lua_hits,'storageHits':storage_hits,'loaderHits':loader_hits,
        'formationHits':form_hits,'pathStrings':path_strings[:120],
        'strings':ss[:160],'externalTargets':ex[:180],
        'callerRids':sorted(callers.get(rid,set()))[:180],
        'calleeRids':sorted(callees.get(rid,set()))[:180]
    }

# Exact boundary seeds from preceding audits + all exact CLR methods whose owner/symbol is XLua/LuaEnv.
seed_rids={15616,25396,29075,31821,31822}
for rid in mm:
    s=symbol(rid).lower()
    if 'xlua.' in s or 'luaenv' in s or 'objecttranslator' in s:
        seed_rids.add(rid)
seed_rids={x for x in seed_rids if x in mm}

# Undirected graph distance is used ONLY as neighborhood evidence, never runtime direction proof.
dist={x:0 for x in seed_rids}; parent={}
dq=deque(sorted(seed_rids))
MAXD=6
while dq:
    x=dq.popleft(); d=dist[x]
    if d>=MAXD: continue
    for y in und.get(x,()):
        if y not in dist:
            dist[y]=d+1; parent[y]=x; dq.append(y)

rows=[]
direct_bridge=[]; storage_near=[]; lua_storage_path=[]
for rid in mm:
    r=method_row(rid)
    d=dist.get(rid)
    r['xluaUndirectedDistance']=d
    # Strong structural bridge = SAME MethodDef has exact external Lua-ish and storage-ish targets.
    same_external_lua=[t for t in r['externalTargets'] if hits_any(t,lua_needles)]
    same_external_storage=[t for t in r['externalTargets'] if hits_any(t,storage_needles)]
    r['exactExternalLuaTargets']=same_external_lua
    r['exactExternalStorageTargets']=same_external_storage
    if same_external_lua and same_external_storage:
        r['evidenceClass']='same_method_exact_external_lua_and_storage_calls'
        direct_bridge.append(r)
    elif same_external_storage and d is not None and d<=MAXD:
        r['evidenceClass']='storage_call_near_xlua_in_methoddef_graph'
        storage_near.append(r)
    elif r['pathStrings'] and (r['luaHits'] or r['loaderHits']) and d is not None and d<=MAXD:
        r['evidenceClass']='lua_or_loader_method_with_path_literal_near_xlua'
        lua_storage_path.append(r)
    if same_external_lua or same_external_storage or r['pathStrings'] or r['loaderHits'] or r['formationHits']:
        score=0
        if same_external_lua and same_external_storage: score+=100
        if same_external_storage: score+=30
        if same_external_lua: score+=25
        if r['pathStrings']: score+=20
        if r['loaderHits']: score+=12
        if r['formationHits']: score+=10
        if d is not None: score+=max(0,10-d)
        r['score']=score; rows.append(r)

# Exact directed common callers: methods that can reach both a Lua-boundary method and a storage-caller
# in <=4 outgoing MethodDef hops. This is stronger than simple undirected proximity, but still not a Formation binding proof.
lua_targets=set(seed_rids)
storage_callers={rid for rid in mm if any(hits_any(t,storage_needles) for t in ext_by_method.get(rid,set()))}

def reverse_dist(targets,maxd=4):
    d={x:0 for x in targets}; q=deque(targets)
    while q:
        x=q.popleft()
        if d[x]>=maxd: continue
        for p in callers.get(x,()):
            if p not in d:
                d[p]=d[x]+1; q.append(p)
    return d
lua_up=reverse_dist(lua_targets,4); stor_up=reverse_dist(storage_callers,4)
common=[]
for rid in sorted(set(lua_up)&set(stor_up)):
    r=method_row(rid)
    r['distanceToLuaBoundaryDirected']=lua_up[rid]
    r['distanceToStorageCallerDirected']=stor_up[rid]
    if r['distanceToLuaBoundaryDirected']==0 and r['distanceToStorageCallerDirected']==0:
        continue
    common.append(r)
common.sort(key=lambda r:(r['distanceToLuaBoundaryDirected']+r['distanceToStorageCallerDirected'], r['symbol']))

# Reconstruct one exact undirected path from each top near-storage method to its closest XLua seed.
def path_to_seed(rid):
    if rid not in dist: return []
    p=[rid]; x=rid
    while dist.get(x,0)>0 and x in parent:
        x=parent[x]; p.append(x)
    return [{'rid':z,'symbol':symbol(z)} for z in p]
for r in storage_near:
    r['pathToXluaUndirected']=path_to_seed(r['rid'])
for r in lua_storage_path:
    r['pathToXluaUndirected']=path_to_seed(r['rid'])

# Ranking.
direct_bridge.sort(key=lambda r:(-len(r['pathStrings']), r['symbol']))
storage_near.sort(key=lambda r:(r['xluaUndirectedDistance'] if r['xluaUndirectedDistance'] is not None else 99,-len(r['pathStrings']),r['symbol']))
lua_storage_path.sort(key=lambda r:(r['xluaUndirectedDistance'] if r['xluaUndirectedDistance'] is not None else 99,-len(r['pathStrings']),r['symbol']))
rows.sort(key=lambda r:(-r['score'], r['symbol']))

# Collect exact path literals globally around relevant Lua/loader/storage methods.
path_literals=[]
seen=set()
for r in rows:
    for s in r['pathStrings']:
        k=(r['rid'],s)
        if k in seen: continue
        seen.add(k)
        path_literals.append({'rid':r['rid'],'stableId':r['stableId'],'symbol':r['symbol'],'literal':s,
                              'luaHits':r['luaHits'],'storageHits':r['storageHits'],'loaderHits':r['loaderHits'],
                              'xluaUndirectedDistance':r['xluaUndirectedDistance']})
path_literals.sort(key=lambda x:(x['xluaUndirectedDistance'] if x['xluaUndirectedDistance'] is not None else 99,x['symbol'],x['literal']))

if direct_bridge:
    strategy='inspect_same_method_exact_lua_storage_bridges'
elif common:
    strategy='inspect_directed_common_callers_between_xlua_and_storage'
elif storage_near:
    strategy='inspect_nearest_storage_callers_then_targeted_container_probe'
elif path_literals:
    strategy='targeted_container_probe_from_exact_path_literals'
else:
    strategy='targeted_readonly_loader_container_probe_required'

result={
  'format':'WFGG_LASTWAR_FORMATION_XLUA_LOADER_STORAGE_BOUNDARY_V1',
  'sources':{
    'codeAtlas':str(atlas_p),
    'previousCrosswalk':str(cross_p)
  },
  'counts':{
    'methods':len(mm),'types':len(tm),'internalEdges':len(internal),'externalTargets':len(external),
    'xluaSeedMethods':len(seed_rids),'methodsWithin6UndirectedHops':len(dist),
    'sameMethodExactLuaStorageBridges':len(direct_bridge),
    'directedCommonCallersLuaStorage':len(common),
    'storageCallersWithin6UndirectedHops':len(storage_near),
    'luaLoaderPathMethodsWithin6UndirectedHops':len(lua_storage_path),
    'relevantPathLiterals':len(path_literals)
  },
  'xluaSeeds':[method_row(x) for x in sorted(seed_rids)[:500]],
  'sameMethodExactLuaStorageBridges':direct_bridge[:300],
  'directedCommonCallersLuaStorage':common[:300],
  'storageCallersNearXlua':storage_near[:500],
  'luaLoaderPathMethodsNearXlua':lua_storage_path[:500],
  'pathLiterals':path_literals[:800],
  'rankedRelevantMethods':rows[:800],
  'conclusion':{
    'nextStrategy':strategy,
    'important':'Undirected proximity is neighborhood evidence only. Exact external calls and exact directed MethodDef reachability remain separate evidence classes. No Formation runtime binding is promoted from proximity alone.'
  },
  'guardrails':{
    'existingAtlasOnly':True,'apkAccess':False,'dllRescan':False,'bundleScan':False,
    'newExtraction':False,'candidatePromotion':False,'mainUntouched':True,'previewUntouched':True
  }
}
out_p.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n','utf-8')

lines=[
 'WfGg Last War — FORMATION XLUA LOADER / STORAGE BOUNDARY V1','',
 f"methods={len(mm)} types={len(tm)} internalEdges={len(internal)} externalTargets={len(external)}",
 f"xluaSeeds={len(seed_rids)} within6Hops={len(dist)}",
 f"sameMethodExactLuaStorageBridges={len(direct_bridge)} directedCommonCallers={len(common)} storageNearXlua={len(storage_near)} luaLoaderPathNearXlua={len(lua_storage_path)} pathLiterals={len(path_literals)}",
 f"nextStrategy={strategy}",'',
 'SAME METHOD — EXACT EXTERNAL LUA + STORAGE CALLS'
]
if direct_bridge:
    for r in direct_bridge[:80]:
        lines.append(f"  M:{r['rid']} symbol={r['symbol']} distance={r['xluaUndirectedDistance']}")
        for t in r['exactExternalLuaTargets'][:8]: lines.append('    LUA='+t)
        for t in r['exactExternalStorageTargets'][:8]: lines.append('    STORAGE='+t)
        for s in r['pathStrings'][:12]: lines.append('    PATH='+s)
else: lines.append('  NONE')
lines += ['', 'DIRECTED COMMON CALLERS — CAN REACH XLUA BOUNDARY + STORAGE CALLER']
if common:
    for r in common[:100]:
        lines.append(f"  M:{r['rid']} luaD={r['distanceToLuaBoundaryDirected']} storageD={r['distanceToStorageCallerDirected']} symbol={r['symbol']}")
        for s in r['pathStrings'][:8]: lines.append('    PATH='+s)
else: lines.append('  NONE')
lines += ['', 'NEAREST EXACT STORAGE CALLERS AROUND XLUA (UNDIRECTED NEIGHBORHOOD ONLY)']
if storage_near:
    for r in storage_near[:100]:
        st=' | '.join(r['exactExternalStorageTargets'][:6])
        lines.append(f"  M:{r['rid']} d={r['xluaUndirectedDistance']} symbol={r['symbol']}")
        if st: lines.append('    STORAGE='+st)
        for s in r['pathStrings'][:8]: lines.append('    PATH='+s)
else: lines.append('  NONE')
lines += ['', 'EXACT PATH LITERALS AROUND LUA / LOADER / STORAGE METHODS']
if path_literals:
    for x in path_literals[:160]:
        lines.append(f"  M:{x['rid']} d={x['xluaUndirectedDistance']} symbol={x['symbol']} literal={x['literal']}")
else: lines.append('  NONE')
lines += ['', 'NEXT '+strategy,
 'RULE: same-method exact external calls > directed MethodDef reachability > undirected neighborhood > string/path correlation.',
 'RULE: no APK read, DLL rescan, extraction, bundle scan, main or preview modification performed.'
]
report_p.write_text('\n'.join(lines)+'\n','utf-8')

print('FORMATION_XLUA_STORAGE_OK',
      f'bridges={len(direct_bridge)}',f'common={len(common)}',f'storageNear={len(storage_near)}',
      f'pathLiterals={len(path_literals)}')
for r in direct_bridge[:20]: print('FORMATION_XLUA_STORAGE_BRIDGE',f"M:{r['rid']}",r['symbol'])
for r in common[:20]: print('FORMATION_XLUA_STORAGE_COMMON',f"M:{r['rid']}",r['distanceToLuaBoundaryDirected'],r['distanceToStorageCallerDirected'],r['symbol'])
for r in storage_near[:20]: print('FORMATION_XLUA_STORAGE_NEAR',f"M:{r['rid']}",r['xluaUndirectedDistance'],r['symbol'])
for x in path_literals[:20]: print('FORMATION_XLUA_STORAGE_PATH',f"M:{x['rid']}",x['literal'])
print('FORMATION_XLUA_STORAGE_NEXT',strategy)
print('FORMATION_XLUA_STORAGE_JSON',out_p)
print('FORMATION_XLUA_STORAGE_REPORT',report_p)
PY

git add "$OUT"
if ! git diff --cached --quiet; then
  git commit -m "lab: trace Formation XLua loader storage boundary"
  git push origin "$BRANCH"
fi

printf '\nOK — rapport: %s\n' "$REPORT"
