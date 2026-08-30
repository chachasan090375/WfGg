#!/data/data/com.termux/files/usr/bin/bash
set -Eeuo pipefail

# WfGg Last War LAB — exact ancestor/controller map for FormationBg / FormationRT.
# Existing evidence only: closed V4 PPtr graph + background anchors + CLR atlas.
# NO APK read, NO DLL rescan, NO bundle extraction/scan, NO candidate promotion.

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BRANCH="portal-auth-lastwar-lab-v1"
META="$ROOT/frontend/lab/master-assets-v2/meta"
V4="$META/formation-ptr-exact-v4.json"
BG="$META/formation-background-pipeline-v1.json"
SUMMARY="$META/formation-ptr-exact-v4-summary-v1.json"
ATLAS="$ROOT/frontend/lab/master-assets-v2/index/lastwar-code-discovery-atlas-v1.json"
OUT="$META/formation-rawimage-ancestor-controller-map-v1.json"
REPORT="$HOME/storage/downloads/WFGG_LASTWAR_FORMATION_RAWIMAGE_ANCESTOR_CONTROLLER_MAP_V1.txt"

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
nodes=g.get('nodes') or []
edges=g.get('edges') or []
sc=sj.get('counts') or {}
expected_nodes=int(sc.get('objects') or 0)
if expected_nodes!=3209 or len(nodes)!=expected_nodes:
    raise SystemExit(f'PTR_V4_NODE_COUNT_MISMATCH expectedSummary={expected_nodes} actual={len(nodes)}')
if int(sc.get('unresolvedRefs') or 0) or int(sc.get('parseErrors') or 0):
    raise SystemExit('PTR_V4_NOT_CLOSED')
root_id=str(((sj.get('target') or {}).get('rootObject')) or '')
if not root_id: raise SystemExit('ROOT_ID_MISSING')

# ---------- exact V4 helpers ----------
by_id={str(n.get('id')):n for n in nodes if n.get('id') is not None}
by_pid=defaultdict(list)
for n in nodes:
    try: by_pid[int(n.get('pathID'))].append(n)
    except: pass

def relation(e): return str(e.get('relation') or '').lower()
def field(e): return str(e.get('fieldPath') or '')
def node_type(n): return str((n or {}).get('type') or '')
def node_name(n): return str((n or {}).get('name') or '')
def edge_from(x,rel=None):
    out=[]
    for e in edges:
        if str(e.get('from'))!=str(x): continue
        if rel and relation(e)!=rel: continue
        out.append(e)
    return out

def edge_to(x,rel=None):
    out=[]
    for e in edges:
        if str(e.get('to'))!=str(x): continue
        if rel and relation(e)!=rel: continue
        out.append(e)
    return out

def unique_node_for_pid(pid,typ=None,name=None):
    rows=list(by_pid.get(int(pid),[]))
    if typ: rows=[n for n in rows if node_type(n)==typ]
    if name: rows=[n for n in rows if node_name(n)==name]
    if len(rows)!=1:
        raise SystemExit(f'NODE_PID_NOT_UNIQUE pid={pid} typ={typ} name={name} count={len(rows)} ids={[n.get("id") for n in rows[:12]]}')
    return rows[0]

def first(x): return (x or [{}])[0] if isinstance(x,list) else (x or {})
def pptr(row,path):
    for p in row.get('pointers') or []:
        if p.get('path')==path:
            return int(p.get('pathId') or p.get('pathID') or 0)
    return 0
bgr=first(bg.get('FormationBgRawImage')); rtr=first(bg.get('FormationRTRawImage'))
anchors={
 'FormationBg':{'componentPathID':int(bgr.get('pathId') or 0),'gameObjectPathID':pptr(bgr,'m_GameObject')},
 'FormationRT':{'componentPathID':int(rtr.get('pathId') or 0),'gameObjectPathID':pptr(rtr,'m_GameObject')},
}
for nm,x in anchors.items():
    go=unique_node_for_pid(x['gameObjectPathID'],'GameObject',nm)
    raw=unique_node_for_pid(x['componentPathID'])
    x['gameObjectId']=str(go['id']); x['rawImageId']=str(raw['id'])

