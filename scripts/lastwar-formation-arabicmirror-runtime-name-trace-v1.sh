#!/data/data/com.termux/files/usr/bin/bash
set -Eeuo pipefail

# WfGg Last War LAB — ArabicMirror producer check + exact FormationBg/FormationRT runtime-name trace.
# Existing CLR atlas + exact owner junction only. NO APK read, NO DLL rescan, NO bundle scan/extraction.

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BRANCH="portal-auth-lastwar-lab-v1"
ATLAS="$ROOT/frontend/lab/master-assets-v2/index/lastwar-code-discovery-atlas-v1.json"
JUNCTION="$ROOT/frontend/lab/master-assets-v2/meta/formation-rawimage-owner-clr-junction-v2.json"
OUT="$ROOT/frontend/lab/master-assets-v2/meta/formation-arabicmirror-runtime-name-trace-v1.json"
REPORT="$HOME/storage/downloads/WFGG_LASTWAR_FORMATION_ARABICMIRROR_RUNTIME_NAME_TRACE_V1.txt"

fail(){ printf 'ERREUR: %s\n' "$*" >&2; exit 1; }
cd "$ROOT"
[[ "$(git branch --show-current)" == "$BRANCH" ]] || fail "branche LAB incorrecte"
[[ -s "$ATLAS" ]] || fail "atlas CLR absent: $ATLAS"
[[ -s "$JUNCTION" ]] || fail "junction V2 absent: $JUNCTION"
command -v python >/dev/null 2>&1 || fail "python absent"
mkdir -p "$(dirname "$OUT")" "$(dirname "$REPORT")"

python - "$ATLAS" "$JUNCTION" "$OUT" "$REPORT" <<'PY'
from __future__ import annotations
from pathlib import Path
from collections import defaultdict, deque
import json,sys

atlasp,juncp,outp,reportp=map(Path,sys.argv[1:])
a=json.loads(atlasp.read_text('utf-8'))
j=json.loads(juncp.read_text('utf-8'))

# Guard against silently using the broken zero-node junction.
counts=j.get('counts') or {}
if int(counts.get('ptrObjects') or 0) != 3209:
    raise SystemExit(f'JUNCTION_V2_PTR_OBJECT_COUNT_MISMATCH expected=3209 actual={counts.get("ptrObjects")}')

methods=a.get('methods') or []
types=a.get('types') or []
internal=a.get('internalEdges') or []
external=a.get('externalCalls') or []
if len(methods) < 50000 or len(types) < 5000:
    raise SystemExit(f'ATLAS_UNEXPECTED_SIZE methods={len(methods)} types={len(types)}')

type_by_rid={int(t['rid']):t for t in types}
method_by_rid={int(m['rid']):m for m in methods}
methods_by_type=defaultdict(list)
for m in methods:
    if m.get('typeRid') is not None: methods_by_type[int(m['typeRid'])].append(m)

def full_type(t):
    return ((str(t.get('namespace'))+'.') if t.get('namespace') else '')+str(t.get('name') or '')

def symbol(m):
    t=type_by_rid.get(int(m.get('typeRid') or 0))
    return ((full_type(t)+'.') if t else '')+str(m.get('name') or '')

def string_values(m):
    vals=m.get('strings') or []
    out=[]
    for x in vals:
        if isinstance(x,str): out.append(x)
        elif isinstance(x,dict):
            for k in ('value','text','string','literal'):
                if isinstance(x.get(k),str): out.append(x[k]); break
        else: out.append(str(x))
    return out

# Exact external MemberRef calls keyed by caller RID.
ext_by_caller=defaultdict(list)
for ex in external:
    target=str(ex.get('target') or '')
    for rid in ex.get('callerRids') or []:
        try: rid=int(rid)
        except: continue
        ext_by_caller[rid].append({'target':target,'classification':ex.get('classification'),'tags':ex.get('tags') or []})

