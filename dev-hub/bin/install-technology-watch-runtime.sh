#!/usr/bin/env bash
set -Eeuo pipefail
REV="${CHACHA_DEV_TECH_WATCH_REV:-}"
if ! printf '%s' "$REV" | grep -Eq '^[0-9a-f]{40}$'; then
  echo "CHACHA_TECHNOLOGY_WATCH_INSTALL=BLOCKED reason=pinned_revision_required"
  exit 2
fi
RAW="https://raw.githubusercontent.com/chachasan090375/WfGg/${REV}"
BASE="/opt/chacha-dev/platform"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
RELEASE="$BASE/releases/$STAMP"
CURRENT="$BASE/current"

if [ "$(id -u)" -ne 0 ]; then
  echo "CHACHA_TECHNOLOGY_WATCH_INSTALL=BLOCKED reason=root_required"
  exit 2
fi
for cmd in curl python3 systemctl install ln; do
  command -v "$cmd" >/dev/null 2>&1 || { echo "CHACHA_TECHNOLOGY_WATCH_INSTALL=BLOCKED reason=missing_command:$cmd"; exit 2; }
done

mkdir -p "$RELEASE/dev-hub/bin" "$RELEASE/dev-hub/config" "$RELEASE/dev-hub/systemd" /opt/chacha-dev/runtime/technology-watch

fetch() {
  local rel="$1" dst="$2"
  curl -fsSL "$RAW/$rel" -o "$dst"
}
fetch dev-hub/bin/technology_watch_runtime.py "$RELEASE/dev-hub/bin/technology_watch_runtime.py"
fetch dev-hub/bin/technology-watch-service.py "$RELEASE/dev-hub/bin/technology-watch-service.py"
fetch dev-hub/config/technology-watch-runtime.v1.json "$RELEASE/dev-hub/config/technology-watch-runtime.v1.json"
fetch dev-hub/config/capability-registry.v1.json "$RELEASE/dev-hub/config/capability-registry.v1.json"
fetch dev-hub/config/domain-orchestration.v1.json "$RELEASE/dev-hub/config/domain-orchestration.v1.json"
fetch dev-hub/config/provider-economics.v1.json "$RELEASE/dev-hub/config/provider-economics.v1.json"
fetch dev-hub/config/mcp-provider-catalog.v1.json "$RELEASE/dev-hub/config/mcp-provider-catalog.v1.json"
fetch dev-hub/systemd/chacha-dev-technology-watch.service "$RELEASE/dev-hub/systemd/chacha-dev-technology-watch.service"
fetch dev-hub/systemd/chacha-dev-technology-watch.timer "$RELEASE/dev-hub/systemd/chacha-dev-technology-watch.timer"

