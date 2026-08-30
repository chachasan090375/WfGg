#!/data/data/com.termux/files/usr/bin/bash
set -Eeuo pipefail

# WfGg Last War LAB — direct FormationBg / FormationRT owner -> CLR render API junction.
# Existing evidence only: exact closed V4 PPtr graph + background anchors + existing CLR atlas.
# NO APK read, NO DLL rescan, NO bundle extraction/scan, NO candidate promotion.

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BRANCH="portal-auth-lastwar-lab-v1"
META="$ROOT/frontend/lab/master-assets-v2/meta"
V4="$META/formation-ptr-exact-v4.json"
BG="$META/formation-background-pipeline-v1.json"
SUMMARY="$META/formation-ptr-exact-v4-summary-v1.json"
ATLAS="$ROOT/frontend/lab/master-assets-v2/index/lastwar-code-discovery-atlas-v1.json"
OUT="$META/formation-rawimage-owner-clr-junction-v1.json"
REPORT="$HOME/storage/downloads/WFGG_LASTWAR_FORMATION_RAWIMAGE_OWNER_CLR_JUNCTION_V1.txt"

fail(){ printf 'ERREUR: %s\n' "$*" >&2; exit 1; }
cd "$ROOT"
[[ "$(git branch --show-current)" == "$BRANCH" ]] || fail "branche LAB incorrecte"
for f in "$V4" "$BG" "$SUMMARY" "$ATLAS"; do [[ -s "$f" ]] || fail "fichier absent: $f"; done
command -v python >/dev/null 2>&1 || fail "python absent"
mkdir -p "$(dirname "$OUT")" "$(dirname "$REPORT")"

python - "$V4" "$BG" "$SUMMARY" "$ATLAS" "$OUT" "$REPORT" <<'PY'
from __future__ import annotations
from pathlib import Path
from collections import defaultdict, deque
import json,re,sys

v4p,bgp,sump,atlasp,outp,reportp=map(Path,sys.argv[1:])
g=json.loads(v4p.read_text('utf-8'))
bg=json.loads(bgp.read_text('utf-8'))
sj=json.loads(sump.read_text('utf-8'))
a=json.loads(atlasp.read_text('utf-8'))
objects=g.get('objects') or []
edges=g.get('edges') or []
counts=sj.get('counts') or {}
if int(counts.get('unresolvedRefs') or 0)!=0 or int(counts.get('parseErrors') or 0)!=0:
    raise SystemExit('PTR_V4_NOT_CLOSED')

def first(x): return (x or [{}])[0] if isinstance(x,list) else (x or {})
def pptr(row,path):
    for p in row.get('pointers') or []:
        if p.get('path')==path:
            return int(p.get('pathId') or p.get('pathID') or 0)
    return 0

def pid_of_obj(o):
    for k in ('pathID','pathId','pathid'):
        try:
            if k in o:return int(o[k])
        except:pass
    for k in ('id','objectId','objectID','key','ref','canonicalId','canonicalID'):
        v=o.get(k)
        if isinstance(v,str):
            m=re.search(r'#(-?\d+)$',v)
            if m:return int(m.group(1))
    return None

def ids_of_obj(o):
    z=set()
    for k in ('id','objectId','objectID','key','ref','canonicalId','canonicalID'):
        v=o.get(k)
        if isinstance(v,(str,int)):z.add(str(v))
    p=pid_of_obj(o)
    if p is not None:z.add(str(p))
    return z

def trailing_pid(v):
    if isinstance(v,int):return v
    if not isinstance(v,str):return None
    if re.fullmatch(r'-?\d+',v):
        try:return int(v)
        except:return None
    m=re.search(r'#(-?\d+)$',v)
    return int(m.group(1)) if m else None

def relation(e):return str(e.get('relation') or e.get('rel') or e.get('kind') or '').lower()
def otype(o):
    for k in ('type','class','className','objectType','objectClass'):
        if o.get(k) is not None:return str(o.get(k))
    return ''

