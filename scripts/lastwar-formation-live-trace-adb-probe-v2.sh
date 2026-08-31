#!/data/data/com.termux/files/usr/bin/bash
set -u
PKG="com.fun.lastwar.gp"
printf 'FORMATION_LIVE_TRACE_ADB_PROBE_V2_START\n'
printf 'shell=%s\n' "${SHELL:-?}"
printf 'termux=%s\n' "${PREFIX:-?}"

if ! command -v adb >/dev/null 2>&1; then
  printf 'ADB=ABSENT\n'
  printf 'NEXT=pkg install -y android-tools\n'
  exit 2
fi
printf 'ADB=FOUND path=%s\n' "$(command -v adb)"
printf '%s\n' '--- ADB VERSION ---'
timeout 5 adb version 2>&1 || printf 'ADB_VERSION_TIMEOUT_OR_ERROR rc=%s\n' "$?"

printf '%s\n' '--- ADB DEVICES ---'
DEVOUT="$(timeout 8 adb devices -l 2>&1)"; RC=$?
printf '%s\n' "$DEVOUT"
if [[ $RC -ne 0 ]]; then
  printf 'ADB_DEVICES_ERROR rc=%s\n' "$RC"
fi
SERIAL="$(printf '%s\n' "$DEVOUT" | awk 'NR>1 && $2=="device"{print $1;exit}' | tr -d '\r')"

if [[ -z "$SERIAL" ]]; then
  printf '%s\n' '--- ADB MDNS ---'
  MDNS="$(timeout 8 adb mdns services 2>&1)"; MRC=$?
  printf '%s\n' "$MDNS"
  [[ $MRC -eq 0 ]] || printf 'ADB_MDNS_ERROR rc=%s\n' "$MRC"
  EP="$(printf '%s\n' "$MDNS" | awk '/_adb-tls-connect\._tcp/{print $NF;exit}' | tr -d '\r')"
  if [[ -n "$EP" ]]; then
    printf 'ADB_MDNS_ENDPOINT=%s\n' "$EP"
    timeout 8 adb connect "$EP" 2>&1 || printf 'ADB_CONNECT_ERROR rc=%s\n' "$?"
    sleep 1
    DEVOUT="$(timeout 8 adb devices -l 2>&1)"
    printf '%s\n' "$DEVOUT"
    SERIAL="$(printf '%s\n' "$DEVOUT" | awk 'NR>1 && $2=="device"{print $1;exit}' | tr -d '\r')"
  fi
fi

if [[ -z "$SERIAL" ]]; then
  printf 'RESULT=ADB_NOT_CONNECTED\n'
  printf 'NEXT=bash scripts/lastwar-formation-live-trace-v1.sh pair\n'
  exit 3
fi

printf 'RESULT=ADB_CONNECTED serial=%s\n' "$SERIAL"
printf '%s\n' '--- DEVICE ---'
timeout 8 adb -s "$SERIAL" shell 'printf "model="; getprop ro.product.model; printf "sdk="; getprop ro.build.version.sdk' 2>&1 || true
printf '%s\n' '--- LAST WAR PACKAGE ---'
PKGOUT="$(timeout 8 adb -s "$SERIAL" shell pm path "$PKG" 2>&1)"; PRC=$?
printf '%s\n' "$PKGOUT"
[[ $PRC -eq 0 ]] || printf 'PACKAGE_QUERY_ERROR rc=%s\n' "$PRC"
printf '%s\n' '--- LAST WAR PROCESS ---'
PID="$(timeout 8 adb -s "$SERIAL" shell pidof "$PKG" 2>/dev/null | tr -d '\r')"
printf 'pid=%s\n' "${PID:-NONE}"
printf '%s\n' '--- LOGCAT CAPABILITY ---'
timeout 8 adb -s "$SERIAL" logcat -d -t 3 -v brief 2>&1 || printf 'LOGCAT_ERROR rc=%s\n' "$?"
printf 'FORMATION_LIVE_TRACE_ADB_PROBE_V2_DONE\n'