# GO -> Transform/RectTransform exact component, Transform -> father, father -> GO.
def transform_for_go(go_id):
    cands=[]
    for e in edge_from(go_id,'component_ref'):
        n=by_id.get(str(e.get('to')))
        if n and node_type(n) in ('Transform','RectTransform'):
            cands.append(n)
    # Unity GO should have exactly one Transform/RectTransform.
    if len(cands)!=1:
        raise SystemExit(f'TRANSFORM_NOT_UNIQUE go={go_id} count={len(cands)} ids={[n.get("id") for n in cands]}')
    return cands[0]

def go_for_transform(tr_id):
    c=[]
    for e in edge_from(tr_id,'gameobject_ref'):
        if 'm_gameobject' not in field(e).lower(): continue
        n=by_id.get(str(e.get('to')))
        if n and node_type(n)=='GameObject': c.append(n)
    if len(c)!=1:
        raise SystemExit(f'GAMEOBJECT_FOR_TRANSFORM_NOT_UNIQUE tr={tr_id} count={len(c)}')
    return c[0]

def parent_transform(tr_id):
    c=[]
    for e in edge_from(tr_id,'hierarchy_ref'):
        if 'm_father' not in field(e).lower(): continue
        n=by_id.get(str(e.get('to')))
        if n and node_type(n) in ('Transform','RectTransform'): c.append(n)
    if len(c)>1: raise SystemExit(f'PARENT_TRANSFORM_AMBIGUOUS tr={tr_id} count={len(c)}')
    return c[0] if c else None

def component_rows(go):
    out=[]
    for e in edge_from(go['id'],'component_ref'):
        n=by_id.get(str(e.get('to')))
        if n: out.append(n)
    return out

def script_for_component(comp):
    out=[]
    for e in edge_from(comp['id'],'script_ref'):
        n=by_id.get(str(e.get('to')))
        if n: out.append(n)
    # MonoBehaviour normally exactly one m_Script. Built-ins zero.
    return out

# Build chain anchor GO -> ... -> root GO.
chains={}; all_script_rows=[]
for an,x in anchors.items():
    go=by_id[x['gameObjectId']]; chain=[]; seen=set(); depth=0
    while True:
        gid=str(go['id'])
        if gid in seen: raise SystemExit(f'HIERARCHY_LOOP anchor={an} go={gid}')
        seen.add(gid)
        comps=component_rows(go)
        scripts=[]
        for comp in comps:
            for scr in script_for_component(comp):
                row={
                  'anchor':an,'depth':depth,'gameObjectId':gid,'gameObjectName':node_name(go),
                  'componentId':str(comp.get('id')),'componentPathID':comp.get('pathID'),'componentType':node_type(comp),
                  'scriptId':str(scr.get('id')),'scriptPathID':scr.get('pathID'),'scriptType':node_type(scr),'scriptName':node_name(scr)
                }
                scripts.append(row); all_script_rows.append(row)
        chain.append({
          'depth':depth,'gameObjectId':gid,'gameObjectPathID':go.get('pathID'),'gameObjectName':node_name(go),
          'components':[{'id':str(c.get('id')),'pathID':c.get('pathID'),'type':node_type(c),'name':node_name(c)} for c in comps],
          'scripts':scripts
        })
        if gid==root_id: break
        tr=transform_for_go(gid); ptr=parent_transform(tr['id'])
        if ptr is None:
            break
        go=go_for_transform(ptr['id']); depth+=1
        if depth>64: raise SystemExit(f'HIERARCHY_DEPTH_LIMIT anchor={an}')
    chains[an]=chain

