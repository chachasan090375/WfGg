#!/data/data/com.termux/files/usr/bin/bash
set -Eeuo pipefail

# WfGg Last War LAB — trace the two exact Lua storage axes already exposed:
# 1) LuaUIFormLogic.LuaInit -> TextAsset source
# 2) XLuaManager.Initialize -> encrypted/zip Lua container
# Existing repository metadata only. NO APK read, NO DLL rescan, NO extraction.

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BRANCH="portal-auth-lastwar-lab-v1"
INDEX="$ROOT/frontend/lab/master-assets-v2/index"
META="$ROOT/frontend/lab/master-assets-v2/meta"
ATLAS="$INDEX/lastwar-code-discovery-atlas-v1.json"
OUT="$META/formation-lua-source-container-crosswalk-v1.json"
REPORT="$HOME/storage/downloads/WFGG_LASTWAR_FORMATION_LUA_SOURCE_CONTAINER_CROSSWALK_V1.txt"

fail(){ printf 'ERREUR: %s\n' "$*" >&2; exit 1; }
cd "$ROOT"
[[ "$(git branch --show-current)" == "$BRANCH" ]] || fail "branche LAB incorrecte"
[[ -s "$ATLAS" ]] || fail "atlas CLR absent: $ATLAS"
command -v python >/dev/null 2>&1 || fail "python absent"
mkdir -p "$META" "$(dirname "$REPORT")"

python - "$ROOT" "$ATLAS" "$OUT" "$REPORT" <<'PY'
from pathlib import Path
from collections import defaultdict,deque
import json,re,sys
root, atlas_p, out_p, report_p = map(Path,sys.argv[1:])
a=json.loads(atlas_p.read_text('utf-8'))
methods=a.get('methods') or []; types=a.get('types') or []; internal=a.get('internalEdges') or []; external=a.get('externalCalls') or []
mm={int(x['rid']):x for x in methods if x.get('rid') is not None}
tm={int(x['rid']):x for x in types if x.get('rid') is not None}

def owner(rid):
    m=mm.get(int(rid)) or {}; t=tm.get(int(m.get('typeRid') or 0)) or {}
    return ((str(t.get('namespace'))+'.') if t.get('namespace') else '')+str(t.get('name') or '')
def sym(rid):
    m=mm.get(int(rid)) or {}; o=owner(rid); return (o+'.' if o else '')+str(m.get('name') or f'M:{rid}')
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

callers=defaultdict(set); callees=defaultdict(set)
for e in internal:
    if not isinstance(e,(list,tuple)) or len(e)<2: continue
    try:c,d=int(e[0]),int(e[1])
    except Exception:continue
    callees[c].add(d); callers[d].add(c)

ext_by_caller=defaultdict(list)
for row in external:
    target=str(row.get('target') or '')
    for x in row.get('callerRids') or []:
        try: ext_by_caller[int(x)].append(target)
        except Exception: pass
for rid in list(ext_by_caller): ext_by_caller[rid]=sorted(set(ext_by_caller[rid]))

TARGETS=[13830,4807,4809,4806,14817,14819,16002,16003]

def method_record(rid):
    m=mm.get(rid) or {}
    return {
      'rid':rid,'symbol':sym(rid),'owner':owner(rid),
      'methodRowKeys':sorted(m.keys()),
      'methodRow':m,
      'strings':strings(rid),
      'externalCalls':ext_by_caller.get(rid,[]),
      'directCallers':[{'rid':x,'symbol':sym(x)} for x in sorted(callers.get(rid,set()))],
      'directCallees':[{'rid':x,'symbol':sym(x)} for x in sorted(callees.get(rid,set()))],
    }

