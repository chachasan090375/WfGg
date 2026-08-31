#!/data/data/com.termux/files/usr/bin/bash
set -Eeuo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BRANCH="portal-auth-lastwar-lab-v1"
PKG="com.fun.lastwar.gp"
REMOTE="/data/local/tmp/wfgg-strace-v2"
cd "$ROOT"
[[ "$(git branch --show-current)" == "$BRANCH" ]] || { echo 'ERREUR: branche LAB incorrecte'; exit 1; }
command -v adb >/dev/null 2>&1 || { echo 'ADB=ABSENT'; exit 1; }
LOCAL_STRACE="$(command -v strace || true)"
[[ -n "$LOCAL_STRACE" ]] || { echo 'LOCAL_STRACE=ABSENT'; echo 'NEXT=pkg install strace'; exit 2; }
SERIAL="$(adb devices 2>/dev/null | awk 'NR>1 && $2=="device"{print $1;exit}')"
[[ -n "$SERIAL" ]] || { echo 'ADB_DEVICE=ABSENT'; exit 3; }
PID="$(timeout 2 adb -s "$SERIAL" shell pidof "$PKG" 2>/dev/null | tr -d '\r' | awk '{print $1}')"
[[ -n "$PID" ]] || { echo 'LASTWAR_PID=ABSENT'; exit 4; }
echo "FORMATION_STRACE_DEPLOY_PROBE_V2_START device=$SERIAL pid=$PID"
echo "LOCAL_STRACE=$LOCAL_STRACE"
mkdir -p "$ROOT/frontend/lab/master-assets-v2/strace-deploy-v2"
RAW="$ROOT/frontend/lab/master-assets-v2/strace-deploy-v2"
{
  echo "binary=$LOCAL_STRACE"
  file "$LOCAL_STRACE" 2>&1 || true
  ldd "$LOCAL_STRACE" 2>&1 || true
} > "$RAW/local-strace.txt"
head -n 30 "$RAW/local-strace.txt" || true
adb -s "$SERIAL" shell "rm -rf $REMOTE; mkdir -p $REMOTE/lib" >/dev/null 2>&1 || true
adb -s "$SERIAL" push "$LOCAL_STRACE" "$REMOTE/strace" >/dev/null
# Push every Termux-side dependency reported by ldd. System libraries are intentionally skipped.
mapfile -t DEPS < <(ldd "$LOCAL_STRACE" 2>/dev/null | awk '{for(i=1;i<=NF;i++) if($i ~ /^\/data\/data\/com\.termux\/files\/usr\/lib\//) print $i}' | sort -u)
for dep in "${DEPS[@]:-}"; do
  [[ -f "$dep" ]] || continue
  echo "PUSH_LIB=$(basename "$dep")"
  adb -s "$SERIAL" push "$dep" "$REMOTE/lib/$(basename "$dep")" >/dev/null || true
done
adb -s "$SERIAL" shell "chmod 755 $REMOTE/strace; chmod 644 $REMOTE/lib/* 2>/dev/null || true" >/dev/null 2>&1 || true
set +e
adb -s "$SERIAL" shell "LD_LIBRARY_PATH=$REMOTE/lib $REMOTE/strace --version 2>&1" | tr -d '\r' | tee "$RAW/remote-version.txt"
VRC=${PIPESTATUS[0]}
set -e
if [[ $VRC -ne 0 ]]; then
  echo "REMOTE_STRACE_RUN=FAIL rc=$VRC"
  echo 'RESULT=REMOTE_STRACE_NOT_RUNNABLE'
  exit 5
fi
echo 'REMOTE_STRACE_RUN=OK'
set +e
timeout 4 adb -s "$SERIAL" shell "timeout 1 env LD_LIBRARY_PATH=$REMOTE/lib $REMOTE/strace -tt -f -p $PID -e trace=none 2>&1" | tr -d '\r' | tee "$RAW/attach.txt"
ARC=${PIPESTATUS[0]}
set -e
ATTACH_TEXT="$(cat "$RAW/attach.txt" 2>/dev/null || true)"
if printf '%s\n' "$ATTACH_TEXT" | grep -Eqi 'operation not permitted|permission denied|ptrace|attach:.*denied|no such process'; then
  echo "REMOTE_STRACE_ATTACH=DENIED rc=$ARC"
  echo 'RESULT=STRACE_ATTACH_DENIED'
  exit 6
fi
# timeout rc is acceptable: an attached trace=none session normally has nothing to print until timeout stops it.
echo "REMOTE_STRACE_ATTACH=LIKELY_OK rc=$ARC"
# Final functional syscall smoke test. We only need a handful of lines to prove real interception.
set +e
timeout 4 adb -s "$SERIAL" shell "timeout 1 env LD_LIBRARY_PATH=$REMOTE/lib $REMOTE/strace -tt -f -p $PID -e trace=openat,read,mmap,connect,sendto,recvfrom -s 160 2>&1" | tr -d '\r' | tee "$RAW/syscall-smoke.txt"
SRC=${PIPESTATUS[0]}
set -e
LINES="$(grep -Ec '\b(openat|read|mmap|connect|sendto|recvfrom)\(' "$RAW/syscall-smoke.txt" 2>/dev/null || true)"
if [[ "$LINES" -gt 0 ]]; then
  echo "SYSCALL_SMOKE_LINES=$LINES"
  echo 'RESULT=REMOTE_STRACE_READY'
  echo "REMOTE_STRACE=$REMOTE/strace"
  echo "REMOTE_LD_LIBRARY_PATH=$REMOTE/lib"
else
  echo "SYSCALL_SMOKE_LINES=0 rc=$SRC"
  echo 'RESULT=STRACE_ATTACH_NO_SYSCALLS_YET'
fi
