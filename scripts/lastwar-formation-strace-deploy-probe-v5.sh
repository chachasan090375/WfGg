#!/data/data/com.termux/files/usr/bin/bash
set -Eeuo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BRANCH="portal-auth-lastwar-lab-v1"
PKG="com.fun.lastwar.gp"
PREFIX="${PREFIX:-/data/data/com.termux/files/usr}"
PREFIX_LIB="$PREFIX/lib"
REMOTE="/data/local/tmp/wfgg-strace-v5"
RAW="$ROOT/frontend/lab/master-assets-v2/strace-deploy-v5"
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
echo "FORMATION_STRACE_DEPLOY_PROBE_V5_START device=$SERIAL pid=$PID"
echo "LOCAL_STRACE=$LOCAL_STRACE"

ELF_TOOL=''
if command -v readelf >/dev/null 2>&1; then ELF_TOOL=readelf
elif command -v llvm-readelf >/dev/null 2>&1; then ELF_TOOL=llvm-readelf
elif command -v objdump >/dev/null 2>&1; then ELF_TOOL=objdump
fi
if [[ -z "$ELF_TOOL" ]]; then
  echo 'ELF_DEP_TOOL=ABSENT'
  echo 'NEXT=pkg install binutils'
  exit 5
fi
echo "ELF_DEP_TOOL=$ELF_TOOL"

needed_names() {
  local obj="$1"
  case "$ELF_TOOL" in
    readelf|llvm-readelf)
      "$ELF_TOOL" -d "$obj" 2>/dev/null | sed -n 's/.*Shared library: \[\([^]]*\)\].*/\1/p'
      ;;
    objdump)
      objdump -p "$obj" 2>/dev/null | awk '$1=="NEEDED"{print $2}'
      ;;
  esac
}

resolve_termux_lib() {
  local soname="$1" p=''
  # Exact SONAME path first (often a symlink), then a conservative versioned fallback.
  if [[ -e "$PREFIX_LIB/$soname" ]]; then
    readlink -f "$PREFIX_LIB/$soname" 2>/dev/null || printf '%s\n' "$PREFIX_LIB/$soname"
    return 0
  fi
  p="$(find "$PREFIX_LIB" -maxdepth 1 -type f -name "$soname.*" -print 2>/dev/null | sort -V | tail -n1)"
  [[ -n "$p" ]] && { printf '%s\n' "$p"; return 0; }
  return 1
}

adb -s "$SERIAL" shell "rm -rf $REMOTE; mkdir -p $REMOTE/lib" >/dev/null 2>&1 || true
adb -s "$SERIAL" push "$LOCAL_STRACE" "$REMOTE/strace" >/dev/null

declare -A SONAME_PATH=()
declare -A SCANNED=()
QUEUE=("$LOCAL_STRACE")
QINDEX=0
printf '%s\n' '--- ELF DT_NEEDED RECURSIVE CLOSURE ---'
while (( QINDEX < ${#QUEUE[@]} )); do
  obj="${QUEUE[$QINDEX]}"; QINDEX=$((QINDEX+1))
  [[ -f "$obj" ]] || continue
  real="$(readlink -f "$obj" 2>/dev/null || printf '%s' "$obj")"
  [[ -n "${SCANNED[$real]:-}" ]] && continue
  SCANNED[$real]=1
  echo "SCAN=$(basename "$obj")"
  while IFS= read -r soname; do
    [[ -n "$soname" ]] || continue
    # If Termux has this SONAME, bundle it. Otherwise Android's system linker supplies it.
    dep="$(resolve_termux_lib "$soname" 2>/dev/null || true)"
    if [[ -n "$dep" && -f "$dep" ]]; then
      if [[ -z "${SONAME_PATH[$soname]:-}" ]]; then
        SONAME_PATH[$soname]="$dep"
        echo "DISCOVER_TERMUX soname=$soname source=$(basename "$dep")"
        QUEUE+=("$dep")
      fi
    else
      echo "SYSTEM_OR_UNRESOLVED soname=$soname"
    fi
  done < <(needed_names "$obj" | sort -u)
done

printf 'DEPENDENCY_CLOSURE_COUNT=%s\n' "${#SONAME_PATH[@]}"
printf '%s\n' '--- PUSH ELF CLOSURE BY REQUESTED SONAME ---'
for soname in "${!SONAME_PATH[@]}"; do
  dep="${SONAME_PATH[$soname]}"
  echo "PUSH_LIB soname=$soname source=$(basename "$dep")"
  adb -s "$SERIAL" push "$dep" "$REMOTE/lib/$soname" >/dev/null
done
adb -s "$SERIAL" shell "chmod 755 $REMOTE/strace; chmod 644 $REMOTE/lib/* 2>/dev/null || true; ls -l $REMOTE/lib | head -n 240" 2>/dev/null | tr -d '\r' | tee "$RAW/remote-libs.txt" || true

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
  exit 6
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
  exit 7
fi
if printf '%s\n' "$ATTACH_TEXT" | grep -Eqi 'no such process|cannot link executable|linker:|not found'; then
  echo "REMOTE_STRACE_ATTACH=ERROR rc=$ARC"
  echo 'RESULT=STRACE_ATTACH_ERROR'
  exit 8
fi
echo "REMOTE_STRACE_ATTACH=LIKELY_OK rc=$ARC"

printf '%s\n' '--- SYSCALL SMOKE TEST ---'
set +e
timeout 6 adb -s "$SERIAL" shell "timeout 2 env LD_LIBRARY_PATH=$REMOTE/lib $REMOTE/strace -tt -f -p $PID -e trace=openat,read,pread64,mmap,connect,sendto,recvfrom -s 220 2>&1" | tr -d '\r' | tee "$RAW/syscall-smoke.txt"
SRC=${PIPESTATUS[0]}
set -e
LINES="$(grep -Ec '\b(openat|read|pread64|mmap|connect|sendto|recvfrom)\(' "$RAW/syscall-smoke.txt" 2>/dev/null || true)"
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
