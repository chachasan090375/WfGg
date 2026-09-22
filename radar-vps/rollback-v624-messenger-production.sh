#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="/opt/wfgg-radar"
BIN="$ROOT/messenger/bin/wfgg-messenger-outbox"
STATE="$ROOT/data/messenger/production-install-state.env"

fail(){ printf 'RADAR_V624_MESSENGER_PRODUCTION_ROLLBACK=FAIL reason=%s\n' "$1"; exit 1; }
[[ "$(id -u)" -eq 0 ]] || fail ROOT_REQUIRED
[[ -f "$STATE" ]] || fail STATE_MISSING

# shellcheck disable=SC1090
source "$STATE"
case "${RADAR_V624_MESSENGER_PREVIOUS_PRESENT:-}" in
  YES)
    B="${RADAR_V624_MESSENGER_BACKUP:-}/wfgg-messenger-outbox"
    [[ -f "$B" ]] || fail BACKUP_MISSING
    install -m 0755 "$B" "$BIN.new"
    mv -f "$BIN.new" "$BIN"
    if [[ -n "${RADAR_V624_MESSENGER_PREVIOUS_SHA:-}" ]]; then
      ACTUAL="$(sha256sum "$BIN" | awk '{print $1}')"
      [[ "$ACTUAL" == "$RADAR_V624_MESSENGER_PREVIOUS_SHA" ]] || fail RESTORE_SHA_MISMATCH
    fi
    echo RADAR_V624_MESSENGER_ROLLBACK_ACTION=RESTORED_PREVIOUS
    ;;
  NO)
    rm -f "$BIN"
    echo RADAR_V624_MESSENGER_ROLLBACK_ACTION=REMOVED_V624_BINARY
    ;;
  *) fail STATE_INVALID ;;
esac

echo RADAR_V624_MESSENGER_LEDGER_PRESERVED=YES
echo RADAR_V624_PRODUCTION_CONNECTOR_TOUCHED=NO
echo RADAR_V624_PRODUCTION_SERVICE_RESTARTED=NO
echo RADAR_V624_MESSENGER_PRODUCTION_ROLLBACK=PASS
