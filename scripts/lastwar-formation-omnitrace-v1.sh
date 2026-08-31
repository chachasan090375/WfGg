#!/data/data/com.termux/files/usr/bin/bash
set -Eeuo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BRANCH="portal-auth-lastwar-lab-v1"
PKG="com.fun.lastwar.gp"
BASE="$ROOT/frontend/lab/master-assets-v2/formation-omnitrace"
STATE="$BASE/current.env"
REMOTE_BASE="/data/local/tmp/wfgg-omnitrace"
cd "$ROOT"

say(){ printf '%s\n' "$*"; }
need_branch(){ [[ "$(git branch --show-current)" == "$BRANCH" ]] || { say "ERREUR: branche LAB incorrecte"; exit 1; }; }
adb_serial(){ adb devices 2>/dev/null | awk 'NR>1 && $2=="device"{print $1;exit}'; }
lastwar_pid(){ timeout 3 adb -s "$1" shell pidof "$PKG" 2>/dev/null | tr -d '\r' | awk '{print $1}'; }
now(){ date +%Y%m%d_%H%M%S; }

snap(){
  local phase="$1"
  {
    echo "=== $phase $(date -Iseconds) ==="
    echo '--- ACTIVITY TOP ---'; timeout 4 adb -s "$SERIAL" shell dumpsys activity top 2>&1 || true
    echo '--- MEMINFO ---'; timeout 4 adb -s "$SERIAL" shell dumpsys meminfo "$PKG" 2>&1 || true
    echo '--- PACKAGE PATH ---'; timeout 3 adb -s "$SERIAL" shell pm path "$PKG" 2>&1 || true
    echo '--- PROCESS ---'; timeout 3 adb -s "$SERIAL" shell ps -A -T 2>&1 | grep -E "(^|[[:space:]])$PID([[:space:]]|$)|$PKG" || true
    echo '--- PROC STATUS ---'; timeout 3 adb -s "$SERIAL" shell cat "/proc/$PID/status" 2>&1 || true
    echo '--- PROC MAPS ---'; timeout 3 adb -s "$SERIAL" shell cat "/proc/$PID/maps" 2>&1 | head -n 400 || true
    echo '--- PROC FD ---'; timeout 3 adb -s "$SERIAL" shell ls -l "/proc/$PID/fd" 2>&1 | head -n 400 || true
    echo '--- SS ---'; timeout 4 adb -s "$SERIAL" shell ss -tpna 2>&1 | head -n 600 || true
    echo '--- NETSTATS ---'; timeout 5 adb -s "$SERIAL" shell dumpsys netstats detail 2>&1 | grep -E "$PKG|uid=|iface=|networkId|ident=" | head -n 500 || true
    echo '--- GFXINFO ---'; timeout 4 adb -s "$SERIAL" shell dumpsys gfxinfo "$PKG" 2>&1 | head -n 500 || true
  } >"$SESSION/snapshot-$phase.txt" 2>&1
}

start_logcats(){
  if timeout 2 adb -s "$SERIAL" logcat --help 2>&1 | grep -q -- '--pid'; then
    ( adb -s "$SERIAL" logcat -v threadtime --pid="$PID" ) >"$SESSION/logcat-pid.log" 2>&1 & echo $! >"$SESSION/logcat-pid.pid"
  else
    ( adb -s "$SERIAL" logcat -v threadtime ) >"$SESSION/logcat-all.log" 2>&1 & echo $! >"$SESSION/logcat-all.pid"
  fi
  ( adb -s "$SERIAL" logcat -b events -v threadtime ) >"$SESSION/logcat-events.log" 2>&1 & echo $! >"$SESSION/logcat-events.pid"
}

start_pollers(){
  (
    while :; do
      echo "@@T $(date +%s.%3N)"
      timeout 2 adb -s "$SERIAL" shell "ps -A -T 2>/dev/null | grep '$PKG'; ss -tpna 2>/dev/null | head -n 250; cat /proc/$PID/status 2>/dev/null | head -n 80" 2>&1 || true
      sleep 1
    done
  ) >"$SESSION/poller-runtime.log" 2>&1 & echo $! >"$SESSION/poller-runtime.pid"
  (
    while :; do
      echo "@@T $(date +%s.%3N)"
      timeout 3 adb -s "$SERIAL" shell "dumpsys activity activities 2>/dev/null | grep -E 'mResumedActivity|topResumedActivity|$PKG' | head -n 30" 2>&1 || true
      sleep 1
    done
  ) >"$SESSION/poller-activity.log" 2>&1 & echo $! >"$SESSION/poller-activity.pid"
}

