#!/data/data/com.termux/files/usr/bin/bash
set -Eeuo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BRANCH="portal-auth-lastwar-lab-v1"
META="$ROOT/frontend/lab/master-assets-v2/meta"
CACHE="$META/lastwar-installed-apk-paths-v1.txt"
RESOLVED="$META/lua-runtime-apk-resolved-v1.txt"
ENTRY="assets/lwScripts/LWScripts.data"
fail(){ printf 'ERREUR: %s\n' "$*" >&2; exit 1; }
cd "$ROOT"
[[ "$(git branch --show-current)" == "$BRANCH" ]] || fail "branche LAB incorrecte"
command -v python >/dev/null 2>&1 || fail "python absent"
mkdir -p "$META"
python - "$CACHE" "$RESOLVED" "$ENTRY" <<'PY'
from pathlib import Path
import subprocess,sys,time,os
cache,resolved,entry=map(Path,sys.argv[1:])

def zip_has(path:str)->bool:
    try:
        cp=subprocess.run(['unzip','-Z1',path],capture_output=True,text=True,timeout=45)
        return any(x.rstrip('\r')==str(entry) for x in cp.stdout.splitlines())
    except Exception:
        return False

def parse_pm(text:str):
    out=[]
    for line in text.splitlines():
        line=line.strip().rstrip('\r')
        if line.startswith('package:'):
            p=line.split(':',1)[1].strip().rstrip('\r')
            if p and p not in out: out.append(p)
    return out

# Reuse a valid cache first: /data/app split paths are stable until app update.
old=[]
if cache.exists():
    try: old=[x.strip().rstrip('\r') for x in cache.read_text('utf-8','replace').splitlines() if x.strip()]
    except: old=[]
for p in old:
    if zip_has(p):
        resolved.write_text(p+'\n','utf-8')
        print('APK_CACHE_REUSE '+p)
        raise SystemExit(0)

paths=[]
commands=[['pm','path','com.fun.lastwar.gp'],['cmd','package','path','com.fun.lastwar.gp']]
for attempt in range(1,7):
    for cmd in commands:
        try:
            cp=subprocess.run(cmd,capture_output=True,text=True,timeout=20)
            got=parse_pm((cp.stdout or '')+'\n'+(cp.stderr or ''))
            for p in got:
                if p not in paths: paths.append(p)
            if got:
                print(f"APK_PATH_ATTEMPT {attempt} via={' '.join(cmd[:2])} count={len(got)}")
        except Exception as e:
            print(f"APK_PATH_ATTEMPT {attempt} via={' '.join(cmd[:2])} error={type(e).__name__}")
    for p in paths:
        if zip_has(p):
            cache.write_text('\n'.join(paths)+'\n','utf-8')
            resolved.write_text(p+'\n','utf-8')
            print('APK_CACHE_RESOLVED '+p)
            raise SystemExit(0)
    time.sleep(0.25*attempt)

# Preserve any paths that were discovered even if validation failed, for diagnosis.
if paths: cache.write_text('\n'.join(paths)+'\n','utf-8')
try: resolved.unlink()
except FileNotFoundError: pass
print(f'APK_CACHE_UNRESOLVED paths={len(paths)} entry={entry}')
raise SystemExit(1)
PY
