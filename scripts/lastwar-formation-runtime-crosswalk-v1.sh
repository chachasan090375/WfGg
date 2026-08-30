#!/data/data/com.termux/files/usr/bin/bash
set -Eeuo pipefail

# WfGg Last War LAB — crosswalk between the CLOSED Formation PPtr V4 graph
# and the serialized FormationBg / FormationRT RawImage state already recovered.
# Existing JSON only: no APK read, no extraction, no bundle scan, no promotion.

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BRANCH="portal-auth-lastwar-lab-v1"
META="$ROOT/frontend/lab/master-assets-v2/meta"
GRAPH="$META/formation-ptr-exact-v4.json"
SUMMARY="$META/formation-ptr-exact-v4-summary-v1.json"
BGPIPE="$META/formation-background-pipeline-v1.json"
BINDING="$META/formation-runtime-binding-v1.json"
OUT="$META/formation-runtime-crosswalk-v1.json"
REPORT="$HOME/storage/downloads/WFGG_LASTWAR_FORMATION_RUNTIME_CROSSWALK_V1.txt"

fail(){ printf 'ERREUR: %s\n' "$*" >&2; exit 1; }
cd "$ROOT"
[[ "$(git branch --show-current)" == "$BRANCH" ]] || fail "branche LAB incorrecte"
for f in "$GRAPH" "$SUMMARY" "$BGPIPE" "$BINDING"; do [[ -s "$f" ]] || fail "fichier absent: $f"; done
command -v python >/dev/null 2>&1 || fail "python absent"
mkdir -p "$(dirname "$OUT")" "$(dirname "$REPORT")"

python - "$GRAPH" "$SUMMARY" "$BGPIPE" "$BINDING" "$OUT" "$REPORT" <<'PY'
from pathlib import Path
import json, sys

graph_p, summary_p, bgpipe_p, binding_p, out_p, report_p = map(Path, sys.argv[1:])
graph = json.loads(graph_p.read_text('utf-8'))
summary = json.loads(summary_p.read_text('utf-8'))
bgpipe = json.loads(bgpipe_p.read_text('utf-8'))
binding = json.loads(binding_p.read_text('utf-8'))

counts = summary.get('counts') or {}
closed = (
    int(counts.get('renderUnresolvedEdges') or 0) == 0 and
    int(counts.get('unresolvedRefs') or 0) == 0 and
    int(counts.get('parseErrors') or 0) == 0
)
if not closed:
    raise SystemExit('ERREUR: le graphe PPtr V4 n est pas ferme')

objects = graph.get('objects') or []
edges = graph.get('edges') or []

def first_row(v):
    return (v or [{}])[0] if isinstance(v, list) else (v or {})

bg = first_row(bgpipe.get('FormationBgRawImage'))
rt = first_row(bgpipe.get('FormationRTRawImage'))
if not bg or not rt:
    raise SystemExit('ERREUR: FormationBg/FormationRT absents du pipeline background')

def ptr_from_fields(row, key):
    f = (row.get('fields') or {}).get(key) or {}
    return {'fileID': int(f.get('m_FileID') or 0), 'pathID': int(f.get('m_PathID') or 0)}

def ptr_from_pointers(row, path):
    for p in row.get('pointers') or []:
        if p.get('path') == path:
            return {'fileID': int(p.get('fileId') or 0), 'pathID': int(p.get('pathId') or 0)}
    return {'fileID': 0, 'pathID': 0}

def pid(row):
    return int(row.get('pathId') or row.get('pathID') or 0)

bg_comp = pid(bg)
rt_comp = pid(rt)
bg_go = ptr_from_pointers(bg, 'm_GameObject')['pathID']
rt_go = ptr_from_pointers(rt, 'm_GameObject')['pathID']
bg_mat = ptr_from_fields(bg, 'm_Material')
bg_tex = ptr_from_fields(bg, 'm_Texture')
rt_mat = ptr_from_fields(rt, 'm_Material')
rt_tex = ptr_from_fields(rt, 'm_Texture')

# Compact helpers deliberately avoid copying multi-megabyte object payloads.
def scalar(v):
    return isinstance(v, (str, int, float, bool)) or v is None

def object_id(o):
    for k in ('id','objectId','objectID','key','ref','canonicalId','canonicalID'):
        if k in o and scalar(o.get(k)):
            return o.get(k)
    # Fall back to the first scalar containing CAB/# or a path id.
    for k,v in o.items():
        if isinstance(v, str) and ('CAB-' in v or '#' in v):
            return v
    return None