# Dedupe script identities while preserving every hierarchy occurrence.
script_names=sorted({r['scriptName'] for r in all_script_rows if r.get('scriptName')})

# ---------- exact CLR joins ----------
types=a.get('types') or []; methods=a.get('methods') or []; internal=a.get('internalEdges') or []; external=a.get('externalCalls') or []
type_by_rid={int(t['rid']):t for t in types}; method_by_rid={int(m['rid']):m for m in methods}
methods_by_type=defaultdict(list)
for m in methods:
    if m.get('typeRid') is not None: methods_by_type[int(m['typeRid'])].append(m)
def full_type(t): return ((str(t.get('namespace'))+'.') if t.get('namespace') else '')+str(t.get('name') or '')
def method_symbol(m):
    t=type_by_rid.get(int(m.get('typeRid') or 0)); return ((full_type(t)+'.') if t else '')+str(m.get('name') or '')
by_simple=defaultdict(list); by_full=defaultdict(list)
for t in types:
    by_simple[str(t.get('name') or '')].append(t); by_full[full_type(t)].append(t)

# Exact external APIs already indexed by MethodDef caller RID.
def classify(target):
    s=str(target).lower()
    if 'rawimage' in s and 'set_texture' in s:return 'WRITE RawImage.set_texture'
    if 'rawimage' in s and 'get_texture' in s:return 'READ RawImage.get_texture'
    if 'camera' in s and ('set_targettexture' in s or 'set_target_texture' in s):return 'WRITE Camera.set_targetTexture'
    if 'videoplayer' in s and ('set_targettexture' in s or 'set_target_texture' in s):return 'WRITE VideoPlayer.set_targetTexture'
    if 'graphics' in s and 'blit' in s:return 'WRITE Graphics.Blit'
    if 'commandbuffer' in s and 'blit' in s:return 'WRITE CommandBuffer.Blit'
    if 'material' in s and ('settexture' in s or 'set_texture' in s or 'set_maintexture' in s or 'set_main_texture' in s):return 'WRITE Material.texture'
    if 'shader' in s and ('setglobaltexture' in s or 'set_global_texture' in s):return 'WRITE Shader.SetGlobalTexture'
    if 'rendertexture' in s:return 'RENDER RenderTexture'
    if any(x in s for x in ('gameobject.find','transform.find','getcomponent','trygetcomponent')):return 'LOOKUP Component/Transform'
    if any(x in s for x in ('xlua','luaenv','luatable','luafunction','objecttranslator','lua.load_','lua_pcall','lua_raw')):return 'BOUNDARY Lua/XLua'
    if any(x in s for x in ('resources.load','assetbundle.load','resourcemanager','resourceprovider','assetmanager','textasset','zipfile','ziparchive','file.read','streamreader')):return 'BOUNDARY Resource/Storage'
    return None
api_by_method=defaultdict(list)
for ex in external:
    cl=classify(ex.get('target') or '')
    if not cl: continue
    for rid in ex.get('callerRids') or []:
        api_by_method[int(rid)].append({'class':cl,'target':ex.get('target'),'classification':ex.get('classification')})

resolved=[]; ambiguous=[]; unresolved=[]; controller_method_rids=set()
for name in script_names:
    cands=list(by_simple.get(name,[]))
    if '.' in name: cands += by_full.get(name,[])
    uniq={int(t['rid']):t for t in cands}; cands=list(uniq.values())
    occ=[r for r in all_script_rows if r.get('scriptName')==name]
    row={'scriptName':name,'occurrences':occ,'atlasCandidates':[{'typeRid':int(t['rid']),'fullName':full_type(t)} for t in cands]}
    if len(cands)==1:
        t=cands[0]; tr=int(t['rid']); ms=methods_by_type.get(tr,[])
        row['typeRid']=tr; row['fullName']=full_type(t); row['methodCount']=len(ms)
        controller_method_rids.update(int(m['rid']) for m in ms); resolved.append(row)
    elif len(cands)>1: ambiguous.append(row)
    else: unresolved.append(row)

