#!/usr/bin/env bash
set -Eeuo pipefail
ROOT="${1:-/opt/chacha-dev/platform/current}"
UNIT_SRC="$ROOT/dev-hub/systemd/chacha-dev-autonomous-recovery-agent.service"
TMP_SRC="$ROOT/dev-hub/systemd/chacha-dev-autonomous-recovery.tmpfiles.conf"
UNIT_DST=/etc/systemd/system/chacha-dev-autonomous-recovery-agent.service
TMP_DST=/etc/tmpfiles.d/chacha-dev-autonomous-recovery.conf
test -f "$UNIT_SRC"
test -f "$TMP_SRC"
install -m 0644 "$TMP_SRC" "$TMP_DST"
systemd-tmpfiles --create "$TMP_DST"
test -d /opt/chacha-dev/runtime/autonomous-recovery/work
install -m 0644 "$UNIT_SRC" "$UNIT_DST"
systemctl daemon-reload
cmp -s "$UNIT_SRC" "$UNIT_DST"
cmp -s "$TMP_SRC" "$TMP_DST"
echo CHACHA_DEV_AUTONOMOUS_RECOVERY_INSTALL=PASS
echo AUTOMATIC_EXTERNAL_SPEND_EUR=0
