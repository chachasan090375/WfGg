#!/usr/bin/env bash
set -Eeuo pipefail

SOURCE_REVISION="89712cc7abd43c422cf4ff82dc4fbcd1801e0776"
RAW="https://raw.githubusercontent.com/chachasan090375/WfGg/${SOURCE_REVISION}"
PORTABLE_SHA="db0da08a11c2b2cbdddb5f1ac6b89aba228acac624815079e48e2fd13148eec3"

STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
GOV_BASE="/opt/chacha-dev/adapters/storage-governor"
VER_BASE="/opt/chacha-dev/adapters/storage-restore-verifier"
GOV_RELEASE="$GOV_BASE/releases/$STAMP"
VER_RELEASE="$VER_BASE/releases/$STAMP"
BIN_DIR="/opt/chacha-dev/bin"
WATCH_BIN="$BIN_DIR/collector-incremental-auto-watch"
EVIDENCE_DIR="/opt/chacha-dev/evidence"
SERVICE="/etc/systemd/system/wfgg-collector-incremental-auto-watch.service"
TIMER="/etc/systemd/system/wfgg-collector-incremental-auto-watch.timer"
WORK="/tmp/chacha-incremental-auto-watch-$STAMP"

OLD_GOV="$(readlink -f "$GOV_BASE/current" 2>/dev/null || true)"
OLD_VER="$(readlink -f "$VER_BASE/current" 2>/dev/null || true)"
WATCH_BACKUP=""
PROMOTED=0

cleanup() {
  rm -rf -- "$WORK" 2>/dev/null || true
}
rollback() {
  rc=$?
  if [ "$PROMOTED" = "1" ]; then
    systemctl disable --now wfgg-collector-incremental-auto-watch.timer >/dev/null 2>&1 || true
    if [ -n "$OLD_GOV" ] && [ -d "$OLD_GOV" ]; then
      ln -sfn "$OLD_GOV" "$GOV_BASE/current" || true
    fi
    if [ -n "$OLD_VER" ] && [ -d "$OLD_VER" ]; then
      ln -sfn "$OLD_VER" "$VER_BASE/current" || true
    fi
    if [ -n "$WATCH_BACKUP" ] && [ -f "$WATCH_BACKUP" ]; then
      install -m 0755 "$WATCH_BACKUP" "$WATCH_BIN" || true
    fi
    systemctl daemon-reload >/dev/null 2>&1 || true
    echo "COLLECTOR_INCREMENTAL_AUTO_WATCH_ROLLBACK=APPLIED"
  fi
  cleanup
  exit "$rc"
}
trap rollback ERR
trap cleanup EXIT

if [ "$(id -u)" -ne 0 ]; then
  echo "COLLECTOR_INCREMENTAL_AUTO_WATCH_INSTALL=BLOCKED reason=root_required"
  exit 2
fi

for cmd in curl python3 sha256sum ssh systemctl install readlink; do
  command -v "$cmd" >/dev/null 2>&1 || {
    echo "COLLECTOR_INCREMENTAL_AUTO_WATCH_INSTALL=BLOCKED reason=missing_command:$cmd"
    exit 2
  }
done

mkdir -p "$GOV_RELEASE" "$VER_RELEASE" "$BIN_DIR" "$EVIDENCE_DIR" "$WORK"

COLLECTOR_BEFORE="$(systemctl is-active wfgg-collector || true)"
PID_BEFORE="$(systemctl show -p MainPID --value wfgg-collector 2>/dev/null || true)"
echo "COLLECTOR_SERVICE_BEFORE=$COLLECTOR_BEFORE"
echo "COLLECTOR_PID_BEFORE=$PID_BEFORE"
test "$COLLECTOR_BEFORE" = "active"
test -n "$PID_BEFORE"
test "$PID_BEFORE" != "0"

ssh -o BatchMode=yes -o ConnectTimeout=12 chachanas   'test -d /share/CACHEDEV1_DATA/ChaCha-DEV-HUB && echo NAS_AUTO_WATCH_LINK=PASS'
test -x /opt/chacha-dev/adapters/nas-ssh/current/nas-ssh-adapter

curl -fsSL "$RAW/dev-hub/adapters/storage-governor-adapter.py"   -o "$GOV_RELEASE/storage-governor-adapter"
curl -fsSL "$RAW/dev-hub/adapters/storage-governor-incremental-chain.py"   -o "$GOV_RELEASE/storage-governor-incremental-chain.py"
curl -fsSL "$RAW/dev-hub/adapters/storage-restore-verifier-adapter.py"   -o "$VER_RELEASE/storage-restore-verifier-adapter"
curl -fsSL "$RAW/dev-hub/release/storage-restore-verifier-nas-linux-amd64"   -o "$VER_RELEASE/storage-restore-verifier-nas-linux-amd64"
curl -fsSL "$RAW/dev-hub/bin/collector-incremental-auto-watch.py"   -o "$WORK/collector-incremental-auto-watch"
curl -fsSL "$RAW/dev-hub/systemd/wfgg-collector-incremental-auto-watch.service"   -o "$WORK/wfgg-collector-incremental-auto-watch.service"
curl -fsSL "$RAW/dev-hub/systemd/wfgg-collector-incremental-auto-watch.timer"   -o "$WORK/wfgg-collector-incremental-auto-watch.timer"

