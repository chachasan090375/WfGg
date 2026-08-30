#!/data/data/com.termux/files/usr/bin/bash
set -Eeuo pipefail

# WfGg Last War LAB — exact audit for external serialized resource
# referenced by Formation PPtr graph as: Library/unity default resources#10101
# No candidate substitution. Installed game stays read-only.

PKG="com.fun.lastwar.gp"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BRANCH="portal-auth-lastwar-lab-v1"
OUT="$ROOT/frontend/lab/master-assets-v2/meta/unity-default-resources-audit-v1.json"
REPORT="$HOME/storage/downloads/WFGG_LASTWAR_UNITY_DEFAULT_RESOURCES_AUDIT.txt"
LOCAL="$ROOT/frontend/lab/local_assets/unity-default-resources-audit-v1"
UNITY_VERSION="2019.4.41f1"

fail(){ printf 'ERREUR: %s\n' "$*" >&2; exit 1; }
cd "$ROOT"
[[ "$(git branch --show-current)" == "$BRANCH" ]] || fail "branche LAB incorrecte"
command -v python >/dev/null 2>&1 || fail "python absent"
python - <<'PYCHK' >/dev/null 2>&1 || fail "UnityPy absent dans Python Termux"
import UnityPy
PYCHK
mapfile -t APKS < <(cmd package path "$PKG" 2>/dev/null | sed -n 's/^package://p')
[[ ${#APKS[@]} -gt 0 ]] || fail "APK Last War introuvable"
mkdir -p "$(dirname "$OUT")" "$(dirname "$REPORT")" "$LOCAL"

python - "$OUT" "$REPORT" "$LOCAL" "$UNITY_VERSION" "${APKS[@]}" <<'PY'
from __future__ import annotations
from pathlib import Path
import hashlib, json, os, zipfile, sys
import UnityPy

out=Path(sys.argv[1]); report=Path(sys.argv[2]); local=Path(sys.argv[3]); unity_version=sys.argv[4]; apks=[Path(x) for x in sys.argv[5:]]
UnityPy.config.FALLBACK_UNITY_VERSION=unity_version

TARGET_EXTERNAL='Library/unity default resources'
TARGET_BASENAME='unity default resources'
TARGET_PATH_ID=10101

def norm(s:str)->str:
    return str(s).replace('\\','/').strip().lower()

def basename(s:str)->str:
    return norm(s).rsplit('/',1)[-1]

apk_rows=[]
exact_entries=[]
near_entries=[]
for apk in apks:
    rec={'apk':str(apk),'exists':apk.is_file(),'sizeBytes':apk.stat().st_size if apk.is_file() else None,'exactEntries':[],'nearEntries':[]}
    if not apk.is_file():
        apk_rows.append(rec); continue
    try:
        with zipfile.ZipFile(apk) as z:
            for n in z.namelist():
                b=basename(n)
                if b==TARGET_BASENAME:
                    row={'apk':str(apk),'entry':n,'sizeBytes':z.getinfo(n).file_size}
                    rec['exactEntries'].append(row); exact_entries.append(row)
                elif ('unity' in b and 'resource' in b) or 'unity_builtin' in b or 'default resource' in b:
                    row={'apk':str(apk),'entry':n,'sizeBytes':z.getinfo(n).file_size}
                    rec['nearEntries'].append(row); near_entries.append(row)
    except Exception as e:
        rec['zipError']=f'{type(e).__name__}:{e}'
    apk_rows.append(rec)

result={
  'format':'WFGG_LASTWAR_UNITY_DEFAULT_RESOURCES_AUDIT_V1',
  'targetExternalPath':TARGET_EXTERNAL,
  'targetBasename':TARGET_BASENAME,
  'targetPathID':TARGET_PATH_ID,
  'unityVersionFallback':unity_version,
  'apkCount':len(apks),
  'apks':apk_rows,
  'exactEntryCount':len(exact_entries),
  'nearEntryCount':len(near_entries),
  'selectionRule':'Only APK entries whose basename normalizes exactly to "unity default resources" are eligible. Near matches are diagnostic only.',
  'exactLoads':[],
  'guardrails':{'installedGameReadOnly':True,'candidateSubstitution':False,'globalBundleScan':False}
}

for i,row in enumerate(exact_entries):
    apk=Path(row['apk']); entry=row['entry']; dst=local/f'exact-{i:02d}-unity-default-resources.bin'
    load={'apk':str(apk),'entry':entry,'dst':str(dst)}
    try:
        with zipfile.ZipFile(apk) as z:
            data=z.read(entry)
        dst.write_bytes(data)
        load['bytes']=len(data)
        load['sha256']=hashlib.sha256(data).hexdigest()
        env=UnityPy.load(str(dst))
        objects=list(getattr(env,'objects',[]) or [])
        load['objectCount']=len(objects)
        hit=[r for r in objects if int(getattr(r,'path_id',0))==TARGET_PATH_ID]
        load['pathIdHitCount']=len(hit)
        load['pathIdHits']=[]
        for r in hit:
            typ=getattr(getattr(r,'type',None),'name',str(getattr(r,'type',None)))
            try:
                name=r.peek_name()
            except Exception:
                name=None
            h={'pathID':int(r.path_id),'type':typ,'name':str(name) if name is not None else None}
            try:
                tree=r.read_typetree()
                h['typetreeReadable']=True
                if isinstance(tree,dict):
                    for k in ('m_Name','m_ShaderName'):
                        if k in tree: h[k]=tree[k]
            except Exception as e:
                h['typetreeReadable']=False; h['typetreeError']=f'{type(e).__name__}:{e}'
            load['pathIdHits'].append(h)
    except Exception as e:
        load['error']=f'{type(e).__name__}:{e}'
    result['exactLoads'].append(load)

result['resolvedExactly']=any(x.get('pathIdHitCount')==1 for x in result['exactLoads'])
result['ambiguousExactResolution']=sum(1 for x in result['exactLoads'] if x.get('pathIdHitCount')==1)>1
out.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n','utf-8')

lines=[
 'WfGg Last War — UNITY DEFAULT RESOURCES EXACT AUDIT','',
 f'targetExternal={TARGET_EXTERNAL}',f'targetPathID={TARGET_PATH_ID}',
 f'apks={len(apks)} exactEntries={len(exact_entries)} nearEntries={len(near_entries)}',
 f'resolvedExactly={result["resolvedExactly"]} ambiguousExactResolution={result["ambiguousExactResolution"]}','',
 'EXACT ENTRIES'
]
for x in exact_entries: lines.append(f"  {x['apk']} :: {x['entry']} bytes={x['sizeBytes']}")
if not exact_entries: lines.append('  NONE')
lines += ['', 'EXACT LOADS']
for x in result['exactLoads']:
    lines.append(f"  entry={x['entry']} objects={x.get('objectCount')} pathIdHits={x.get('pathIdHitCount')} error={x.get('error')}")
    for h in x.get('pathIdHits',[]): lines.append('    '+json.dumps(h,ensure_ascii=False))
lines += ['', 'NEAR MATCHES — DIAGNOSTIC ONLY / NEVER SELECTED']
for x in near_entries[:80]: lines.append(f"  {x['apk']} :: {x['entry']} bytes={x['sizeBytes']}")
if not near_entries: lines.append('  NONE')
lines += ['', 'RULE: no near match is promoted to exact evidence.']
report.write_text('\n'.join(lines)+'\n','utf-8')

print('UNITY_DEFAULT_RESOURCES_AUDIT_OK',f'exactEntries={len(exact_entries)}',f'nearEntries={len(near_entries)}',f'resolvedExactly={result["resolvedExactly"]}')
print('UNITY_DEFAULT_RESOURCES_JSON',out)
print('UNITY_DEFAULT_RESOURCES_REPORT',report)
PY

git add "$OUT"
if ! git diff --cached --quiet; then git commit -m "lab: audit Unity default resources exact Formation external"; fi
git push origin "$BRANCH"
printf '%s\n' '=== UNITY DEFAULT RESOURCES AUDIT TERMINE ===' "JSON: $OUT" "Rapport: $REPORT"