start_atrace(){
  set +e
  timeout 5 adb -s "$SERIAL" shell "atrace --async_start -b 8192 sched freq idle am wm gfx view binder_driver" >"$SESSION/atrace-start.log" 2>&1
  echo $? >"$SESSION/atrace-start.rc"
  set -e
}

start_perfetto(){
  local rfile="$REMOTE_SESSION/perfetto.trace"
  set +e
  timeout 5 adb -s "$SERIAL" shell "perfetto -o '$rfile' -t 180s sched freq idle am wm gfx view binder_driver >/dev/null 2>'$REMOTE_SESSION/perfetto.err' & echo \$!" >"$SESSION/perfetto.pid.remote" 2>"$SESSION/perfetto-start.err"
  echo $? >"$SESSION/perfetto-start.rc"
  set -e
}

start_simpleperf(){
  local rfile="$REMOTE_SESSION/simpleperf.data"
  set +e
  timeout 5 adb -s "$SERIAL" shell "simpleperf record -p '$PID' -e cpu-clock -o '$rfile' --duration 180 >/dev/null 2>'$REMOTE_SESSION/simpleperf.err' & echo \$!" >"$SESSION/simpleperf.pid.remote" 2>"$SESSION/simpleperf-start.err"
  echo $? >"$SESSION/simpleperf-start.rc"
  set -e
}

prepare_remote_strace(){
  local probe="$ROOT/scripts/lastwar-formation-strace-deploy-probe-v5.sh"
  [[ -x "$probe" || -f "$probe" ]] || { echo 'STRACE_PREP=SCRIPT_ABSENT' >"$SESSION/strace-prep.log"; return 0; }
  set +e
  bash "$probe" >"$SESSION/strace-prep.log" 2>&1
  local rc=$?
  set -e
  echo "$rc" >"$SESSION/strace-prep.rc"
  if grep -qE 'RESULT=REMOTE_STRACE_READY|RESULT=STRACE_ATTACH_NO_SYSCALLS_YET' "$SESSION/strace-prep.log"; then
    REMOTE_STRACE="$(grep '^REMOTE_STRACE=' "$SESSION/strace-prep.log" | tail -n1 | cut -d= -f2-)"
    REMOTE_LD="$(grep '^REMOTE_LD_LIBRARY_PATH=' "$SESSION/strace-prep.log" | tail -n1 | cut -d= -f2-)"
    [[ -n "$REMOTE_STRACE" && -n "$REMOTE_LD" ]] || return 0
    local rout="$REMOTE_SESSION/strace.log"
    set +e
    timeout 4 adb -s "$SERIAL" shell "nohup env LD_LIBRARY_PATH='$REMOTE_LD' '$REMOTE_STRACE' -tt -f -p '$PID' -s 240 -e trace=openat,read,pread64,mmap,munmap,connect,sendto,recvfrom,sendmsg,recvmsg -o '$rout' >/dev/null 2>'$REMOTE_SESSION/strace.err' </dev/null & echo \$!" >"$SESSION/strace.pid.remote" 2>"$SESSION/strace-start.err"
    echo $? >"$SESSION/strace-start.rc"
    set -e
  fi
}

mark(){
  local what="$1" epoch
  epoch="$(date +%s.%3N)"
  echo "$what=$epoch" >>"$STATE"
  echo "@@$what $epoch" >>"$SESSION/markers.log"
  timeout 2 adb -s "$SERIAL" shell "log -t WFGG_OMNITRACE '$what $ID $epoch'" >/dev/null 2>&1 || true
}

