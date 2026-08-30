#!/data/data/com.termux/files/usr/bin/bash
set -Eeuo pipefail

# WfGg Last War LAB — trace the runtime/later-stage Formation texture binding
# through the EXISTING persistent CLR code atlas.
# No APK read, DLL re-scan, extraction, bundle scan, candidate promotion,
# main modification or preview modification.

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BRANCH="portal-auth-lastwar-lab-v1"
META="$ROOT/frontend/lab/master-assets-v2/meta"
INDEX="$ROOT/frontend/lab/master-assets-v2/index"
ATLAS="$INDEX/lastwar-code-discovery-atlas-v1.json"
CROSS="$META/formation-runtime-crosswalk-v1.json"
OUT="$META/formation-runtime-atlas-binding-v1.json"
REPORT="$HOME/storage/downloads/WFGG_LASTWAR_FORMATION_RUNTIME_ATLAS_BINDING_V1.txt"

fail(){ printf 'ERREUR: %s\n' "$*" >&2; exit 1; }
cd "$ROOT"
[[ "$(git branch --show-current)" == "$BRANCH" ]] || fail "branche LAB incorrecte"
[[ -s "$ATLAS" ]] || fail "atlas CLR absent: $ATLAS"
[[ -s "$CROSS" ]] || fail "crosswalk runtime absent: $CROSS"
command -v python >/dev/null 2>&1 || fail "python absent"
mkdir -p "$(dirname "$OUT")" "$(dirname "$REPORT")"

python - "$ATLAS" "$CROSS" "$OUT" "$REPORT" <<'PY'
from pathlib import Path
from collections import defaultdict, deque
import json, re, sys

atlas_p, cross_p, out_p, report_p = map(Path, sys.argv[1:])
a = json.loads(atlas_p.read_text('utf-8'))
cross = json.loads(cross_p.read_text('utf-8'))

cc = cross.get('conclusion') or {}
pc = cross.get('ptrClosure') or {}
if not pc.get('closed'):
    raise SystemExit('ERREUR: graphe PPtr non ferme dans le crosswalk')
if not cc.get('runtimeAssignmentSearchRequired'):
    raise SystemExit('ERREUR: le crosswalk ne demande pas de recherche runtime')

types = a.get('types') or []
methods = a.get('methods') or []
external = a.get('externalCalls') or []
internal = a.get('internalEdges') or []
tm = {int(x['rid']): x for x in types if x.get('rid') is not None}
mm = {int(x['rid']): x for x in methods if x.get('rid') is not None}

def fullname_type(t):
    if not t: return ''
    return ((str(t.get('namespace'))+'.') if t.get('namespace') else '') + str(t.get('name') or '')

def symbol(rid):
    m = mm.get(int(rid)) or {}
    t = tm.get(int(m.get('typeRid') or 0))
    owner = fullname_type(t)
    return (owner+'.' if owner else '') + str(m.get('name') or f'M:{rid}')

def is_wrapper(rid):
    m = mm.get(int(rid)) or {}
    owner = fullname_type(tm.get(int(m.get('typeRid') or 0))).lower()
    return owner.startswith('xlua.csobjectwrap.') or 'csobjectwrap' in owner or owner.endswith('wrap')

def text_strings(m):
    vals = m.get('strings') or []
    if not isinstance(vals, list): vals=[vals]
    out=[]
    for v in vals:
        if isinstance(v, str): out.append(v)
        elif isinstance(v, dict):
            for k in ('string','value','text'):
                if isinstance(v.get(k),str): out.append(v[k]); break
    return out

# Exact external MemberRef families. Matching stays literal/semantic; no fuzzy promotion.
patterns = {
    'rawImageSetTexture': ('unityengine.ui.rawimage.set_texture',),
    'rawImageGetTexture': ('unityengine.ui.rawimage.get_texture',),
    'rawImageSetMaterial': ('unityengine.ui.rawimage.set_material',),
    'cameraSetTargetTexture': ('unityengine.camera.set_targettexture', 'unityengine.camera.set_target_texture'),
    'cameraGetTargetTexture': ('unityengine.camera.get_targettexture', 'unityengine.camera.get_target_texture'),
    'renderTexture': ('unityengine.rendertexture.', 'unityengine.rendering.rendertexture.'),
    'graphicsBlit': ('unityengine.graphics.blit',),
    'materialSetTexture': ('unityengine.material.settexture', 'unityengine.material.set_texture'),
    'shaderPropertyToID': ('unityengine.shader.propertytoid',),
}

