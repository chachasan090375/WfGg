#!/usr/bin/env bash
set -Eeuo pipefail

SOURCE_REVISION="5ec2c8e6e48fc0623f234e59cd0a5d19eff0b92a"
RAW="https://raw.githubusercontent.com/chachasan090375/WfGg/${SOURCE_REVISION}"
PORTABLE_SHA="db0da08a11c2b2cbdddb5f1ac6b89aba228acac624815079e48e2fd13148eec3"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"

GOV_BASE="/opt/chacha-dev/adapters/storage-governor"
VER_BASE="/opt/chacha-dev/adapters/storage-restore-verifier"
BIN_DIR="/opt/chacha-dev/bin"
EVIDENCE_DIR="/opt/chacha-dev/evidence"
GOV_RELEASE="$GOV_BASE/releases/$STAMP"
VER_RELEASE="$VER_BASE/releases/$STAMP"
WATCHER="$BIN_DIR/storage-governor-incremental-watch.py"

SERVICE="/etc/systemd/system/chacha-storage-incremental-watch.service"
TIMER="/etc/systemd/system/chacha-storage-incremental-watch.timer"

if [ "$(id -u)" -ne 0 ]; then
  echo "STORAGE_INCREMENTAL_WATCH_INSTALL=BLOCKED reason=root_required"
  exit 2
fi

for cmd in curl python3 sha256sum systemctl install ln ssh; do
  command -v "$cmd" >/dev/null 2>&1 || {
    echo "STORAGE_INCREMENTAL_WATCH_INSTALL=BLOCKED reason=missing_command:$cmd"
    exit 2
  }
done

test -x /opt/chacha-dev/adapters/nas-ssh/current/nas-ssh-adapter || {
  echo "STORAGE_INCREMENTAL_WATCH_INSTALL=BLOCKED reason=nas_adapter_missing"
  exit 3
}

ssh -o BatchMode=yes -o ConnectTimeout=12 chachanas 'echo NAS_RUNTIME_LINK=OK'   | grep -Fq 'NAS_RUNTIME_LINK=OK' || {
    echo "STORAGE_INCREMENTAL_WATCH_INSTALL=BLOCKED reason=nas_runtime_link_failed"
    exit 3
  }

mkdir -p "$GOV_RELEASE" "$VER_RELEASE" "$BIN_DIR" "$EVIDENCE_DIR"

curl -fsSL "$RAW/dev-hub/adapters/storage-governor-adapter.py"   -o "$GOV_RELEASE/storage-governor-adapter"
curl -fsSL "$RAW/dev-hub/adapters/storage-governor-incremental-chain.py"   -o "$GOV_RELEASE/storage-governor-incremental-chain.py"
chmod 0755 "$GOV_RELEASE/storage-governor-adapter"
chmod 0644 "$GOV_RELEASE/storage-governor-incremental-chain.py"

curl -fsSL "$RAW/dev-hub/adapters/storage-restore-verifier-adapter.py"   -o "$VER_RELEASE/storage-restore-verifier-adapter"
curl -fsSL "$RAW/dev-hub/release/storage-restore-verifier-nas-linux-amd64"   -o "$VER_RELEASE/storage-restore-verifier-nas-linux-amd64"
chmod 0755 "$VER_RELEASE/storage-restore-verifier-adapter"
chmod 0700 "$VER_RELEASE/storage-restore-verifier-nas-linux-amd64"

ACTUAL_SHA="$(sha256sum "$VER_RELEASE/storage-restore-verifier-nas-linux-amd64" | awk '{print $1}')"
test "$ACTUAL_SHA" = "$PORTABLE_SHA" || {
  echo "STORAGE_INCREMENTAL_WATCH_INSTALL=BLOCKED reason=portable_sha_mismatch"
  exit 4
}

curl -fsSL "$RAW/dev-hub/bin/storage-governor-incremental-watch.py"   -o "$WATCHER"
chmod 0755 "$WATCHER"

python3 -m py_compile   "$GOV_RELEASE/storage-governor-adapter"   "$GOV_RELEASE/storage-governor-incremental-chain.py"   "$VER_RELEASE/storage-restore-verifier-adapter"   "$WATCHER"

