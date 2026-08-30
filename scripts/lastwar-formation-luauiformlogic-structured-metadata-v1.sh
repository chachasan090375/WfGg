#!/data/data/com.termux/files/usr/bin/bash
set -Eeuo pipefail

# WfGg Last War LAB — Formation LuaUIFormLogic structured metadata audit V1.
# Existing metadata only. NO APK read, NO DLL rescan, NO bundle extraction/scan.

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BRANCH="portal-auth-lastwar-lab-v1"
META="$ROOT/frontend/lab/master-assets-v2/meta"
V4="$META/formation-ptr-exact-v4.json"
OUT="$META/formation-luauiformlogic-structured-metadata-v1.json"
REPORT="$HOME/storage/downloads/WFGG_LASTWAR_FORMATION_LUAUIFORMLOGIC_STRUCTURED_METADATA_V1.txt"

fail(){ printf 'ERREUR: %s\n' "$*" >&2; exit 1; }
cd "$ROOT"
[[ "$(git branch --show-current)" == "$BRANCH" ]] || fail "branche LAB incorrecte"
[[ -d "$META" ]] || fail "meta absent"
[[ -s "$V4" ]] || fail "V4 absent"
command -v python >/dev/null 2>&1 || fail "python absent"
mkdir -p "$(dirname "$OUT")" "$(dirname "$REPORT")"

python - "$META" "$V4" "$OUT" "$REPORT" <<'PY'
from pathlib import Path
import json,sys,re
meta,v4p,outp,reportp=map(Path,sys.argv[1:])
TERM='luauiformlogic'
SELF_PREFIXES=(
 'formation-xlua-',
 'formation-lua-',
 'formation-luauiformlogic-',
)
STRUCT_KEYS={
 'pathid','path_id','m_pathid','fileid','file_id','m_fileid','bundleid','bundle_id',
 'type','objecttype','classid','class_id','script','scriptref','script_ref','m_script',
 'monoscript','serializedfile','serialized_file','assetpath','asset_path','container',
 'gameobject','component','sourceobject','source_object','targetobject','target_object',
 'pptr','objectid','object_id','rootpathid','root_pathid'
}
STRONG_KEYS={'pathid','m_pathid','fileid','m_fileid','bundleid','type','objecttype','classid','m_script','monoscript','pptr'}

def contains_term(x):
    if isinstance(x,str): return TERM in x.lower()
    if isinstance(x,list): return any(contains_term(v) for v in x)
    if isinstance(x,dict): return any(TERM in str(k).lower() or contains_term(v) for k,v in x.items())
    return False

def scalar_preview(x):
    if isinstance(x,(str,int,float,bool)) or x is None:
        s=str(x)
        return s if len(s)<=220 else s[:217]+'...'
    return None

def walk(x,path='$'):
    if isinstance(x,dict):
        yield path,x
        for k,v in x.items():
            yield from walk(v,path+'.'+str(k))
    elif isinstance(x,list):
        for i,v in enumerate(x): yield from walk(v,f'{path}[{i}]')

def classify_record(d):
    keys={str(k).lower() for k in d}
    struct=sorted(keys & STRUCT_KEYS)
    strong=sorted(keys & STRONG_KEYS)
    # Exact only if the SAME dict contains LuaUIFormLogic and structured object identity fields.
    exact=contains_term(d) and bool(strong)
    # Prefer actual serialized/object evidence over free-form report blobs.
    evidence='exact_structured_record' if exact else ('structured_context' if contains_term(d) and struct else 'name_only')
    values={}
    for k,v in d.items():
        lk=str(k).lower()
        if lk in STRUCT_KEYS or (isinstance(v,str) and TERM in v.lower()):
            pv=scalar_preview(v)
            if pv is not None: values[str(k)]=pv
            elif isinstance(v,dict):
                small={}
                for kk,vv in list(v.items())[:12]:
                    pp=scalar_preview(vv)
                    if pp is not None: small[str(kk)]=pp
                if small: values[str(k)]=small
    return evidence,struct,strong,values

files=[]; exact=[]; contexts=[]; parse_errors=[]
for p in sorted(meta.glob('*.json')):
    if p==outp: continue
    if p.name.startswith(SELF_PREFIXES):
        continue
    try:
        # Fast prefilter prevents loading unrelated large JSON files.
        raw=p.read_text('utf-8',errors='replace')
    except Exception as e:
        parse_errors.append({'file':str(p.relative_to(meta.parent.parent.parent.parent)) if False else str(p),'error':type(e).__name__+':'+str(e)})
        continue
    if TERM not in raw.lower():
        continue
    try:data=json.loads(raw)
    except Exception as e:
        parse_errors.append({'file':str(p),'error':type(e).__name__+':'+str(e)})
        continue
    frow={'file':str(p.relative_to(meta.parent.parent.parent.parent)) if False else str(p.relative_to(meta.parent.parent.parent)),'bytes':p.stat().st_size,'records':0,'exact':0}
    # Keep only the smallest dicts that themselves contain the term; this avoids duplicated ancestor blobs.
    candidates=[]
    for jpath,d in walk(data):
        if not contains_term(d): continue
        child_has=False
        for v in d.values():
            if isinstance(v,dict) and contains_term(v): child_has=True; break
            if isinstance(v,list) and any(isinstance(z,dict) and contains_term(z) for z in v): child_has=True; break
        ev,struct,strong,vals=classify_record(d)
        if child_has and ev=='name_only':
            continue
        row={'file':str(p.relative_to(meta.parent.parent.parent)),'jsonPath':jpath,'evidenceClass':ev,'structuredKeys':struct,'strongKeys':strong,'values':vals,'recordKeys':list(map(str,d.keys()))[:80]}
        candidates.append(row)
    # Dedup path/evidence and prefer exact.
    seen=set()
    for row in candidates:
        key=(row['jsonPath'],row['evidenceClass'],json.dumps(row['values'],sort_keys=True,ensure_ascii=False))
        if key in seen: continue
        seen.add(key); frow['records']+=1
        if row['evidenceClass']=='exact_structured_record':
            exact.append(row);frow['exact']+=1
        else: contexts.append(row)
    files.append(frow)

