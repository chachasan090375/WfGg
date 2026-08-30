#!/data/data/com.termux/files/usr/bin/bash
set -Eeuo pipefail

# WfGg Last War LAB — inspect EXISTING serialized evidence for LuaUIFormLogic.
# Existing metadata only: no APK read, no DLL rescan, no bundle extraction/scan.

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BRANCH="portal-auth-lastwar-lab-v1"
BASE="$ROOT/frontend/lab/master-assets-v2"
META="$BASE/meta"
INDEX="$BASE/index"
V4="$META/formation-ptr-exact-v4.json"
OUT="$META/formation-luauiformlogic-serialized-evidence-v1.json"
REPORT="$HOME/storage/downloads/WFGG_LASTWAR_FORMATION_LUAUIFORMLOGIC_SERIALIZED_EVIDENCE_V1.txt"

fail(){ printf 'ERREUR: %s\n' "$*" >&2; exit 1; }
cd "$ROOT"
[[ "$(git branch --show-current)" == "$BRANCH" ]] || fail "branche LAB incorrecte"
[[ -s "$V4" ]] || fail "graphe V4 absent: $V4"
command -v python >/dev/null 2>&1 || fail "python absent"
mkdir -p "$(dirname "$OUT")" "$(dirname "$REPORT")"

python - "$ROOT" "$V4" "$META" "$INDEX" "$OUT" "$REPORT" <<'PY'
from pathlib import Path
import json,re,sys

root,v4p,meta,index,outp,reportp=map(Path,sys.argv[1:])
TERM='LuaUIFormLogic'; term=TERM.lower()
SECONDARY=('TextAsset','MonoScript','script_ref')

v4=json.loads(v4p.read_text('utf-8'))
records=[]

def scalar_blob(x):
    try:return json.dumps(x,ensure_ascii=False,separators=(',',':'))
    except:return str(x)

def walk(x,path='$'):
    if isinstance(x,dict):
        blob=scalar_blob(x)
        if term in blob.lower():
            records.append({'path':path,'record':x})
        for k,v in x.items(): walk(v,f'{path}.{k}')
    elif isinstance(x,list):
        for i,v in enumerate(x): walk(v,f'{path}[{i}]')
walk(v4)

# Extract edge-like rows conservatively. We do not infer endpoint identity when schema is unclear.
script_edges=[]
all_edge_rows=[]
def collect_edges(x,path='$'):
    if isinstance(x,dict):
        rel=''
        for k in ('relation','rel','kind','edgeType','type'):
            if isinstance(x.get(k),str): rel=x[k]; break
        if rel:
            row={'path':path,'relation':rel,'record':x}
            all_edge_rows.append(row)
            if rel.lower()=='script_ref' or 'script_ref' in rel.lower(): script_edges.append(row)
        for k,v in x.items(): collect_edges(v,f'{path}.{k}')
    elif isinstance(x,list):
        for i,v in enumerate(x): collect_edges(v,f'{path}[{i}]')
collect_edges(v4)

# Exact V4 relation evidence exists only if the serialized record itself contains the exact type name.
exact_v4=[]
for r in records:
    blob=scalar_blob(r['record'])
    exact_v4.append({
      'path':r['path'],
      'record':r['record'],
      'containsTextAsset':'textasset' in blob.lower(),
      'containsMonoScript':'monoscript' in blob.lower(),
      'containsScriptRef':'script_ref' in blob.lower(),
    })

# Existing serialized/provenance metadata only. Filename filter prevents a broad repository sweep.
name_rx=re.compile(r'(serial|ptr|prefab|formation|component|structure|scene|graph)',re.I)
text_hits=[]; scanned=[]
for base in (meta,index):
    if not base.is_dir(): continue
    for p in sorted(base.iterdir()):
        if not p.is_file() or p==outp or not name_rx.search(p.name): continue
        if p.suffix.lower() not in ('.json','.txt','.tsv','.csv','.md'): continue
        # Avoid pathological unrelated giant indexes. V4 is handled structurally above.
        try: size=p.stat().st_size
        except: continue
        if p==v4p: continue
        if size>64*1024*1024: continue
        scanned.append({'path':str(p.relative_to(root)),'bytes':size})
        try: txt=p.read_text('utf-8',errors='replace')
        except: continue
        low=txt.lower(); start=0; n=0
        while n<40:
            i=low.find(term,start)
            if i<0: break
            a=max(0,i-260);b=min(len(txt),i+len(TERM)+420)
            snip=re.sub(r'\s+',' ',txt[a:b]).strip()
            text_hits.append({'file':str(p.relative_to(root)),'offset':i,'snippet':snip[:900]})
            start=i+len(term);n+=1

