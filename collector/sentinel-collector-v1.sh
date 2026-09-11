#!/usr/bin/env bash
set -Eeuo pipefail

# WfGg Sentinel extension for Collector V1.
# Sentinel supervises Collector without ever reading Last War credentials.

ROOT="${WFGG_COLLECTOR_ROOT:-/opt/wfgg-collector}"
BIN_DIR="$ROOT/bin"
DATA_DIR="$ROOT/data"
BACKUP_DIR="$DATA_DIR/sentinel-backups"
STATE_FILE="$DATA_DIR/sentinel-collector-state.env"
LOCK_FILE="/run/wfgg-collector-sentinel.lock"
SERVICE="${WFGG_COLLECTOR_SERVICE:-wfgg-collector.service}"
RELEASE_BASE="${WFGG_COLLECTOR_RELEASE_BASE:-https://raw.githubusercontent.com/chachasan090375/WfGg/collector-v1/collector/release}"
SAMPLE_PLAYER="${WFGG_COLLECTOR_SENTINEL_SAMPLE:-zazavibes}"

log(){ printf '%s %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*"; }
fail(){ log "SENTINEL_COLLECTOR=FAILED reason=$*"; exit 1; }

[[ "$(id -u)" -eq 0 ]] || fail ROOT_REQUIRED
for c in curl sha256sum install systemctl flock mktemp cp mv python3 awk; do
  command -v "$c" >/dev/null 2>&1 || fail "COMMAND_MISSING:$c"
done

install -d -m 0755 "$BIN_DIR"
install -d -o wfgg-radar -g wfgg-radar -m 0750 "$DATA_DIR"
install -d -m 0750 "$BACKUP_DIR"

exec 9>"$LOCK_FILE"
if ! flock -n 9; then
  log "SENTINEL_COLLECTOR=SKIP reason=ALREADY_RUNNING"
  exit 0
fi

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT INT TERM

log "SENTINEL_COLLECTOR=START"
curl -fsSL --max-time 20 "$RELEASE_BASE/SHA256SUMS" -o "$TMP/SHA256SUMS" || fail RELEASE_MANIFEST_UNAVAILABLE
EXPECTED_NATIVE="$(awk '$2=="radar-native-template"{print $1}' "$TMP/SHA256SUMS" | head -1)"
[[ -n "$EXPECTED_NATIVE" ]] || fail RELEASE_MANIFEST_INCOMPLETE

local_sha(){ [[ -f "$1" ]] && sha256sum "$1" | awk '{print $1}' || true; }
CURRENT_NATIVE="$(local_sha "$BIN_DIR/radar-native-template")"
RECOVERED=0

if [[ "$CURRENT_NATIVE" != "$EXPECTED_NATIVE" ]]; then
  log "SENTINEL_COLLECTOR=REPAIR action=deploy_native reason=SHA_DRIFT"
  curl -fsSL --max-time 90 "$RELEASE_BASE/radar-native-template" -o "$TMP/radar-native-template" || fail RELEASE_NATIVE_UNAVAILABLE
  printf '%s  %s\n' "$EXPECTED_NATIVE" radar-native-template >"$TMP/ONE_SHA256SUMS"
  (cd "$TMP" && sha256sum -c ONE_SHA256SUMS) >/dev/null || fail RELEASE_CHECKSUM_INVALID
  chmod 0755 "$TMP/radar-native-template"

  STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
  BACKUP="$BACKUP_DIR/$STAMP"
  install -d -m 0750 "$BACKUP"
  [[ -f "$BIN_DIR/radar-native-template" ]] && cp -a "$BIN_DIR/radar-native-template" "$BACKUP/radar-native-template" || true

  install -m 0755 "$TMP/radar-native-template" "$BIN_DIR/.radar-native-template.sentinel-new"
  mv -f "$BIN_DIR/.radar-native-template.sentinel-new" "$BIN_DIR/radar-native-template"
  CURRENT_NATIVE="$(local_sha "$BIN_DIR/radar-native-template")"
  [[ "$CURRENT_NATIVE" == "$EXPECTED_NATIVE" ]] || fail POST_INSTALL_CHECKSUM_MISMATCH
  RECOVERED=1
fi

if ! systemctl is-active --quiet "$SERVICE"; then
  log "SENTINEL_COLLECTOR=REPAIR action=restart reason=SERVICE_INACTIVE"
  systemctl restart "$SERVICE" || true
  sleep 2
  systemctl is-active --quiet "$SERVICE" || fail SERVICE_RESTART_FAILED
  RECOVERED=1
fi

probe_collector(){
  python3 - "$SAMPLE_PLAYER" <<'PY'
import json,sys,urllib.parse,urllib.request
sample=sys.argv[1]
with urllib.request.urlopen('http://127.0.0.1:8790/health',timeout=5) as r:
    health=json.load(r)
if health.get('ok') is not True:
    raise SystemExit(2)
with urllib.request.urlopen('http://127.0.0.1:8790/stats',timeout=5) as r:
    stats=json.load(r)
players=int(stats.get('players') or 0)
obs=int(stats.get('observations') or 0)
last=stats.get('lastSeen') or ''
found='NO'; power='UNKNOWN'; uid=''
try:
    u='http://127.0.0.1:8790/player?q='+urllib.parse.quote(sample,safe='')
    with urllib.request.urlopen(u,timeout=5) as r:
        d=json.load(r)
    p=d.get('player') or {}
    if d.get('ok') and p:
        found='YES'
        uid=str(p.get('game_uid') or '')
        power='PRESENT' if p.get('power') is not None else 'MISSING'
except Exception:
    pass
print('PLAYERS='+str(players))
print('OBSERVATIONS='+str(obs))
print('LAST_SEEN='+last)
print('SAMPLE_FOUND='+found)
print('SAMPLE_UID_PRESENT='+('YES' if uid else 'NO'))
print('SAMPLE_POWER='+power)
PY
}

if ! PROBE="$(probe_collector)"; then
  log "SENTINEL_COLLECTOR=REPAIR action=restart reason=API_UNHEALTHY"
  systemctl restart "$SERVICE" || true
  sleep 2
  PROBE="$(probe_collector)" || fail API_HEALTH_FAILED
  RECOVERED=1
fi

PLAYERS="$(printf '%s\n' "$PROBE" | awk -F= '$1=="PLAYERS"{print $2}')"
OBSERVATIONS="$(printf '%s\n' "$PROBE" | awk -F= '$1=="OBSERVATIONS"{print $2}')"
LAST_SEEN="$(printf '%s\n' "$PROBE" | awk -F= '$1=="LAST_SEEN"{sub(/^LAST_SEEN=/,"");print}')"
SAMPLE_FOUND="$(printf '%s\n' "$PROBE" | awk -F= '$1=="SAMPLE_FOUND"{print $2}')"
SAMPLE_UID_PRESENT="$(printf '%s\n' "$PROBE" | awk -F= '$1=="SAMPLE_UID_PRESENT"{print $2}')"
SAMPLE_POWER="$(printf '%s\n' "$PROBE" | awk -F= '$1=="SAMPLE_POWER"{print $2}')"

STATUS=HEALTHY
[[ "$RECOVERED" -eq 1 ]] && STATUS=RECOVERED

cat >"$STATE_FILE" <<EOF
SENTINEL_COLLECTOR_STATUS=$STATUS
SENTINEL_COLLECTOR_LAST_CHECK=$(date -u +%Y-%m-%dT%H:%M:%SZ)
SENTINEL_COLLECTOR_NATIVE_SHA=$CURRENT_NATIVE
SENTINEL_COLLECTOR_EXPECTED_NATIVE_SHA=$EXPECTED_NATIVE
SENTINEL_COLLECTOR_SERVICE=active
SENTINEL_COLLECTOR_PLAYERS=${PLAYERS:-0}
SENTINEL_COLLECTOR_OBSERVATIONS=${OBSERVATIONS:-0}
SENTINEL_COLLECTOR_LAST_SEEN=$LAST_SEEN
SENTINEL_COLLECTOR_SAMPLE=$SAMPLE_PLAYER
SENTINEL_COLLECTOR_SAMPLE_FOUND=$SAMPLE_FOUND
SENTINEL_COLLECTOR_SAMPLE_UID_PRESENT=$SAMPLE_UID_PRESENT
SENTINEL_COLLECTOR_SAMPLE_POWER=$SAMPLE_POWER
EOF
chmod 0640 "$STATE_FILE"
chown root:wfgg-radar "$STATE_FILE" 2>/dev/null || true

log "SENTINEL_COLLECTOR=$STATUS players=${PLAYERS:-0} sample=$SAMPLE_PLAYER found=$SAMPLE_FOUND power=$SAMPLE_POWER"