def api_kind(target):
    s=target.lower()
    # Texture consumers / readers.
    if 'unityengine.ui.rawimage' in s and ('get_texture' in s or '.get_texture' in s): return 'RawImage.get_texture','read'
    if 'unityengine.ui.rawimage' in s and ('set_texture' in s or '.set_texture' in s): return 'RawImage.set_texture','write'
    if 'unityengine.ui.image' in s and ('set_sprite' in s or '.set_sprite' in s): return 'Image.set_sprite','write'
    if 'camera' in s and ('set_targettexture' in s or 'set_target_texture' in s): return 'Camera.set_targetTexture','write'
    if 'camera' in s and ('get_targettexture' in s or 'get_target_texture' in s): return 'Camera.get_targetTexture','read'
    if 'videoplayer' in s and ('set_targettexture' in s or 'set_target_texture' in s): return 'VideoPlayer.set_targetTexture','write'
    if 'rendertexture' in s:
        # Constructor/Create/GetTemporary can produce, getters/read-only cannot be safely collapsed.
        if any(x in s for x in ('.ctor','create','gettemporary','set_')): return 'RenderTexture.producer_or_mutator','write'
        return 'RenderTexture','other'
    if 'graphics' in s and 'blit' in s: return 'Graphics.Blit','write'
    if 'commandbuffer' in s and 'blit' in s: return 'CommandBuffer.Blit','write'
    if 'material' in s and ('settexture' in s or 'set_texture' in s): return 'Material.SetTexture','write'
    if 'shader' in s and ('setglobaltexture' in s or 'set_global_texture' in s): return 'Shader.SetGlobalTexture','write'
    return None,None

def lookup_kind(target):
    s=target.lower()
    if 'gameobject.find' in s: return 'GameObject.Find'
    if 'transform.find' in s: return 'Transform.Find'
    if 'getcomponent' in s: return 'GetComponent'
    if 'findobject' in s or 'findfirstobject' in s or 'findanyobject' in s: return 'FindObject'
    if 'resources.load' in s: return 'Resources.Load'
    if 'assetbundle.load' in s: return 'AssetBundle.Load'
    return None

# -------- ArabicMirror exact type audit --------
arabic_types=[t for t in types if full_type(t)=='ArabicMirror' or (str(t.get('name') or '')=='ArabicMirror' and not t.get('namespace'))]
if len(arabic_types)!=1:
    raise SystemExit('ARABICMIRROR_TYPE_NOT_UNIQUE count='+str(len(arabic_types)))
arabic_t=arabic_types[0]
arabic_rid=int(arabic_t['rid'])
if arabic_rid != 1199:
    raise SystemExit(f'ARABICMIRROR_RID_DRIFT expected=1199 actual={arabic_rid}')
arabic_methods=sorted(methods_by_type.get(arabic_rid,[]),key=lambda m:int(m['rid']))
if len(arabic_methods)!=21:
    raise SystemExit(f'ARABICMIRROR_METHOD_COUNT_DRIFT expected=21 actual={len(arabic_methods)}')

arabic_rows=[];arabic_read=[];arabic_write=[];arabic_lookup=[]
for m in arabic_methods:
    rid=int(m['rid']);apis=[];lookups=[]
    for ex in ext_by_caller.get(rid,[]):
        k,mode=api_kind(ex['target'])
        if k: apis.append({**ex,'api':k,'mode':mode})
        lk=lookup_kind(ex['target'])
        if lk: lookups.append({**ex,'lookup':lk})
    row={'rid':rid,'symbol':symbol(m),'name':m.get('name'),'strings':string_values(m),'externalCalls':ext_by_caller.get(rid,[]),'renderTextureApis':apis,'lookupApis':lookups,'callers':m.get('callers') or [],'callees':m.get('callees') or []}
    arabic_rows.append(row)
    arabic_read += [{'rid':rid,'symbol':symbol(m),**x} for x in apis if x['mode']=='read']
    arabic_write += [{'rid':rid,'symbol':symbol(m),**x} for x in apis if x['mode']=='write']
    arabic_lookup += [{'rid':rid,'symbol':symbol(m),**x} for x in lookups]

# External callers into ArabicMirror from other CLR types: useful to establish whether it is generic UI plumbing.
arabic_ids={int(m['rid']) for m in arabic_methods}
rev=defaultdict(list);adj=defaultdict(list)
for e in internal:
    if isinstance(e,(list,tuple)) and len(e)>=2:
        try:x,y=int(e[0]),int(e[1])
        except:continue
        adj[x].append(y);rev[y].append(x)
external_into=[]
for target in sorted(arabic_ids):
    for caller in rev.get(target,[]):
        if caller not in arabic_ids:
            cm=method_by_rid.get(caller)
            external_into.append({'callerRid':caller,'callerSymbol':symbol(cm) if cm else str(caller),'targetRid':target,'targetSymbol':symbol(method_by_rid[target])})

# -------- exact FormationBg / FormationRT literal carriers --------
NEEDLES=('FormationBg','FormationRT')
exact_carriers=[];containing_carriers=[]
for m in methods:
    vals=string_values(m)
    exact=[n for n in NEEDLES if n in vals]
    contain=[n for n in NEEDLES if any(n in v for v in vals)]
    if exact:
        exact_carriers.append({'rid':int(m['rid']),'symbol':symbol(m),'needles':exact,'strings':vals,'externalCalls':ext_by_caller.get(int(m['rid']),[])})
    elif contain:
        containing_carriers.append({'rid':int(m['rid']),'symbol':symbol(m),'needles':contain,'strings':vals,'externalCalls':ext_by_caller.get(int(m['rid']),[])})

