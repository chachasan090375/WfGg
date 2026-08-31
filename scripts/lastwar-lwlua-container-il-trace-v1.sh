#!/data/data/com.termux/files/usr/bin/bash
set -Eeuo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BRANCH="portal-auth-lastwar-lab-v1"
SRC="$ROOT/scripts/lastwar-formation-dynamic-binding-bridge-v1.sh"
TMP="$ROOT/scripts/.lastwar-lwlua-container-il-trace-v1.$$.sh"
OUT="$ROOT/frontend/lab/master-assets-v2/meta/lwlua-container-il-trace-v1.json"
REPORT="$HOME/storage/downloads/WFGG_LASTWAR_LWLUA_CONTAINER_IL_TRACE_V1.txt"
trap 'rm -f "$TMP"' EXIT
fail(){ printf 'ERREUR: %s\n' "$*" >&2; exit 1; }
cd "$ROOT"
[[ "$(git branch --show-current)" == "$BRANCH" ]] || fail "branche LAB incorrecte"
[[ -s "$SRC" ]] || fail "traceur IL source absent: $SRC"
python - "$SRC" "$TMP" "$OUT" "$REPORT" <<'PY'
from pathlib import Path
import sys,re
src,tmp,out,report=map(Path,sys.argv[1:])
s=src.read_text('utf-8')
s=s.replace('OUT="$ROOT/frontend/lab/master-assets-v2/meta/formation-dynamic-binding-bridge-v1.json"',f'OUT="{out}"')
s=s.replace('REPORT="$HOME/storage/downloads/WFGG_LASTWAR_FORMATION_DYNAMIC_BINDING_BRIDGE_V1.txt"',f'REPORT="{report}"')
old=re.compile(r"needle_symbols=\[\n(?:.*\n)*?\]\nselected=\[\]",re.M)
new="""needle_symbols=[
 'LWLuaFile.Load',
 'LWLuaFile._Load',
 'LWLuaFile.LoadFile',
 'LWLuaFile.InWhiteList',
 'LWLuaFile.GetSizeAndCrc',
 'LWLuaFileUpdate.InitFileOnAppStart',
 'LWLuaFileUpdate.SaveUpdateFile',
 'LWLuaFileUpdate.ApplyUpdate',
 'LWLuaFileUpdateParallel.th_LwScriptLoad',
 'LWLuaFileUpdateParallel.mt_LwScriptSwap',
]
selected=[]"""
s,n=old.subn(new,s,count=1)
if n!=1: raise SystemExit('NEEDLE_PATCH_FAILED')
tmp.write_text(s,'utf-8')
PY
chmod 700 "$TMP"
bash "$TMP" >/dev/null
[[ -s "$OUT" ]] || fail "sortie IL absente"
python - "$OUT" "$REPORT" <<'PY'
from pathlib import Path
import json,sys,re,subprocess,os
out,report=map(Path,sys.argv[1:])
d=json.loads(out.read_text('utf-8'))
rows=d.get('exactBoundaryMethodIL') or []
lines=['LWLUA_CONTAINER_IL_TRACE_V1_READY','--- EXACT LWLUA METHODS ---']
interesting=[]
for r in rows:
    sym=r.get('symbol','')
    strings=[str(x) for x in r.get('strings') or []]
    internal=[str(x) for x in r.get('internalCalls') or []]
    external=[str(x) for x in r.get('externalCalls') or []]
    lines.append(f"METHOD {sym} rid={r.get('rid')} strings={len(strings)}")
    for s in strings: lines.append('  STR '+repr(s))
    for x in internal:
        if any(k in x.lower() for k in ('lua','file','resource','version','update','load')): lines.append('  CALL '+x)
    for x in external:
        if any(k in x.lower() for k in ('file','stream','binary','decrypt','chacha','zip','path','crc','read','seek')): lines.append('  EXT '+x)
    for s in strings:
        sl=s.lower()
        if len(s)>=3 and (any(c in s for c in ('/','\\','.')) or any(k in sl for k in ('lua','script','lw','zip','bytes','data'))):
            interesting.append(s)
# Keep useful, stable literal tokens only.
seen=[]
for s in interesting:
    if s not in seen: seen.append(s)
lines.append('--- LITERAL CANDIDATES ---')
if seen:
    for s in seen[:80]: lines.append('LITERAL '+repr(s))
else: lines.append('NONE')
# Narrow local-name match only, not a content scan.
roots=[Path.home()/ 'storage'/'downloads']
hits=[]
terms=[]
for s in seen:
    b=re.split(r'[\\/]',s)[-1].strip().lower()
    if len(b)>=4 and b not in terms: terms.append(b)
for root in roots:
    if not root.exists(): continue
    for p in root.rglob('*'):
        try:
            if not p.is_file(): continue
        except: continue
        low=p.name.lower()
        if any(t in low or low in t for t in terms): hits.append(str(p))
lines.append('--- LOCAL NAME HITS ---')
if hits:
    for p in hits[:80]: lines.append('FILE '+p)
else: lines.append('NONE')
# APK entry-name lookup only (metadata, no extraction/content scan).
lines.append('--- INSTALLED APK LUA/SCRIPT ENTRY NAMES ---')
apkhits=[]
try:
    cp=subprocess.run(['pm','path','com.fun.lastwar.gp'],capture_output=True,text=True,timeout=15)
    apks=[x.split(':',1)[1].strip() for x in cp.stdout.splitlines() if x.startswith('package:')]
    pat=re.compile(r'(lua|lwscript|script)',re.I)
    for apk in apks:
        try:
            z=subprocess.run(['unzip','-Z1',apk],capture_output=True,text=True,timeout=60)
            for n in z.stdout.splitlines():
                if pat.search(n): apkhits.append((apk,n))
        except Exception: pass
except Exception: pass
if apkhits:
    for apk,n in apkhits[:160]: lines.append(f'APKENTRY {os.path.basename(apk)} :: {n}')
else: lines.append('NONE')
lines.append(f'JSON={out}')
text='\n'.join(lines)+'\n'
report.write_text(text,'utf-8')
print(text,end='')
PY
