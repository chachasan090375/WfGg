#!/usr/bin/env bash
set -Eeuo pipefail

REV="${WFGG_RADAR_V61911_REV:-radar-v61911-manual-search-stop}"
BASE="https://raw.githubusercontent.com/chachasan090375/WfGg/${REV}/radar-vps/pilot-v61911"
ROOT="/opt/wfgg-radar"
BIN="${ROOT}/bin"
DATA="${ROOT}/data"
TMP_ROOT="/opt/chacha-dev/runtime/tmp"
mkdir -p "$TMP_ROOT"
TMP="$(mktemp -d "$TMP_ROOT/wfgg-radar-v61911.XXXXXX")"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
BACKUP="${DATA}/v61911-pilot-backups/${STAMP}"
SERVICE="wfgg-radar-connector"
PROMOTED=0

log(){ printf '%s\n' "$*"; }
fail(){ log "RADAR_V61911_PILOT_INSTALL=FAIL reason=$*"; exit 1; }
cleanup(){ rm -rf "$TMP"; }
rollback(){
  rc=$?
  if [[ "$rc" -ne 0 && "$PROMOTED" -eq 1 ]]; then
    log "RADAR_V61911_PILOT_ROLLBACK=START"
    [[ -f "$BACKUP/radar-connector" ]] && install -m 0755 "$BACKUP/radar-connector" "$BIN/radar-connector"
    systemctl restart "$SERVICE" || true
    sleep 2
    systemctl is-active --quiet "$SERVICE" && log "RADAR_V61911_PILOT_ROLLBACK=PASS" || log "RADAR_V61911_PILOT_ROLLBACK=FAIL"
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

log "=== WFGG RADAR V6.19.11 MANUAL SEARCH STOP PILOT INSTALL ==="
log "RADAR_V61911_REV=$REV"

BEFORE_CONNECTOR="$(sha256sum "$BIN/radar-connector" 2>/dev/null | awk '{print $1}' || true)"
log "RADAR_CONNECTOR_BEFORE=${BEFORE_CONNECTOR:-MISSING}"

for f in SHA256SUMS PILOT_INFO.txt radar-connector; do
  curl --fail --silent --show-error --location --max-time 90 "$BASE/$f" -o "$TMP/$f" || fail "DOWNLOAD:$f"
done
(cd "$TMP" && sha256sum -c SHA256SUMS) >/dev/null || fail CHECKSUM

grep -Fq 'WFGG_RADAR_PILOT=V6.19.11' "$TMP/PILOT_INFO.txt" || fail PILOT_INFO_VERSION
grep -Fq 'MANUAL_SEARCH_STOP=YES' "$TMP/PILOT_INFO.txt" || fail PILOT_INFO_FEATURE
grep -Fq 'LASTWAR_MODE=READ_ONLY' "$TMP/PILOT_INFO.txt" || fail PILOT_INFO_READONLY
grep -Fq 'GAME_SCAN_GUARD_PROBE=NO' "$TMP/PILOT_INFO.txt" || fail PILOT_INFO_NO_SCAN
grep -Fq 'TOKEN_PERSISTENCE=NO' "$TMP/PILOT_INFO.txt" || fail PILOT_INFO_TOKEN
grep -Fq 'PRODUCTION_DEPLOYMENT=NO' "$TMP/PILOT_INFO.txt" || fail PILOT_INFO_PRODUCTION

EXPECTED_CONNECTOR="$(awk '$2=="radar-connector"{print $1}' "$TMP/SHA256SUMS" | head -1)"
[[ -n "$EXPECTED_CONNECTOR" ]] || fail MANIFEST

install -d -m 0750 "$BACKUP"
cp -a "$BIN/radar-connector" "$BACKUP/radar-connector"

install -m 0755 "$TMP/radar-connector" "$BIN/.radar-connector-v61911-new"
mv -f "$BIN/.radar-connector-v61911-new" "$BIN/radar-connector"
PROMOTED=1

ACTUAL_CONNECTOR="$(sha256sum "$BIN/radar-connector" | awk '{print $1}')"
[[ "$ACTUAL_CONNECTOR" == "$EXPECTED_CONNECTOR" ]] || fail CONNECTOR_POST_SHA

systemctl restart "$SERVICE"
sleep 2
systemctl is-active --quiet "$SERVICE" || fail SERVICE

log "RADAR_CONNECTOR_AFTER=$ACTUAL_CONNECTOR"
log "RADAR_SERVICE_AFTER=active"
log "RADAR_V61911_PILOT_BACKUP=$BACKUP"
log "RADAR_V61911_LASTWAR_MODE=READ_ONLY"
log "RADAR_V61911_TOKEN_PERSISTENCE=NO"
log "RADAR_V61911_PRODUCTION_DEPLOYMENT=NO"
log "RADAR_V61911_PILOT_INSTALL=PASS"

PROMOTED=0
trap - EXIT
cleanup
