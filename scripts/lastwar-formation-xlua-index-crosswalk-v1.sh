#!/data/data/com.termux/files/usr/bin/bash
set -Eeuo pipefail

# WfGg Last War LAB — Formation runtime boundary: existing indexes + XLua/CLR atlas.
# Purpose: decide whether the Formation Lua/script asset is already known before any new extraction.
# NO APK read, NO DLL rescan, NO bundle extraction, NO candidate promotion.

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BRANCH="portal-auth-lastwar-lab-v1"
INDEX="$ROOT/frontend/lab/master-assets-v2/index"
META="$ROOT/frontend/lab/master-assets-v2/meta"
QUERY="$ROOT/scripts/lastwar-graphics-index-query.sh"
ATLAS="$INDEX/lastwar-code-discovery-atlas-v1.json"
HISTORY="$INDEX/lastwar-graphics-history-v002-0012-v1.json"
EVIDENCE="$INDEX/lastwar-graphics-history-evidence-v1.json"
CONNECT="$META/formation-camera-rawimage-connectivity-v1.json"
OUT="$META/formation-xlua-index-crosswalk-v1.json"
REPORT="$HOME/storage/downloads/WFGG_LASTWAR_FORMATION_XLUA_INDEX_CROSSWALK_V1.txt"
TMP="${TMPDIR:-$HOME/.cache}/wfgg-formation-xlua-index-v1"