def direct_name(o):
    for k in ('name','objectName','m_Name','gameObject','scriptName'):
        if isinstance(o.get(k),str) and o.get(k):return o.get(k)
    return ''

def deep_values(x, wanted, out=None, depth=0):
    if out is None:out=defaultdict(list)
    if depth>8:return out
    if isinstance(x,dict):
        for k,v in x.items():
            if k in wanted and isinstance(v,(str,int,float,bool)) and str(v):out[k].append(v)
            if isinstance(v,(dict,list)):deep_values(v,wanted,out,depth+1)
    elif isinstance(x,list):
        for v in x[:2000]:
            if isinstance(v,(dict,list)):deep_values(v,wanted,out,depth+1)
    return out

def uniq(seq):
    out=[];seen=set()
    for x in seq:
        s=str(x)
        if s not in seen:seen.add(s);out.append(x)
    return out

def script_identity(o):
    dv=deep_values(o,{'m_ClassName','className','scriptName','m_Name','name','m_Namespace','namespace','m_AssemblyName','assemblyName'})
    cls=uniq(dv.get('m_ClassName',[])+dv.get('className',[])+dv.get('scriptName',[]))
    names=uniq(dv.get('m_Name',[])+dv.get('name',[]))
    ns=uniq(dv.get('m_Namespace',[])+dv.get('namespace',[]))
    asm=uniq(dv.get('m_AssemblyName',[])+dv.get('assemblyName',[]))
    if not cls:
        # For MonoScript records, m_Name is a fallback identity only; retained as lower confidence metadata.
        cls=[x for x in names if isinstance(x,str) and re.fullmatch(r'[A-Za-z_][A-Za-z0-9_+.]*',x)]
    return {'classNames':[str(x) for x in cls[:12]],'names':[str(x) for x in names[:12]],'namespaces':[str(x) for x in ns[:8]],'assemblies':[str(x) for x in asm[:8]]}

def compact_obj(o):
    return {'pathID':pid_of_obj(o),'type':otype(o),'name':direct_name(o),'identity':script_identity(o) if 'script' in otype(o).lower() else None}

by_id=defaultdict(list);by_pid=defaultdict(list)
for o in objects:
    for i in ids_of_obj(o):by_id[i].append(o)
    p=pid_of_obj(o)
    if p is not None:by_pid[p].append(o)

def resolve_endpoint(v):
    rows=[]
    if isinstance(v,(str,int)):rows.extend(by_id.get(str(v),[]))
    p=trailing_pid(v)
    if p is not None:rows.extend(by_pid.get(p,[]))
    out=[];seen=set()
    for o in rows:
        q=id(o)
        if q not in seen:seen.add(q);out.append(o)
    return out

def endpoint_matches(v,pids,ids):
    if isinstance(v,(str,int)) and str(v) in ids:return True
    p=trailing_pid(v)
    return p in pids if p is not None else False

def outgoing(o,rel=None):
    ids=ids_of_obj(o);pid=pid_of_obj(o);out=[]
    for e in edges:
        fr=e.get('from')
        hit=(isinstance(fr,(str,int)) and str(fr) in ids) or (pid is not None and trailing_pid(fr)==pid)
        if not hit:continue
        if rel and relation(e)!=rel:continue
        out.append(e)
    return out

bgr=first(bg.get('FormationBgRawImage'));rtr=first(bg.get('FormationRTRawImage'))
anchors={
 'FormationBg':{'componentPathID':int(bgr.get('pathId') or 0),'gameObjectPathID':pptr(bgr,'m_GameObject')},
 'FormationRT':{'componentPathID':int(rtr.get('pathId') or 0),'gameObjectPathID':pptr(rtr,'m_GameObject')},
}
for n,x in anchors.items():
    if not x['componentPathID'] or not x['gameObjectPathID']:raise SystemExit('ANCHOR_MISSING_'+n)