# Same-type context for LuaUIFormLogic, PBController, XLuaManager and StaticLuaCallbacks.
context={}
for seed in (13830,4807,14817,16002):
    tid=int((mm.get(seed) or {}).get('typeRid') or 0)
    rows=[]
    for rid,m in mm.items():
        if int(m.get('typeRid') or 0)!=tid: continue
        rows.append({
          'rid':rid,'symbol':sym(rid),'name':m.get('name'),
          'strings':strings(rid),
          'externalCalls':ext_by_caller.get(rid,[]),
          'callers':sorted(callers.get(rid,set())),
          'callees':sorted(callees.get(rid,set())),
          'rowKeys':sorted(m.keys())
        })
    rows.sort(key=lambda x:x['rid'])
    context[sym(seed).rsplit('.',1)[0]]={'typeRid':tid,'typeRow':tm.get(tid,{}),'methods':rows}

# TextAsset-related methods in LuaUIFormLogic type; this is exact call evidence only.
lua_tid=int((mm.get(13830) or {}).get('typeRid') or 0)
lua_type_textasset=[]
for rid,m in mm.items():
    if int(m.get('typeRid') or 0)!=lua_tid: continue
    ex=ext_by_caller.get(rid,[])
    hits=[x for x in ex if 'TextAsset' in x or 'VEngine.Asset' in x or 'Asset.get_asset' in x]
    if hits:
        lua_type_textasset.append({'rid':rid,'symbol':sym(rid),'externalHits':hits,'strings':strings(rid)})

# Whole atlas methods that mention/call LuaUIFormLogic by symbol/string. No semantic promotion.
term_hits=[]
need=('luauiformlogic','luainit')
for rid,m in mm.items():
    blob=(sym(rid)+' '+' '.join(strings(rid))).lower()
    hs=[n for n in need if n in blob]
    if hs:
        term_hits.append({'rid':rid,'symbol':sym(rid),'hits':hs,'strings':strings(rid)})

# Directed neighborhood around PB reload chain and XLuaManager initialization.
def upstream(seed,maxd=5):
    dist={seed:0};q=deque([seed])
    while q:
        x=q.popleft();d=dist[x]
        if d>=maxd:continue
        for y in callers.get(x,()):
            if y not in dist:dist[y]=d+1;q.append(y)
    return dist

def downstream(seed,maxd=4):
    dist={seed:0};q=deque([seed])
    while q:
        x=q.popleft();d=dist[x]
        if d>=maxd:continue
        for y in callees.get(x,()):
            if y not in dist:dist[y]=d+1;q.append(y)
    return dist

neighborhood={}
for seed in (13830,4807,14817,14819):
    up=upstream(seed,6); dn=downstream(seed,4)
    rows=[]
    ids=set(up)|set(dn)
    for rid in ids:
        rows.append({
          'rid':rid,'symbol':sym(rid),'upstreamDistance':up.get(rid),
          'downstreamDistance':dn.get(rid),'strings':strings(rid),
          'externalCalls':ext_by_caller.get(rid,[])
        })
    rows.sort(key=lambda x:(999 if x['upstreamDistance'] is None else x['upstreamDistance'],999 if x['downstreamDistance'] is None else x['downstreamDistance'],x['rid']))
    neighborhood[f'M:{seed}']={'symbol':sym(seed),'rows':rows}

# Search already-generated repo metadata (NOT APK/DLL) for references that may expose a
# serialized TextAsset field, loader name, zip/container name, or Lua path.
meta_hits=[]
terms=['LuaUIFormLogic','LuaInit','XLuaManager','PBController','Load_luaUtil','FromChachaToPKZip','IsChachaTable']
roots=[root/'frontend/lab/master-assets-v2/index',root/'frontend/lab/master-assets-v2/meta']
allowed={'.json','.txt','.tsv','.csv','.md'}
for base in roots:
    if not base.is_dir(): continue
    for p in base.rglob('*'):
        if not p.is_file() or p.suffix.lower() not in allowed or p==atlas_p or p==out_p: continue
        try:
            if p.stat().st_size>80*1024*1024: continue
            txt=p.read_text('utf-8','replace')
        except Exception: continue
        low=txt.lower(); hs=[t for t in terms if t.lower() in low]
        if not hs: continue
        snippets=[]
        for t in hs:
            tl=t.lower(); pos=0
            while len(snippets)<16:
                i=low.find(tl,pos)
                if i<0: break
                s=re.sub(r'\s+',' ',txt[max(0,i-180):min(len(txt),i+len(t)+260)]).strip()
                snippets.append({'term':t,'text':s[:520]}); pos=i+len(tl)
        meta_hits.append({'path':str(p.relative_to(root)),'terms':hs,'snippets':snippets})