# Same-method exact lookup/render evidence on literal carriers.
def classify_method(rid):
    looks=[];apis=[]
    for ex in ext_by_caller.get(rid,[]):
        lk=lookup_kind(ex['target'])
        if lk:looks.append({**ex,'lookup':lk})
        ak,mode=api_kind(ex['target'])
        if ak:apis.append({**ex,'api':ak,'mode':mode})
    return looks,apis

same_method=[]
for c in exact_carriers:
    looks,apis=classify_method(c['rid'])
    if looks or apis:
        same_method.append({**c,'lookupApis':looks,'renderTextureApis':apis})

# Directed paths from exact literal carriers to a method that calls a WRITE render/texture API.
write_callers=set()
write_meta=defaultdict(list)
for rid,rows in ext_by_caller.items():
    for ex in rows:
        k,mode=api_kind(ex['target'])
        if k and mode=='write':
            write_callers.add(rid);write_meta[rid].append({**ex,'api':k,'mode':mode})

paths=[];MAX_DEPTH=5
for c in exact_carriers:
    start=c['rid']
    q=deque([start]);parent={start:None};depth={start:0};found=[]
    while q:
        x=q.popleft();d=depth[x]
        if d>=MAX_DEPTH: continue
        for y in adj.get(x,[]):
            if y in parent: continue
            parent[y]=x;depth[y]=d+1
            if y in write_callers: found.append(y)
            q.append(y)
    for target in sorted(found,key=lambda z:(depth[z],z))[:8]:
        chain=[];x=target
        while x is not None:chain.append(x);x=parent[x]
        chain.reverse()
        paths.append({'needleMethods':[start],'depth':len(chain)-1,'rids':chain,'symbols':[symbol(method_by_rid[r]) if r in method_by_rid else str(r) for r in chain],'targetWriteApis':write_meta[target]})

# Also inspect exact upstream callers (<=3 hops) of literal carriers for business-owner context.
upstream=[]
for c in exact_carriers:
    start=c['rid'];q=deque([start]);dist={start:0}
    while q:
        x=q.popleft();d=dist[x]
        if d>=3:continue
        for y in rev.get(x,[]):
            if y not in dist:dist[y]=d+1;q.append(y)
    for rid,d in sorted(dist.items(),key=lambda kv:(kv[1],kv[0])):
        if rid==start:continue
        m=method_by_rid.get(rid)
        if m:upstream.append({'carrierRid':start,'distance':d,'rid':rid,'symbol':symbol(m),'strings':string_values(m)})

# Decision tree: do not treat a getter as producer evidence.
if arabic_write:
    next_strategy='inspect_arabicmirror_exact_texture_write_methods'
elif exact_carriers and (same_method or paths):
    next_strategy='inspect_exact_formation_name_lookup_to_texture_write_chain'
elif exact_carriers:
    next_strategy='inspect_exact_formation_name_literal_carriers_and_callers'
else:
    next_strategy='targeted_il_string_xref_for_formationbg_formationrt_required'

result={
 'format':'WFGG_LASTWAR_FORMATION_ARABICMIRROR_RUNTIME_NAME_TRACE_V1',
 'sources':{'atlas':str(atlasp),'junctionV2':str(juncp)},
 'counts':{
   'atlasTypes':len(types),'atlasMethods':len(methods),'arabicMirrorMethods':len(arabic_methods),
   'arabicMirrorReadApis':len(arabic_read),'arabicMirrorWriteApis':len(arabic_write),'arabicMirrorLookupApis':len(arabic_lookup),
   'externalClrCallersIntoArabicMirror':len(external_into),
   'exactFormationNameLiteralMethods':len(exact_carriers),'containingFormationNameLiteralMethods':len(containing_carriers),
   'exactCarrierSameMethodLookupOrRender':len(same_method),'directedExactCarrierToWritePaths':len(paths),
 },
 'arabicMirror':{'typeRid':arabic_rid,'fullName':full_type(arabic_t),'methods':arabic_rows,'readApis':arabic_read,'writeApis':arabic_write,'lookupApis':arabic_lookup,'externalClrCallers':external_into},
 'exactFormationNameLiteralMethods':exact_carriers,
 'containingFormationNameLiteralMethods':containing_carriers,
 'exactCarrierSameMethodEvidence':same_method,
 'directedExactCarrierToTextureWritePaths':paths,
 'exactCarrierUpstreamCallers':upstream[:300],
 'conclusion':{
   'arabicMirrorHasTextureProducerEvidence':bool(arabic_write),
   'getterOnlyDoesNotProveAssignment':True,
   'nextStrategy':next_strategy,
 },
 'guardrails':{'existingAtlasOnly':True,'apkAccess':False,'dllRescan':False,'bundleExtraction':False,'bundleScan':False,'candidatePromotion':False,'mainUntouched':True,'previewUntouched':True}
}
outp.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n','utf-8')

