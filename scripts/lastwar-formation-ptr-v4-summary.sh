#!/data/data/com.termux/files/usr/bin/bash
set -Eeuo pipefail

# WfGg Last War LAB — compact summary of the EXISTING Formation PPtr V4 graph.
# No APK access, no extraction, no scan, no candidate promotion.

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BRANCH="portal-auth-lastwar-lab-v1"
SRC="$ROOT/frontend/lab/master-assets-v2/meta/formation-ptr-exact-v4.json"
OUT="$ROOT/frontend/lab/master-assets-v2/meta/formation-ptr-exact-v4-summary-v1.json"
REPORT="$HOME/storage/downloads/WFGG_LASTWAR_FORMATION_PTR_EXACT_V4_SUMMARY.txt"

fail(){ printf 'ERREUR: %s\n' "$*" >&2; exit 1; }
cd "$ROOT"
[[ "$(git branch --show-current)" == "$BRANCH" ]] || fail "branche LAB incorrecte"
[[ -s "$SRC" ]] || fail "formation-ptr-exact-v4.json absent"
command -v python >/dev/null 2>&1 || fail "python absent"
mkdir -p "$(dirname "$OUT")" "$(dirname "$REPORT")"

python - "$SRC" "$OUT" "$REPORT" <<'PY'
from pathlib import Path
from collections import Counter
import json, sys

src=Path(sys.argv[1]); out=Path(sys.argv[2]); report=Path(sys.argv[3])
d=json.loads(src.read_text('utf-8'))
counts=d.get('counts') or {}
edges=d.get('edges') or []
unresolved=d.get('unresolvedRefs') or []

def extpath(x):
    e=x.get('external') or {}
    return str(e.get('path') or '')

def edge_relation_for_unresolved(u):
    # Prefer exact edge match if relation is not embedded in unresolvedRefs.
    for e in edges:
        if e.get('from')==u.get('from') and e.get('fieldPath')==u.get('fieldPath') and e.get('fileID')==u.get('fileID') and e.get('pathID')==u.get('pathID'):
            return e.get('relation')
    return None

unity_exact=[]
for e in edges:
    p=extpath(e).replace('\\','/').strip().lower()
    if p.endswith('library/unity default resources') or p.endswith('unity default resources'):
        if int(e.get('pathID') or 0)==10101 and e.get('confidence')=='serialized_exact':
            unity_exact.append(e)

unity_unresolved=[]
for u in unresolved:
    p=extpath(u).replace('\\','/').strip().lower()
    if (p.endswith('library/unity default resources') or p.endswith('unity default resources')) and int(u.get('pathID') or 0)==10101:
        unity_unresolved.append(u)

groups=Counter()
remaining=[]
for u in unresolved:
    relation=edge_relation_for_unresolved(u)
    row={
        'from':u.get('from'),
        'sourceType':u.get('sourceType'),
        'relation':relation,
        'fieldPath':u.get('fieldPath'),
        'fileID':u.get('fileID'),
        'pathID':u.get('pathID'),
        'externalPath':extpath(u),
        'resolutionError':u.get('resolutionError'),
    }
    remaining.append(row)
    groups[(row['externalPath'],row['pathID'],row['relation'],row['fieldPath'],row['sourceType'],row['resolutionError'])]+=1

