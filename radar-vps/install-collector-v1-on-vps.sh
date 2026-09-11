#!/usr/bin/env bash
set -Eeuo pipefail

# Run on ChaChaVPS after /opt/wfgg-collector/private/session.json has been
# provisioned mode 0600. This installer never reads or prints session contents.

BASE='https://raw.githubusercontent.com/chachasan090375/WfGg/radar-collector-v1'
ROOT='/opt/wfgg-collector'
BIN="$ROOT/bin"
PRIVATE="$ROOT/private"
DATA="$ROOT/data"
SCAN_INTERVAL="${WFGG_COLLECTOR_SCAN_INTERVAL:-900}"

install -d -m 0755 "$ROOT" "$BIN" "$DATA"
install -d -m 0700 "$PRIVATE"

[[ -s "$PRIVATE/session.json" ]] || { echo 'ERROR=COLLECTOR_SESSION_MISSING'; exit 2; }
[[ -s /opt/wfgg-radar/private/lastwar-native-capture.pcap ]] || { echo 'ERROR=CAPTURE_MISSING'; exit 2; }

TMPDIR_COL="$(mktemp -d)"
trap 'rm -rf "$TMPDIR_COL"' EXIT

curl -fsSL "$BASE/collector/wfgg_collector.py" -o "$TMPDIR_COL/wfgg_collector.py"
curl -fsSL "$BASE/radar-vps/release/SHA256SUMS" -o "$TMPDIR_COL/SHA256SUMS"
curl -fsSL "$BASE/radar-vps/release/radar-native-template" -o "$TMPDIR_COL/radar-native-template"

EXPECTED="$(awk '$2=="radar-native-template" {print $1}' "$TMPDIR_COL/SHA256SUMS")"
ACTUAL="$(sha256sum "$TMPDIR_COL/radar-native-template" | awk '{print $1}')"
[[ -n "$EXPECTED" ]] || { echo 'ERROR=COLLECTOR_SHA_MISSING'; exit 3; }
echo "COLLECTOR_NATIVE_SHA=$ACTUAL"
[[ "$ACTUAL" = "$EXPECTED" ]] || { echo 'ERROR=COLLECTOR_SHA_MISMATCH'; exit 3; }

python3 -m py_compile "$TMPDIR_COL/wfgg_collector.py"
install -m 0755 "$TMPDIR_COL/wfgg_collector.py" "$BIN/wfgg_collector.py"
install -m 0755 "$TMPDIR_COL/radar-native-template" "$BIN/radar-native-collector"
chmod 0600 "$PRIVATE/session.json"

cat > "$ROOT/collector.env" <<EOF
WFGG_COLLECTOR_ROOT=$ROOT
WFGG_COLLECTOR_NATIVE=$BIN/radar-native-collector
WFGG_COLLECTOR_SESSION=$PRIVATE/session.json
WFGG_COLLECTOR_CAPTURE=/opt/wfgg-radar/private/lastwar-native-capture.pcap
WFGG_COLLECTOR_PORT=8791
WFGG_COLLECTOR_SCAN_INTERVAL=$SCAN_INTERVAL
WFGG_COLLECTOR_SCAN_TIMEOUT=90
EOF
chmod 0600 "$ROOT/collector.env"

cat > /etc/systemd/system/wfgg-collector.service <<'EOF'
[Unit]
Description=WfGg Collector V1 READONLY data agent
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=root
Group=root
EnvironmentFile=/opt/wfgg-collector/collector.env
ExecStart=/usr/bin/python3 /opt/wfgg-collector/bin/wfgg_collector.py
Restart=on-failure
RestartSec=5
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=full
ProtectHome=true
ReadWritePaths=/opt/wfgg-collector
ReadOnlyPaths=/opt/wfgg-radar/private

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable --now wfgg-collector.service >/dev/null
sleep 3

echo '=== COLLECTOR SERVICE ==='
systemctl is-active wfgg-collector.service
echo '=== COLLECTOR HEALTH ==='
curl -fsS http://127.0.0.1:8791/health
echo
echo 'INSTALL_COLLECTOR_V1=OK'