chmod 0755 "$RELEASE/dev-hub/bin/technology-watch-service.py"
python3 -m py_compile "$RELEASE/dev-hub/bin/technology_watch_runtime.py" "$RELEASE/dev-hub/bin/technology-watch-service.py"
for f in "$RELEASE"/dev-hub/config/*.json; do python3 -m json.tool "$f" >/dev/null; done

ln -sfn "$RELEASE" "$CURRENT"
install -m 0644 "$RELEASE/dev-hub/systemd/chacha-dev-technology-watch.service" /etc/systemd/system/chacha-dev-technology-watch.service
install -m 0644 "$RELEASE/dev-hub/systemd/chacha-dev-technology-watch.timer" /etc/systemd/system/chacha-dev-technology-watch.timer
systemctl daemon-reload
systemctl start chacha-dev-technology-watch.service
systemctl enable --now chacha-dev-technology-watch.timer

python3 "$CURRENT/dev-hub/bin/technology-watch-service.py" --repo-root "$CURRENT" status | tee /tmp/chacha-tech-watch-status.txt
systemctl is-enabled chacha-dev-technology-watch.timer
systemctl is-active chacha-dev-technology-watch.timer
test -s /opt/chacha-dev/runtime/technology-watch/optimizer-input.json

echo "CHACHA_TECHNOLOGY_WATCH_INSTALL=PASS"
echo "CHACHA_TECHNOLOGY_WATCH_TIMER=ACTIVE"
echo "CHACHA_TECHNOLOGY_WATCH_SNAPSHOT=READY"
echo "AUTOMATIC_EXTERNAL_SPEND_EUR=0"
; then
  echo "CHACHA_TECHNOLOGY_WATCH_INSTALL=BLOCKED reason=pinned_revision_required"
  exit 2
fi
RAW="https://raw.githubusercontent.com/chachasan090375/WfGg/${REV}"
BASE="/opt/chacha-dev/platform"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
RELEASE="$BASE/releases/$STAMP"
CURRENT="$BASE/current"

if [ "$(id -u)" -ne 0 ]; then
  echo "CHACHA_TECHNOLOGY_WATCH_INSTALL=BLOCKED reason=root_required"
  exit 2
fi
for cmd in curl python3 systemctl install ln; do
  command -v "$cmd" >/dev/null 2>&1 || { echo "CHACHA_TECHNOLOGY_WATCH_INSTALL=BLOCKED reason=missing_command:$cmd"; exit 2; }
done

mkdir -p "$RELEASE/dev-hub/bin" "$RELEASE/dev-hub/config" "$RELEASE/dev-hub/systemd" /opt/chacha-dev/runtime/technology-watch

fetch() {
  local rel="$1" dst="$2"
  curl -fsSL "$RAW/$rel" -o "$dst"
}
fetch dev-hub/bin/technology_watch_runtime.py "$RELEASE/dev-hub/bin/technology_watch_runtime.py"
fetch dev-hub/bin/technology-watch-service.py "$RELEASE/dev-hub/bin/technology-watch-service.py"
fetch dev-hub/config/technology-watch-runtime.v1.json "$RELEASE/dev-hub/config/technology-watch-runtime.v1.json"
fetch dev-hub/config/capability-registry.v1.json "$RELEASE/dev-hub/config/capability-registry.v1.json"
fetch dev-hub/config/domain-orchestration.v1.json "$RELEASE/dev-hub/config/domain-orchestration.v1.json"
fetch dev-hub/config/provider-economics.v1.json "$RELEASE/dev-hub/config/provider-economics.v1.json"
fetch dev-hub/config/mcp-provider-catalog.v1.json "$RELEASE/dev-hub/config/mcp-provider-catalog.v1.json"
fetch dev-hub/systemd/chacha-dev-technology-watch.service "$RELEASE/dev-hub/systemd/chacha-dev-technology-watch.service"
fetch dev-hub/systemd/chacha-dev-technology-watch.timer "$RELEASE/dev-hub/systemd/chacha-dev-technology-watch.timer"

chmod 0755 "$RELEASE/dev-hub/bin/technology-watch-service.py"
python3 -m py_compile "$RELEASE/dev-hub/bin/technology_watch_runtime.py" "$RELEASE/dev-hub/bin/technology-watch-service.py"
for f in "$RELEASE"/dev-hub/config/*.json; do python3 -m json.tool "$f" >/dev/null; done

ln -sfn "$RELEASE" "$CURRENT"
install -m 0644 "$RELEASE/dev-hub/systemd/chacha-dev-technology-watch.service" /etc/systemd/system/chacha-dev-technology-watch.service
install -m 0644 "$RELEASE/dev-hub/systemd/chacha-dev-technology-watch.timer" /etc/systemd/system/chacha-dev-technology-watch.timer
systemctl daemon-reload
systemctl start chacha-dev-technology-watch.service
systemctl enable --now chacha-dev-technology-watch.timer

python3 "$CURRENT/dev-hub/bin/technology-watch-service.py" --repo-root "$CURRENT" status | tee /tmp/chacha-tech-watch-status.txt
systemctl is-enabled chacha-dev-technology-watch.timer
systemctl is-active chacha-dev-technology-watch.timer
test -s /opt/chacha-dev/runtime/technology-watch/optimizer-input.json

echo "CHACHA_TECHNOLOGY_WATCH_INSTALL=PASS"
echo "CHACHA_TECHNOLOGY_WATCH_TIMER=ACTIVE"
echo "CHACHA_TECHNOLOGY_WATCH_SNAPSHOT=READY"
echo "AUTOMATIC_EXTERNAL_SPEND_EUR=0"
