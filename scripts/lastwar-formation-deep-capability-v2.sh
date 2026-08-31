#!/data/data/com.termux/files/usr/bin/bash
set -Eeuo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BRANCH="portal-auth-lastwar-lab-v1"
PKG="com.fun.lastwar.gp"
OUT="$ROOT/frontend/lab/formation-deep-live-trace-data/capability-v2.json"
RAW="$ROOT/frontend/lab/master-assets-v2/deep-capability-v2"
PORT=8788
VIEWER="http://127.0.0.1:${PORT}/lab/lastwar-formation-deep-capability-v2.html?v=1"
fail(){ printf 'ERREUR: %s\n' "$*" >&2; exit 1; }
cd "$ROOT"
[[ "$(git branch --show-current)" == "$BRANCH" ]] || fail "branche LAB incorrecte"
command -v adb >/dev/null 2>&1 || fail "adb absent"
SERIAL="$(adb devices 2>/dev/null | awk 'NR>1 && $2=="device"{print $1;exit}')"
[[ -n "$SERIAL" ]] || fail "ADB non connecté"
PID="$(timeout 2 adb -s "$SERIAL" shell pidof "$PKG" 2>/dev/null | tr -d '\r' | awk '{print $1}')"
[[ -n "$PID" ]] || fail "Last War ne tourne pas"
mkdir -p "$RAW" "$(dirname "$OUT")"
printf 'FORMATION_DEEP_CAPABILITY_V2_START device=%s pid=%s\n' "$SERIAL" "$PID"
probe(){
  local name="$1" cmd="$2"
  printf -- '--- %s ---\n' "$name"
  set +e
  timeout 5 adb -s "$SERIAL" shell "$cmd" >"$RAW/$name.out" 2>"$RAW/$name.err"
  rc=$?
  set -e
  tr -d '\r' <"$RAW/$name.out" >"$RAW/$name.out.clean" || true
  tr -d '\r' <"$RAW/$name.err" >"$RAW/$name.err.clean" || true
  mv "$RAW/$name.out.clean" "$RAW/$name.out"; mv "$RAW/$name.err.clean" "$RAW/$name.err"
  printf 'rc=%s\n' "$rc" >"$RAW/$name.rc"
  printf 'rc=%s out=%s err=%s\n' "$rc" "$(wc -c <"$RAW/$name.out")" "$(wc -c <"$RAW/$name.err")"
  head -n 4 "$RAW/$name.out" 2>/dev/null || true
  head -n 4 "$RAW/$name.err" 2>/dev/null || true
}
probe shell_identity 'id; getenforce 2>/dev/null || true'
probe fd_numbers "ls /proc/$PID/fd 2>&1 | head -n 20"
FIRSTFD="$(head -n1 "$RAW/fd_numbers.out" 2>/dev/null | tr -cd '0-9')"
[[ -n "$FIRSTFD" ]] || FIRSTFD=0
probe fd_ls "ls -l /proc/$PID/fd/$FIRSTFD 2>&1"
probe fd_readlink "readlink /proc/$PID/fd/$FIRSTFD 2>&1"
probe fd_toybox_readlink "toybox readlink /proc/$PID/fd/$FIRSTFD 2>&1"
probe fd_stat "stat /proc/$PID/fd/$FIRSTFD 2>&1"
probe fdinfo "cat /proc/$PID/fdinfo/$FIRSTFD 2>&1"
probe proc_status "cat /proc/$PID/status 2>&1 | head -n 35"
probe strace_attach "timeout 1 strace -tt -f -p $PID -e trace=none 2>&1"
probe simpleperf_stat "timeout 2 simpleperf stat -p $PID --duration 1 2>&1"
probe atrace_app "atrace --async_start -b 1024 gfx view sched 2>&1; sleep .2; atrace --async_stop 2>&1 | head -n 15"
# Small Perfetto ftrace capability test. No game action is required.
cat >"$RAW/perfetto.cfg" <<'CFG'
buffers: { size_kb: 2048 fill_policy: RING_BUFFER }
data_sources: {
  config {
    name: "linux.ftrace"
    ftrace_config {
      ftrace_events: "syscalls/sys_enter_openat"
      ftrace_events: "syscalls/sys_exit_openat"
      ftrace_events: "syscalls/sys_enter_connect"
      ftrace_events: "syscalls/sys_enter_sendto"
      atrace_categories: "sched"
    }
  }
}
duration_ms: 1200
CFG
set +e
adb -s "$SERIAL" push "$RAW/perfetto.cfg" /data/local/tmp/wfgg-perfetto.cfg >/dev/null 2>"$RAW/perfetto_push.err"
timeout 6 adb -s "$SERIAL" shell 'perfetto --txt -c /data/local/tmp/wfgg-perfetto.cfg -o /data/local/tmp/wfgg-perfetto.pftrace 2>&1; ls -l /data/local/tmp/wfgg-perfetto.pftrace 2>&1' >"$RAW/perfetto.out" 2>"$RAW/perfetto.err"
prc=$?
set -e
printf '%s\n' "$prc" >"$RAW/perfetto.rc"
python - "$RAW" "$OUT" "$SERIAL" "$PID" <<'PY'
from pathlib import Path
import json,re,sys,time
raw,out=Path(sys.argv[1]),Path(sys.argv[2]); serial,pid=sys.argv[3:5]
names=['shell_identity','fd_numbers','fd_ls','fd_readlink','fd_toybox_readlink','fd_stat','fdinfo','proc_status','strace_attach','simpleperf_stat','atrace_app','perfetto']
def get(n,ext):
 p=raw/f'{n}.{ext}'
 return p.read_text('utf-8','replace') if p.exists() else ''