# Evidence classification. Textual metadata occurrence is not promoted to a serialized link.
serialized_named_hits=[]
for h in text_hits:
    s=(h['file']+' '+h['snippet']).lower()
    if any(x in s for x in ('script_ref','monoscript','m_script','textasset','pathid','fileid','serialized')):
        serialized_named_hits.append(h)

if exact_v4:
    strategy='inspect_exact_v4_luauiformlogic_record_and_follow_serialized_refs'
elif serialized_named_hits:
    strategy='inspect_named_existing_serialized_metadata_records_before_any_apk_access'
else:
    strategy='targeted_current_install_luauiformlogic_component_locator_required'

result={
 'format':'WFGG_LASTWAR_FORMATION_LUAUIFORMLOGIC_SERIALIZED_EVIDENCE_V1',
 'source':{'formationPtrV4':str(v4p.relative_to(root))},
 'counts':{
   'v4ExactLuaUIFormLogicRecordHits':len(exact_v4),
   'v4ScriptRefEdgeRows':len(script_edges),
   'existingFilteredMetadataFilesScanned':len(scanned),
   'existingMetadataLuaUIFormLogicHits':len(text_hits),
   'serializedLookingMetadataHits':len(serialized_named_hits),
 },
 'v4ExactRecords':exact_v4[:120],
 'v4ScriptRefEdges':script_edges[:120],
 'existingMetadataHits':text_hits[:160],
 'serializedLookingMetadataHits':serialized_named_hits[:120],
 'scannedFiles':scanned,
 'conclusion':{
   'exactNamePresentInClosedFormationV4':bool(exact_v4),
   'existingSerializedLookingEvidencePresent':bool(serialized_named_hits),
   'nextStrategy':strategy,
   'rule':'Only an exact serialized record/ref can bind LuaUIFormLogic to a Formation object. Metadata text/name proximity remains non-binding.'
 },
 'guardrails':{
   'existingEvidenceOnly':True,'apkAccess':False,'dllRescan':False,'bundleExtraction':False,
   'bundleScan':False,'candidatePromotion':False,'mainUntouched':True,'previewUntouched':True
 }
}
outp.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n','utf-8')

lines=[
 'WfGg Last War — FORMATION LUAUIFORMLOGIC SERIALIZED EVIDENCE V1','',
 f"v4ExactLuaUIFormLogicRecordHits={len(exact_v4)} v4ScriptRefEdgeRows={len(script_edges)}",
 f"metadataFilesScanned={len(scanned)} metadataHits={len(text_hits)} serializedLookingHits={len(serialized_named_hits)}",
 f"nextStrategy={strategy}",'',
 'EXACT LUAUIFORMLOGIC RECORDS IN CLOSED FORMATION V4'
]
if exact_v4:
    for x in exact_v4[:40]:
        lines.append('  PATH '+x['path'])
        lines.append('    '+scalar_blob(x['record'])[:1200])
else: lines.append('  NONE')
lines += ['', 'EXISTING SERIALIZED-LOOKING METADATA HITS']
if serialized_named_hits:
    for h in serialized_named_hits[:60]:
        lines.append(f"  FILE {h['file']} offset={h['offset']}")
        lines.append('    '+h['snippet'][:1000])
else: lines.append('  NONE')
lines += ['', 'SCRIPT_REF EDGE COUNT IN V4',f'  {len(script_edges)}','',
 'NEXT '+strategy,
 'RULE: exact serialized record/ref > serialized-looking metadata text > name proximity. No promotion without exact link.',
 'RULE: no APK read, DLL rescan, bundle extraction/scan, main or preview modification performed.'
]
reportp.write_text('\n'.join(lines)+'\n','utf-8')
print('FORMATION_LUAUI_SERIALIZED_OK',f'v4Exact={len(exact_v4)}',f'serializedMetadata={len(serialized_named_hits)}',f'scriptRefEdges={len(script_edges)}')
print('FORMATION_LUAUI_SERIALIZED_NEXT',strategy)
print('FORMATION_LUAUI_SERIALIZED_JSON',outp)
print('FORMATION_LUAUI_SERIALIZED_REPORT',reportp)
PY

git add "$OUT"
if ! git diff --cached --quiet; then
  git commit -m "lab: inspect serialized LuaUIFormLogic evidence"
  git push origin "$BRANCH"
fi

echo "FORMATION_LUAUI_SERIALIZED_DONE"