# Direct relevant APIs and directed paths from ancestor controller methods.
direct=[]
for rid in sorted(controller_method_rids):
    if rid not in api_by_method: continue
    m=method_by_rid.get(rid)
    direct.append({'rid':rid,'symbol':method_symbol(m) if m else str(rid),'apis':api_by_method[rid],'strings':(m or {}).get('strings',[])})

adj=defaultdict(list)
for p in internal:
    if isinstance(p,(list,tuple)) and len(p)>=2:
        try: adj[int(p[0])].append(int(p[1]))
        except: pass
write_targets={rid for rid,rows in api_by_method.items() if any(str(x['class']).startswith('WRITE ') for x in rows)}
paths=[]; MAXD=5
for start in sorted(controller_method_rids):
    if start in write_targets: continue
    q=deque([start]); par={start:None}; dep={start:0}; found=[]
    while q:
        x=q.popleft(); d=dep[x]
        if d>=MAXD: continue
        for y in adj.get(x,[]):
            if y in par: continue
            par[y]=x; dep[y]=d+1
            if y in write_targets:
                z=[y]; cur=x
                while cur is not None: z.append(cur); cur=par[cur]
                z.reverse(); found.append(z); continue
            q.append(y)
    if found:
        md=min(len(z) for z in found)
        for z in found:
            if len(z)!=md: continue
            end=z[-1]
            paths.append({'startRid':start,'startSymbol':method_symbol(method_by_rid[start]),'depth':len(z)-1,'pathRids':z,'pathSymbols':[method_symbol(method_by_rid[r]) if r in method_by_rid else str(r) for r in z],'writeApis':[x for x in api_by_method[end] if str(x['class']).startswith('WRITE ')]})
            break

# Rank only exact hierarchy-derived controllers; no name proximity promotion.
write_direct=[r for r in direct if any(str(x['class']).startswith('WRITE ') for x in r['apis'])]
lua_direct=[r for r in direct if any(x['class']=='BOUNDARY Lua/XLua' for x in r['apis'])]
if write_direct or paths:
    strategy='inspect_exact_ancestor_controller_write_paths'
elif lua_direct:
    strategy='trace_exact_ancestor_controller_lua_boundary'
elif resolved:
    strategy='inspect_exact_ancestor_controller_methods_then_dynamic_binding'
else:
    strategy='ancestor_chain_has_no_resolved_controller_trace_lua_dynamic_binding'

result={
 'format':'WFGG_LASTWAR_FORMATION_RAWIMAGE_ANCESTOR_CONTROLLER_MAP_V1',
 'sources':{'ptrGraph':str(v4p),'backgroundPipeline':str(bgp),'ptrSummary':str(sump),'clrAtlas':str(atlasp)},
 'counts':{'ptrNodes':len(nodes),'ptrEdges':len(edges),'ancestorScriptOccurrences':len(all_script_rows),'uniqueScriptNames':len(script_names),'resolvedClrTypes':len(resolved),'ambiguousClrTypes':len(ambiguous),'unresolvedClrTypes':len(unresolved),'controllerMethods':len(controller_method_rids),'directRelevantMethods':len(direct),'directWriteMethods':len(write_direct),'directedWritePaths':len(paths)},
 'anchors':anchors,'chains':chains,'resolvedClrTypes':resolved,'ambiguousClrTypes':ambiguous,'unresolvedClrTypes':unresolved,
 'directRelevantMethods':direct,'directWriteMethods':write_direct,'directedWritePaths':paths,
 'conclusion':{'nextStrategy':strategy,'important':'Only exact V4 hierarchy/component/script edges and exact CLR atlas joins are evidence. Ancestor presence does not by itself prove ownership of the runtime texture assignment.'},
 'guardrails':{'existingEvidenceOnly':True,'apkAccess':False,'dllRescan':False,'bundleExtraction':False,'bundleScan':False,'candidatePromotion':False,'mainUntouched':True,'previewUntouched':True}
}
outp.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n','utf-8')