# Exact script candidates from two evidence classes:
# 1) components colocated on the exact RawImage GameObject;
# 2) exact serialized_ref sources that point to the RawImage component or its GO.
script_rows=[]
component_rows=[]

def add_component(anchor,component,provenance,edge=None):
    cp=pid_of_obj(component)
    cr={'anchor':anchor,'componentPathID':cp,'componentType':otype(component),'componentName':direct_name(component),'provenance':provenance,'edge':{k:edge.get(k) for k in ('from','to','relation','fieldPath','fileID','pathID') if k in edge} if edge else None}
    component_rows.append(cr)
    for se in outgoing(component,'script_ref'):
        targets=resolve_endpoint(se.get('to'))
        for so in targets:
            ident=script_identity(so)
            script_rows.append({'anchor':anchor,'componentPathID':cp,'componentType':otype(component),'componentName':direct_name(component),'provenance':provenance,'scriptPathID':pid_of_obj(so),'scriptObjectType':otype(so),'scriptObjectName':direct_name(so),'scriptIdentity':ident,'scriptRef':{k:se.get(k) for k in ('from','to','relation','fieldPath','fileID','pathID') if k in se}})

for name,x in anchors.items():
    for go in by_pid.get(x['gameObjectPathID'],[]):
        for ce in outgoing(go,'component_ref'):
            for comp in resolve_endpoint(ce.get('to')):
                add_component(name,comp,'colocated_on_exact_rawimage_gameobject',ce)
    pids={x['componentPathID'],x['gameObjectPathID']};ids=set(map(str,pids))
    for p in pids:
        for o in by_pid.get(p,[]):ids.update(ids_of_obj(o))
    for e in edges:
        if relation(e)!='serialized_ref':continue
        hit=endpoint_matches(e.get('to'),pids,ids)
        if not hit:
            try:hit=int(e.get('pathID')) in pids
            except:hit=False
        if not hit:continue
        for src in resolve_endpoint(e.get('from')):
            add_component(name,src,'exact_serialized_referrer_of_rawimage_or_go',e)

# Dedupe exact script rows.
ded={}
for r in script_rows:
    k=(r['anchor'],r['componentPathID'],r['scriptPathID'],r['provenance'])
    ded[k]=r
script_rows=list(ded.values())

# CLR atlas exact type join.
types=a.get('types') or [];methods=a.get('methods') or [];internal=a.get('internalEdges') or [];external=a.get('externalCalls') or []
type_by_rid={int(t['rid']):t for t in types}
methods_by_type=defaultdict(list);method_by_rid={}
for m in methods:
    rid=int(m['rid']);method_by_rid[rid]=m
    if m.get('typeRid') is not None:methods_by_type[int(m['typeRid'])].append(m)

def full_type(t):return ((str(t.get('namespace'))+'.') if t.get('namespace') else '')+str(t.get('name') or '')
def method_symbol(m):
    t=type_by_rid.get(int(m.get('typeRid') or 0));owner=full_type(t) if t else ''
    return (owner+'.' if owner else '')+str(m.get('name') or '')

by_type_name=defaultdict(list);by_full_type=defaultdict(list)
for t in types:
    by_type_name[str(t.get('name') or '')].append(t);by_full_type[full_type(t)].append(t)

# Relevant runtime APIs are classified by exact external MemberRef target text already stored in atlas.
def api_class(target):
    s=str(target).lower()
    if 'rawimage' in s and ('set_texture' in s or 'get_texture' in s):return 'RawImage.texture'
    if 'camera' in s and ('set_targettexture' in s or 'set_target_texture' in s or 'targettexture' in s):return 'Camera.targetTexture'
    if 'rendertexture' in s:return 'RenderTexture'
    if 'graphics' in s and 'blit' in s:return 'Graphics.Blit'
    if 'commandbuffer' in s and 'blit' in s:return 'CommandBuffer.Blit'
    if 'material' in s and ('settexture' in s or 'set_texture' in s):return 'Material.SetTexture'
    if 'shader' in s and ('setglobaltexture' in s or 'set_global_texture' in s):return 'Shader.SetGlobalTexture'
    if 'videoplayer' in s and 'targettexture' in s:return 'VideoPlayer.targetTexture'
    return None

