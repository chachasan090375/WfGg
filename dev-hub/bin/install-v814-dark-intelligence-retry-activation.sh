#!/usr/bin/env bash
set -Eeuo pipefail

REV="${CHACHA_DEV_V814_REV:-}"
SOURCE_ROOT="${CHACHA_DEV_V814_SOURCE_ROOT:-/opt/chacha-dev/platform/current}"
UNIT_DIR="/etc/systemd/system"
WORK="$(mktemp -d /tmp/chacha-v814.XXXXXX)"
STAGE="bootstrap"
TOUCHED=0

UNITS=(
  chacha-dev-dark-intelligence-analysis-retry.service
  chacha-dev-dark-intelligence-analysis-retry.timer
  chacha-dev-dark-intelligence-corroboration-retry.service
  chacha-dev-dark-intelligence-corroboration-retry.timer
)
TIMERS=(
  chacha-dev-dark-intelligence-analysis-retry.timer
  chacha-dev-dark-intelligence-corroboration-retry.timer
)

stage(){ STAGE="$1"; echo "CHACHA_DEV_V814_STAGE=$STAGE"; }
cleanup(){ rm -rf "$WORK" 2>/dev/null || true; }
rollback(){
  rc=$?
  if [ "$rc" -ne 0 ]; then
    echo "CHACHA_DEV_V814_FAILURE_STAGE=$STAGE"
    if [ "$TOUCHED" -eq 1 ]; then
      for timer in "${TIMERS[@]}"; do systemctl disable --now "$timer" >/dev/null 2>&1 || true; done
      for unit in "${UNITS[@]}"; do
        if [ -f "$WORK/$unit.existed" ]; then
          cp -a "$WORK/$unit.backup" "$UNIT_DIR/$unit"
        else
          rm -f "$UNIT_DIR/$unit"
        fi
      done
      systemctl daemon-reload >/dev/null 2>&1 || true
      for timer in "${TIMERS[@]}"; do
        if [ -f "$WORK/$timer.was-enabled" ]; then systemctl enable "$timer" >/dev/null 2>&1 || true; fi
        if [ -f "$WORK/$timer.was-active" ]; then systemctl start "$timer" >/dev/null 2>&1 || true; fi
      done
      echo "CHACHA_DEV_V814_UNIT_ROLLBACK=PASS"
    fi
  fi
  cleanup
  exit "$rc"
}
trap rollback EXIT

[ "$(id -u)" -eq 0 ] || { echo "CHACHA_DEV_V814_INSTALL=BLOCKED reason=root_required"; exit 2; }
SRC="$(readlink -f "$SOURCE_ROOT")"
[ -d "$SRC/dev-hub" ] || { echo "CHACHA_DEV_V814_INSTALL=BLOCKED reason=source_root_invalid"; exit 2; }
if [ -n "$REV" ]; then
  printf '%s' "$REV" | grep -Eq '^[0-9a-f]{40}$' || { echo "CHACHA_DEV_V814_INSTALL=BLOCKED reason=pinned_revision_invalid"; exit 2; }
  ACTUAL="$(cat "$SRC/.revision" 2>/dev/null || true)"
  [ "$ACTUAL" = "$REV" ] || { echo "CHACHA_DEV_V814_INSTALL=BLOCKED reason=revision_mismatch actual=$ACTUAL"; exit 2; }
fi
for cmd in systemctl systemd-analyze install python3 readlink; do
  command -v "$cmd" >/dev/null || { echo "CHACHA_DEV_V814_INSTALL=BLOCKED reason=missing_command:$cmd"; exit 2; }
done
for unit in "${UNITS[@]}"; do
  [ -f "$SRC/dev-hub/systemd/$unit" ] || { echo "CHACHA_DEV_V814_INSTALL=BLOCKED reason=missing_unit:$unit"; exit 2; }
done

stage verify-units
systemd-analyze verify \
  "$SRC/dev-hub/systemd/chacha-dev-dark-intelligence-analysis-retry.service" \
  "$SRC/dev-hub/systemd/chacha-dev-dark-intelligence-analysis-retry.timer" \
  "$SRC/dev-hub/systemd/chacha-dev-dark-intelligence-corroboration-retry.service" \
  "$SRC/dev-hub/systemd/chacha-dev-dark-intelligence-corroboration-retry.timer"
echo "CHACHA_DEV_V814_SYSTEMD_VERIFY=PASS"

stage backup
for unit in "${UNITS[@]}"; do
  if [ -f "$UNIT_DIR/$unit" ]; then
    cp -a "$UNIT_DIR/$unit" "$WORK/$unit.backup"
    touch "$WORK/$unit.existed"
  fi
done
for timer in "${TIMERS[@]}"; do
  if systemctl is-enabled --quiet "$timer" 2>/dev/null; then touch "$WORK/$timer.was-enabled"; fi
  if systemctl is-active --quiet "$timer" 2>/dev/null; then touch "$WORK/$timer.was-active"; fi
done

stage install
TOUCHED=1
for unit in "${UNITS[@]}"; do
  install -m 0644 "$SRC/dev-hub/systemd/$unit" "$UNIT_DIR/$unit"
done
systemctl daemon-reload
for timer in "${TIMERS[@]}"; do
  systemctl enable --now "$timer"
  systemctl is-enabled --quiet "$timer"
  systemctl is-active --quiet "$timer"
done

stage verify-runtime
for timer in "${TIMERS[@]}"; do
  NEXT="$(systemctl show "$timer" -p NextElapseUSecRealtime --value)"
  [ -n "$NEXT" ] && [ "$NEXT" != "infinity" ] || { echo "CHACHA_DEV_V814_INSTALL=BLOCKED reason=timer_not_scheduled:$timer"; exit 3; }
  echo "CHACHA_DEV_V814_TIMER_NEXT=$timer:$NEXT"
done
python3 "$SRC/dev-hub/bin/dark-intelligence-analysis-queue.py" status >/dev/null
python3 "$SRC/dev-hub/bin/dark-intelligence-corroboration-queue.py" status >/dev/null
echo "CHACHA_DEV_V814_RETRY_QUEUES=PASS"
echo "CHACHA_DEV_V814_AUTOMATIC_EXTERNAL_SPEND_EUR=0"
echo "CHACHA_DEV_V814_INSTALL=PASS"

trap - EXIT
cleanup