lines=['WfGg Last War — FORMATION RAWIMAGE ANCESTOR CONTROLLER MAP V1','',
 f"ptrNodes={len(nodes)} ptrEdges={len(edges)} ancestorScriptOccurrences={len(all_script_rows)} uniqueScriptNames={len(script_names)}",
 f"resolvedClrTypes={len(resolved)} ambiguousClrTypes={len(ambiguous)} unresolvedClrTypes={len(unresolved)} controllerMethods={len(controller_method_rids)}",
 f"directRelevantMethods={len(direct)} directWriteMethods={len(write_direct)} directedWritePaths={len(paths)}",
 f"nextStrategy={strategy}",'']
for an,chain in chains.items():
    lines.append('ANCESTOR CHAIN '+an)
    for row in chain:
        lines.append(f"  depth={row['depth']} GO={row['gameObjectName']} id={row['gameObjectId']}")
        for s in row['scripts']:
            lines.append(f"    SCRIPT component={s['componentType']}:{s['componentPathID']} script={s['scriptName']} scriptPathID={s['scriptPathID']}")
    lines.append('')
lines.append('EXACT CLR TYPE JOINS')
if resolved:
    for r in resolved: lines.append(f"  {r['scriptName']} -> T:{r['typeRid']} {r['fullName']} methods={r['methodCount']} occurrences={len(r['occurrences'])}")
else: lines.append('  NONE')
lines += ['', 'DIRECT ANCESTOR CONTROLLER APIS']
if direct:
    for r in direct:
        lines.append(f"  M:{r['rid']} {r['symbol']}")
        for x in r['apis']: lines.append(f"    {x['class']} :: {x['target']}")
else: lines.append('  NONE')
lines += ['', 'SHORTEST DIRECTED ANCESTOR CONTROLLER -> TEXTURE WRITE PATHS']
if paths:
    for r in paths[:80]:
        lines.append(f"  depth={r['depth']} {' -> '.join('M:'+str(x) for x in r['pathRids'])}")
        lines.append('    SYMBOLS '+' -> '.join(r['pathSymbols']))
        for x in r['writeApis']: lines.append(f"    {x['class']} :: {x['target']}")
else: lines.append('  NONE')
lines += ['', 'NEXT '+strategy,
 'RULE: ancestor/controller identity is exact V4 hierarchy+script evidence; ancestor presence alone is not runtime assignment proof.',
 'RULE: no APK read, DLL rescan, bundle extraction/scan, candidate promotion, main or preview modification.']
reportp.write_text('\n'.join(lines)+'\n','utf-8')
print('FORMATION_ANCESTOR_OK',f'scripts={len(all_script_rows)}',f'unique={len(script_names)}',f'resolved={len(resolved)}',f'directWrites={len(write_direct)}',f'paths={len(paths)}')
for r in resolved[:30]: print('FORMATION_ANCESTOR_TYPE',r['scriptName'],f"T:{r['typeRid']}",r['fullName'],f"methods={r['methodCount']}")
for r in write_direct[:30]: print('FORMATION_ANCESTOR_DIRECT_WRITE',f"M:{r['rid']}",r['symbol'])
for r in paths[:30]: print('FORMATION_ANCESTOR_WRITE_PATH',f"depth={r['depth']}",'->'.join('M:'+str(x) for x in r['pathRids']))
print('FORMATION_ANCESTOR_NEXT',strategy)
print('FORMATION_ANCESTOR_JSON',outp)
print('FORMATION_ANCESTOR_REPORT',reportp)
PY

git add "$OUT"
if ! git diff --cached --quiet; then
  git commit -m "lab: map Formation RawImage ancestor controllers"
  git push origin "$BRANCH"
fi

echo "FORMATION_ANCESTOR_DONE"
