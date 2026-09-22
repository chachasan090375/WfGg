#!/usr/bin/env bash
set -Eeuo pipefail

REV="${WFGG_RADAR_V624_PRODUCTION_REV:-}"
EXPECTED="${WFGG_V624_MESSENGER_SHA256:-3cf5d175325a319d601667e50388e8472057bcc152df7a618938daf357a3dfa1}"
BASE="https://raw.githubusercontent.com/chachasan090375/WfGg/${REV}/radar-vps/pilot-v624-messenger"
ROOT="/opt/wfgg-radar"
MESSENGER_ROOT="$ROOT/messenger"
BIN_DIR="$MESSENGER_ROOT/bin"
DATA_DIR="$ROOT/data/messenger"
BACKUP_ROOT="$ROOT/data/messenger-backups"
BIN="$BIN_DIR/wfgg-messenger-outbox"
STATE="$DATA_DIR/production-install-state.env"
TMP="$(mktemp -d /opt/chacha-dev/runtime/tmp/wfgg-messenger-prod.XXXXXX)"

log(){ printf '%s\n' "$*"; }
fail(){ log "RADAR_V624_MESSENGER_PRODUCTION_INSTALL=FAIL reason=$*"; exit 1; }
cleanup(){ rm -rf "$TMP"; }
trap cleanup EXIT

[[ "$(id -u)" -eq 0 ]] || fail ROOT_REQUIRED
[[ "$REV" =~ ^[0-9a-f]{40}$ ]] || fail PINNED_REVISION_REQUIRED
[[ "$EXPECTED" =~ ^[0-9a-f]{64}$ ]] || fail EXPECTED_SHA_INVALID
for c in curl sha256sum install mkdir cp mv date; do
  command -v "$c" >/dev/null 2>&1 || fail "COMMAND_MISSING:$c"
done

log "=== WFGG RADAR V6.24 MESSENGER PRODUCTION INSTALL ==="
log "RADAR_V624_PRODUCTION_REV=$REV"
log "RADAR_V624_EXPECTED_MESSENGER_SHA256=$EXPECTED"

curl --fail --silent --show-error --location --max-time 90 "$BASE/wfgg-messenger-outbox" -o "$TMP/wfgg-messenger-outbox" || fail DOWNLOAD_BINARY
curl --fail --silent --show-error --location --max-time 30 "$BASE/SHA256SUMS" -o "$TMP/SHA256SUMS" || fail DOWNLOAD_MANIFEST
(
  cd "$TMP"
  sha256sum -c SHA256SUMS
) >/dev/null || fail RELEASE_CHECKSUM_INVALID
DOWNLOADED="$(sha256sum "$TMP/wfgg-messenger-outbox" | awk '{print $1}')"
[[ "$DOWNLOADED" == "$EXPECTED" ]] || fail EXPECTED_SHA_MISMATCH

install -d -m 0755 "$BIN_DIR"
install -d -m 0750 "$DATA_DIR" "$BACKUP_ROOT"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
BACKUP="$BACKUP_ROOT/$STAMP"
PREVIOUS_PRESENT=NO
PREVIOUS_SHA=
if [[ -f "$BIN" ]]; then
  PREVIOUS_PRESENT=YES
  PREVIOUS_SHA="$(sha256sum "$BIN" | awk '{print $1}')"
  install -d -m 0750 "$BACKUP"
  cp -a "$BIN" "$BACKUP/wfgg-messenger-outbox"
fi

install -m 0755 "$TMP/wfgg-messenger-outbox" "$BIN.new"
mv -f "$BIN.new" "$BIN"
ACTUAL="$(sha256sum "$BIN" | awk '{print $1}')"
if [[ "$ACTUAL" != "$EXPECTED" ]]; then
  if [[ "$PREVIOUS_PRESENT" == YES && -f "$BACKUP/wfgg-messenger-outbox" ]]; then
    install -m 0755 "$BACKUP/wfgg-messenger-outbox" "$BIN"
  else
    rm -f "$BIN"
  fi
  fail POST_INSTALL_SHA_MISMATCH_ROLLED_BACK
fi

cat >"$STATE" <<EOF
RADAR_V624_MESSENGER_PRODUCTION_REV=$REV
RADAR_V624_MESSENGER_SHA256=$ACTUAL
RADAR_V624_MESSENGER_INSTALLED_AT=$(date -u +%Y-%m-%dT%H:%M:%SZ)
RADAR_V624_MESSENGER_PREVIOUS_PRESENT=$PREVIOUS_PRESENT
RADAR_V624_MESSENGER_PREVIOUS_SHA=$PREVIOUS_SHA
RADAR_V624_MESSENGER_BACKUP=$BACKUP
RADAR_V624_MESSENGER_ROLLBACK_SCRIPT=radar-vps/rollback-v624-messenger-production.sh
EOF
chmod 0640 "$STATE"

log "RADAR_V624_MESSENGER_PRODUCTION_BIN=$BIN"
log "RADAR_V624_MESSENGER_PRODUCTION_LEDGER=$DATA_DIR/outbox.jsonl"
log "RADAR_V624_MESSENGER_SHA256=$ACTUAL"
log "RADAR_V624_MESSENGER_PREVIOUS_PRESENT=$PREVIOUS_PRESENT"
log "RADAR_V624_MESSENGER_BACKUP=$BACKUP"
log "RADAR_V624_PRODUCTION_CONNECTOR_TOUCHED=NO"
log "RADAR_V624_PRODUCTION_SERVICE_RESTARTED=NO"
log "RADAR_V624_GAME_CONNECTION=NONE"
log "RADAR_V624_MAIL_SEND_EXECUTED=NO"
log "RADAR_V624_LASTWAR_MUTATION=NO"
log "RADAR_V624_MESSENGER_PRODUCTION_INSTALL=PASS"
