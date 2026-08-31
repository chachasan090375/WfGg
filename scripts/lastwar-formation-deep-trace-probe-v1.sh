#!/data/data/com.termux/files/usr/bin/bash
set -Eeuo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BRANCH="portal-auth-lastwar-lab-v1"
PKG="com.fun.lastwar.gp"
PORT=8788
OUT="$ROOT/frontend/lab/formation-live-trace-data/deep-probe.json"
VIEWER="http://127.0.0.1:${PORT}/lab/lastwar-formation-deep-trace-probe.html?v=1"
fail(){ printf 'ERREUR: %s\n' "$*" >&2; exit 1; }
cd "$ROOT"
[[ "$(git branch --show-current)" == "$BRANCH" ]] || fail "branche LAB incorrecte"
command -v adb >/dev/null 2>&1 || fail "adb absent"
SERIAL="$(adb devices 2>/dev/null | awk 'NR>1 && $2=="device"{print $1; exit}')"
[[ -n "$SERIAL" ]] || fail "ADB non connecté"
PID="$(timeout 2 adb -s "$SERIAL" shell pidof "$PKG" 2>/dev/null | tr -d '\r' | awk '{print $1}')"
[[ -n "$PID" ]] || fail "Last War ne tourne pas"
TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
run(){ local name="$1"; shift; { timeout 4 adb -s "$SERIAL" shell "$@"; } >"$TMP/$name.out" 2>"$TMP/$name.err" || true; }
printf 'DEEP_TRACE_PROBE_START device=%s pid=%s\n' "$SERIAL" "$PID"
run proc_fd sh -c "ls -l /proc/$PID/fd 2>&1 | head -n 120"
run proc_maps sh -c "cat /proc/$PID/maps 2>&1 | head -n 160"
run proc_net_tcp sh -c "cat /proc/$PID/net/tcp 2>&1 | head -n 80"
run run_as sh -c "run-as $PKG id 2>&1"
run atrace sh -c "atrace --list_categories 2>&1 | head -n 120"
run perfetto sh -c "command -v perfetto 2>/dev/null; perfetto --help 2>&1 | head -n 80"
run simpleperf sh -c "command -v simpleperf 2>/dev/null; simpleperf --help 2>&1 | head -n 80"
run strace sh -c "command -v strace 2>/dev/null; strace -V 2>&1 | head -n 20"
run package_flags sh -c "dumpsys package $PKG 2>/dev/null | grep -i -E 'DEBUGGABLE|flags=|pkgFlags' | head -n 40"
python - "$TMP" "$OUT" "$SERIAL" "$PID" <<'PY'
from pathlib import Path
import json,sys,re,time
root,out=Path(sys.argv[1]),Path(sys.argv[2]); serial,pid=sys.argv[3],sys.argv[4]
checks={}
for p in sorted(root.glob('*.out')):
    name=p.stem
    txt=p.read_text('utf-8','replace')
    err=(root/(name+'.err')).read_text('utf-8','replace') if (root/(name+'.err')).exists() else ''
    low=(txt+'\n'+err).lower()
    checks[name]={'stdout':txt[:12000],'stderr':err[:4000]}

def denied(name):
    s=(checks.get(name,{}).get('stdout','')+' '+checks.get(name,{}).get('stderr','')).lower()
    return any(x in s for x in ['permission denied','not permitted','operation not permitted','run-as: package not debuggable'])

def nonempty(name): return bool(checks.get(name,{}).get('stdout','').strip())
cap={
 'procFd': nonempty('proc_fd') and not denied('proc_fd'),
 'procMaps': nonempty('proc_maps') and not denied('proc_maps'),
 'procNetTcp': nonempty('proc_net_tcp') and not denied('proc_net_tcp'),
 'runAs': nonempty('run_as') and not denied('run_as') and 'uid=' in checks.get('run_as',{}).get('stdout',''),
 'atrace': nonempty('atrace') and 'unknown command' not in checks.get('atrace',{}).get('stdout','').lower(),
 'perfetto': 'perfetto' in checks.get('perfetto',{}).get('stdout','').lower(),
 'simpleperf': 'simpleperf' in checks.get('simpleperf',{}).get('stdout','').lower(),
 'strace': 'strace' in checks.get('strace',{}).get('stdout','').lower(),
}
priority=[]
if cap['runAs']: priority.append('RUN_AS_PRIVATE_STATE')
if cap['procFd']: priority.append('PROC_FD_FILE_DELTA')
if cap['procMaps']: priority.append('PROC_MAPS_MODULE_DELTA')
if cap['perfetto'] or cap['atrace']: priority.append('PERFETTO_ATRACE_RUNTIME')
if cap['simpleperf']: priority.append('SIMPLEPERF_NATIVE_PROFILE')
if cap['procNetTcp']: priority.append('PROC_NET_DELTA')
if not priority: priority.append('NETWORK_VPN_OR_INSTRUMENTATION_REQUIRED')
result={'format':'WFGG_LASTWAR_FORMATION_DEEP_TRACE_PROBE_V1','generatedAt':int(time.time()),'device':serial,'pid':pid,'capabilities':cap,'priority':priority,'checks':checks}
out.parent.mkdir(parents=True,exist_ok=True); out.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n','utf-8')
print('FORMATION_DEEP_TRACE_PROBE_V1_READY')
print('capabilities='+json.dumps(cap,ensure_ascii=False,separators=(',',':')))
print('priority='+','.join(priority))
print('JSON='+str(out))
PY
if command -v curl >/dev/null 2>&1 && curl -fsS --max-time 1 "http://127.0.0.1:${PORT}/lab/" >/dev/null 2>&1; then :; else
  (cd "$ROOT/frontend" && nohup python -m http.server "$PORT" --bind 127.0.0.1 >/dev/null 2>&1 &)
  sleep 1
fi
printf 'VIEWER=%s\n' "$VIEWER"
