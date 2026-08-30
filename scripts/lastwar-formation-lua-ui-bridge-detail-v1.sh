#!/data/data/com.termux/files/usr/bin/bash
set -Eeuo pipefail

# WfGg Last War LAB — targeted detail of the exact Lua/storage bridges already found.
# Existing CLR atlas only. NO APK read, NO DLL rescan, NO extraction, NO bundle scan.

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BRANCH="portal-auth-lastwar-lab-v1"
ATLAS="$ROOT/frontend/lab/master-assets-v2/index/lastwar-code-discovery-atlas-v1.json"
OUT="$ROOT/frontend/lab/master-assets-v2/meta/formation-lua-ui-bridge-detail-v1.json"
REPORT="$HOME/storage/downloads/WFGG_LASTWAR_FORMATION_LUA_UI_BRIDGE_DETAIL_V1.txt"

fail(){ printf 'ERREUR: %s\n' "$*" >&2; exit 1; }
cd "$ROOT"
[[ "$(git branch --show-current)" == "$BRANCH" ]] || fail "branche LAB incorrecte"
[[ -s "$ATLAS" ]] || fail "atlas CLR absent: $ATLAS"
command -v python >/dev/null 2>&1 || fail "python absent"
mkdir -p "$(dirname "$OUT")" "$(dirname "$REPORT")"

python - "$ATLAS" "$OUT" "$REPORT" <<'PY'
from pathlib import Path
from collections import defaultdict, deque
import json,re,sys

atlas_p,out_p,report_p=map(Path,sys.argv[1:])
a=json.loads(atlas_p.read_text('utf-8'))
methods=a.get('methods') or []
types=a.get('types') or []
internal=a.get('internalEdges') or []
external=a.get('externalCalls') or []
mm={int(x['rid']):x for x in methods if x.get('rid') is not None}
tm={int(x['rid']):x for x in types if x.get('rid') is not None}
callers=defaultdict(set);callees=defaultdict(set)
for e in internal:
    if not isinstance(e,(list,tuple)) or len(e)<2: continue
    try:c,d=int(e[0]),int(e[1])
    except Exception:continue
    callees[c].add(d);callers[d].add(c)

ext_by_caller=defaultdict(list)
for row in external:
    tgt=str(row.get('target') or '')
    for x in row.get('callerRids') or []:
        try:ext_by_caller[int(x)].append(tgt)
        except Exception:pass

def owner(rid):
    m=mm.get(rid) or {};t=tm.get(int(m.get('typeRid') or 0)) or {}
    return ((str(t.get('namespace'))+'.') if t.get('namespace') else '')+str(t.get('name') or '')
def symbol(rid):
    m=mm.get(rid) or {};o=owner(rid)
    return (o+'.' if o else '')+str(m.get('name') or f'M:{rid}')
def strings(rid):
    vals=(mm.get(rid) or {}).get('strings') or []
    if not isinstance(vals,list): vals=[vals]
    out=[]
    for v in vals:
        if isinstance(v,str):out.append(v)
        elif isinstance(v,dict):
            for k in ('string','value','text'):
                if isinstance(v.get(k),str):out.append(v[k]);break
    return out

def method_row(rid):
    m=mm.get(rid) or {}
    return {
      'rid':rid,'stableId':f'M:{rid}','symbol':symbol(rid),'owner':owner(rid),
      'status':m.get('status'),'score':m.get('score'),'tags':m.get('tags') or [],
      'strings':strings(rid),
      'externalCalls':sorted(set(ext_by_caller.get(rid,[]))),
      'directCallers':[{'rid':x,'symbol':symbol(x)} for x in sorted(callers.get(rid,set()))],
      'directCallees':[{'rid':x,'symbol':symbol(x)} for x in sorted(callees.get(rid,set()))],
    }

def bfs(start,adj,maxd=4):
    dist={start:0};dq=deque([start])
    while dq:
        x=dq.popleft();d=dist[x]
        if d>=maxd:continue
        for y in adj.get(x,()):
            if y not in dist:dist[y]=d+1;dq.append(y)
    return dist

# Exact bridge/framework anchors identified by the previous audit.
targets=[4807,13830,14817,14819,16002,16003]
keywords=('formation','pvp','hero','ui','form','lua','resource','asset','bundle','panel','prefab','textasset','stream','zip')
storage_markers=('TextAsset','AssetBundle','Resources.','System.IO.','File.','Stream','Zip','ResourceManager','WWW','UnityWebRequest')
lua_markers=('XLua.','LuaDLL','LuaEnv','lua_','luaL_','xlua')