chmod 0755   "$GOV_RELEASE/storage-governor-adapter"   "$VER_RELEASE/storage-restore-verifier-adapter"   "$WORK/collector-incremental-auto-watch"
chmod 0700 "$VER_RELEASE/storage-restore-verifier-nas-linux-amd64"

python3 -m py_compile   "$GOV_RELEASE/storage-governor-adapter"   "$GOV_RELEASE/storage-governor-incremental-chain.py"   "$VER_RELEASE/storage-restore-verifier-adapter"   "$WORK/collector-incremental-auto-watch"

ACTUAL_PORTABLE_SHA="$(
  sha256sum "$VER_RELEASE/storage-restore-verifier-nas-linux-amd64" | awk '{print $1}'
)"
test "$ACTUAL_PORTABLE_SHA" = "$PORTABLE_SHA"
echo "COLLECTOR_INCREMENTAL_PORTABLE_SHA256=sha256:$ACTUAL_PORTABLE_SHA"
echo "COLLECTOR_INCREMENTAL_AUTO_WATCH_STAGE=PASS"

if [ -f "$WATCH_BIN" ]; then
  WATCH_BACKUP="$WORK/collector-incremental-auto-watch.previous"
  cp -p "$WATCH_BIN" "$WATCH_BACKUP"
fi

ln -sfn "$GOV_RELEASE" "$GOV_BASE/current"
ln -sfn "$VER_RELEASE" "$VER_BASE/current"
install -m 0755 "$WORK/collector-incremental-auto-watch" "$WATCH_BIN"
install -m 0644 "$WORK/wfgg-collector-incremental-auto-watch.service" "$SERVICE"
install -m 0644 "$WORK/wfgg-collector-incremental-auto-watch.timer" "$TIMER"
PROMOTED=1

systemctl daemon-reload

echo "=== FIRST SUPERVISED ITERATION ==="
systemctl reset-failed wfgg-collector-incremental-auto-watch.service 2>/dev/null || true
systemctl start wfgg-collector-incremental-auto-watch.service
SERVICE_RESULT="$(systemctl show -p Result --value wfgg-collector-incremental-auto-watch.service)"
echo "COLLECTOR_INCREMENTAL_AUTO_WATCH_FIRST_RESULT=$SERVICE_RESULT"
test "$SERVICE_RESULT" = "success"

python3 - "$EVIDENCE_DIR/collector-incremental-auto-watch-last.json" <<'PY'
import json,sys
p=sys.argv[1]
x=json.load(open(p))
assert x["schema"]=="chacha.dev/collector-incremental-auto-watch-run/v1",x
assert x["status"]=="PASS",x
assert x["production_data_mutation"] is False,x
assert x["service_interruption"] is False,x
print("COLLECTOR_INCREMENTAL_AUTO_WATCH_EVIDENCE=PASS")
print("COLLECTOR_INCREMENTAL_AUTO_WATCH_ADVANCED="+str(x["advanced"]))
PY

COLLECTOR_AFTER="$(systemctl is-active wfgg-collector || true)"
PID_AFTER="$(systemctl show -p MainPID --value wfgg-collector 2>/dev/null || true)"
echo "COLLECTOR_SERVICE_AFTER=$COLLECTOR_AFTER"
echo "COLLECTOR_PID_AFTER=$PID_AFTER"
test "$COLLECTOR_AFTER" = "active"
test "$PID_AFTER" = "$PID_BEFORE"
echo "COLLECTOR_SERVICE_INTERRUPTION=NO"

systemctl enable --now wfgg-collector-incremental-auto-watch.timer
TIMER_ACTIVE="$(systemctl is-active wfgg-collector-incremental-auto-watch.timer)"
TIMER_ENABLED="$(systemctl is-enabled wfgg-collector-incremental-auto-watch.timer)"
echo "COLLECTOR_INCREMENTAL_AUTO_WATCH_TIMER_ACTIVE=$TIMER_ACTIVE"
echo "COLLECTOR_INCREMENTAL_AUTO_WATCH_TIMER_ENABLED=$TIMER_ENABLED"
test "$TIMER_ACTIVE" = "active"
test "$TIMER_ENABLED" = "enabled"

# Remove the superseded single-cycle watcher only after the new timer is proven active.
systemctl disable --now chacha-storage-incremental-watch.timer >/dev/null 2>&1 || true
rm -f   /etc/systemd/system/chacha-storage-incremental-watch.timer   /etc/systemd/system/chacha-storage-incremental-watch.service   /opt/chacha-dev/bin/storage-governor-incremental-watch.py
systemctl daemon-reload
echo "COLLECTOR_INCREMENTAL_LEGACY_WATCH=DISABLED"

systemctl list-timers --all --no-pager wfgg-collector-incremental-auto-watch.timer || true

PROMOTED=0
echo "COLLECTOR_INCREMENTAL_AUTO_WATCH_CURRENT_GOVERNOR=$GOV_BASE/current/storage-governor-adapter"
echo "COLLECTOR_INCREMENTAL_AUTO_WATCH_CURRENT_VERIFIER=$VER_BASE/current/storage-restore-verifier-adapter"
echo "COLLECTOR_INCREMENTAL_AUTO_WATCH_PRODUCTION_MUTATION=NO"
echo "COLLECTOR_INCREMENTAL_AUTO_WATCH_INSTALL=PASS"
