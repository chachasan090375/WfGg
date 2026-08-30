#!/data/data/com.termux/files/usr/bin/bash
set -Eeuo pipefail

# WfGg Last War LAB — exact V4 RawImage owner/script crosswalk.
# Existing recovered JSON only. NO APK read, NO DLL rescan, NO bundle extraction/scan.

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BRANCH="portal-auth-lastwar-lab-v1"
META="$ROOT/frontend/lab/master-assets-v2/meta"
V4="$META/formation-ptr-exact-v4.json"
BG="$META/formation-background-pipeline-v1.json"
SUMMARY="$META/formation-ptr-exact-v4-summary-v1.json"
OUT="$META/formation-rawimage-owner-script-crosswalk-v1.json"
REPORT="$HOME/storage/downloads/WFGG_LASTWAR_FORMATION_RAWIMAGE_OWNER_SCRIPT_CROSSWALK_V1.txt"

fail(){ printf 'ERREUR: %s\n' "$*" >&2; exit 1; }
cd "$ROOT"
[[ "$(git branch --show-current)" == "$BRANCH" ]] || fail "branche LAB incorrecte"
for f in "$V4" "$BG" "$SUMMARY"; do [[ -s "$f" ]] || fail "fichier absent: $f"; done
command -v python >/dev/null 2>&1 || fail "python absent"
mkdir -p "$(dirname "$OUT")" "$(dirname "$REPORT")"

python - "$V4" "$BG" "$SUMMARY" "$OUT" "$REPORT" <<'PY'
from pathlib import Path
from collections import defaultdict
import json,re,sys
v4p,bgp,sump,outp,reportp=map(Path,sys.argv[1:])
g=json.loads(v4p.read_text('utf-8'))
bg=json.loads(bgp.read_text('utf-8'))
sumj=json.loads(sump.read_text('utf-8'))
objects=g.get('objects') or []
edges=g.get('edges') or []
counts=sumj.get('counts') or {}
if int(counts.get('unresolvedRefs') or 0) or int(counts.get('parseErrors') or 0):
    raise SystemExit('ERREUR: graphe V4 non ferme')

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
    out=set()
    for k in ('id','objectId','objectID','key','ref','canonicalId','canonicalID'):
        v=o.get(k)
        if isinstance(v,(str,int)):out.add(str(v))
    p=pid_of_obj(o)
    if p is not None: out.add(str(p))
    return out

def obj_type(o):
    for k in ('type','class','className','objectType','objectClass'):
        if o.get(k) is not None:return str(o.get(k))
    return ''

def obj_name(o):
    for k in ('name','objectName','m_Name','gameObject','scriptName'):
        if isinstance(o.get(k),str) and o.get(k):return o.get(k)
    return ''

def summary(o):
    keep={}
    for k in ('id','objectId','objectID','key','ref','canonicalId','canonicalID','pathID','pathId','bundleId','bundleID','assetPath','sourcePath','file','type','class','className','objectType','name','objectName','gameObject','script','scriptName'):
        if k in o and isinstance(o.get(k),(str,int,float,bool)):
            keep[k]=o.get(k)
    keep['_derivedPathID']=pid_of_obj(o)
    keep['_derivedType']=obj_type(o)
    keep['_derivedName']=obj_name(o)
    return keep

def compact_edge(e):
    r={k:e.get(k) for k in ('from','to','sourceType','targetType','relation','fieldPath','fileID','pathID','confidence','resolutionError') if k in e}
    if e.get('external'):r['external']=e.get('external')
    return r

def edge_relation(e):return str(e.get('relation') or e.get('rel') or e.get('kind') or '')

def trailing_pid(v):
    if isinstance(v,int):return v
    if not isinstance(v,str):return None
    if re.fullmatch(r'-?\d+',v):
        try:return int(v)
        except:return None
    m=re.search(r'#(-?\d+)$',v)
    return int(m.group(1)) if m else None

# Exact object indexes.
by_id=defaultdict(list);by_pid=defaultdict(list)
for o in objects:
    for i in ids_of_obj(o):by_id[i].append(o)
    p=pid_of_obj(o)
    if p is not None:by_pid[p].append(o)

def resolve_endpoint(v):
    rows=[]
    if isinstance(v,(str,int)):
        rows.extend(by_id.get(str(v),[]))
    p=trailing_pid(v)
    if p is not None: rows.extend(by_pid.get(p,[]))
    # stable dedup by Python identity
    seen=set();out=[]
    for o in rows:
        k=id(o)
        if k not in seen:seen.add(k);out.append(o)
    return out

def endpoint_matches(v,ids,pids):
    if isinstance(v,(str,int)) and str(v) in ids:return True
    p=trailing_pid(v)
    return p in pids if p is not None else False