def interesting(rid):
    blob=(symbol(rid)+' '+' '.join(strings(rid))+' '+' '.join(ext_by_caller.get(rid,[]))).lower()
    return any(k in blob for k in keywords)

def has_storage(rid):return any(any(m in x for m in storage_markers) for x in ext_by_caller.get(rid,[]))
def has_lua(rid):return any(any(m.lower() in x.lower() for m in lua_markers) for x in ext_by_caller.get(rid,[]))

details=[]
for rid in targets:
    if rid not in mm:continue
    up=bfs(rid,callers,4);down=bfs(rid,callees,4)
    type_rid=int((mm[rid].get('typeRid') or 0))
    t=tm.get(type_rid) or {}
    same=[]
    for m in methods:
        try:mr=int(m.get('rid'))
        except Exception:continue
        if int(m.get('typeRid') or 0)==type_rid:
            same.append({'rid':mr,'symbol':symbol(mr),'strings':strings(mr)[:20],'externalCalls':sorted(set(ext_by_caller.get(mr,[])))[:30]})
    up_rows=[]
    for x,d in sorted(up.items(),key=lambda z:(z[1],symbol(z[0]))):
        if x==rid:continue
        if interesting(x) or has_storage(x) or has_lua(x):
            up_rows.append({'distance':d,**method_row(x)})
    down_rows=[]
    for x,d in sorted(down.items(),key=lambda z:(z[1],symbol(z[0]))):
        if x==rid:continue
        if interesting(x) or has_storage(x) or has_lua(x):
            down_rows.append({'distance':d,**method_row(x)})
    details.append({
      'target':method_row(rid),
      'typeRecord':t,
      'sameTypeMethods':same,
      'interestingDirectedCallersWithin4':up_rows[:250],
      'interestingDirectedCalleesWithin4':down_rows[:250],
    })

# Find exact non-wrapper methods that themselves bridge Lua + storage.
bridges=[]
for rid in sorted(mm):
    if not (has_lua(rid) and has_storage(rid)):continue
    sym=symbol(rid)
    wrapper=('XLua.CSObjectWrap.' in sym or sym.startswith('XLua.StaticLuaCallbacks.'))
    bridges.append({'wrapper':wrapper,**method_row(rid)})
bridges.sort(key=lambda x:(x['wrapper'],x['symbol']))

# Specifically inspect who calls LuaUIFormLogic.LuaInit and PBController.OnLoadAssets,
# and whether those callers touch Formation/PVP/Hero/UI/resource concepts.
priority=[]
for anchor in (13830,4807):
    up=bfs(anchor,callers,6)
    rows=[]
    for rid,d in sorted(up.items(),key=lambda z:(z[1],symbol(z[0]))):
        if rid==anchor:continue
        blob=(symbol(rid)+' '+' '.join(strings(rid))+' '+' '.join(ext_by_caller.get(rid,[]))).lower()
        hits=[k for k in keywords if k in blob]
        if hits or d<=2:
            rows.append({'distance':d,'hits':hits,**method_row(rid)})
    priority.append({'anchor':method_row(anchor),'upstreamWithin6':rows[:400]})

# Exact string/path-like literals in the priority subgraphs only.
path_re=re.compile(r'(?i)(?:^|[/\\])[^\s]{1,160}\.(?:lua|luac|bytes|txt|json|zip|bundle|prefab|asset)(?:$|[?#])')
path_rows=[]
seen=set()
priority_rids=set(targets)
for p in priority:
    priority_rids.update(x['rid'] for x in p['upstreamWithin6'])
for rid in sorted(priority_rids):
    for s in strings(rid):
        if path_re.search(s) or any(x in s.lower() for x in ('streamingassets','resources/','assetbundle','lua/')):
            key=(rid,s)
            if key not in seen:
                seen.add(key);path_rows.append({'rid':rid,'symbol':symbol(rid),'literal':s})

# Decide only from exact graph facts; no semantic promotion.
if any(x for x in path_rows):
    next_strategy='audit_exact_literal_or_container_from_priority_bridge'
elif any(x for x in priority[0]['upstreamWithin6'] if 'formation' in x['hits'] or 'pvp' in x['hits']):
    next_strategy='inspect_exact_formation_correlated_upstream_of_luauiformlogic'
else:
    next_strategy='trace_luauiformlogic_textasset_argument_source_and_xluamanager_zip_container'