cat_callers = {k:set() for k in patterns}
cat_targets = {k:set() for k in patterns}
method_targets = defaultdict(set)
for row in external:
    target = str(row.get('target') or '')
    low = target.lower()
    callers = [int(x) for x in (row.get('callerRids') or []) if str(x).lstrip('-').isdigit()]
    for rid in callers:
        method_targets[rid].add(target)
    for cat,pats in patterns.items():
        if any(p in low for p in pats):
            cat_targets[cat].add(target)
            cat_callers[cat].update(callers)

# Exact internal MethodDef call graph from the persistent atlas.
callers_of = defaultdict(set)
callees_of = defaultdict(set)
for e in internal:
    if not isinstance(e,(list,tuple)) or len(e)<2: continue
    try: caller, callee = int(e[0]), int(e[1])
    except Exception: continue
    callers_of[callee].add(caller)
    callees_of[caller].add(callee)

name_terms = ('formationrt','formationbg','uiheropvpformationpanel','formationcontent','pvpformation','heroshow','showcamera','formationcamera')
owner_terms = ('formation','pvp','hero','showcamera','heroshow')

def evidence_row(rid, distance=None, via=None):
    m = mm.get(int(rid)) or {}
    strings = text_strings(m)
    s_hits = [s for s in strings if any(t in s.lower() for t in name_terms)]
    sym = symbol(rid)
    cats = [k for k,v in cat_callers.items() if rid in v]
    row = {
        'rid':int(rid),
        'stableId':f'M:{int(rid)}',
        'symbol':sym,
        'status':m.get('status'),
        'score':m.get('score'),
        'tags':m.get('tags') or [],
        'wrapper':is_wrapper(rid),
        'apiCategories':cats,
        'matchedExternalTargets':sorted(method_targets.get(int(rid),set())),
        'formationLiteralHits':s_hits,
        'formationOwnerCorrelation':any(t in sym.lower() for t in owner_terms),
        'directInternalCallers':sorted(callers_of.get(int(rid),set())),
        'directInternalCallees':sorted(callees_of.get(int(rid),set())),
    }
    if distance is not None: row['distanceToRawImageSetTextureCaller']=int(distance)
    if via is not None: row['viaMethodRid']=int(via)
    return row

raw = set(cat_callers['rawImageSetTexture'])
renderish = set().union(
    cat_callers['renderTexture'],
    cat_callers['cameraSetTargetTexture'],
    cat_callers['cameraGetTargetTexture'],
    cat_callers['graphicsBlit'],
    cat_callers['materialSetTexture'],
)
bridges = sorted(raw & renderish)
raw_literal = sorted(r for r in raw if evidence_row(r)['formationLiteralHits'])
raw_formation_owner = sorted(r for r in raw if evidence_row(r)['formationOwnerCorrelation'])
raw_nonwrapper = sorted(r for r in raw if not is_wrapper(r))
raw_wrapper = sorted(r for r in raw if is_wrapper(r))

# Reverse call closure: exact callers that can reach a direct RawImage.set_texture caller.
# Distances are static MethodDef-call distances, not runtime execution proof.
dist = {r:0 for r in raw}
via = {}
q = deque(raw)
while q:
    x=q.popleft(); d=dist[x]
    if d>=4: continue
    for p in callers_of.get(x,()):
        if p not in dist:
            dist[p]=d+1; via[p]=x; q.append(p)

upstream=[]
for rid,d in dist.items():
    if d==0: continue
    row=evidence_row(rid,d,via.get(rid))
    if row['formationLiteralHits'] or row['formationOwnerCorrelation'] or any(k in row['apiCategories'] for k in ('renderTexture','cameraSetTargetTexture','cameraGetTargetTexture','graphicsBlit')):
        upstream.append(row)
upstream.sort(key=lambda r:(r['distanceToRawImageSetTextureCaller'], not bool(r['formationLiteralHits']), not r['formationOwnerCorrelation'], r['symbol']))

