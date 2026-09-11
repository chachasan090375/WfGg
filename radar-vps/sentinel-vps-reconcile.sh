#!/usr/bin/env bash
set -Eeuo pipefail

# WfGg Radar Sentinel — privileged local VPS reconciler.
# Purpose: keep the already Guardian-published Radar connector binaries in sync
# with radar-vps/release without ever handling a Last War access token.
# It performs checksum verification, atomic replacement, service restart,
# health verification and rollback on deployment failure.

RELEASE_BASE="${RADAR_RELEASE_BASE:-https://raw.githubusercontent.com/chachasan090375/WfGg/radar-production-v1/radar-vps/release}"
ROOT="${RADAR_ROOT:-/opt/wfgg-radar}"
BIN_DIR="$ROOT/bin"
DATA_DIR="$ROOT/data"
BACKUP_DIR="$DATA_DIR/sentinel-backups"
STATE_FILE="$DATA_DIR/sentinel-vps-state.env"
SERVICE="${RADAR_SERVICE:-wfgg-radar-connector}"
LOCK_FILE="/run/wfgg-radar-sentinel.lock"

log() { printf '%s %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*"; }
fail() { log "SENTINEL_VPS=FAILED reason=$*"; exit 1; }

[[ "$(id -u)" -eq 0 ]] || fail "ROOT_REQUIRED"
for c in curl sha256sum install systemctl grep flock mktemp cp mv; do
  command -v "$c" >/dev/null 2>&1 || fail "COMMAND_MISSING:$c"
done

install -d -m 0755 "$BIN_DIR"
install -d -m 0750 "$DATA_DIR" "$BACKUP_DIR"

exec 9>"$LOCK_FILE"
if ! flock -n 9; then
  log "SENTINEL_VPS=SKIP reason=ALREADY_RUNNING"
  exit 0
fi

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT INT TERM

log "SENTINEL_VPS=START"
curl --fail --silent --show-error --location --max-time 20 "$RELEASE_BASE/SHA256SUMS" -o "$TMP/SHA256SUMS"
for f in radar-connector radar-native-template; do
  curl --fail --silent --show-error --location --max-time 60 "$RELEASE_BASE/$f" -o "$TMP/$f"
done
(
  cd "$TMP"
  sha256sum -c SHA256SUMS
) >/dev/null || fail "RELEASE_CHECKSUM_INVALID"
chmod 0755 "$TMP/radar-connector" "$TMP/radar-native-template"

# Guardrails: Sentinel may deploy only the already published READONLY v4 family.
grep -aFq 'native-template-readonly-v4' "$TMP/radar-native-template" || fail "RELEASE_NOT_READONLY_V4"
grep -aFq 'world.get.block' "$TMP/radar-native-template" || fail "RELEASE_MAP_COMMAND_MISSING"
grep -aFq 'get.user.info.multi' "$TMP/radar-native-template" || fail "RELEASE_PROFILE_COMMAND_MISSING"

EXPECTED_CONNECTOR="$(awk '$2=="radar-connector"{print $1}' "$TMP/SHA256SUMS" | head -1)"
EXPECTED_NATIVE="$(awk '$2=="radar-native-template"{print $1}' "$TMP/SHA256SUMS" | head -1)"
[[ -n "$EXPECTED_CONNECTOR" && -n "$EXPECTED_NATIVE" ]] || fail "RELEASE_MANIFEST_INCOMPLETE"

local_sha() {
  local f="$1"
  [[ -f "$f" ]] && sha256sum "$f" | awk '{print $1}' || true
}

CURRENT_CONNECTOR="$(local_sha "$BIN_DIR/radar-connector")"
CURRENT_NATIVE="$(local_sha "$BIN_DIR/radar-native-template")"
DRIFT=0
[[ "$CURRENT_CONNECTOR" == "$EXPECTED_CONNECTOR" ]] || DRIFT=1
[[ "$CURRENT_NATIVE" == "$EXPECTED_NATIVE" ]] || DRIFT=1

if [[ "$DRIFT" -eq 0 ]]; then
  if systemctl is-active --quiet "$SERVICE"; then
    log "SENTINEL_VPS=HEALTHY release=matched service=active"
  else
    log "SENTINEL_VPS=REPAIR action=restart reason=SERVICE_INACTIVE"
    systemctl restart "$SERVICE"
    sleep 2
    systemctl is-active --quiet "$SERVICE" || fail "SERVICE_RESTART_FAILED"
    log "SENTINEL_VPS=RECOVERED action=restart"
  fi
  cat >"$STATE_FILE" <<EOF
SENTINEL_VPS_STATUS=HEALTHY
SENTINEL_VPS_LAST_CHECK=$(date -u +%Y-%m-%dT%H:%M:%SZ)
SENTINEL_VPS_CONNECTOR_SHA=$EXPECTED_CONNECTOR
SENTINEL_VPS_NATIVE_SHA=$EXPECTED_NATIVE
EOF
  chmod 0640 "$STATE_FILE"
  exit 0
fi

STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
BACKUP="$BACKUP_DIR/$STAMP"
install -d -m 0750 "$BACKUP"
[[ -f "$BIN_DIR/radar-connector" ]] && cp -a "$BIN_DIR/radar-connector" "$BACKUP/radar-connector" || true
[[ -f "$BIN_DIR/radar-native-template" ]] && cp -a "$BIN_DIR/radar-native-template" "$BACKUP/radar-native-template" || true

log "SENTINEL_VPS=REPAIR action=deploy_guardian_release"
install -m 0755 "$TMP/radar-connector" "$BIN_DIR/.radar-connector.sentinel-new"
install -m 0755 "$TMP/radar-native-template" "$BIN_DIR/.radar-native-template.sentinel-new"
mv -f "$BIN_DIR/.radar-connector.sentinel-new" "$BIN_DIR/radar-connector"
mv -f "$BIN_DIR/.radar-native-template.sentinel-new" "$BIN_DIR/radar-native-template"

NEW_CONNECTOR="$(local_sha "$BIN_DIR/radar-connector")"
NEW_NATIVE="$(local_sha "$BIN_DIR/radar-native-template")"
if [[ "$NEW_CONNECTOR" != "$EXPECTED_CONNECTOR" || "$NEW_NATIVE" != "$EXPECTED_NATIVE" ]]; then
  fail "POST_INSTALL_CHECKSUM_MISMATCH"
fi

systemctl restart "$SERVICE" || true
sleep 2
if ! systemctl is-active --quiet "$SERVICE"; then
  log "SENTINEL_VPS=ROLLBACK reason=SERVICE_FAILED_AFTER_DEPLOY"
  [[ -f "$BACKUP/radar-connector" ]] && install -m 0755 "$BACKUP/radar-connector" "$BIN_DIR/radar-connector"
  [[ -f "$BACKUP/radar-native-template" ]] && install -m 0755 "$BACKUP/radar-native-template" "$BIN_DIR/radar-native-template"
  systemctl restart "$SERVICE" || true
  sleep 2
  systemctl is-active --quiet "$SERVICE" || fail "ROLLBACK_SERVICE_FAILED"
  cat >"$STATE_FILE" <<EOF
SENTINEL_VPS_STATUS=ROLLED_BACK
SENTINEL_VPS_LAST_CHECK=$(date -u +%Y-%m-%dT%H:%M:%SZ)
SENTINEL_VPS_FAILED_CONNECTOR_SHA=$EXPECTED_CONNECTOR
SENTINEL_VPS_FAILED_NATIVE_SHA=$EXPECTED_NATIVE
EOF
  chmod 0640 "$STATE_FILE"
  fail "DEPLOYMENT_ROLLED_BACK"
fi

cat >"$STATE_FILE" <<EOF
SENTINEL_VPS_STATUS=RECOVERED
SENTINEL_VPS_LAST_CHECK=$(date -u +%Y-%m-%dT%H:%M:%SZ)
SENTINEL_VPS_CONNECTOR_SHA=$EXPECTED_CONNECTOR
SENTINEL_VPS_NATIVE_SHA=$EXPECTED_NATIVE
SENTINEL_VPS_BACKUP=$BACKUP
EOF
chmod 0640 "$STATE_FILE"
log "SENTINEL_VPS=RECOVERED action=deploy_guardian_release service=active"