bgr=first(bg.get('FormationBgRawImage'));rtr=first(bg.get('FormationRTRawImage'))
anchors={
 'FormationBg':{'componentPathID':int(bgr.get('pathId') or 0),'gameObjectPathID':pptr(bgr,'m_GameObject')},
 'FormationRT':{'componentPathID':int(rtr.get('pathId') or 0),'gameObjectPathID':pptr(rtr,'m_GameObject')},
}
for a in anchors.values():
    a['componentObjects']=[summary(o) for o in by_pid.get(a['componentPathID'],[])]
    a['gameObjectObjects']=[summary(o) for o in by_pid.get(a['gameObjectPathID'],[])]

# Build exact anchor identities.
anchor_ids={};anchor_pids={}
for name,a in anchors.items():
    ps={a['componentPathID'],a['gameObjectPathID']};anchor_pids[name]=ps
    ids=set(map(str,ps))
    for p in ps:
        for o in by_pid.get(p,[]):ids.update(ids_of_obj(o))
    anchor_ids[name]=ids

# Incoming exact refs to component/GO anchors.
incoming=[]
for name in anchors:
    for e in edges:
        to=e.get('to')
        # Prefer resolved endpoint identity. pathID on an edge is also a serialized target pointer in V4.
        hit=endpoint_matches(to,anchor_ids[name],anchor_pids[name])
        if not hit:
            try: hit=int(e.get('pathID')) in anchor_pids[name]
            except: hit=False
        if not hit:continue
        rel=edge_relation(e)
        row={'anchor':name,'edge':compact_edge(e),'sourceObjects':[summary(o) for o in resolve_endpoint(e.get('from'))]}
        incoming.append(row)

# Exact serialized refs are the strongest runtime-owner candidates; hierarchy/component bookkeeping retained separately.
serialized_in=[r for r in incoming if edge_relation(r['edge']).lower()=='serialized_ref']
source_objs=[]
for r in serialized_in:
    for o in resolve_endpoint(r['edge'].get('from')):
        source_objs.append((r,o))

# Follow script_ref from exact source MonoBehaviours/components.
def outgoing_from_object(o,relation=None):
    ids=ids_of_obj(o);p=pid_of_obj(o);out=[]
    for e in edges:
        fr=e.get('from')
        hit=(isinstance(fr,(str,int)) and str(fr) in ids) or (p is not None and trailing_pid(fr)==p)
        if not hit:continue
        if relation and edge_relation(e).lower()!=relation.lower():continue
        out.append(e)
    return out

controllers=[]
seen_controller=set()
for inrow,o in source_objs:
    scripts=[]
    for se in outgoing_from_object(o,'script_ref'):
        scripts.append({'edge':compact_edge(se),'targets':[summary(x) for x in resolve_endpoint(se.get('to'))]})
    key=(inrow['anchor'],str(inrow['edge'].get('from')),str(inrow['edge'].get('fieldPath')),pid_of_obj(o))
    if key in seen_controller:continue
    seen_controller.add(key)
    controllers.append({
      'anchor':inrow['anchor'],'incomingEdge':inrow['edge'],'source':summary(o),
      'sourceType':obj_type(o),'sourceName':obj_name(o),'scriptRefs':scripts,
      'exactSerializedReference':True
    })

# Components colocated on the FormationBg / FormationRT GameObjects.
colocated=[]
for name,a in anchors.items():
    go_objs=by_pid.get(a['gameObjectPathID'],[])
    for go in go_objs:
        for e in outgoing_from_object(go):
            if edge_relation(e).lower()!='component_ref':continue
            for comp in resolve_endpoint(e.get('to')):
                scripts=[]
                for se in outgoing_from_object(comp,'script_ref'):
                    scripts.append({'edge':compact_edge(se),'targets':[summary(x) for x in resolve_endpoint(se.get('to'))]})
                colocated.append({'anchor':name,'componentEdge':compact_edge(e),'component':summary(comp),'scriptRefs':scripts})

# Compact exact script target names for report. This is identity evidence only, not behavioral proof.
def script_names(rows):
    out=[]
    for r in rows:
        for s in r.get('scriptRefs') or []:
            for t in s.get('targets') or []:
                n=t.get('_derivedName') or t.get('name') or t.get('objectName') or ''
                typ=t.get('_derivedType') or ''
                ident=t.get('id') or t.get('objectId') or t.get('ref') or t.get('_derivedPathID')
                out.append({'anchor':r.get('anchor'),'name':n,'type':typ,'id':ident,'source':r.get('source') or r.get('component')})
    # dedup
    ded=[];seen=set()
    for x in out:
        k=(x['anchor'],x['name'],x['type'],str(x['id']))
        if k not in seen:seen.add(k);ded.append(x)
    return ded
controller_scripts=script_names(controllers)
colocated_scripts=script_names(colocated)