# Independent Formation-name evidence in the atlas, useful if the texture setter boundary is XLua.
formation_named=[]
for rid,m in mm.items():
    sym=symbol(rid)
    strings=text_strings(m)
    hits=[s for s in strings if any(t in s.lower() for t in name_terms)]
    ownercorr=any(t in sym.lower() for t in owner_terms)
    if hits or ownercorr:
        cats=[k for k,v in cat_callers.items() if rid in v]
        if hits or cats or any(t in sym.lower() for t in ('formation','pvpformation','heroshow')):
            formation_named.append(evidence_row(rid,dist.get(rid),via.get(rid)))
formation_named.sort(key=lambda r:(r.get('distanceToRawImageSetTextureCaller',99), not bool(r['formationLiteralHits']), r['symbol']))

all_raw_wrappers = bool(raw) and len(raw_wrapper)==len(raw)
lua_boundary_likely = all_raw_wrappers and not bridges and not raw_literal and not upstream
if bridges:
    strategy='inspect_exact_same_method_api_bridges'
elif raw_literal:
    strategy='inspect_rawimage_setter_methods_with_exact_formation_literals'
elif upstream:
    strategy='inspect_exact_upstream_methoddef_call_chain'
elif all_raw_wrappers:
    strategy='trace_lua_binding_or_existing_lua_asset_index'
elif raw_nonwrapper:
    strategy='inspect_nonwrapper_rawimage_setter_callers'
else:
    strategy='trace_alternate_texture_assignment_api_or_lua_boundary'

result={
    'format':'WFGG_LASTWAR_FORMATION_RUNTIME_ATLAS_BINDING_V1',
    'sources':{
        'codeAtlas':str(atlas_p),
        'codeAtlasDllSha256':(a.get('source') or {}).get('sha256'),
        'runtimeCrosswalk':str(cross_p),
    },
    'precondition':{
        'ptrClosed':bool(pc.get('closed')),
        'runtimeAssignmentSearchRequired':bool(cc.get('runtimeAssignmentSearchRequired')),
        'serializedTextureBindingAbsentOnBothRawImages':bool(cc.get('serializedTextureBindingAbsentOnBothRawImages')),
    },
    'atlasCounts':a.get('counts') or {},
    'externalTargetsByCategory':{k:sorted(v) for k,v in cat_targets.items()},
    'callerCountsByCategory':{k:len(v) for k,v in cat_callers.items()},
    'rawImageSetTexture':{
        'callerCount':len(raw),
        'wrapperCallerCount':len(raw_wrapper),
        'nonWrapperCallerCount':len(raw_nonwrapper),
        'allCallersAreXLuaOrWrap':all_raw_wrappers,
        'callers':[evidence_row(r) for r in sorted(raw)],
    },
    'exactSameMethodApiBridges':[evidence_row(r) for r in bridges],
    'rawSetterWithExactFormationLiteral':[evidence_row(r) for r in raw_literal],
    'rawSetterWithFormationOwnerCorrelation':[evidence_row(r) for r in raw_formation_owner],
    'exactUpstreamCallEvidence':upstream[:300],
    'formationNamedEvidence':formation_named[:500],
    'conclusion':{
        'exactSameMethodBridgeCount':len(bridges),
        'rawSetterExactFormationLiteralCount':len(raw_literal),
        'exactUpstreamCorrelatedCount':len(upstream),
        'luaBoundaryLikely':lua_boundary_likely,
        'nextStrategy':strategy,
        'note':'Only exact CLR MemberRef and MethodDef-call evidence is treated as exact. Name/string correlations remain correlations and are never promoted to runtime proof.'
    },
    'guardrails':{
        'persistentCodeAtlasOnly':True,
        'apkAccess':False,
        'dllRescan':False,
        'newExtraction':False,
        'bundleScan':False,
        'candidatePromotion':False,
        'mainUntouched':True,
        'previewUntouched':True,
    }
}
out_p.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n','utf-8')