meta_hits=meta_hits[:250]

# Container-relevant exact calls in XLuaManager type.
x_tid=int((mm.get(14817) or {}).get('typeRid') or 0)
container_needles=('ZipFile','File.OpenRead','File.ReadAllBytes','MemoryStream','Stream.Read','FromChachaToPKZip','IsChachaTable','TextAsset','AssetBundle','Resources.Load')
xlua_container=[]
for rid,m in mm.items():
    if int(m.get('typeRid') or 0)!=x_tid:continue
    ex=ext_by_caller.get(rid,[])
    hits=[x for x in ex if any(n.lower() in x.lower() for n in container_needles)]
    ss=strings(rid)
    if hits or ss:
        xlua_container.append({'rid':rid,'symbol':sym(rid),'externalHits':hits,'strings':ss})

# Conservative next-step selection.
serialized_source_hits=[x for x in meta_hits if any(t in x['terms'] for t in ('LuaUIFormLogic','LuaInit'))]
container_named_hits=[]
for x in xlua_container:
    for s in x['strings']:
        sl=s.lower()
        if any(k in sl for k in ('.zip','.lua','.bytes','streamingassets','chacha','script','luac')):
            container_named_hits.append({'rid':x['rid'],'symbol':x['symbol'],'literal':s})

if serialized_source_hits:
    next_strategy='inspect_existing_serialized_luauiformlogic_source_evidence'
elif container_named_hits:
    next_strategy='audit_exact_named_xlua_container_read_only'
else:
    next_strategy='targeted_serialized_component_and_xluamanager_container_locator'

result={
 'format':'WFGG_LASTWAR_FORMATION_LUA_SOURCE_CONTAINER_CROSSWALK_V1',
 'counts':{
   'methods':len(methods),'types':len(types),
   'luaTypeTextAssetMethods':len(lua_type_textasset),
   'luaNameOrStringHits':len(term_hits),
   'existingMetadataHits':len(meta_hits),
   'serializedSourceMetadataHits':len(serialized_source_hits),
   'xluaContainerMethods':len(xlua_container),
   'xluaNamedContainerLiterals':len(container_named_hits),
 },
 'targetMethods':[method_record(x) for x in TARGETS],
 'sameTypeContext':context,
 'luaUIFormLogicTextAssetMethods':lua_type_textasset,
 'luaUIFormLogicNameOrStringHits':term_hits,
 'directedNeighborhoods':neighborhood,
 'existingMetadataHits':meta_hits,
 'xluaManagerContainerMethods':xlua_container,
 'xluaNamedContainerLiterals':container_named_hits,
 'conclusion':{
   'luaInitHasDirectMethodDefCallers':bool(callers.get(13830)),
   'pbOnLoadAssetsIsExactLuaTextAssetBridge':('UnityEngine.TextAsset.get_bytes' in ext_by_caller.get(4807,[]) and any('Load_luaUtil' in x for x in ext_by_caller.get(4807,[]))),
   'nextStrategy':next_strategy,
   'rule':'No TextAsset source/container is promoted unless backed by exact serialized or call evidence.'
 },
 'guardrails':{'existingRepositoryMetadataOnly':True,'apkAccess':False,'dllRescan':False,'newExtraction':False,'bundleScan':False,'candidatePromotion':False,'mainUntouched':True,'previewUntouched':True}
}
out_p.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n','utf-8')

