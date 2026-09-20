#!/usr/bin/env bash
set -Eeuo pipefail

REV="${WFGG_RADAR_V6197_REV:-radar-v6197-autopilot-stale-cycle-recovery}"
BASE="https://raw.githubusercontent.com/chachasan090375/WfGg/${REV}/radar-vps/pilot-v6197"
ROOT="/opt/wfgg-radar"
BIN="${ROOT}/bin"
DATA="${ROOT}/data"
TMP_ROOT="/opt/chacha-dev/runtime/tmp"
mkdir -p "$TMP_ROOT"
TMP="$(mktemp -d "$TMP_ROOT/wfgg-radar-v6197.XXXXXX")"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
BACKUP="${DATA}/v6197-pilot-backups/${STAMP}"
SERVICE="wfgg-radar-connector"
PROMOTED=0

log(){ printf '%s\n' "$*"; }
fail(){ log "RADAR_V6197_PILOT_INSTALL=FAIL reason=$*"; exit 1; }
cleanup(){ rm -rf "$TMP"; }
rollback(){
  rc=$?
  if [[ "$rc" -ne 0 && "$PROMOTED" -eq 1 ]]; then
    log "RADAR_V6197_PILOT_ROLLBACK=START"
    [[ -f "$BACKUP/radar-connector" ]] && install -m 0755 "$BACKUP/radar-connector" "$BIN/radar-connector"
    [[ -f "$BACKUP/radar-native-template" ]] && install -m 0755 "$BACKUP/radar-native-template" "$BIN/radar-native-template"
    systemctl restart "$SERVICE" || true
    sleep 2
    systemctl is-active --quiet "$SERVICE" && log "RADAR_V6197_PILOT_ROLLBACK=PASS" || log "RADAR_V6197_PILOT_ROLLBACK=FAIL"
  fi
  cleanup
  exit "$rc"
}
trap rollback EXIT

[[ "$(id -u)" -eq 0 ]] || fail ROOT_REQUIRED
for c in curl sha256sum install systemctl mktemp cp mv date awk grep; do
  command -v "$c" >/dev/null 2>&1 || fail "COMMAND_MISSING:$c"
done
systemctl is-active --quiet "$SERVICE" || fail SERVICE_NOT_ACTIVE

log "=== WFGG RADAR V6.19.7 STALE-CYCLE RECOVERY PILOT INSTALL ==="
log "RADAR_V6197_REV=$REV"

BEFORE_CONNECTOR="$(sha256sum "$BIN/radar-connector" 2>/dev/null | awk '{print $1}' || true)"
BEFORE_NATIVE="$(sha256sum "$BIN/radar-native-template" 2>/dev/null | awk '{print $1}' || true)"
log "RADAR_CONNECTOR_BEFORE=${BEFORE_CONNECTOR:-MISSING}"
log "RADAR_NATIVE_BEFORE=${BEFORE_NATIVE:-MISSING}"

for f in SHA256SUMS PILOT_INFO.txt radar-connector radar-native-template; do
  curl --fail --silent --show-error --location --max-time 90 "$BASE/$f" -o "$TMP/$f" || fail "DOWNLOAD:$f"
done
(cd "$TMP" && sha256sum -c SHA256SUMS) >/dev/null || fail CHECKSUM

grep -Fq 'WFGG_RADAR_PILOT=V6.19.7' "$TMP/PILOT_INFO.txt" || fail PILOT_INFO_VERSION
grep -Fq 'STALE_CYCLE_RECOVERY=YES' "$TMP/PILOT_INFO.txt" || fail PILOT_INFO_STALE
grep -Fq 'STALE_THRESHOLD_MINUTES=15' "$TMP/PILOT_INFO.txt" || fail PILOT_INFO_THRESHOLD
grep -Fq 'NO_DATA_CONTINUE_PRESERVED=YES' "$TMP/PILOT_INFO.txt" || fail PILOT_INFO_NO_DATA
grep -Fq 'GLOBAL_FAILURE_GUARDS=PRESERVED' "$TMP/PILOT_INFO.txt" || fail PILOT_INFO_GUARDS
grep -Fq 'LASTWAR_MUTATION=NO' "$TMP/PILOT_INFO.txt" || fail PILOT_INFO_SAFETY

EXPECTED_CONNECTOR="$(awk '$2=="radar-connector"{print $1}' "$TMP/SHA256SUMS" | head -1)"
EXPECTED_NATIVE="$(awk '$2=="radar-native-template"{print $1}' "$TMP/SHA256SUMS" | head -1)"
[[ -n "$EXPECTED_CONNECTOR" && -n "$EXPECTED_NATIVE" ]] || fail MANIFEST

install -d -m 0750 "$BACKUP"
cp -a "$BIN/radar-connector" "$BACKUP/radar-connector"
cp -a "$BIN/radar-native-template" "$BACKUP/radar-native-template"

install -m 0755 "$TMP/radar-connector" "$BIN/.radar-connector-v6197-new"
install -m 0755 "$TMP/radar-native-template" "$BIN/.radar-native-template-v6197-new"
mv -f "$BIN/.radar-connector-v6197-new" "$BIN/radar-connector"
mv -f "$BIN/.radar-native-template-v6197-new" "$BIN/radar-native-template"
PROMOTED=1

ACTUAL_CONNECTOR="$(sha256sum "$BIN/radar-connector" | awk '{print $1}')"
ACTUAL_NATIVE="$(sha256sum "$BIN/radar-native-template" | awk '{print $1}')"
[[ "$ACTUAL_CONNECTOR" == "$EXPECTED_CONNECTOR" ]] || fail CONNECTOR_POST_SHA
[[ "$ACTUAL_NATIVE" == "$EXPECTED_NATIVE" ]] || fail NATIVE_POST_SHA

systemctl restart "$SERVICE"
sleep 2
systemctl is-active --quiet "$SERVICE" || fail SERVICE

log "RADAR_CONNECTOR_AFTER=$ACTUAL_CONNECTOR"
log "RADAR_NATIVE_AFTER=$ACTUAL_NATIVE"
log "RADAR_SERVICE_AFTER=active"
log "RADAR_V6197_PILOT_BACKUP=$BACKUP"
log "RADAR_V6197_LASTWAR_MUTATION=NO"
log "RADAR_V6197_PILOT_INSTALL=PASS"

PROMOTED=0
trap - EXIT
cleanup