if controller_scripts:
    strategy='inspect_exact_rawimage_referencing_scripts_in_clr_atlas'
elif colocated_scripts:
    strategy='inspect_exact_colocated_scripts_and_runtime_lookup_paths'
else:
    strategy='targeted_current_install_locator_or_runtime_name_lookup_trace_required'

result={
 'format':'WFGG_LASTWAR_FORMATION_RAWIMAGE_OWNER_SCRIPT_CROSSWALK_V1',
 'sources':{'ptrGraph':str(v4p),'backgroundPipeline':str(bgp),'ptrSummary':str(sump)},
 'anchors':anchors,
 'counts':{
   'objects':len(objects),'edges':len(edges),'incomingAnchorEdges':len(incoming),
   'incomingSerializedRefs':len(serialized_in),'exactControllerRows':len(controllers),
   'exactControllerScriptTargets':len(controller_scripts),'colocatedComponentRows':len(colocated),
   'colocatedScriptTargets':len(colocated_scripts),
 },
 'incomingAnchorEdges':incoming[:500],
 'exactSerializedRawImageReferrers':controllers[:300],
 'exactControllerScriptTargets':controller_scripts[:300],
 'colocatedComponents':colocated[:300],
 'colocatedScriptTargets':colocated_scripts[:300],
 'conclusion':{
   'nextStrategy':strategy,
   'important':'Only exact V4 PPtr edges are used for identity. Script proximity/name does not prove runtime texture assignment behavior.'
 },
 'guardrails':{'existingJsonOnly':True,'apkAccess':False,'dllRescan':False,'bundleExtraction':False,'bundleScan':False,'candidatePromotion':False,'mainUntouched':True,'previewUntouched':True}
}
outp.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n','utf-8')

lines=['WfGg Last War — FORMATION RAWIMAGE OWNER / SCRIPT CROSSWALK V1','',
 f"objects={len(objects)} edges={len(edges)} incomingAnchorEdges={len(incoming)} incomingSerializedRefs={len(serialized_in)}",
 f"exactControllerRows={len(controllers)} exactControllerScriptTargets={len(controller_scripts)} colocatedComponents={len(colocated)} colocatedScriptTargets={len(colocated_scripts)}",
 f"nextStrategy={strategy}",'', 'ANCHORS']
for n,a in anchors.items():
    lines.append(f"  {n}: componentPathID={a['componentPathID']} gameObjectPathID={a['gameObjectPathID']}")
lines += ['', 'EXACT SERIALIZED REFERRERS OF FormationBg / FormationRT']
if controllers:
    for r in controllers[:100]:
        e=r['incomingEdge'];s=r['source']
        lines.append(f"  {r['anchor']} field={e.get('fieldPath')} relation={e.get('relation')} source={e.get('from')} type={s.get('_derivedType')} name={s.get('_derivedName')} pathID={s.get('_derivedPathID')}")
        for sr in r['scriptRefs'][:12]:
            for t in sr['targets'][:12]:
                lines.append(f"    SCRIPT target={sr['edge'].get('to')} type={t.get('_derivedType')} name={t.get('_derivedName')} pathID={t.get('_derivedPathID')}")
else: lines.append('  NONE')
lines += ['', 'COLOCATED COMPONENT SCRIPT TARGETS']
if colocated_scripts:
    for x in colocated_scripts[:100]:lines.append(f"  {x['anchor']} scriptName={x['name']} type={x['type']} id={x['id']}")
else: lines.append('  NONE')
lines += ['', 'NEXT '+strategy,
 'RULE: exact serialized edge identity only; script/name correlation is not promoted to runtime behavior.',
 'RULE: no APK read, DLL rescan, bundle extraction/scan, main or preview modification performed.']
reportp.write_text('\n'.join(lines)+'\n','utf-8')
print('FORMATION_RAWIMAGE_OWNER_OK',f'incoming={len(incoming)}',f'serialized={len(serialized_in)}',f'controllers={len(controllers)}',f'controllerScripts={len(controller_scripts)}',f'colocatedScripts={len(colocated_scripts)}')
for x in controller_scripts[:30]:print('FORMATION_RAWIMAGE_OWNER_SCRIPT',x['anchor'],x['name'] or '-',x['type'] or '-',x['id'])
print('FORMATION_RAWIMAGE_OWNER_NEXT',strategy)
print('FORMATION_RAWIMAGE_OWNER_JSON',outp)
print('FORMATION_RAWIMAGE_OWNER_REPORT',reportp)
PY

git add "$OUT"
if ! git diff --cached --quiet; then
  git commit -m "lab: trace exact Formation RawImage owners to scripts"
  git push origin "$BRANCH"
fi

echo "FORMATION_RAWIMAGE_OWNER_DONE"