def boundary_class(target):
    s=str(target).lower()
    if any(x in s for x in ('xlua','luaenv','luatable','luafunction','objecttranslator','lua.dll','lua.load_','lua_pcall','lua_raw')):return 'Lua/XLua'
    if any(x in s for x in ('resources.load','assetbundle.load','resourceprovider','resourcemanager','assetmanager','textasset','file.read','streamreader','zipfile','ziparchive')):return 'Resource/Storage'
    return None

api_callers=defaultdict(list);boundary_callers=defaultdict(list)
for ex in external:
    target=str(ex.get('target') or '')
    ac=api_class(target);bc=boundary_class(target)
    for rid in ex.get('callerRids') or []:
        rid=int(rid)
        if ac:api_callers[rid].append({'class':ac,'target':target,'classification':ex.get('classification')})
        if bc:boundary_callers[rid].append({'class':bc,'target':target,'classification':ex.get('classification')})

resolved=[];ambiguous=[];unresolved=[]
owner_method_rids=set()
for r in script_rows:
    ids=r['scriptIdentity'];cls=ids.get('classNames') or [] ; nss=ids.get('namespaces') or []
    candidates=[];reason=''
    for c in cls:
        if nss:
            for ns in nss:
                candidates.extend(by_full_type.get((ns+'.' if ns else '')+c,[]))
        if not candidates:candidates.extend(by_type_name.get(c,[]))
    # stable dedupe
    uu={int(t['rid']):t for t in candidates};candidates=list(uu.values())
    row={**r,'atlasCandidates':[{'typeRid':int(t['rid']),'fullName':full_type(t),'status':t.get('status'),'interest':t.get('interest')} for t in candidates]}
    if len(candidates)==1:
        t=candidates[0];tr=int(t['rid']);ms=methods_by_type.get(tr,[]);owner_method_rids.update(int(m['rid']) for m in ms)
        row['atlasTypeRid']=tr;row['atlasFullName']=full_type(t);row['methodCount']=len(ms);resolved.append(row)
    elif len(candidates)>1:ambiguous.append(row)
    else:unresolved.append(row)

# Exact direct relevant external APIs from owner methods.
direct=[]
for rid in sorted(owner_method_rids):
    if rid not in api_callers and rid not in boundary_callers:continue
    m=method_by_rid.get(rid)
    direct.append({'rid':rid,'symbol':method_symbol(m) if m else str(rid),'renderApis':api_callers.get(rid,[]),'boundaries':boundary_callers.get(rid,[]),'strings':(m or {}).get('strings',[])})

# Directed CLR paths owner-method -> a method with a relevant render API external call.
adj=defaultdict(list)
for pair in internal:
    if isinstance(pair,(list,tuple)) and len(pair)>=2:
        try:adj[int(pair[0])].append(int(pair[1]))
        except:pass
render_targets=set(api_callers)
paths=[]
MAX_DEPTH=5
for start in sorted(owner_method_rids):
    if start in render_targets:continue
    q=deque([start]);parent={start:None};depth={start:0};found=[]
    while q:
        x=q.popleft();d=depth[x]
        if d>=MAX_DEPTH:continue
        for y in adj.get(x,[]):
            if y in parent:continue
            parent[y]=x;depth[y]=d+1
            if y in render_targets:
                found.append(y)
                if len(found)>=4:break
            q.append(y)
        if found:break
    for y in found:
        seq=[];z=y
        while z is not None:seq.append(z);z=parent.get(z)
        seq.reverse()
        paths.append({'depth':len(seq)-1,'fromRid':start,'fromSymbol':method_symbol(method_by_rid.get(start,{})),'toRid':y,'toSymbol':method_symbol(method_by_rid.get(y,{})),'pathRids':seq,'pathSymbols':[method_symbol(method_by_rid.get(r,{})) for r in seq],'renderApis':api_callers.get(y,[])})