fail(){ printf 'ERREUR: %s\n' "$*" >&2; exit 1; }
cd "$ROOT"
[[ "$(git branch --show-current)" == "$BRANCH" ]] || fail "branche LAB incorrecte"
[[ -s "$ATLAS" ]] || fail "atlas CLR absent: $ATLAS"
[[ -s "$CONNECT" ]] || fail "connectivite Camera/RawImage absente: $CONNECT"
[[ -s "$QUERY" ]] || fail "query engine graphique absent: $QUERY"
command -v python >/dev/null 2>&1 || fail "python absent"
mkdir -p "$TMP" "$(dirname "$OUT")" "$(dirname "$REPORT")"
rm -f "$TMP"/*.txt 2>/dev/null || true

TERMS=(
  UIHeroPVPFormationPanel
  FormationRT
  FormationBg
  PVPFormation
  HeroPVPFormation
  FormationContent
  HeroShow
)

# Reuse the existing graphics master-index query engine. No APK/bundle access here.
for term in "${TERMS[@]}"; do
  safe="$(printf '%s' "$term" | tr -c 'A-Za-z0-9._-' '_')"
  bash "$QUERY" "$term" > "$TMP/$safe.txt" 2>&1 || true
done

python - "$TMP" "$ATLAS" "$HISTORY" "$EVIDENCE" "$CONNECT" "$OUT" "$REPORT" <<'PY'
from pathlib import Path
from collections import defaultdict
import json,re,sys

tmp, atlas_p, hist_p, evid_p, connect_p, out_p, report_p = map(Path, sys.argv[1:])
terms=['UIHeroPVPFormationPanel','FormationRT','FormationBg','PVPFormation','HeroPVPFormation','FormationContent','HeroShow']
term_lows=[x.lower() for x in terms]
script_markers=('.lua','/lua/','\\lua\\','luac','.bytes','textasset','lua_','lua-','script')

# 1) CURRENT GRAPHICS INDEX — parse only output from the repository's existing query engine.
queries=[]; current_assets=[]; current_bundles=[]; current_discoveries=[]
for term in terms:
    safe=re.sub(r'[^A-Za-z0-9._-]','_',term)
    p=tmp/(safe+'.txt')
    txt=p.read_text('utf-8','replace') if p.is_file() else ''
    m=re.search(r'matches=(\d+)',txt)
    q={'term':term,'matches':int(m.group(1)) if m else None,'lines':[]}
    for line in txt.splitlines():
        s=line.strip()
        if s.startswith('BUNDLE '):
            current_bundles.append({'term':term,'line':s}); q['lines'].append(s)
        elif s.startswith('DISCOVERY '):
            current_discoveries.append({'term':term,'line':s}); q['lines'].append(s)
        elif s.startswith('ASSET '):
            path=s[6:].strip(); row={'term':term,'path':path,'scriptLike':any(x in path.lower() for x in script_markers)}
            current_assets.append(row); q['lines'].append(s)
        elif s.startswith(('LOCATION ','DEPS ','USED_BY ','NAME ')):
            q['lines'].append(s)
    q['lines']=q['lines'][:250]
    queries.append(q)

# Deduplicate current indexed asset hits while preserving which query terms matched.
asset_map={}
for r in current_assets:
    k=r['path']
    x=asset_map.setdefault(k,{'path':k,'terms':[],'scriptLike':r['scriptLike']})
    if r['term'] not in x['terms']: x['terms'].append(r['term'])
    x['scriptLike']=x['scriptLike'] or r['scriptLike']
assets=sorted(asset_map.values(),key=lambda x:(not x['scriptLike'],x['path'].lower()))
script_assets=[x for x in assets if x['scriptLike']]

# 2) HISTORY/EVIDENCE — streaming substring evidence only. This is NOT promoted to a structured relation.
def scan_text_file(path:Path):
    result={'path':str(path),'exists':path.is_file(),'bytes':path.stat().st_size if path.is_file() else None,'termCounts':{},'snippets':[]}
    if not path.is_file(): return result
    # Chunked scan to avoid loading large historical indexes into RAM.
    overlap=''; max_snips=80
    counts=defaultdict(int)
    with path.open('r',encoding='utf-8',errors='replace') as f:
        while True:
            chunk=f.read(1024*1024)
            if not chunk: break
            text=overlap+chunk; low=text.lower()
            for term,tl in zip(terms,term_lows):
                counts[term]+=low.count(tl)
                if len(result['snippets'])<max_snips:
                    start=0
                    while len(result['snippets'])<max_snips:
                        i=low.find(tl,start)
                        if i<0: break
                        a=max(0,i-180); b=min(len(text),i+len(term)+260)
                        snip=re.sub(r'\s+',' ',text[a:b]).strip()
                        result['snippets'].append({'term':term,'text':snip[:520]})
                        start=i+len(tl)
            overlap=text[-512:]
    result['termCounts']=dict(counts)
    return result
hist=scan_text_file(hist_p)
evid=scan_text_file(evid_p)

# 3) CLR / XLua persistent atlas.
a=json.loads(atlas_p.read_text('utf-8'))
connect=json.loads(connect_p.read_text('utf-8'))
types=a.get('types') or []; methods=a.get('methods') or []; external=a.get('externalCalls') or []; internal=a.get('internalEdges') or []
tm={int(x['rid']):x for x in types if x.get('rid') is not None}
mm={int(x['rid']):x for x in methods if x.get('rid') is not None}

def owner(rid):
    m=mm.get(int(rid)) or {}; t=tm.get(int(m.get('typeRid') or 0)) or {}
    return ((str(t.get('namespace'))+'.') if t.get('namespace') else '')+str(t.get('name') or '')
def symbol(rid):
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

callers_of=defaultdict(set); callees_of=defaultdict(set)
for e in internal:
    if not isinstance(e,(list,tuple)) or len(e)<2: continue
    try:c,d=int(e[0]),int(e[1])
    except Exception:continue
    callees_of[c].add(d); callers_of[d].add(c)

# The exact wrapper/register IDs were exposed by the preceding Camera/RawImage connectivity audit.
boundary_rids=[15616,25396,29075,31821,31822]
boundary=[]
for rid in boundary_rids:
    boundary.append({
      'rid':rid,'stableId':f'M:{rid}','symbol':symbol(rid),'owner':owner(rid),
      'strings':strings(rid)[:80],
      'directCallers':[{'rid':x,'symbol':symbol(x)} for x in sorted(callers_of.get(rid,set()))[:100]],
      'directCallees':[{'rid':x,'symbol':symbol(x)} for x in sorted(callees_of.get(rid,set()))[:100]],
    })

# Exact MemberRef targets related to the non-MethodDef Lua/storage boundary.
loader_needles=(
 'xlua','luaenv','lua.lua','luadll','dostring','loadstring','addloader','customloader',
 'textasset','assetbundle.loadasset','resources.load','resourcemanager','loadasset'
)
loader_targets=[]; loader_callers=set(); target_by_caller=defaultdict(set)
for row in external:
    target=str(row.get('target') or '')
    low=target.lower()
    if not any(n in low for n in loader_needles): continue
    callers=[]
    for x in row.get('callerRids') or []:
        try: callers.append(int(x))
        except Exception: pass
    loader_targets.append({'target':target,'classification':row.get('classification'),'callerRids':callers})
    for rid in callers:
        loader_callers.add(rid); target_by_caller[rid].add(target)

# Correlation only: Formation terms in symbol/string AND exact call to a loader/Lua MemberRef.
formation_loader=[]
for rid in sorted(loader_callers):
    sym=symbol(rid); ss=strings(rid)
    blob=(sym+' '+' '.join(ss)).lower()
    hits=[t for t,tl in zip(terms,term_lows) if tl in blob]
    if hits:
        formation_loader.append({
          'rid':rid,'stableId':f'M:{rid}','symbol':sym,'matchedFormationTerms':hits,
          'strings':[s for s in ss if any(tl in s.lower() for tl in term_lows)][:60],
          'exactLoaderTargets':sorted(target_by_caller[rid]),
          'evidenceLevel':'exact_loader_call_plus_name_or_string_correlation_not_runtime_binding_proof'
        })

# Methods around the wrapper path are exact MethodDef graph facts; semantics are still interpreted cautiously.
path_rows=[]
for path in ([25396,15616,29075],[31821],[31822]):
    path_rows.append([{'rid':rid,'symbol':symbol(rid)} for rid in path])

if script_assets:
    strategy='inspect_or_extract_exact_indexed_formation_script_asset'
elif formation_loader:
    strategy='trace_exact_loader_container_from_formation_correlated_clr_method'
else:
    strategy='trace_xlua_loader_storage_boundary_then_targeted_container_audit'

result={
 'format':'WFGG_LASTWAR_FORMATION_XLUA_INDEX_CROSSWALK_V1',
 'sources':{
   'graphicsQueryEngine':'scripts/lastwar-graphics-index-query.sh',
   'codeAtlas':str(atlas_p),
   'history':str(hist_p),
   'historyEvidence':str(evid_p),
   'cameraRawConnectivity':str(connect_p),
 },
 'precondition':{
   'directedCameraRawMethodDefPaths':(connect.get('counts') or {}).get('directedCameraRawPaths'),
   'formationCommonUpstream':(connect.get('counts') or {}).get('formationCommonUpstream'),
   'note':'Previous audit found no Formation-correlated C# MethodDef producer-consumer chain; XLua registration is the closest non-business boundary.'
 },
 'currentGraphicsIndex':{
   'queries':queries,
   'uniqueAssetHitCount':len(assets),
   'scriptLikeAssetHitCount':len(script_assets),
   'assets':assets[:500],
   'scriptLikeAssets':script_assets[:300],
   'bundleLines':current_bundles[:400],
   'discoveryLines':current_discoveries[:400],
 },
 'historicalTextEvidence':{'history':hist,'evidence':evid,'rule':'substring occurrence/snippet only; never promoted to structured exact relation'},
 'clrXluaBoundary':{
   'atlasCounts':a.get('counts') or {},
   'exactBoundaryMethods':boundary,
   'knownWrapperPaths':path_rows,
   'loaderTargetCount':len(loader_targets),
   'loaderCallerCount':len(loader_callers),
   'loaderTargets':loader_targets[:600],
   'formationCorrelatedLoaderMethodCount':len(formation_loader),
   'formationCorrelatedLoaderMethods':formation_loader[:300],
 },
 'conclusion':{
   'indexedFormationScriptLikeAssetFound':bool(script_assets),
   'formationCorrelatedClrLoaderFound':bool(formation_loader),
   'nextStrategy':strategy,
   'important':'XLua is the highest-priority boundary, not yet proven to be the Formation texture assignment implementation.'
 },
 'guardrails':{
   'existingIndexesOnly':True,'apkAccess':False,'dllRescan':False,'newExtraction':False,
   'bundleScan':False,'candidatePromotion':False,'mainUntouched':True,'previewUntouched':True
 }
}
out_p.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n','utf-8')

lines=[
 'WfGg Last War — FORMATION XLUA / INDEX CROSSWALK V1','',
 f"currentIndex uniqueAssets={len(assets)} scriptLikeAssets={len(script_assets)}",
 f"clr loaderTargets={len(loader_targets)} loaderCallers={len(loader_callers)} formationCorrelatedLoaderMethods={len(formation_loader)}",
 f"nextStrategy={strategy}",'',
 'CURRENT INDEX QUERY COUNTS'
]
for q in queries: lines.append(f"  {q['term']}: matches={q['matches']}")
lines += ['', 'SCRIPT-LIKE ASSETS ALREADY INDEXED']
if script_assets:
    for x in script_assets[:120]: lines.append(f"  terms={','.join(x['terms'])} path={x['path']}")
else: lines.append('  NONE')
lines += ['', 'EXACT XLUA / BOUNDARY METHODS']
for x in boundary:
    lines.append(f"  M:{x['rid']} symbol={x['symbol']} callers={len(x['directCallers'])} callees={len(x['directCallees'])}")
lines += ['', 'FORMATION-CORRELATED CLR METHODS WITH EXACT LUA/LOADER CALLS']
if formation_loader:
    for x in formation_loader[:100]:
        lines.append(f"  M:{x['rid']} terms={','.join(x['matchedFormationTerms'])} symbol={x['symbol']}")
        for t in x['exactLoaderTargets'][:12]: lines.append('    target='+t)
else: lines.append('  NONE')
lines += ['', 'HISTORY TERM COUNTS']
for src in (hist,evid):
    lines.append(f"  {Path(src['path']).name}: "+' '.join(f"{k}={v}" for k,v in src.get('termCounts',{}).items()))
lines += ['', 'NEXT '+strategy,
 'RULE: index hits and exact CLR calls remain separate evidence classes. Name/string correlation is not promoted to runtime proof.',
 'RULE: no APK read, DLL rescan, extraction, bundle scan, main or preview modification performed.'
]
report_p.write_text('\n'.join(lines)+'\n','utf-8')

print('FORMATION_XLUA_INDEX_OK',f'assets={len(assets)}',f'scriptLike={len(script_assets)}',f'loaderTargets={len(loader_targets)}',f'formationLoader={len(formation_loader)}')
for x in script_assets[:30]: print('FORMATION_XLUA_INDEX_SCRIPT',','.join(x['terms']),x['path'])
for x in formation_loader[:30]: print('FORMATION_XLUA_INDEX_LOADER',f"M:{x['rid']}",','.join(x['matchedFormationTerms']),x['symbol'])
print('FORMATION_XLUA_INDEX_NEXT',strategy)
print('FORMATION_XLUA_INDEX_JSON',out_p)
print('FORMATION_XLUA_INDEX_REPORT',report_p)
PY

git add "$OUT"
if ! git diff --cached --quiet; then git commit -m "lab: map Formation XLua boundary through existing indexes"; fi
git push origin "$BRANCH"
printf '%s\n' '=== FORMATION XLUA / INDEX CROSSWALK V1 TERMINE ===' "JSON: $OUT" "Rapport: $REPORT"