result={
 'format':'WFGG_LASTWAR_FORMATION_LUA_UI_BRIDGE_DETAIL_V1',
 'sources':{'codeAtlas':str(atlas_p)},
 'counts':{
   'methods':len(methods),'types':len(types),'internalEdges':len(internal),'externalTargets':len(external),
   'exactLuaStorageBridges':len(bridges),'nonWrapperLuaStorageBridges':sum(1 for x in bridges if not x['wrapper']),
   'priorityPathLiterals':len(path_rows)
 },
 'targets':details,
 'exactLuaStorageBridges':bridges,
 'priorityUpstream':priority,
 'priorityPathLiterals':path_rows,
 'conclusion':{
   'nextStrategy':next_strategy,
   'rule':'PBController/LuaUIFormLogic are exact graph/storage facts; relevance to Formation remains unproven until a directed or serialized binding is found.'
 },
 'guardrails':{
   'existingAtlasOnly':True,'apkAccess':False,'dllRescan':False,'newExtraction':False,
   'bundleScan':False,'candidatePromotion':False,'mainUntouched':True,'previewUntouched':True
 }
}
out_p.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n','utf-8')

lines=['WfGg Last War — FORMATION LUA UI BRIDGE DETAIL V1','',
 f"methods={len(methods)} exactLuaStorageBridges={len(bridges)} nonWrapper={sum(1 for x in bridges if not x['wrapper'])} priorityPathLiterals={len(path_rows)}",
 f"nextStrategy={next_strategy}",'',
 'TARGET METHODS']
for d in details:
    x=d['target'];lines.append(f"  M:{x['rid']} {x['symbol']}")
    if x['strings']:
        for s in x['strings'][:30]:lines.append('    STRING='+s)
    for e in x['externalCalls'][:50]:lines.append('    EXT='+e)
    lines.append(f"    directCallers={len(x['directCallers'])} directCallees={len(x['directCallees'])} sameTypeMethods={len(d['sameTypeMethods'])}")

lines += ['', 'NON-WRAPPER SAME-METHOD EXACT LUA + STORAGE BRIDGES']
non=[x for x in bridges if not x['wrapper']]
if non:
    for x in non[:100]:
        lines.append(f"  M:{x['rid']} {x['symbol']}")
        for e in x['externalCalls']:
            if any(m in e for m in storage_markers) or any(m.lower() in e.lower() for m in lua_markers):lines.append('    EXT='+e)
        for s in x['strings'][:20]:lines.append('    STRING='+s)
else:lines.append('  NONE')

lines += ['', 'PRIORITY UPSTREAM — LuaUIFormLogic.LuaInit / PBController.OnLoadAssets']
for p in priority:
    a0=p['anchor'];lines.append(f"ANCHOR M:{a0['rid']} {a0['symbol']}")
    for x in p['upstreamWithin6'][:160]:
        lines.append(f"  d={x['distance']} M:{x['rid']} hits={','.join(x['hits']) or '-'} {x['symbol']}")
        for s in x['strings'][:8]:lines.append('    STRING='+s)
        for e in x['externalCalls'][:12]:
            if any(m in e for m in storage_markers) or any(m.lower() in e.lower() for m in lua_markers):lines.append('    EXT='+e)

lines += ['', 'EXACT PATH / CONTAINER LITERALS IN PRIORITY SUBGRAPHS']
if path_rows:
    for x in path_rows[:200]:lines.append(f"  M:{x['rid']} {x['symbol']} :: {x['literal']}")
else:lines.append('  NONE')
lines += ['', 'NEXT '+next_strategy,
 'RULE: exact MethodDef/external-call facts are preserved; UI/Lua naming alone is not promoted to Formation runtime proof.',
 'RULE: no APK read, DLL rescan, extraction, bundle scan, main or preview modification performed.']
report_p.write_text('\n'.join(lines)+'\n','utf-8')

print('FORMATION_LUA_UI_BRIDGE_OK',f'bridges={len(bridges)}',f'nonWrapper={sum(1 for x in bridges if not x["wrapper"])}',f'paths={len(path_rows)}')
for x in non[:20]:print('FORMATION_LUA_UI_BRIDGE_NONWRAP',f"M:{x['rid']}",x['symbol'])
for x in path_rows[:30]:print('FORMATION_LUA_UI_BRIDGE_PATH',f"M:{x['rid']}",x['literal'])
print('FORMATION_LUA_UI_BRIDGE_NEXT',next_strategy)
print('FORMATION_LUA_UI_BRIDGE_JSON',out_p)
print('FORMATION_LUA_UI_BRIDGE_REPORT',report_p)
PY

git add "$OUT"
if ! git diff --cached --quiet; then
  git commit -m "lab: detail exact Formation Lua UI storage bridges"
  git push origin "$BRANCH"
else
  echo "FORMATION_LUA_UI_BRIDGE_GIT unchanged"
fi

echo "FORMATION_LUA_UI_BRIDGE_DONE report=$REPORT"