paths.sort(key=lambda x:(x['depth'],x['fromSymbol'],x['toSymbol']))

# Owner-method exact Lua/resource boundaries, even when no render API is reached yet.
boundaries=[]
for rid in sorted(owner_method_rids):
    if rid in boundary_callers:
        m=method_by_rid.get(rid)
        boundaries.append({'rid':rid,'symbol':method_symbol(m) if m else str(rid),'calls':boundary_callers[rid],'strings':(m or {}).get('strings',[])})

if direct:
    next_strategy='inspect_exact_owner_methods_with_direct_render_api_calls'
elif paths:
    next_strategy='inspect_shortest_directed_owner_to_render_api_paths'
elif boundaries:
    next_strategy='inspect_exact_owner_lua_or_resource_boundary_methods'
elif resolved:
    next_strategy='inspect_owner_methods_and_runtime_name_lookup_callers'
elif script_rows:
    next_strategy='resolve_exact_monoscript_identity_from_existing_v4_records'
else:
    next_strategy='trace_runtime_component_lookup_from_exact_formationbg_formationrt_names'

result={
 'format':'WFGG_LASTWAR_FORMATION_RAWIMAGE_OWNER_CLR_JUNCTION_V1',
 'sources':{'ptrGraph':str(v4p),'backgroundPipeline':str(bgp),'ptrSummary':str(sump),'clrAtlas':str(atlasp)},
 'anchors':anchors,
 'counts':{'ptrObjects':len(objects),'ptrEdges':len(edges),'ownerComponentRows':len(component_rows),'scriptTargets':len(script_rows),'resolvedClrTypes':len(resolved),'ambiguousClrTypes':len(ambiguous),'unresolvedClrTypes':len(unresolved),'ownerMethods':len(owner_method_rids),'directRelevantMethods':len(direct),'directedRenderPaths':len(paths),'ownerBoundaryMethods':len(boundaries)},
 'ownerComponents':component_rows[:500],
 'scriptTargets':script_rows[:500],
 'resolvedClrTypes':resolved[:300],
 'ambiguousClrTypes':ambiguous[:300],
 'unresolvedClrTypes':unresolved[:300],
 'directRelevantMethods':direct[:300],
 'directedOwnerToRenderApiPaths':paths[:300],
 'ownerBoundaryMethods':boundaries[:300],
 'conclusion':{'nextStrategy':next_strategy,'important':'Only exact V4 component/script identity and exact atlas call edges are evidence. Name/type matching is exact; ambiguous type names are not promoted.'},
 'guardrails':{'existingEvidenceOnly':True,'apkAccess':False,'dllRescan':False,'bundleExtraction':False,'bundleScan':False,'candidatePromotion':False,'mainUntouched':True,'previewUntouched':True}
}
outp.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n','utf-8')

lines=['WfGg Last War — FORMATION RAWIMAGE OWNER → CLR JUNCTION V1','',
 f"ptrObjects={len(objects)} ptrEdges={len(edges)} ownerComponents={len(component_rows)} scriptTargets={len(script_rows)}",
 f"resolvedClrTypes={len(resolved)} ambiguousClrTypes={len(ambiguous)} unresolvedClrTypes={len(unresolved)} ownerMethods={len(owner_method_rids)}",
 f"directRelevantMethods={len(direct)} directedRenderPaths={len(paths)} ownerBoundaryMethods={len(boundaries)}",
 f"nextStrategy={next_strategy}",'','ANCHORS']