def rc(n):
 try:return int(get(n,'rc').strip())
 except:return None
def denied(t): return bool(re.search(r'permission denied|operation not permitted|ptrace.*denied|not permitted',t,re.I))
def useful(n):
 t=get(n,'out')+'\n'+get(n,'err')
 return rc(n)==0 and bool(t.strip()) and not denied(t)
probes=[]
for n in names:
 t=(get(n,'out')+'\n'+get(n,'err')).strip()
 probes.append({'name':n,'rc':rc(n),'ok':useful(n),'denied':denied(t),'output':t[:6000]})
# Path visibility requires actual arrow/readlink target, not merely an fd number.
fd_target=any(x['name'] in ('fd_ls','fd_readlink','fd_toybox_readlink') and x['ok'] and ('->' in x['output'] or ('permission' not in x['output'].lower() and '/proc/' not in x['output'] and len(x['output'].strip())>1)) for x in probes)
fdinfo_ok=next((x['ok'] for x in probes if x['name']=='fdinfo'),False)
strace_ok=next((x['ok'] and not re.search(r'attached|detached',x['output'],re.I)==False for x in probes if x['name']=='strace_attach'),False)
# Better strace criterion: no denial and output contains attached/process or timeout interruption rather than command-not-found.
sx=next((x for x in probes if x['name']=='strace_attach'),{})
stext=sx.get('output','')
strace_attach_ok=bool(stext) and not sx.get('denied') and not re.search(r'not found|invalid option|no such process',stext,re.I)
px=next((x for x in probes if x['name']=='perfetto'),{})
perfetto_ok=px.get('rc')==0 and bool(re.search(r'wfgg-perfetto\.pftrace|bytes',px.get('output',''),re.I)) and not px.get('denied')
simpleperf_ok=next((x['ok'] for x in probes if x['name']=='simpleperf_stat'),False)
atrace_ok=next((x['ok'] for x in probes if x['name']=='atrace_app'),False)
if perfetto_ok: priority='PERFETTO_SYSCALL_TRACE'
elif strace_attach_ok: priority='STRACE_ATTACH'
elif fd_target: priority='PROC_FD_TARGET_POLL'
elif fdinfo_ok: priority='PROC_FDINFO_DELTA'
elif simpleperf_ok: priority='SIMPLEPERF_PROFILE'
elif atrace_ok: priority='ATRACE_RUNTIME'
else: priority='NO_DEEP_RUNTIME_PATH'
result={'format':'WFGG_LASTWAR_FORMATION_DEEP_CAPABILITY_V2','generatedAt':int(time.time()),'device':serial,'pid':int(pid),'priority':priority,
        'capabilities':{'fdTargetVisible':fd_target,'fdinfoReadable':fdinfo_ok,'straceAttach':strace_attach_ok,'perfettoSyscalls':perfetto_ok,'simpleperf':simpleperf_ok,'atrace':atrace_ok},'probes':probes}
out.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n','utf-8')
print('FORMATION_DEEP_CAPABILITY_V2_READY priority='+priority)
for k,v in result['capabilities'].items():print(f'{k}={v}')
print('JSON='+str(out))
PY
# Ensure viewer server.
if command -v curl >/dev/null 2>&1 && curl -fsS --max-time 1 "http://127.0.0.1:${PORT}/lab/" >/dev/null 2>&1; then :; else
 (cd "$ROOT/frontend" && nohup python -m http.server "$PORT" --bind 127.0.0.1 >/dev/null 2>&1 &); sleep 1
fi
printf 'VIEWER=%s\n' "$VIEWER"