start_cmd(){
  need_branch
  command -v adb >/dev/null 2>&1 || { say 'ADB=ABSENT'; exit 2; }
  SERIAL="$(adb_serial)"; [[ -n "$SERIAL" ]] || { say 'ADB_DEVICE=ABSENT'; exit 3; }
  PID="$(lastwar_pid "$SERIAL")"; [[ -n "$PID" ]] || { say 'LASTWAR_PID=ABSENT'; exit 4; }
  LABEL="${1:-formation change}"
  ID="$(now)"; SESSION="$BASE/sessions/$ID"; REMOTE_SESSION="$REMOTE_BASE/$ID"
  mkdir -p "$SESSION" "$BASE/sessions"
  timeout 4 adb -s "$SERIAL" shell "rm -rf '$REMOTE_SESSION'; mkdir -p '$REMOTE_SESSION'" >/dev/null 2>&1 || true
  cat >"$STATE" <<EOF
ID='$ID'
SESSION='$SESSION'
REMOTE_SESSION='$REMOTE_SESSION'
SERIAL='$SERIAL'
PID='$PID'
LABEL='${LABEL//\'/}'
START_EPOCH='$(date +%s.%3N)'
EOF
  say "FORMATION_OMNITRACE_V1_PREP session=$ID device=$SERIAL pid=$PID"
  say 'PACK=logcat+events+proc+network+dumpsys+atrace+perfetto+simpleperf+strace'
  snap before & echo $! >"$SESSION/snapshot-before.pid"
  # Prepare the deepest collector before opening the action window.
  prepare_remote_strace
  start_logcats
  start_pollers
  start_atrace
  start_perfetto
  start_simpleperf
  sleep 1
  mark ACTION_WINDOW_START
  say 'FORMATION_OMNITRACE_V1_READY'
  say "ACTION=$LABEL"
  say 'Fais UNE SEULE modification dans Last War, valide, puis reviens immédiatement dans Termux.'
  say 'STOP=bash scripts/lastwar-formation-omnitrace-v1.sh stop'
}

stop_pidfile(){
  local pf="$1"; [[ -f "$pf" ]] || return 0
  local p; p="$(cat "$pf" 2>/dev/null || true)"; [[ "$p" =~ ^[0-9]+$ ]] || return 0
  kill "$p" 2>/dev/null || true; sleep .08; kill -9 "$p" 2>/dev/null || true
}
stop_remote(){
  local pf="$1"; [[ -f "$pf" ]] || return 0
  local p; p="$(tr -dc '0-9\n' <"$pf" | head -n1)"; [[ "$p" =~ ^[0-9]+$ ]] || return 0
  timeout 2 adb -s "$SERIAL" shell "kill -INT '$p' 2>/dev/null || kill '$p' 2>/dev/null || true" >/dev/null 2>&1 || true
}

stop_cmd(){
  [[ -f "$STATE" ]] || { say 'OMNITRACE_STATE=ABSENT'; exit 5; }
  # shellcheck disable=SC1090
  source "$STATE"
  say "FORMATION_OMNITRACE_V1_STOP session=$ID"
  mark ACTION_WINDOW_STOP
  # Freeze the action window immediately, before any long diagnostic.
  for pf in "$SESSION"/*.pid; do stop_pidfile "$pf"; done
  stop_remote "$SESSION/strace.pid.remote"
  stop_remote "$SESSION/perfetto.pid.remote"
  stop_remote "$SESSION/simpleperf.pid.remote"
  set +e
  timeout 8 adb -s "$SERIAL" shell "atrace --async_stop" >"$SESSION/atrace-stop.log" 2>&1
  echo $? >"$SESSION/atrace-stop.rc"
  set -e
  snap after || true
  for name in strace.log strace.err perfetto.trace perfetto.err simpleperf.data simpleperf.err; do timeout 8 adb -s "$SERIAL" pull "$REMOTE_SESSION/$name" "$SESSION/$name" >/dev/null 2>&1 || true; done
  echo "STOP_EPOCH='$(date +%s.%3N)'" >>"$STATE"
  python3 "$ROOT/scripts/lastwar-formation-omnitrace-analyze-v1.py" "$SESSION" "$BASE/latest.json"
  rm -f "$STATE"
  if ! curl -fsS --max-time 1 http://127.0.0.1:8788/ >/dev/null 2>&1; then nohup python3 -m http.server 8788 --directory "$ROOT/frontend" >"$BASE/http.log" 2>&1 & sleep 1; fi
  say "FORMATION_OMNITRACE_V1_ANALYZED session=$ID"
  say 'VIEWER=http://127.0.0.1:8788/lab/lastwar-formation-omnitrace.html?v=1'
}

status_cmd(){ if [[ -f "$STATE" ]]; then cat "$STATE"; else echo 'OMNITRACE=IDLE'; fi; }
case "${1:-}" in
  start) shift; start_cmd "$*" ;;
  stop) stop_cmd ;;
  status) status_cmd ;;
  *) echo 'Usage: bash scripts/lastwar-formation-omnitrace-v1.sh start "Murphy -> autre héros" | stop | status'; exit 1 ;;
esac
