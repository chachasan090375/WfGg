#!/data/data/com.termux/files/usr/bin/bash
set -Eeuo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BRANCH="portal-auth-lastwar-lab-v1"
OUT="$ROOT/frontend/lab/master-assets-v2/meta/lua-runtime-package-discovery-v1.json"
REPORT="$HOME/storage/downloads/WFGG_LASTWAR_LUA_RUNTIME_PACKAGE_DISCOVERY_V1.txt"
fail(){ printf 'ERREUR: %s\n' "$*" >&2; exit 1; }
cd "$ROOT"
[[ "$(git branch --show-current)" == "$BRANCH" ]] || fail "branche LAB incorrecte"
command -v python >/dev/null 2>&1 || fail "python absent"
mkdir -p "$(dirname "$OUT")" "$(dirname "$REPORT")"
PYTHONUNBUFFERED=1 python - "$ROOT" "$OUT" "$REPORT" <<'PY'
from __future__ import annotations
from pathlib import Path
import json,os,sys,zipfile
root,out,report=map(Path,sys.argv[1:])
roots=[root,Path.home()/"storage"/"downloads"]
exclude_parts={'.git','node_modules','formation-bridge-bundle-viewer-data'}
name_terms=('lua','xlua','zip','script','hot','update','patch','code','logic','bundle','asset')
exact_terms=(b'UIHeroPVPFormationPanel',b'FormationRT',b'FormationBg',b'FormationContent',b'A_Hero_Audie_01')
max_content_scan=128*1024*1024
rows=[]; seen=set()
for base in roots:
    if not base.exists(): continue
    for dp,ds,fs in os.walk(base):
        pdir=Path(dp)
        ds[:]=[d for d in ds if d not in exclude_parts]
        for fn in fs:
            p=pdir/fn
            try:
                rp=str(p.resolve())
                if rp in seen: continue
                seen.add(rp)
                st=p.stat(); size=st.st_size
                if size<=0: continue
                with p.open('rb') as f: head=f.read(64)
            except Exception: continue
            low=fn.lower()
            sig=''
            if head.startswith(b'PK\x03\x04') or head.startswith(b'PK\x05\x06') or head.startswith(b'PK\x07\x08'): sig='PKZIP'
            elif head[:16].lower().startswith(b'chacha') or b'Chacha' in head or b'ChaCha' in head: sig='CHACHA_HEADER'
            elif head.startswith(b'UnityFS'): sig='UNITYFS'
            named=any(t in low for t in name_terms)
            if sig in ('PKZIP','CHACHA_HEADER') or named:
                rows.append({'path':str(p),'size':size,'signature':sig,'namedCandidate':named})

# Exact string hits, but only across reasonably-sized likely runtime/package candidates.
for r in rows:
    p=Path(r['path']); size=r['size']
    hits=[]
    if size<=max_content_scan and (r['signature'] in ('PKZIP','CHACHA_HEADER') or r['namedCandidate']):
        try:
            data=p.read_bytes()
            hits=[t.decode() for t in exact_terms if t in data]
        except Exception: pass
    r['exactStringHits']=hits

zip_rows=[]
for r in rows:
    if r['signature']!='PKZIP': continue
    p=Path(r['path']); info={'path':str(p),'entries':None,'formationEntries':[],'error':None}
    try:
        with zipfile.ZipFile(p) as z:
            names=z.namelist(); info['entries']=len(names)
            kws=('formation','uihero','pvp','hero','lua')
            info['formationEntries']=[n for n in names if any(k in n.lower() for k in kws)][:250]
    except Exception as e: info['error']=f'{type(e).__name__}:{e}'
    zip_rows.append(info)

interesting=[r for r in rows if r['signature'] in ('PKZIP','CHACHA_HEADER') or r['exactStringHits']]
named_only=[r for r in rows if r['namedCandidate'] and not r['signature'] and not r['exactStringHits']]
result={
 'format':'WFGG_LASTWAR_LUA_RUNTIME_PACKAGE_DISCOVERY_V1',
 'roots':[str(x) for x in roots if x.exists()],
 'interesting':interesting,
 'zipInspection':zip_rows,
 'namedCandidates':named_only[:200],
 'counts':{'interesting':len(interesting),'zip':sum(1 for r in interesting if r['signature']=='PKZIP'),'chacha':sum(1 for r in interesting if r['signature']=='CHACHA_HEADER'),'namedOnly':len(named_only)},
 'guardrails':{'labOnly':True,'mainUntouched':True,'noBundleExtraction':True,'noApkRescan':True}
}
out.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n','utf-8')
lines=[]
lines.append('FORMATION_LUA_RUNTIME_PACKAGE_DISCOVERY_V1_READY')
lines.append(f"counts interesting={result['counts']['interesting']} zip={result['counts']['zip']} chacha={result['counts']['chacha']} namedOnly={result['counts']['namedOnly']}")
lines.append('--- INTERESTING PACKAGES ---')
if not interesting: lines.append('NONE')
for r in interesting[:120]:
    lines.append(f"{r['signature'] or 'FILE'} size={r['size']} hits={','.join(r['exactStringHits']) or '-'} path={r['path']}")
lines.append('--- ZIP FORMATION/LUA ENTRIES ---')
anyzip=False
for z in zip_rows:
    if z['formationEntries']:
        anyzip=True; lines.append(f"ZIP path={z['path']} entries={z['entries']}")
        for n in z['formationEntries'][:120]: lines.append('  '+n)
if not anyzip: lines.append('NONE')
lines.append('--- NAMED RUNTIME CANDIDATES (compact) ---')
for r in named_only[:80]: lines.append(f"size={r['size']} path={r['path']}")
lines.append(f'JSON={out}')
text='\n'.join(lines)+'\n'
report.write_text(text,'utf-8')
print(text,end='')
PY