lines=['WfGg Last War — FORMATION LUA SOURCE / CONTAINER CROSSWALK V1','',
 f"methods={len(methods)} luaTypeTextAssetMethods={len(lua_type_textasset)} luaNameOrStringHits={len(term_hits)}",
 f"existingMetadataHits={len(meta_hits)} serializedSourceMetadataHits={len(serialized_source_hits)} xluaContainerMethods={len(xlua_container)} namedContainerLiterals={len(container_named_hits)}",
 f"nextStrategy={next_strategy}",'',
 'LUAUIFORMLOGIC — EXACT TEXTASSET / ASSET CALLS']
for x in lua_type_textasset:
    lines.append(f"  M:{x['rid']} {x['symbol']}")
    for e in x['externalHits']: lines.append('    EXT='+e)
    for s in x['strings'][:20]: lines.append('    STRING='+repr(s))
if not lua_type_textasset:lines.append('  NONE')
lines+=['','LUAUIFORMLOGIC — METHODDEF CALLER FACT',f"  LuaInit directCallers={len(callers.get(13830,set()))}"]
for rid in sorted(callers.get(13830,set())):lines.append(f"    M:{rid} {sym(rid)}")
lines+=['','PB CONTROLLER — EXACT RELOAD CHAIN']
for rid in (4806,4809,4807):
    lines.append(f"  M:{rid} {sym(rid)}")
    for e in ext_by_caller.get(rid,[]):
        if any(k in e for k in ('TextAsset','VEngine.Asset','Load_luaUtil')): lines.append('    EXT='+e)
    for s in strings(rid)[:30]:lines.append('    STRING='+repr(s))
lines+=['','XLUAMANAGER — CONTAINER-RELEVANT METHODS']
for x in xlua_container:
    lines.append(f"  M:{x['rid']} {x['symbol']}")
    for e in x['externalHits'][:30]:lines.append('    EXT='+e)
    for s in x['strings'][:30]:lines.append('    STRING='+repr(s))
lines+=['','EXISTING METADATA HITS (NO APK/DLL READ)']
if meta_hits:
    for x in meta_hits[:80]:
        lines.append(f"  FILE {x['path']} terms={','.join(x['terms'])}")
        for sn in x['snippets'][:5]:lines.append(f"    {sn['term']}: {sn['text']}")
else:lines.append('  NONE')
lines+=['','EXACT/NAMED XLUA CONTAINER LITERALS']
if container_named_hits:
    for x in container_named_hits:lines.append(f"  M:{x['rid']} {x['symbol']} literal={x['literal']!r}")
else:lines.append('  NONE')
lines+=['','NEXT '+next_strategy,
 'RULE: TextAsset source/container requires exact serialized or call evidence; names/proximity remain correlation only.',
 'RULE: no APK read, DLL rescan, extraction, bundle scan, main or preview modification performed.']
report_p.write_text('\n'.join(lines)+'\n','utf-8')

print('FORMATION_LUA_SOURCE_CONTAINER_OK',f'luaTextAsset={len(lua_type_textasset)}',f'metaHits={len(meta_hits)}',f'namedContainer={len(container_named_hits)}')
print('FORMATION_LUA_SOURCE_CONTAINER_NEXT',next_strategy)
print('FORMATION_LUA_SOURCE_CONTAINER_JSON',out_p)
print('FORMATION_LUA_SOURCE_CONTAINER_REPORT',report_p)
PY

git add "$OUT"
if ! git diff --cached --quiet; then
  git commit -m "lab: crosswalk Lua TextAsset source and XLua container"
  git push origin "$BRANCH"
else
  echo "FORMATION_LUA_SOURCE_CONTAINER_GIT unchanged"
fi

echo "FORMATION_LUA_SOURCE_CONTAINER_DONE"