def object_summary(o):
    keep = {}
    for k in ('id','objectId','objectID','key','ref','canonicalId','canonicalID','bundleId','bundleID','bundleAlias','assetPath','sourcePath','file','path','pathID','pathId','type','class','className','name','objectName','script','scriptName'):
        if k in o and scalar(o.get(k)):
            keep[k] = o.get(k)
    if not keep:
        for k,v in o.items():
            if scalar(v):
                keep[k] = v
            if len(keep) >= 12:
                break
    keep['_keys'] = list(o.keys())[:32]
    return keep

def compact_edge(e):
    return {
        k:e.get(k) for k in ('from','to','sourceType','targetType','relation','fieldPath','fileID','pathID','confidence','resolutionError')
        if k in e
    } | ({'external':e.get('external')} if e.get('external') else {})

def contains_pid(value, p):
    if not p:
        return False
    s = str(p)
    if isinstance(value, str):
        return s in value
    if isinstance(value, int):
        return value == p
    return False

def object_matches(o, *, pids=(), terms=()):
    oid = object_id(o)
    for p in pids:
        if contains_pid(oid, p):
            return True
        for k in ('pathID','pathId'):
            if contains_pid(o.get(k), p):
                return True
    # Names/terms can be nested, so serialize only this one object.
    if terms:
        txt = json.dumps(o, ensure_ascii=False, separators=(',',':'))
        low = txt.lower()
        if any(t.lower() in low for t in terms):
            return True
    return False

def edge_incident(e, pids):
    for p in pids:
        if contains_pid(e.get('from'), p) or contains_pid(e.get('to'), p):
            return True
    return False

anchor_pids = [bg_comp, bg_go, rt_comp, rt_go]
anchor_objects = [object_summary(o) for o in objects if object_matches(o, pids=anchor_pids, terms=('FormationBg','FormationRT'))]
anchor_edges = [compact_edge(e) for e in edges if edge_incident(e, anchor_pids)]

# Resolve the exact serialized material PPtr of FormationRT inside V4.
rt_material_edges = []
if rt_mat['pathID']:
    for e in edges:
        try:
            ep = int(e.get('pathID') or 0)
            ef = int(e.get('fileID') or 0)
        except Exception:
            continue
        if ep == rt_mat['pathID'] and ef == rt_mat['fileID']:
            # Prefer the FormationRT source when the source id embeds its path id,
            # but retain all exact matches to avoid silently discarding evidence.
            rt_material_edges.append(compact_edge(e))

rt_material_exact = [e for e in rt_material_edges if e.get('confidence') == 'serialized_exact']

terms = [
    'FormationBg','FormationRT','RenderTexture','FormationCamera',
    'HeroShowCamera','ShowCamera','HeroShowBlend','FormationContent'
]
term_hits = {}
for term in terms:
    os = [object_summary(o) for o in objects if object_matches(o, terms=(term,))]
    es = []
    tl = term.lower()
    for e in edges:
        txt = json.dumps(e, ensure_ascii=False, separators=(',',':')).lower()
        if tl in txt:
            es.append(compact_edge(e))
    term_hits[term] = {
        'objectHitCount': len(os),
        'edgeHitCount': len(es),
        'objects': os[:80],
        'edges': es[:120],
        'truncated': len(os) > 80 or len(es) > 120,
    }

bg_null = bg_mat == {'fileID':0,'pathID':0} and bg_tex == {'fileID':0,'pathID':0}
rt_texture_null = rt_tex == {'fileID':0,'pathID':0}
serialized_texture_binding_absent = bg_tex['pathID'] == 0 and rt_tex['pathID'] == 0

