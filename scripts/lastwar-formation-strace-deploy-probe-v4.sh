#!/data/data/com.termux/files/usr/bin/bash
set -Eeuo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BRANCH="portal-auth-lastwar-lab-v1"
PKG="com.fun.lastwar.gp"
PREFIX_LIB="/data/data/com.termux/files/usr/lib"
REMOTE="/data/local/tmp/wfgg-strace-v4"
RAW="$ROOT/frontend/lab/master-assets-v2/strace-deploy-v4"
cd "$ROOT"
[[ "$(git branch --show-current)" == "$BRANCH" ]] || { echo 'ERREUR: branche LAB incorrecte'; exit 1; }
command -v adb >/dev/null 2>&1 || { echo 'ADB=ABSENT'; exit 1; }
LOCAL_STRACE="$(command -v strace || true)"
[[ -n "$LOCAL_STRACE" ]] || { echo 'LOCAL_STRACE=ABSENT'; echo 'NEXT=pkg install strace'; exit 2; }
SERIAL="$(adb devices 2>/dev/null | awk 'NR>1 && $2=="device"{print $1;exit}')"
[[ -n "$SERIAL" ]] || { echo 'ADB_DEVICE=ABSENT'; exit 3; }
PID="$(timeout 2 adb -s "$SERIAL" shell pidof "$PKG" 2>/dev/null | tr -d '\r' | awk '{print $1}')"
[[ -n "$PID" ]] || { echo 'LASTWAR_PID=ABSENT'; exit 4; }
mkdir -p "$RAW"
echo "FORMATION_STRACE_DEPLOY_PROBE_V4_START device=$SERIAL pid=$PID"
echo "LOCAL_STRACE=$LOCAL_STRACE"
file "$LOCAL_STRACE" 2>&1 | tee "$RAW/file.txt" || true

adb -s "$SERIAL" shell "rm -rf $REMOTE; mkdir -p $REMOTE/lib" >/dev/null 2>&1 || true
adb -s "$SERIAL" push "$LOCAL_STRACE" "$REMOTE/strace" >/dev/null

declare -A SONAME_PATH=()
declare -A SCANNED_PATH=()
QUEUE=("$LOCAL_STRACE")
QINDEX=0

resolve_dep_rows() {
  local obj="$1"
  ldd "$obj" 2>/dev/null |
    awk '$2=="=>" && $3 ~ /^\/data\/data\/com\.termux\/files\/usr\/lib\// {print $1 "|" $3}'
}

