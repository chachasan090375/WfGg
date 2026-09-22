#!/usr/bin/env bash
set -Eeuo pipefail

REV="${CHACHA_DEV_EMERGENCY_BRIDGE_REV:-}"
COMMAND_URL="${CHACHA_DEV_EMERGENCY_COMMAND_URL:-https://raw.githubusercontent.com/chachasan090375/WfGg/chacha-emergency-control/dev-hub/control/emergency-stop-command.json}"
BASE="/opt/chacha-dev/emergency-bridge"
CURRENT="$BASE/current"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
RELEASE="$BASE/releases/$STAMP-$REV"
WORK="$(mktemp -d /tmp/chacha-emergency-bridge.XXXXXX)"
ARCHIVE="$WORK/repo.tar.gz"
STATE="/opt/chacha-dev/runtime/control/emergency-control-bridge.json"

cleanup(){ rm -rf "$WORK" 2>/dev/null || true; }
trap cleanup EXIT

[ "$(id -u)" -eq 0 ] || { echo "CHACHA_DEV_EMERGENCY_BRIDGE_INSTALL=BLOCKED reason=root_required"; exit 2; }
printf '%s' "$REV" | grep -Eq '^[0-9a-f]{40}$' || { echo "CHACHA_DEV_EMERGENCY_BRIDGE_INSTALL=BLOCKED reason=pinned_revision_required"; exit 2; }

for cmd in curl tar python3 install ln systemctl; do
  command -v "$cmd" >/dev/null || { echo "CHACHA_DEV_EMERGENCY_BRIDGE_INSTALL=BLOCKED reason=missing_command:$cmd"; exit 2; }
done

curl -fsSL "https://codeload.github.com/chachasan090375/WfGg/tar.gz/$REV" -o "$ARCHIVE"
tar -xzf "$ARCHIVE" -C "$WORK"
SRC="$(find "$WORK" -mindepth 1 -maxdepth 1 -type d -name 'WfGg-*' | head -1)"
[ -d "$SRC/dev-hub" ] || { echo "CHACHA_DEV_EMERGENCY_BRIDGE_INSTALL=BLOCKED reason=archive_invalid"; exit 2; }

mkdir -p "$RELEASE" /opt/chacha-dev/runtime/control
install -m 0755 "$SRC/dev-hub/bin/emergency-control-bridge.py" "$RELEASE/emergency-control-bridge.py"
install -m 0755 "$SRC/dev-hub/bin/emergency-stop-controller.py" "$RELEASE/emergency-stop-controller.py"
python3 -m py_compile "$RELEASE/emergency-control-bridge.py" "$RELEASE/emergency-stop-controller.py"
printf '%s\n' "$REV" >"$RELEASE/.revision"
ln -sfn "$RELEASE" "$CURRENT"

install -m 0644 "$SRC/dev-hub/systemd/chacha-dev-emergency-control-bridge.service" /etc/systemd/system/chacha-dev-emergency-control-bridge.service

if [ ! -s "$STATE" ]; then
  python3 "$CURRENT/emergency-control-bridge.py"     --baseline     --command-url "$COMMAND_URL"     --state "$STATE"     --controller "$CURRENT/emergency-stop-controller.py"
fi

systemctl daemon-reload
systemctl enable chacha-dev-emergency-control-bridge.service
systemctl restart chacha-dev-emergency-control-bridge.service
systemctl is-active --quiet chacha-dev-emergency-control-bridge.service

python3 "$CURRENT/emergency-control-bridge.py"   --once   --command-url "$COMMAND_URL"   --state "$STATE"   --controller "$CURRENT/emergency-stop-controller.py" >/tmp/chacha-emergency-bridge-once.txt

echo "CHACHA_DEV_EMERGENCY_BRIDGE_OUT_OF_BAND=YES"
echo "CHACHA_DEV_EMERGENCY_BRIDGE_REMOTE_RESET=NO"
echo "CHACHA_DEV_EMERGENCY_BRIDGE_AUTOMATIC_EXTERNAL_SPEND_EUR=0"
echo "CHACHA_DEV_EMERGENCY_BRIDGE_INSTALL=PASS"