out = {
    'format':'WFGG_LASTWAR_FORMATION_RUNTIME_CROSSWALK_V1',
    'sources':{
        'ptrGraph':str(graph_p),
        'ptrSummary':str(summary_p),
        'backgroundPipeline':str(bgpipe_p),
        'legacyRuntimeBindingAudit':str(binding_p),
    },
    'ptrClosure':{
        'closed':closed,
        'objects':counts.get('objects'),
        'edges':counts.get('edges'),
        'renderExactEdges':counts.get('renderExactEdges'),
        'renderUnresolvedEdges':counts.get('renderUnresolvedEdges'),
        'unresolvedRefs':counts.get('unresolvedRefs'),
        'parseErrors':counts.get('parseErrors'),
    },
    'serializedRawImages':{
        'FormationBg':{
            'componentPathID':bg_comp,
            'gameObjectPathID':bg_go,
            'material':bg_mat,
            'texture':bg_tex,
            'materialNull':bg_mat == {'fileID':0,'pathID':0},
            'textureNull':bg_tex == {'fileID':0,'pathID':0},
        },
        'FormationRT':{
            'componentPathID':rt_comp,
            'gameObjectPathID':rt_go,
            'material':rt_mat,
            'texture':rt_tex,
            'textureNull':rt_texture_null,
            'materialExactResolutionCount':len(rt_material_exact),
            'materialExactResolutions':rt_material_exact,
            'allMaterialPPtrMatches':rt_material_edges,
        }
    },
    'graphAnchors':{
        'objectHitCount':len(anchor_objects),
        'edgeHitCount':len(anchor_edges),
        'objects':anchor_objects[:120],
        'edges':anchor_edges[:240],
        'truncated':len(anchor_objects)>120 or len(anchor_edges)>240,
    },
    'termHits':term_hits,
    'legacyRuntimeBindingAudit':{
        'hitCount':len(binding.get('hits') or []),
        'candidateCount':len(binding.get('candidates') or []),
        'scannedEntryCount':len(binding.get('scannedEntries') or []),
    },
    'conclusion':{
        'assetPPtrGraphClosed':closed,
        'serializedFormationBgMaterialAndTextureBothNull':bg_null,
        'serializedFormationRTTextureNull':rt_texture_null,
        'serializedTextureBindingAbsentOnBothRawImages':serialized_texture_binding_absent,
        'runtimeAssignmentSearchRequired':serialized_texture_binding_absent,
        'reason':(
            'The exact serialized asset graph is closed, while both FormationBg and FormationRT '
            'RawImage texture PPtrs are null in the prefab. The next evidence target is therefore '
            'the runtime/later-stage assignment path rather than another unresolved asset PPtr.'
        )
    },
    'guardrails':{
        'existingJsonOnly':True,
        'apkAccess':False,
        'newExtraction':False,
        'bundleScan':False,
        'candidatePromotion':False,
        'mainUntouched':True,
        'previewUntouched':True,
    }
}
out_p.write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n','utf-8')

c = out['conclusion']
rt_targets = [e.get('to') for e in rt_material_exact if e.get('to')]
lines = [
    'WfGg Last War — FORMATION RUNTIME CROSSWALK V1','',
    f"ptrClosed={closed} objects={counts.get('objects')} edges={counts.get('edges')} renderExact={counts.get('renderExactEdges')} unresolvedRefs={counts.get('unresolvedRefs')} parseErrors={counts.get('parseErrors')}",
    f"FormationBg componentPathID={bg_comp} gameObjectPathID={bg_go} material={bg_mat} texture={bg_tex}",
    f"FormationRT componentPathID={rt_comp} gameObjectPathID={rt_go} material={rt_mat} texture={rt_tex}",
    f"FormationRT materialExactResolutionCount={len(rt_material_exact)} targets={json.dumps(rt_targets,ensure_ascii=False,separators=(',',':'))}",
    f"serializedTextureBindingAbsentOnBothRawImages={c['serializedTextureBindingAbsentOnBothRawImages']}",
    f"runtimeAssignmentSearchRequired={c['runtimeAssignmentSearchRequired']}",
    '', 'TERM COUNTS'
]
for t in terms:
    h=term_hits[t]
    lines.append(f"  {t}: objects={h['objectHitCount']} edges={h['edgeHitCount']}")
lines += [
    '',
    'CONCLUSION',
    '  '+c['reason'],
    '',
    'RULE: existing recovered JSON only; no APK read, extraction, bundle scan, candidate promotion, main or preview modification.'
]
report_p.write_text('\n'.join(lines)+'\n','utf-8')

print('FORMATION_RUNTIME_CROSSWALK_OK',
      f"ptrClosed={closed}",
      f"bgTextureNull={bg_tex == {'fileID':0,'pathID':0}}",
      f"rtTextureNull={rt_texture_null}",
      f"rtMaterialExact={len(rt_material_exact)}")
print('FORMATION_RUNTIME_RT_MATERIAL_TARGETS',json.dumps(rt_targets,ensure_ascii=False,separators=(',',':')))
for t in terms:
    h=term_hits[t]
    print('FORMATION_RUNTIME_TERM',t,f"objects={h['objectHitCount']}",f"edges={h['edgeHitCount']}")
print('FORMATION_RUNTIME_NEXT',f"runtimeAssignmentSearchRequired={c['runtimeAssignmentSearchRequired']}")
print('FORMATION_RUNTIME_CROSSWALK_JSON',out_p)
print('FORMATION_RUNTIME_CROSSWALK_REPORT',report_p)
PY

git add "$OUT"
if ! git diff --cached --quiet; then git commit -m "lab: crosswalk Formation PPtr closure with runtime RawImages"; fi
git push origin "$BRANCH"
printf '%s\n' '=== FORMATION RUNTIME CROSSWALK V1 TERMINE ===' "JSON: $OUT" "Rapport: $REPORT"