ln -sfn "$GOV_RELEASE" "$GOV_BASE/current"
ln -sfn "$VER_RELEASE" "$VER_BASE/current"

cat > "$SERVICE" <<'UNIT'
[Unit]
Description=ChaCha DEV verified Collector incremental backup iteration
After=network-online.target wfgg-collector.service
Wants=network-online.target

[Service]
Type=oneshot
User=root
Environment=CHACHA_STORAGE_GOVERNOR=/opt/chacha-dev/adapters/storage-governor/current/storage-governor-adapter
Environment=CHACHA_STORAGE_RESTORE_VERIFIER=/opt/chacha-dev/adapters/storage-restore-verifier/current/storage-restore-verifier-adapter
Environment=CHACHA_PORTABLE_RESTORE_VERIFIER=/opt/chacha-dev/adapters/storage-restore-verifier/current/storage-restore-verifier-nas-linux-amd64
Environment=CHACHA_PORTABLE_RESTORE_VERIFIER_SHA256=sha256:db0da08a11c2b2cbdddb5f1ac6b89aba228acac624815079e48e2fd13148eec3
Environment=CHACHA_NAS_HOST=chachanas
Environment=CHACHA_NAS_ROOT=/share/CACHEDEV1_DATA/ChaCha-DEV-HUB
Environment=WFGG_COLLECTOR_DB=/opt/wfgg-collector/data/collector.db
ExecStart=/usr/bin/python3 /opt/chacha-dev/bin/storage-governor-incremental-watch.py
TimeoutStartSec=45min
Nice=10
IOSchedulingClass=idle
NoNewPrivileges=yes

[Install]
WantedBy=multi-user.target
UNIT

cat > "$TIMER" <<'UNIT'
[Unit]
Description=ChaCha DEV Collector incremental cycle watch timer

[Timer]
OnBootSec=4min
OnUnitInactiveSec=5min
RandomizedDelaySec=30s
AccuracySec=30s
Persistent=true
Unit=chacha-storage-incremental-watch.service

[Install]
WantedBy=timers.target
UNIT

chmod 0644 "$SERVICE" "$TIMER"
systemctl daemon-reload

echo "=== PRE-ENABLE RUNTIME ITERATION ==="
if ! systemctl start chacha-storage-incremental-watch.service; then
  echo "STORAGE_INCREMENTAL_WATCH_INSTALL=BLOCKED reason=initial_iteration_failed"
  systemctl --no-pager --full status chacha-storage-incremental-watch.service || true
  journalctl -u chacha-storage-incremental-watch.service -n 80 --no-pager || true
  systemctl disable --now chacha-storage-incremental-watch.timer 2>/dev/null || true
  exit 5
fi

systemctl enable --now chacha-storage-incremental-watch.timer

echo "=== RUNTIME ==="
systemctl is-active wfgg-collector
systemctl is-active chacha-storage-incremental-watch.timer
systemctl is-enabled chacha-storage-incremental-watch.timer
systemctl list-timers chacha-storage-incremental-watch.timer --no-pager || true

echo "STORAGE_INCREMENTAL_WATCH_SOURCE_REVISION=$SOURCE_REVISION"
echo "STORAGE_INCREMENTAL_WATCH_PORTABLE_SHA256=sha256:$PORTABLE_SHA"
echo "STORAGE_INCREMENTAL_WATCH_GOVERNOR=$GOV_BASE/current/storage-governor-adapter"
echo "STORAGE_INCREMENTAL_WATCH_VERIFIER=$VER_BASE/current/storage-restore-verifier-adapter"
echo "STORAGE_INCREMENTAL_WATCH_TIMER=ENABLED"
echo "STORAGE_INCREMENTAL_WATCH_INTERVAL=5_MIN_AFTER_INACTIVE"
echo "STORAGE_INCREMENTAL_WATCH_COLLECTOR_SERVICE_MUTATION=NO"
echo "STORAGE_INCREMENTAL_WATCH_INSTALL=PASS"