printf '%s\n' '--- RECURSIVE TERMUX DEPENDENCY CLOSURE ---'
while (( QINDEX < ${#QUEUE[@]} )); do
  obj="${QUEUE[$QINDEX]}"
  QINDEX=$((QINDEX+1))
  [[ -f "$obj" ]] || continue
  real="$(readlink -f "$obj" 2>/dev/null || printf '%s' "$obj")"
  [[ -n "${SCANNED_PATH[$real]:-}" ]] && continue
  SCANNED_PATH[$real]=1
  echo "SCAN=$(basename "$obj")"
  while IFS='|' read -r soname dep; do
    [[ -n "$soname" && -n "$dep" ]] || continue
    [[ -f "$dep" ]] || { echo "MISSING_LOCAL_DEP soname=$soname path=$dep"; continue; }
    if [[ -z "${SONAME_PATH[$soname]:-}" ]]; then
      SONAME_PATH[$soname]="$dep"
      echo "DISCOVER soname=$soname source=$(basename "$dep")"
      QUEUE+=("$dep")
    fi
  done < <(resolve_dep_rows "$obj")
done

printf 'DEPENDENCY_CLOSURE_COUNT=%s\n' "${#SONAME_PATH[@]}"
printf '%s\n' '--- PUSH RECURSIVE LIBS BY REQUESTED SONAME ---'
for soname in "${!SONAME_PATH[@]}"; do
  dep="${SONAME_PATH[$soname]}"
  echo "PUSH_LIB soname=$soname source=$(basename "$dep")"
  adb -s "$SERIAL" push "$dep" "$REMOTE/lib/$soname" >/dev/null
 done

adb -s "$SERIAL" shell "chmod 755 $REMOTE/strace; chmod 644 $REMOTE/lib/* 2>/dev/null || true; ls -l $REMOTE/lib | head -n 160" 2>/dev/null | tr -d '\r' | tee "$RAW/remote-libs.txt" || true

printf '%s\n' '--- REMOTE STRACE VERSION ---'
set +e
adb -s "$SERIAL" shell "env LD_LIBRARY_PATH=$REMOTE/lib $REMOTE/strace --version 2>&1" | tr -d '\r' | tee "$RAW/remote-version.txt"
VRC=${PIPESTATUS[0]}
set -e
if [[ $VRC -ne 0 ]]; then
  echo "REMOTE_STRACE_RUN=FAIL rc=$VRC"
  miss="$(grep -oE 'library "[^"]+" not found' "$RAW/remote-version.txt" | head -n1 || true)"
  [[ -n "$miss" ]] && echo "MISSING_REMOTE_DEP=$miss"
  echo 'RESULT=REMOTE_STRACE_NOT_RUNNABLE'
  exit 5
fi
echo 'REMOTE_STRACE_RUN=OK'

printf '%s\n' '--- REAL ATTACH TEST ---'
set +e
timeout 5 adb -s "$SERIAL" shell "timeout 1 env LD_LIBRARY_PATH=$REMOTE/lib $REMOTE/strace -tt -f -p $PID -e trace=none 2>&1" | tr -d '\r' | tee "$RAW/attach.txt"
ARC=${PIPESTATUS[0]}
set -e
ATTACH_TEXT="$(cat "$RAW/attach.txt" 2>/dev/null || true)"
if printf '%s\n' "$ATTACH_TEXT" | grep -Eqi 'operation not permitted|permission denied|ptrace.*denied|attach:.*denied'; then
  echo "REMOTE_STRACE_ATTACH=DENIED rc=$ARC"
  echo 'RESULT=STRACE_ATTACH_DENIED'
  exit 6
fi
if printf '%s\n' "$ATTACH_TEXT" | grep -Eqi 'no such process|not found|linker:'; then
  echo "REMOTE_STRACE_ATTACH=ERROR rc=$ARC"
  echo 'RESULT=STRACE_ATTACH_ERROR'
  exit 7
fi
echo "REMOTE_STRACE_ATTACH=LIKELY_OK rc=$ARC"

printf '%s\n' '--- SYSCALL SMOKE TEST ---'
set +e
timeout 5 adb -s "$SERIAL" shell "timeout 2 env LD_LIBRARY_PATH=$REMOTE/lib $REMOTE/strace -tt -f -p $PID -e trace=openat,read,mmap,connect,sendto,recvfrom -s 200 2>&1" | tr -d '\r' | tee "$RAW/syscall-smoke.txt"
SRC=${PIPESTATUS[0]}
set -e
LINES="$(grep -Ec '\b(openat|read|mmap|connect|sendto|recvfrom)\(' "$RAW/syscall-smoke.txt" 2>/dev/null || true)"
if [[ "$LINES" -gt 0 ]]; then
  echo "SYSCALL_SMOKE_LINES=$LINES"
  echo 'RESULT=REMOTE_STRACE_READY'
  echo "REMOTE_STRACE=$REMOTE/strace"
  echo "REMOTE_LD_LIBRARY_PATH=$REMOTE/lib"
else
  if grep -Eqi 'operation not permitted|permission denied|ptrace.*denied' "$RAW/syscall-smoke.txt" 2>/dev/null; then
    echo "SYSCALL_SMOKE_LINES=0 rc=$SRC"
    echo 'RESULT=STRACE_ATTACH_DENIED'
  else
    echo "SYSCALL_SMOKE_LINES=0 rc=$SRC"
    echo 'RESULT=STRACE_ATTACH_NO_SYSCALLS_YET'
    echo "REMOTE_STRACE=$REMOTE/strace"
    echo "REMOTE_LD_LIBRARY_PATH=$REMOTE/lib"
  fi
fi