lines=['WfGg Last War — ARABICMIRROR + FORMATION RUNTIME NAME TRACE V1','',
 f"atlasTypes={len(types)} atlasMethods={len(methods)} arabicMirrorMethods={len(arabic_methods)}",
 f"arabicReadApis={len(arabic_read)} arabicWriteApis={len(arabic_write)} arabicLookupApis={len(arabic_lookup)} externalCallersIntoArabicMirror={len(external_into)}",
 f"exactFormationNameLiteralMethods={len(exact_carriers)} containingFormationNameLiteralMethods={len(containing_carriers)} sameMethodEvidence={len(same_method)} directedWritePaths={len(paths)}",
 f"nextStrategy={next_strategy}",'',
 'ARABICMIRROR EXACT RENDER / TEXTURE CALLS']
for r in arabic_rows:
    for x in r['renderTextureApis']:
        lines.append(f"  M:{r['rid']} {r['symbol']} mode={x['mode']} api={x['api']} target={x['target']}")
if not arabic_read and not arabic_write:lines.append('  NONE')
lines += ['', 'ARABICMIRROR EXTERNAL CLR CALLERS']
if external_into:
    for x in external_into[:80]:lines.append(f"  M:{x['callerRid']} {x['callerSymbol']} -> M:{x['targetRid']} {x['targetSymbol']}")
else:lines.append('  NONE')
lines += ['', 'EXACT FormationBg / FormationRT STRING LITERAL METHODS']
if exact_carriers:
    for c in exact_carriers:
        lines.append(f"  M:{c['rid']} {c['symbol']} needles={','.join(c['needles'])}")
        looks,apis=classify_method(c['rid'])
        for x in looks:lines.append(f"    LOOKUP {x['lookup']} :: {x['target']}")
        for x in apis:lines.append(f"    API mode={x['mode']} {x['api']} :: {x['target']}")
else:lines.append('  NONE')
lines += ['', 'DIRECTED EXACT NAME CARRIER -> TEXTURE WRITE PATHS']
if paths:
    for p in paths[:80]:
        lines.append('  depth='+str(p['depth'])+' '+' -> '.join('M:'+str(x) for x in p['rids']))
        lines.append('    SYMBOLS '+' -> '.join(p['symbols']))
        for x in p['targetWriteApis']:lines.append(f"    WRITE {x['api']} :: {x['target']}")
else:lines.append('  NONE')
lines += ['', 'NEXT '+next_strategy,
 'RULE: RawImage.get_texture is consumer/read evidence only and is not promoted to assignment.',
 'RULE: exact FormationBg/FormationRT string equality is stronger than substring correlation.',
 'RULE: no APK read, DLL rescan, bundle extraction/scan, main or preview modification.']
reportp.write_text('\n'.join(lines)+'\n','utf-8')

print('FORMATION_ARABIC_NAME_OK',f'arabicMethods={len(arabic_methods)}',f'arabicReads={len(arabic_read)}',f'arabicWrites={len(arabic_write)}',f'exactNames={len(exact_carriers)}',f'writePaths={len(paths)}')
for x in arabic_write[:20]:print('FORMATION_ARABIC_WRITE',f"M:{x['rid']}",x['symbol'],x['api'],x['target'])
for c in exact_carriers[:30]:print('FORMATION_EXACT_NAME',f"M:{c['rid']}",c['symbol'],','.join(c['needles']))
for p in paths[:20]:print('FORMATION_EXACT_NAME_WRITE_PATH','->'.join('M:'+str(x) for x in p['rids']))
print('FORMATION_ARABIC_NAME_NEXT',next_strategy)
print('FORMATION_ARABIC_NAME_JSON',outp)
print('FORMATION_ARABIC_NAME_REPORT',reportp)
PY

git add "$OUT"
if ! git diff --cached --quiet; then
  git commit -m "lab: trace ArabicMirror and exact Formation runtime name lookups"
  git push origin "$BRANCH"
fi

echo "FORMATION_ARABIC_NAME_DONE"