# V4 independent fact: exact term records and script_ref edge count.
v4=json.loads(v4p.read_text('utf-8'))
v4_term=[]; script_refs=0
for jpath,d in walk(v4):
    if isinstance(d,dict):
        rel=str(d.get('relation') or d.get('rel') or d.get('kind') or '').lower()
        if rel=='script_ref' or 'script_ref' in rel: script_refs+=1
        if contains_term(d):
            ev,struct,strong,vals=classify_record(d)
            v4_term.append({'jsonPath':jpath,'evidenceClass':ev,'structuredKeys':struct,'strongKeys':strong,'values':vals})

if exact:
    strategy='trace_exact_serialized_luauiformlogic_record_and_textasset_reference'
elif contexts:
    strategy='inspect_structured_context_records_without_promoting_to_exact'
else:
    strategy='targeted_current_install_luauiformlogic_locator_required'

result={
 'format':'WFGG_LASTWAR_FORMATION_LUAUIFORMLOGIC_STRUCTURED_METADATA_V1',
 'term':'LuaUIFormLogic',
 'counts':{
   'independentMetadataFilesWithTerm':len(files),
   'exactStructuredRecords':len(exact),
   'structuredOrNameContexts':len(contexts),
   'v4TermRecords':len(v4_term),
   'v4ScriptRefEdgesObserved':script_refs,
   'parseErrors':len(parse_errors),
 },
 'excludedEchoPrefixes':list(SELF_PREFIXES),
 'independentFiles':files,
 'exactStructuredRecords':exact[:200],
 'otherContexts':contexts[:300],
 'v4TermRecords':v4_term[:100],
 'parseErrors':parse_errors[:50],
 'conclusion':{
   'nextStrategy':strategy,
   'rule':'Only a same-record LuaUIFormLogic hit plus structured serialized identity fields is exact. Text/name echoes are not promoted.'
 },
 'guardrails':{'existingMetadataOnly':True,'apkAccess':False,'dllRescan':False,'bundleExtraction':False,'bundleScan':False,'mainUntouched':True,'previewUntouched':True}
}
outp.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n','utf-8')

lines=[
 'WfGg Last War — FORMATION LUAUIFORMLOGIC STRUCTURED METADATA V1','',
 f"independentMetadataFilesWithTerm={len(files)} exactStructuredRecords={len(exact)} contexts={len(contexts)} v4TermRecords={len(v4_term)} v4ScriptRefEdgesObserved={script_refs}",
 f"nextStrategy={strategy}",'',
 'EXACT STRUCTURED LUAUIFORMLOGIC RECORDS'
]
if exact:
    for r in exact[:80]:
        lines.append(f"  FILE {r['file']} path={r['jsonPath']} strongKeys={','.join(r['strongKeys'])}")
        if r['values']: lines.append('    values='+json.dumps(r['values'],ensure_ascii=False,separators=(',',':'))[:1200])
else: lines.append('  NONE')
lines += ['', 'OTHER INDEPENDENT STRUCTURED/NAME CONTEXTS — NOT EXACT']
if contexts:
    for r in contexts[:80]:
        lines.append(f"  FILE {r['file']} path={r['jsonPath']} class={r['evidenceClass']} keys={','.join(r['structuredKeys']) or '-'}")
        if r['values']: lines.append('    values='+json.dumps(r['values'],ensure_ascii=False,separators=(',',':'))[:1000])
else: lines.append('  NONE')
lines += ['', 'V4 TERM RECORDS']
if v4_term:
    for r in v4_term[:40]: lines.append(f"  path={r['jsonPath']} class={r['evidenceClass']} strongKeys={','.join(r['strongKeys']) or '-'}")
else: lines.append('  NONE')
lines += ['', 'FILES CONSIDERED']
for f in files[:80]: lines.append(f"  {f['file']} records={f['records']} exact={f['exact']} bytes={f['bytes']}")
lines += ['', 'NEXT '+strategy,
 'RULE: exact serialized record > structured context > name-only echo. No promotion without same-record object identity.',
 'RULE: no APK read, DLL rescan, bundle extraction/scan, main or preview modification performed.'
]
reportp.write_text('\n'.join(lines)+'\n','utf-8')
print('FORMATION_LUAUIFORMLOGIC_STRUCTURED_OK',f'exact={len(exact)}',f'contexts={len(contexts)}',f'v4Term={len(v4_term)}')
print('FORMATION_LUAUIFORMLOGIC_STRUCTURED_NEXT',strategy)
print('FORMATION_LUAUIFORMLOGIC_STRUCTURED_JSON',outp)
print('FORMATION_LUAUIFORMLOGIC_STRUCTURED_REPORT',reportp)
PY

git add "$OUT"
if ! git diff --cached --quiet; then
  git commit -m "lab: classify independent serialized LuaUIFormLogic evidence"
  git push origin "$BRANCH"
fi

echo "FORMATION_LUAUIFORMLOGIC_STRUCTURED_DONE"