for n,x in anchors.items():lines.append(f"  {n} RawImage={x['componentPathID']} GameObject={x['gameObjectPathID']}")
lines+=['','EXACT OWNER SCRIPT TARGETS']
if script_rows:
    for r in script_rows[:120]:
        ident=r['scriptIdentity'];lines.append(f"  {r['anchor']} provenance={r['provenance']} component={r['componentPathID']}:{r['componentType']} script={r['scriptPathID']} class={','.join(ident.get('classNames') or []) or '-'} namespace={','.join(ident.get('namespaces') or []) or '-'}")
else:lines.append('  NONE')
lines+=['','EXACT CLR TYPE JOINS']
if resolved:
    for r in resolved[:100]:lines.append(f"  {r['anchor']} class={','.join(r['scriptIdentity'].get('classNames') or [])} T:{r['atlasTypeRid']} {r['atlasFullName']} methods={r['methodCount']}")
else:lines.append('  NONE')
if ambiguous:
    lines.append('  AMBIGUOUS (not promoted)')
    for r in ambiguous[:40]:lines.append('    '+','.join(x['fullName'] for x in r['atlasCandidates']))
lines+=['','DIRECT OWNER METHODS → RENDER/TEXTURE APIs']
if direct:
    for d in direct[:100]:
        lines.append(f"  M:{d['rid']} {d['symbol']}")
        for c in d['renderApis'][:12]:lines.append(f"    API {c['class']} :: {c['target']}")
        for c in d['boundaries'][:12]:lines.append(f"    BOUNDARY {c['class']} :: {c['target']}")
else:lines.append('  NONE')
lines+=['','SHORTEST DIRECTED OWNER → RENDER API PATHS']
if paths:
    for p in paths[:80]:
        lines.append(f"  depth={p['depth']} {' -> '.join('M:'+str(x) for x in p['pathRids'])}")
        lines.append('    SYMBOLS '+' -> '.join(p['pathSymbols']))
        for c in p['renderApis'][:8]:lines.append(f"    API {c['class']} :: {c['target']}")
else:lines.append('  NONE')
lines+=['','OWNER LUA / RESOURCE BOUNDARIES']
if boundaries:
    for b in boundaries[:80]:
        lines.append(f"  M:{b['rid']} {b['symbol']}")
        for c in b['calls'][:10]:lines.append(f"    {c['class']} :: {c['target']}")
else:lines.append('  NONE')
lines+=['','NEXT '+next_strategy,
 'RULE: exact V4 component/script identity + exact CLR call edges only; ambiguous names are not evidence.',
 'RULE: no APK read, DLL rescan, bundle extraction/scan, candidate promotion, main or preview modification.']
reportp.write_text('\n'.join(lines)+'\n','utf-8')

print('FORMATION_RAWIMAGE_CLR_OK',f'components={len(component_rows)}',f'scripts={len(script_rows)}',f'types={len(resolved)}',f'ownerMethods={len(owner_method_rids)}',f'direct={len(direct)}',f'paths={len(paths)}',f'boundaries={len(boundaries)}')
for r in resolved[:30]:print('FORMATION_RAWIMAGE_CLR_TYPE',r['anchor'],r['atlasTypeRid'],r['atlasFullName'])
for d in direct[:30]:print('FORMATION_RAWIMAGE_CLR_DIRECT',d['rid'],d['symbol'],','.join(sorted({x['class'] for x in d['renderApis']})))
for p in paths[:30]:print('FORMATION_RAWIMAGE_CLR_PATH',p['depth'],'>'.join(map(str,p['pathRids'])),p['toSymbol'])
print('FORMATION_RAWIMAGE_CLR_NEXT',next_strategy)
print('FORMATION_RAWIMAGE_CLR_JSON',outp)
print('FORMATION_RAWIMAGE_CLR_REPORT',reportp)
PY

git add "$OUT"
if ! git diff --cached --quiet; then
  git commit -m "lab: join Formation RawImage owners to CLR render APIs"
  git push origin "$BRANCH"
else
  echo "FORMATION_RAWIMAGE_CLR_GIT no-change"
fi