summary={
    'format':'WFGG_LASTWAR_FORMATION_PTR_EXACT_V4_SUMMARY_V1',
    'source':str(src),
    'target':d.get('target'),
    'dependencySelection':d.get('dependencySelection'),
    'counts':{
        'objects':counts.get('objects'),
        'edges':counts.get('edges'),
        'renderExactEdges':counts.get('renderExactEdges'),
        'renderUnresolvedEdges':counts.get('renderUnresolvedEdges'),
        'unresolvedRefs':counts.get('unresolvedRefs',len(unresolved)),
        'parseErrors':counts.get('parseErrors'),
    },
    'unityDefaultResources10101':{
        'exactSerializedEdges':len(unity_exact),
        'remainingUnresolvedRefs':len(unity_unresolved),
        'closed':len(unity_exact)>0 and len(unity_unresolved)==0,
        'relations':dict(Counter(e.get('relation') for e in unity_exact)),
        'sourceObjects':len(set(e.get('from') for e in unity_exact)),
        'targetObjects':sorted(set(e.get('to') for e in unity_exact)),
    },
    'remainingUnresolvedGroups':[
        {
            'count':n,'externalPath':k[0],'pathID':k[1],'relation':k[2],
            'fieldPath':k[3],'sourceType':k[4],'resolutionError':k[5]
        }
        for k,n in sorted(groups.items(), key=lambda kv:(str(kv[0][0]),str(kv[0][1]),str(kv[0][2]),str(kv[0][3]),str(kv[0][4]),str(kv[0][5])))
    ],
    'remainingUnresolvedRefs':remaining,
    'guardrails':{
        'sourceJsonOnly':True,
        'apkAccess':False,
        'newExtraction':False,
        'newScan':False,
        'candidatePromotion':False,
    }
}
out.write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n','utf-8')

c=summary['counts']; ud=summary['unityDefaultResources10101']
lines=[
    'WfGg Last War — FORMATION PPtr V4 COMPACT SUMMARY','',
    f"objects={c['objects']} edges={c['edges']} renderExact={c['renderExactEdges']} renderUnresolved={c['renderUnresolvedEdges']} unresolvedRefs={c['unresolvedRefs']} parseErrors={c['parseErrors']}",
    f"unityDefaultResources10101 exactEdges={ud['exactSerializedEdges']} unresolvedRemaining={ud['remainingUnresolvedRefs']} closed={ud['closed']}",
    'unityDefaultResources10101 relations='+json.dumps(ud['relations'],ensure_ascii=False,separators=(',',':')),
    'unityDefaultResources10101 targets='+json.dumps(ud['targetObjects'],ensure_ascii=False,separators=(',',':')),
    '', 'REMAINING UNRESOLVED GROUPS'
]
if summary['remainingUnresolvedGroups']:
    for g in summary['remainingUnresolvedGroups']:
        lines.append('  '+json.dumps(g,ensure_ascii=False,separators=(',',':')))
else:
    lines.append('  NONE')
lines += ['', 'RULE: summary reads the existing V4 graph only; no scan/extraction/candidate promotion.']
report.write_text('\n'.join(lines)+'\n','utf-8')

print('FORMATION_PTR_V4_SUMMARY_OK',f"objects={c['objects']}",f"edges={c['edges']}",f"renderExact={c['renderExactEdges']}",f"renderUnresolved={c['renderUnresolvedEdges']}",f"unresolvedRefs={c['unresolvedRefs']}",f"parseErrors={c['parseErrors']}")
print('FORMATION_PTR_V4_UNITY_DEFAULT_10101',f"exactEdges={ud['exactSerializedEdges']}",f"remaining={ud['remainingUnresolvedRefs']}",f"closed={ud['closed']}")
if summary['remainingUnresolvedGroups']:
    for g in summary['remainingUnresolvedGroups']:
        print('FORMATION_PTR_V4_REMAINING',json.dumps(g,ensure_ascii=False,separators=(',',':')))
else:
    print('FORMATION_PTR_V4_REMAINING NONE')
print('FORMATION_PTR_V4_SUMMARY_JSON',out)
print('FORMATION_PTR_V4_SUMMARY_REPORT',report)
PY

git add "$OUT"
if ! git diff --cached --quiet; then git commit -m "lab: summarize exact Formation PPtr V4 closure"; fi
git push origin "$BRANCH"
printf '%s\n' '=== FORMATION PPtr V4 SUMMARY TERMINE ===' "JSON: $OUT" "Rapport: $REPORT"