co=result['conclusion']; counts=result['callerCountsByCategory']
lines=[
    'WfGg Last War — FORMATION RUNTIME ATLAS BINDING V1','',
    f"atlas methods={(a.get('counts') or {}).get('methods')} internalEdges={(a.get('counts') or {}).get('internalEdges')} externalTargets={(a.get('counts') or {}).get('externalTargets')}",
    f"rawImageSetTexture callers={len(raw)} wrappers={len(raw_wrapper)} nonWrappers={len(raw_nonwrapper)}",
    f"renderTexture callers={counts['renderTexture']} cameraSetTargetTexture callers={counts['cameraSetTargetTexture']} graphicsBlit callers={counts['graphicsBlit']}",
    f"exactSameMethodApiBridges={len(bridges)} rawSetterExactFormationLiteral={len(raw_literal)} exactUpstreamCorrelated={len(upstream)}",
    f"allRawSetterCallersAreXLuaOrWrap={all_raw_wrappers} luaBoundaryLikely={lua_boundary_likely}",
    '', 'RAWIMAGE.SET_TEXTURE CALLERS'
]
if raw:
    for r in sorted(raw):
        x=evidence_row(r)
        lines.append(f"  M:{r} wrapper={x['wrapper']} ownerCorrelation={x['formationOwnerCorrelation']} symbol={x['symbol']}")
else: lines.append('  NONE')
lines += ['', 'EXACT SAME-METHOD API BRIDGES']
if bridges:
    for r in bridges:
        x=evidence_row(r); lines.append(f"  M:{r} categories={','.join(x['apiCategories'])} symbol={x['symbol']}")
else: lines.append('  NONE')
lines += ['', 'RAW SETTER + EXACT FORMATION LITERAL']
if raw_literal:
    for r in raw_literal:
        x=evidence_row(r); lines.append(f"  M:{r} strings={json.dumps(x['formationLiteralHits'],ensure_ascii=False)} symbol={x['symbol']}")
else: lines.append('  NONE')
lines += ['', 'EXACT UPSTREAM CALL EVIDENCE (CORRELATED NAMES/STRINGS ONLY)']
if upstream:
    for x in upstream[:80]:
        lines.append(f"  M:{x['rid']} d={x['distanceToRawImageSetTextureCaller']} via=M:{x.get('viaMethodRid')} strings={json.dumps(x['formationLiteralHits'],ensure_ascii=False)} symbol={x['symbol']}")
else: lines.append('  NONE')
lines += [
    '',
    f"NEXT strategy={strategy}",
    'RULE: exact CLR MemberRef/MethodDef links are exact evidence; names/strings remain correlations. No APK/DLL scan or candidate promotion performed.'
]
report_p.write_text('\n'.join(lines)+'\n','utf-8')

print('FORMATION_RUNTIME_ATLAS_OK',
      f"rawSet={len(raw)}",f"rawWrap={len(raw_wrapper)}",f"rawNonWrap={len(raw_nonwrapper)}",
      f"renderTexture={counts['renderTexture']}",f"cameraTarget={counts['cameraSetTargetTexture']}",
      f"bridges={len(bridges)}",f"upstream={len(upstream)}")
for r in sorted(raw)[:40]:
    x=evidence_row(r)
    print('FORMATION_RUNTIME_ATLAS_RAW',f"M:{r}",f"wrapper={x['wrapper']}",x['symbol'])
for r in bridges[:40]:
    x=evidence_row(r)
    print('FORMATION_RUNTIME_ATLAS_BRIDGE',f"M:{r}",','.join(x['apiCategories']),x['symbol'])
for x in upstream[:40]:
    print('FORMATION_RUNTIME_ATLAS_UPSTREAM',f"M:{x['rid']}",f"d={x['distanceToRawImageSetTextureCaller']}",f"via=M:{x.get('viaMethodRid')}",x['symbol'])
print('FORMATION_RUNTIME_ATLAS_NEXT',f"strategy={strategy}",f"luaBoundaryLikely={lua_boundary_likely}")
print('FORMATION_RUNTIME_ATLAS_JSON',out_p)
print('FORMATION_RUNTIME_ATLAS_REPORT',report_p)
PY

git add "$OUT"
if ! git diff --cached --quiet; then git commit -m "lab: map Formation runtime texture binding from code atlas"; fi
git push origin "$BRANCH"
printf '%s\n' '=== FORMATION RUNTIME ATLAS BINDING V1 TERMINE ===' "JSON: $OUT" "Rapport: $REPORT"
